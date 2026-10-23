"""
Event-driven Intraday Options Backtesting Simulator
Accurately models:
- Black-Scholes synthetic option prices based on 5m NIFTY spot moves
- Indian Market Expiry Calendar (Weekly Thursdays) & Intraday Theta Decay
- Realistic Slippage & Brokerage/STT/GST Cost Model
- Fixed SL, Dynamic Trailing Stop Loss, Target, and 15:15 IST Square-off
"""
import pandas as pd
import numpy as np
from datetime import datetime, time
from typing import List, Dict, Any, Optional
from dataclasses import dataclass, asdict

from config import BacktestConfig
from options_pricing import BlackScholesEngine

@dataclass
class TradeRecord:
    trade_id: int
    entry_time: str
    exit_time: str
    instrument: str
    option_type: str
    strike: int
    spot_entry: float
    spot_exit: float
    entry_premium: float
    fill_price: float
    exit_premium: float
    exit_price: float
    quantity: int
    gross_pnl: float
    brokerage: float
    stt: float
    exchange_charges: float
    gst: float
    total_charges: float
    net_pnl: float
    return_pct: float
    exit_reason: str
    holding_mins: int
    entry_delta: float
    entry_theta: float
    entry_iv: float
    entry_pcr: float = 1.0
    oi_quadrant: str = ""

class BacktestEngine:
    def __init__(self, config: Optional[BacktestConfig] = None):
        self.config = config or BacktestConfig()
        self.bs_engine = BlackScholesEngine(risk_free_rate=self.config.risk_free_rate)
        self.trades: List[TradeRecord] = []
        self.daily_pnl_series: Dict[str, float] = {}

    def calculate_charges(self, buy_premium: float, sell_premium: float, quantity: int) -> Dict[str, float]:
        """
        Calculates exact Indian broker charges (Zerodha/Angel/Groww equivalent)
        """
        buy_turnover = buy_premium * quantity
        sell_turnover = sell_premium * quantity
        total_turnover = buy_turnover + sell_turnover

        brokerage = self.config.brokerage_per_order * 2.0
        stt = sell_turnover * self.config.stt_rate
        exchange_charges = total_turnover * self.config.exchange_charges_pct
        gst = (brokerage + exchange_charges) * self.config.gst_rate
        stamp_sebi = total_turnover * self.config.sebi_stamp_pct

        total_charges = brokerage + stt + exchange_charges + gst + stamp_sebi
        return {
            "brokerage": round(brokerage, 2),
            "stt": round(stt, 2),
            "exchange_charges": round(exchange_charges, 2),
            "gst": round(gst, 2),
            "total_charges": round(total_charges, 2)
        }

    def run(self, df_with_signals: pd.DataFrame) -> List[TradeRecord]:
        """
        Executes the backtest simulation across all 5-minute bars.
        """
        self.trades.clear()
        data = df_with_signals.copy()

        trade_counter = 0
        active_position = None
        square_off_t = pd.to_datetime(self.config.square_off_time).time()
        quantity = self.config.lot_size * self.config.num_lots

        for i in range(len(data)):
            current_dt = data.index[i]
            bar_time = current_dt.time()
            bar_open = data["Open"].iloc[i]
            bar_high = data["High"].iloc[i]
            bar_low = data["Low"].iloc[i]
            bar_close = data["Close"].iloc[i]
            signal = data["Signal"].iloc[i]
            iv = data["IV"].iloc[i]

            # ----------------------------------------------------
            # 1. Manage Active Position (Exits, SL, Target, TSL)
            # ----------------------------------------------------
            if active_position is not None:
                pos = active_position
                opt_sim = self.bs_engine.simulate_option_candle(
                    spot_open=bar_open,
                    spot_high=bar_high,
                    spot_low=bar_low,
                    spot_close=bar_close,
                    strike=pos["strike"],
                    current_dt=current_dt,
                    iv=iv,
                    option_type=pos["option_type"]
                )

                exit_triggered = False
                exit_premium = opt_sim["close"]
                exit_reason = ""

                # Check End of Day Square-Off (15:15 IST)
                if bar_time >= square_off_t or current_dt.date() > pos["entry_dt"].date():
                    exit_triggered = True
                    exit_premium = opt_sim["close"]
                    exit_reason = "EOD Square-Off (15:15)"

                # Check Stop Loss
                elif opt_sim["low"] <= pos["current_sl"]:
                    exit_triggered = True
                    exit_premium = min(pos["current_sl"], opt_sim["open"])
                    exit_reason = "Trailing SL" if pos["trailed"] else "Stop Loss"

                # Check Target (Take Profit)
                elif opt_sim["high"] >= pos["target_price"]:
                    exit_triggered = True
                    exit_premium = max(pos["target_price"], opt_sim["open"])
                    exit_reason = "Target Hit"

                # Trailing Stop Loss Logic (if position still open)
                elif self.config.enable_trailing_sl:
                    gain_pct = (opt_sim["high"] - pos["entry_premium"]) / pos["entry_premium"]
                    if gain_pct >= self.config.trail_trigger_pct:
                        # Calculate trail steps achieved
                        steps = int((gain_pct - self.config.trail_trigger_pct) / self.config.trail_step_pct) + 1
                        new_sl = pos["entry_premium"] * (1.0 + (steps - 1) * self.config.trail_step_pct)
                        # Lock at least breakeven once trigger is hit
                        if new_sl < pos["entry_premium"]:
                            new_sl = pos["entry_premium"]
                        if new_sl > pos["current_sl"]:
                            pos["current_sl"] = new_sl
                            pos["trailed"] = True

                if exit_triggered:
                    # Apply slippage on exit
                    exit_price = max(0.05, exit_premium * (1.0 - self.config.slippage_pct))
                    charges = self.calculate_charges(pos["fill_price"], exit_price, quantity)
                    gross_pnl = (exit_price - pos["fill_price"]) * quantity
                    net_pnl = gross_pnl - charges["total_charges"]
                    ret_pct = ((exit_price - pos["fill_price"]) / pos["fill_price"]) * 100.0
                    holding_mins = int((current_dt - pos["entry_dt"]).total_seconds() / 60)

                    record = TradeRecord(
                        trade_id=pos["trade_id"],
                        entry_time=pos["entry_dt"].strftime("%Y-%m-%d %H:%M"),
                        exit_time=current_dt.strftime("%Y-%m-%d %H:%M"),
                        instrument=f"NIFTY {pos['strike']} {pos['option_type']}",
                        option_type=pos["option_type"],
                        strike=pos["strike"],
                        spot_entry=round(pos["spot_entry"], 2),
                        spot_exit=round(bar_close, 2),
                        entry_premium=round(pos["entry_premium"], 2),
                        fill_price=round(pos["fill_price"], 2),
                        exit_premium=round(exit_premium, 2),
                        exit_price=round(exit_price, 2),
                        quantity=quantity,
                        gross_pnl=round(gross_pnl, 2),
                        brokerage=charges["brokerage"],
                        stt=charges["stt"],
                        exchange_charges=charges["exchange_charges"],
                        gst=charges["gst"],
                        total_charges=charges["total_charges"],
                        net_pnl=round(net_pnl, 2),
                        return_pct=round(ret_pct, 2),
                        exit_reason=exit_reason,
                        holding_mins=holding_mins,
                        entry_delta=pos["delta"],
                        entry_theta=pos["theta"],
                        entry_iv=round(pos["iv"] * 100, 2),
                        entry_pcr=round(pos.get("pcr", 1.0), 2),
                        oi_quadrant=pos.get("oi_quadrant", "")
                    )
                    self.trades.append(record)
                    active_position = None
                    continue

            # ----------------------------------------------------
            # 2. Check New Trade Entry Signal
            # ----------------------------------------------------
            if active_position is None and signal in (1, -1) and bar_time < square_off_t:
                option_type = "CE" if signal == 1 else "PE"
                strike = int(data["Strike"].iloc[i])
                expiry_dt = self.bs_engine.get_expiry_date(current_dt)
                T = self.bs_engine.time_to_expiry_years(current_dt, expiry_dt)

                entry_premium = self.bs_engine.price(bar_close, strike, T, iv, option_type)
                # Slippage applied to entry fill
                fill_price = entry_premium * (1.0 + self.config.slippage_pct)

                greeks = self.bs_engine.greeks(bar_close, strike, T, iv, option_type)

                initial_sl = entry_premium * (1.0 - self.config.sl_pct)
                target_price = entry_premium * (1.0 + self.config.target_pct)

                trade_counter += 1
                active_position = {
                    "trade_id": trade_counter,
                    "entry_dt": current_dt,
                    "option_type": option_type,
                    "strike": strike,
                    "spot_entry": bar_close,
                    "entry_premium": entry_premium,
                    "fill_price": fill_price,
                    "initial_sl": initial_sl,
                    "current_sl": initial_sl,
                    "target_price": target_price,
                    "trailed": False,
                    "delta": greeks["delta"],
                    "theta": greeks["theta"],
                    "iv": iv,
                    "pcr": data["PCR"].iloc[i] if "PCR" in data.columns else 1.0,
                    "oi_quadrant": data["OI_Quadrant"].iloc[i] if "OI_Quadrant" in data.columns else "N/A"
                }

        return self.trades

    def to_dataframe(self) -> pd.DataFrame:
        """
        Converts trade list to pandas DataFrame
        """
        if not self.trades:
            return pd.DataFrame()
        return pd.DataFrame([asdict(t) for t in self.trades])
