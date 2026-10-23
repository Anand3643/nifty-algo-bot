"""
Institutional SPR + Open Interest (OI) Confluence Strategy
Integrates:
1. Locked SPR (Support, Pivot, Resistance) & CPR Formulas
2. Real Institutional Open Interest (PCR, Max Call Wall, Max Put Wall, Max Pain)
3. Realistic Options Premium Execution (Slippage, STT, Brokerage, Theta Decay)
"""
import os
import sys
import numpy as np
import pandas as pd
from datetime import datetime, time
import math
from scipy.stats import norm

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

class BlackScholes:
    @staticmethod
    def calculate_price(spot: float, strike: float, tte: float, vol: float, r: float = 0.07, is_call: bool = True) -> float:
        if tte <= 0.0001:
            return max(0.0, (spot - strike) if is_call else (strike - spot))
        d1 = (math.log(spot / strike) + (r + 0.5 * vol ** 2) * tte) / (vol * math.sqrt(tte))
        d2 = d1 - vol * math.sqrt(tte)
        if is_call:
            price = spot * norm.cdf(d1) - strike * math.exp(-r * tte) * norm.cdf(d2)
        else:
            price = strike * math.exp(-r * tte) * norm.cdf(-d2) - spot * norm.cdf(-d1)
        return max(price, 0.5)

def run_spr_oi_backtest():
    base_dir = r"c:\Users\Admin\Desktop\nifty backttteest\nifty_data"
    
    print("=" * 80)
    print("   INSTITUTIONAL STRATEGY: LOCKED SPR LEVELS + REAL OPEN INTEREST CONFLUENCE")
    print("=" * 80)

    # 1. Load 5m Spot Data
    df_5m = pd.read_csv(os.path.join(base_dir, "candles", "NIFTY_5min.csv"))
    df_5m["datetime"] = pd.to_datetime(df_5m["datetime"])
    df_5m.sort_values("datetime", inplace=True)
    df_5m.set_index("datetime", inplace=True)

    # 2. Load Daily Data (for previous day SPR calculation)
    df_1d = pd.read_csv(os.path.join(base_dir, "candles", "NIFTY_1day.csv"))
    df_1d["datetime"] = pd.to_datetime(df_1d["datetime"]).dt.date
    df_1d.drop_duplicates(subset=["datetime"], inplace=True)
    df_1d.set_index("datetime", inplace=True)

    # 3. Load Real Options Summary
    df_opt = pd.read_csv(os.path.join(base_dir, "options", "NIFTY_options_summary.csv"))
    df_opt["date"] = pd.to_datetime(df_opt["date"]).dt.date
    df_opt.drop_duplicates(subset=["date"], inplace=True)
    df_opt.set_index("date", inplace=True)

    print(f"[*] Loaded 5m Spot Bars: {len(df_5m):,} from {df_5m.index.min().date()} to {df_5m.index.max().date()}")
    print(f"[*] Loaded Daily Sessions: {len(df_1d):,} | Real Options Sessions: {len(df_opt):,}")
    print("-" * 80)

    # Strategy Parameters
    INITIAL_CAPITAL = 500000.0  # Rs 5,00,000
    LOT_SIZE = 75               # 1 Lot = 75 qty (or 2 lots = 150 qty)
    LOTS = 2
    QUANTITY = LOT_SIZE * LOTS
    SL_PCT = 0.20               # 20% SL on option premium
    TARGET_PCT = 0.50           # 50% Target on option premium (1:2.5 Risk-Reward)
    BROKERAGE_PER_ORDER = 20.0
    STT_RATE = 0.000625         # 0.0625% on sell turnover
    SLIPPAGE = 0.005            # 0.5% slippage on fills

    trades = []
    equity = INITIAL_CAPITAL
    equity_curve = []
    
    unique_dates = sorted(list(set(df_5m.index.date)))

    for current_date in unique_dates:
        # Get previous trading day
        prior_dates = [d for d in df_1d.index if d < current_date]
        if not prior_dates:
            continue
        prev_date = prior_dates[-1]
        
        prev_day = df_1d.loc[prev_date]
        prev_high = float(prev_day["high"])
        prev_low = float(prev_day["low"])
        prev_close = float(prev_day["close"])
        prev_range = prev_high - prev_low

        # --- CALCULATE LOCKED SPR LEVELS ---
        # CPR
        pivot = round(((prev_high + prev_low + prev_close) / 3.0) / 5) * 5
        bc = round(((prev_high + prev_low) / 2.0) / 5) * 5
        tc = round(((2.0 * pivot) - bc) / 5) * 5

        # Locked Supports
        s1 = round((prev_close - 0.300 * prev_range) / 5) * 5
        s2 = round((prev_close - 0.550 * prev_range) / 5) * 5
        s3 = round((prev_close - 0.900 * prev_range) / 5) * 5
        s4 = round((prev_close - 1.314 * prev_range) / 5) * 5

        # Locked Resistances
        r1 = round((prev_close + 0.236 * prev_range) / 5) * 5
        r2 = round((prev_close + 0.500 * prev_range) / 5) * 5
        r3 = round((prev_close + 0.866 * prev_range) / 5) * 5
        r4 = round((prev_close + 1.333 * prev_range) / 5) * 5

        # --- LOAD REAL OPEN INTEREST FILTERS ---
        opt_data = df_opt.loc[prev_date] if prev_date in df_opt.index else None
        pcr = float(opt_data["pcr_oi"]) if opt_data is not None and not pd.isna(opt_data["pcr_oi"]) else 1.0
        max_ce_strike = float(opt_data["max_ce_oi_strike"]) if opt_data is not None and not pd.isna(opt_data["max_ce_oi_strike"]) else 99999.0
        max_pe_strike = float(opt_data["max_pe_oi_strike"]) if opt_data is not None and not pd.isna(opt_data["max_pe_oi_strike"]) else 0.0
        max_pain = float(opt_data["max_pain"]) if opt_data is not None and not pd.isna(opt_data["max_pain"]) else pivot

        day_bars = df_5m[df_5m.index.date == current_date]
        if len(day_bars) < 10:
            continue

        in_trade = False
        trade_dir = None
        strike = 0
        entry_price = 0.0
        entry_time = None
        entry_spot = 0.0
        sl_price = 0.0
        target_price = 0.0
        trade_type = ""
        setup_name = ""

        # Days to expiry approximation (weekly Thursday = 3, weekly cycle)
        day_of_week = current_date.weekday()
        dte = max(0.5, (3 - day_of_week) % 7 + 0.5) / 365.0
        vol = 0.135  # standard Indian IV ~13.5%

        trades_today = 0

        for i in range(2, len(day_bars) - 2):
            bar = day_bars.iloc[i]
            prev_bar = day_bars.iloc[i-1]
            t = bar.name.time()

            # No new trades before 09:30 or after 14:45
            if t < time(9, 30) or t > time(14, 45):
                continue

            spot = float(bar["close"])
            bar_open = float(bar["open"])
            bar_high = float(bar["high"])
            bar_low = float(bar["low"])

            # -------------------------------------------------------------
            # EXIT LOGIC FOR ACTIVE TRADE
            # -------------------------------------------------------------
            if in_trade:
                curr_prem = BlackScholes.calculate_price(spot, strike, dte, vol, is_call=(trade_dir == "CE"))

                # Check SL
                if curr_prem <= sl_price:
                    exit_prem = sl_price * (1 - SLIPPAGE)
                    gross_pnl = (exit_prem - entry_price) * QUANTITY
                    stt = exit_prem * QUANTITY * STT_RATE
                    costs = (2 * BROKERAGE_PER_ORDER) + stt
                    net_pnl = gross_pnl - costs
                    equity += net_pnl
                    trades.append({
                        "Date": current_date.strftime("%Y-%m-%d"),
                        "Time": entry_time.strftime("%H:%M"),
                        "Exit_Time": bar.name.strftime("%H:%M"),
                        "Type": trade_type,
                        "Strike": strike,
                        "Setup": setup_name,
                        "Entry_Spot": entry_spot,
                        "Exit_Spot": spot,
                        "Entry_Prem": round(entry_price, 2),
                        "Exit_Prem": round(exit_prem, 2),
                        "Result": "STOP LOSS",
                        "Net_PnL": round(net_pnl, 2),
                        "Return_Pct": round((exit_prem - entry_price) / entry_price * 100, 2),
                        "Capital": round(equity, 2)
                    })
                    in_trade = False
                    trades_today += 1
                    continue

                # Check Target
                elif curr_prem >= target_price:
                    exit_prem = target_price * (1 - SLIPPAGE)
                    gross_pnl = (exit_prem - entry_price) * QUANTITY
                    stt = exit_prem * QUANTITY * STT_RATE
                    costs = (2 * BROKERAGE_PER_ORDER) + stt
                    net_pnl = gross_pnl - costs
                    equity += net_pnl
                    trades.append({
                        "Date": current_date.strftime("%Y-%m-%d"),
                        "Time": entry_time.strftime("%H:%M"),
                        "Exit_Time": bar.name.strftime("%H:%M"),
                        "Type": trade_type,
                        "Strike": strike,
                        "Setup": setup_name,
                        "Entry_Spot": entry_spot,
                        "Exit_Spot": spot,
                        "Entry_Prem": round(entry_price, 2),
                        "Exit_Prem": round(exit_prem, 2),
                        "Result": "TARGET HIT",
                        "Net_PnL": round(net_pnl, 2),
                        "Return_Pct": round((exit_prem - entry_price) / entry_price * 100, 2),
                        "Capital": round(equity, 2)
                    })
                    in_trade = False
                    trades_today += 1
                    continue

                # End of day square-off at 15:15
                elif t >= time(15, 15):
                    exit_prem = curr_prem * (1 - SLIPPAGE)
                    gross_pnl = (exit_prem - entry_price) * QUANTITY
                    stt = exit_prem * QUANTITY * STT_RATE
                    costs = (2 * BROKERAGE_PER_ORDER) + stt
                    net_pnl = gross_pnl - costs
                    equity += net_pnl
                    trades.append({
                        "Date": current_date.strftime("%Y-%m-%d"),
                        "Time": entry_time.strftime("%H:%M"),
                        "Exit_Time": bar.name.strftime("%H:%M"),
                        "Type": trade_type,
                        "Strike": strike,
                        "Setup": setup_name,
                        "Entry_Spot": entry_spot,
                        "Exit_Spot": spot,
                        "Entry_Prem": round(entry_price, 2),
                        "Exit_Prem": round(exit_prem, 2),
                        "Result": "EOD EXIT",
                        "Net_PnL": round(net_pnl, 2),
                        "Return_Pct": round((exit_prem - entry_price) / entry_price * 100, 2),
                        "Capital": round(equity, 2)
                    })
                    in_trade = False
                    trades_today += 1
                    continue

            # -------------------------------------------------------------
            # ENTRY LOGIC (SPR + OPEN INTEREST CONFLUENCE)
            # -------------------------------------------------------------
            if not in_trade and trades_today < 2:
                # SETUP 1: BULLISH SUPPORT REBOUND (BUY ATM CE)
                # Condition: Tested S1, S2, or CPR BC, green candle reversal, and PCR >= 0.80 or Spot above Put Wall
                near_support = (abs(bar_low - s1) <= 15) or (abs(bar_low - s2) <= 15) or (abs(bar_low - bc) <= 12)
                bullish_candle = (spot > bar_open) and (prev_bar["close"] <= prev_bar["open"])
                oi_bull_confirmed = (pcr >= 0.80) and (spot >= max_pe_strike - 50)

                if near_support and bullish_candle and oi_bull_confirmed:
                    in_trade = True
                    trade_dir = "CE"
                    trade_type = "ATM CALL (CE)"
                    setup_name = "SPR Support Bounce + Put Wall Defense"
                    strike = int(round(spot / 50) * 50)
                    entry_spot = spot
                    entry_time = bar.name
                    entry_price = BlackScholes.calculate_price(spot, strike, dte, vol, is_call=True) * (1 + SLIPPAGE)
                    sl_price = entry_price * (1 - SL_PCT)
                    target_price = entry_price * (1 + TARGET_PCT)
                    continue

                # SETUP 2: BULLISH RESISTANCE SQUEEZE (BUY ATM CE)
                # Condition: Breaks R1 or R2, and PCR is expanding (>1.0)
                r_breakout = (prev_bar["close"] <= r1 and spot > r1) or (prev_bar["close"] <= r2 and spot > r2)
                if r_breakout and (pcr >= 0.98) and (spot > max_pain):
                    in_trade = True
                    trade_dir = "CE"
                    trade_type = "ATM CALL (CE)"
                    setup_name = "SPR Breakout + Call Short Squeeze"
                    strike = int(round(spot / 50) * 50)
                    entry_spot = spot
                    entry_time = bar.name
                    entry_price = BlackScholes.calculate_price(spot, strike, dte, vol, is_call=True) * (1 + SLIPPAGE)
                    sl_price = entry_price * (1 - SL_PCT)
                    target_price = entry_price * (1 + TARGET_PCT)
                    continue

                # SETUP 3: BEARISH RESISTANCE REJECTION (BUY ATM PE)
                # Condition: Tested R1, R2, or CPR TC, red candle rejection, and PCR <= 1.05 or near Call Wall
                near_res = (abs(bar_high - r1) <= 15) or (abs(bar_high - r2) <= 15) or (abs(bar_high - tc) <= 12)
                bearish_candle = (spot < bar_open) and (prev_bar["close"] >= prev_bar["open"])
                oi_bear_confirmed = (pcr <= 1.05) or (spot >= max_ce_strike - 40)

                if near_res and bearish_candle and oi_bear_confirmed:
                    in_trade = True
                    trade_dir = "PE"
                    trade_type = "ATM PUT (PE)"
                    setup_name = "SPR Resistance Rejection + Call Wall Rebuff"
                    strike = int(round(spot / 50) * 50)
                    entry_spot = spot
                    entry_time = bar.name
                    entry_price = BlackScholes.calculate_price(spot, strike, dte, vol, is_call=False) * (1 + SLIPPAGE)
                    sl_price = entry_price * (1 - SL_PCT)
                    target_price = entry_price * (1 + TARGET_PCT)
                    continue

                # SETUP 4: BEARISH SUPPORT BREAKDOWN FLUSH (BUY ATM PE)
                # Condition: Breaks S1 or S2, and Spot below Max Pain
                s_breakdown = (prev_bar["close"] >= s1 and spot < s1) or (prev_bar["close"] >= s2 and spot < s2)
                if s_breakdown and (pcr <= 0.92) and (spot < max_pain):
                    in_trade = True
                    trade_dir = "PE"
                    trade_type = "ATM PUT (PE)"
                    setup_name = "SPR Breakdown + Put Writer Unwinding"
                    strike = int(round(spot / 50) * 50)
                    entry_spot = spot
                    entry_time = bar.name
                    entry_price = BlackScholes.calculate_price(spot, strike, dte, vol, is_call=False) * (1 + SLIPPAGE)
                    sl_price = entry_price * (1 - SL_PCT)
                    target_price = entry_price * (1 + TARGET_PCT)
                    continue

    # Convert to DataFrame
    df_trades = pd.DataFrame(trades)
    df_trades.to_csv("trades_spr_oi_confluence.csv", index=False)

    total_trades = len(df_trades)
    wins = len(df_trades[df_trades["Net_PnL"] > 0])
    losses = len(df_trades[df_trades["Net_PnL"] <= 0])
    win_rate = (wins / total_trades * 100.0) if total_trades > 0 else 0.0
    total_net_pnl = df_trades["Net_PnL"].sum()
    total_roi = (total_net_pnl / INITIAL_CAPITAL) * 100.0
    
    gross_profit = df_trades[df_trades["Net_PnL"] > 0]["Net_PnL"].sum()
    gross_loss = abs(df_trades[df_trades["Net_PnL"] < 0]["Net_PnL"].sum())
    profit_factor = (gross_profit / gross_loss) if gross_loss > 0 else 99.0

    cum_pnl = df_trades["Net_PnL"].cumsum()
    peak = cum_pnl.cummax()
    dd = (cum_pnl - peak)
    max_dd_val = abs(dd.min())
    max_dd_pct = (max_dd_val / INITIAL_CAPITAL) * 100.0

    print("\n" + "=" * 50)
    print("      SPR + OI CONFLUENCE STRATEGY RESULTS")
    print("=" * 50)
    print(f"Total Completed Trades : {total_trades}")
    print(f"Winning Trades         : {wins} ({win_rate:.1f}%)")
    print(f"Losing Trades          : {losses} ({100-win_rate:.1f}%)")
    print(f"Profit Factor          : {profit_factor:.2f}")
    print(f"Total Net Profit (Rs)  : Rs {total_net_pnl:+,.2f} (+{total_roi:.2f}% on Rs 5L Capital)")
    print(f"Max Peak Drawdown      : Rs {max_dd_val:,.2f} (-{max_dd_pct:.2f}%)")
    print(f"Avg Trade PnL          : Rs {df_trades['Net_PnL'].mean():+,.2f}")
    print("=" * 50 + "\n")

    return df_trades

if __name__ == "__main__":
    run_spr_oi_backtest()
