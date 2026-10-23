"""
Backtesting Engine for Telegram Channel Levels (@FlyingcallsArjun)
Tests Arjun's Intraday NIFTY Support & Resistance Levels (S1-S4, R1-R4)
across 68 live market trading sessions with 5-minute candle execution and options pricing.
"""
import os
import math
import numpy as np
import pandas as pd
from datetime import datetime, time

# Black-Scholes Pricing Model for Realistic Option Premiums
class BlackScholesPricing:
    @staticmethod
    def _cnd(d):
        A1, A2, A3, A4, A5 = 0.31938153, -0.356563782, 1.781477937, -1.821255978, 1.330274429
        L = abs(d)
        K = 1.0 / (1.0 + 0.2316419 * L)
        w = 1.0 - 1.0 / math.sqrt(2 * math.pi) * math.exp(-L * L / 2) * (
            A1 * K + A2 * K**2 + A3 * K**3 + A4 * K**4 + A5 * K**5
        )
        return 1.0 - w if d < 0 else w

    @classmethod
    def calculate_price(cls, spot, strike, dte, iv=0.135, r=0.065, is_call=True):
        if dte <= 0.0001:
            return max(0.5, spot - strike) if is_call else max(0.5, strike - spot)
        d1 = (math.log(spot / strike) + (r + 0.5 * iv**2) * dte) / (iv * math.sqrt(dte))
        d2 = d1 - iv * math.sqrt(dte)
        if is_call:
            p = spot * cls._cnd(d1) - strike * math.exp(-r * dte) * cls._cnd(d2)
        else:
            p = strike * math.exp(-r * dte) * cls._cnd(-d2) - spot * cls._cnd(-d1)
        return max(0.5, round(p, 2))

def load_data():
    base_dir = os.path.dirname(os.path.abspath(__file__))
    levels_file = os.path.join(base_dir, "telegram_levels_nifty.csv")
    candle_file = os.path.join(base_dir, "nifty_data", "candles", "NIFTY_5min.csv")

    if not os.path.exists(levels_file):
        raise FileNotFoundError(f"Missing {levels_file}")
    if not os.path.exists(candle_file):
        raise FileNotFoundError(f"Missing {candle_file}")

    df_levels = pd.read_csv(levels_file)
    df_candles = pd.read_csv(candle_file)

    df_candles["datetime"] = pd.to_datetime(df_candles["datetime"])
    df_candles["date"] = df_candles["datetime"].dt.strftime("%Y-%m-%d")
    df_candles["time"] = df_candles["datetime"].dt.time
    df_candles.sort_values("datetime", inplace=True)

    # Match dates
    level_dict = {}
    for _, row in df_levels.iterrows():
        level_dict[row["date"]] = {
            "s1": float(row["s1"]) if pd.notna(row["s1"]) else None,
            "s2": float(row["s2"]) if pd.notna(row["s2"]) else None,
            "s3": float(row["s3"]) if pd.notna(row["s3"]) else None,
            "s4": float(row["s4"]) if pd.notna(row["s4"]) else None,
            "r1": float(row["r1"]) if pd.notna(row["r1"]) else None,
            "r2": float(row["r2"]) if pd.notna(row["r2"]) else None,
            "r3": float(row["r3"]) if pd.notna(row["r3"]) else None,
            "r4": float(row["r4"]) if pd.notna(row["r4"]) else None,
            "pivot": float(row["pivot"]) if pd.notna(row["pivot"]) else None,
        }

    common_dates = sorted(list(set(df_candles["date"]).intersection(set(level_dict.keys()))))
    return df_candles, level_dict, common_dates

def run_backtest(mode="BOUNCE", sl_pts=35.0, rr=3.0, max_trades_per_day=2):
    """
    mode:
      - 'BOUNCE': Mean reversion (Rejection at S1/S2 -> Buy CE, Rejection at R1/R2 -> Buy PE)
      - 'BREAKOUT': Momentum (Close > R1/R2 -> Buy CE, Close < S1/S2 -> Buy PE)
      - 'HYBRID': Both Bounce and Breakout strategies active
    """
    df_candles, level_dict, common_dates = load_data()
    tp_pts = sl_pts * rr
    lot_size = 65
    initial_capital = 50000.0
    capital = initial_capital
    all_trades = []

    for d in common_dates:
        lvl = level_dict[d]
        s1, s2, r1, r2 = lvl["s1"], lvl["s2"], lvl["r1"], lvl["r2"]
        if not s1 or not r1:
            continue

        day_bars = df_candles[df_candles["date"] == d].copy().reset_index(drop=True)
        if len(day_bars) < 10:
            continue

        # Day of week for options DTE
        dt_obj = datetime.strptime(d, "%Y-%m-%d")
        dow = dt_obj.weekday()
        # Thursday expiry (weekday 3)
        dte = max(0.5, (3 - dow) % 7 + 0.5) / 365.0

        in_trade = False
        trade_dir = None
        strike = 0
        entry_prem = 0.0
        curr_sl = 0.0
        curr_tp = 0.0
        playbook = ""
        category = ""
        entry_time = None
        trades_today = 0

        for i in range(1, len(day_bars)):
            bar = day_bars.iloc[i]
            prev_bar = day_bars.iloc[i - 1]
            t = bar["time"]
            spot = float(bar["close"])
            b_open = float(bar["open"])
            b_high = float(bar["high"])
            b_low = float(bar["low"])
            b_range = b_high - b_low

            # In trade check
            if in_trade:
                is_call = (trade_dir == "CE")
                prem_close = BlackScholesPricing.calculate_price(spot, strike, dte, 0.135, is_call=is_call)
                prem_high = BlackScholesPricing.calculate_price(b_high, strike, dte, 0.135, is_call=is_call) if is_call else BlackScholesPricing.calculate_price(b_low, strike, dte, 0.135, is_call=is_call)
                prem_low = BlackScholesPricing.calculate_price(b_low, strike, dte, 0.135, is_call=is_call) if is_call else BlackScholesPricing.calculate_price(b_high, strike, dte, 0.135, is_call=is_call)

                hit_tp = (prem_high >= curr_tp)
                hit_sl = (prem_low <= curr_sl)
                hit_eod = (t >= time(15, 10))

                if hit_tp or hit_sl or hit_eod:
                    exit_raw = curr_tp if hit_tp else (curr_sl if hit_sl else prem_close)
                    fill_entry = entry_prem * 1.005 # 0.5% realistic slippage
                    fill_exit = max(0.5, exit_raw * 0.995)
                    pts = fill_exit - fill_entry
                    gross = pts * lot_size
                    # Realistic Indian Options Taxes & Charges (NSE, STT, GST, Brokerage)
                    stt = fill_exit * lot_size * 0.000625
                    txn = (fill_entry + fill_exit) * lot_size * 0.00053
                    brokerage = 40.0 # Zerodha / Angel standard roundtrip
                    gst = (brokerage + txn) * 0.18
                    total_costs = brokerage + stt + txn + gst
                    net = gross - total_costs
                    capital += net
                    reason = f"TARGET 1:{int(rr)} HIT" if hit_tp else ("STOP LOSS" if hit_sl else "EOD EXIT")

                    all_trades.append({
                        "Date": d,
                        "Time": entry_time.strftime("%H:%M") if hasattr(entry_time, "strftime") else str(entry_time),
                        "Exit_Time": t.strftime("%H:%M") if hasattr(t, "strftime") else str(t),
                        "Instrument": f"NIFTY {strike} {trade_dir}",
                        "Category": category,
                        "Playbook": playbook,
                        "Type": trade_dir,
                        "Strike": strike,
                        "Spot_Entry": round(spot, 1),
                        "Entry_Prem": round(fill_entry, 2),
                        "Exit_Prem": round(fill_exit, 2),
                        "Prem_Pts": round(pts, 2),
                        "Gross_PnL": round(gross, 2),
                        "Costs": round(total_costs, 2),
                        "Net_PnL": round(net, 2),
                        "Capital": round(capital, 2),
                        "Result": reason
                    })
                    in_trade = False
                    trades_today += 1
                    continue

            # Look for entries
            if not in_trade and trades_today < max_trades_per_day and time(9, 25) <= t <= time(14, 45):
                if b_range < 5:
                    continue
                lower_wick = min(b_open, spot) - b_low
                upper_wick = b_high - max(b_open, spot)
                bull_body = (spot > b_open) and ((spot - b_open) >= 0.35 * b_range)
                bear_body = (spot < b_open) and ((b_open - spot) >= 0.35 * b_range)
                prev_c = float(prev_bar["close"])

                c_dir = None
                c_pb = ""
                c_cat = ""

                # --- 1. BOUNCE / MEAN REVERSION LOGIC ---
                if mode in ["BOUNCE", "HYBRID"]:
                    # S1 Support Bounce
                    tested_s1 = (b_low <= s1 <= b_high) or (b_low <= s1 * 1.001 and spot >= s1)
                    if tested_s1 and spot > s1 and (lower_wick >= 0.30 * b_range or bull_body):
                        c_dir = "CE"
                        c_pb = "Telegram S1 Support Bounce"
                        c_cat = "BOUNCE"

                    # S2 Deep Support Bounce
                    if s2 and not c_dir:
                        tested_s2 = (b_low <= s2 <= b_high) or (b_low <= s2 * 1.001 and spot >= s2)
                        if tested_s2 and spot > s2 and (lower_wick >= 0.30 * b_range or bull_body):
                            c_dir = "CE"
                            c_pb = "Telegram S2 Deep Bounce"
                            c_cat = "BOUNCE"

                    # R1 Resistance Reversal
                    tested_r1 = (b_high >= r1 >= b_low) or (b_high >= r1 * 0.999 and spot <= r1)
                    if tested_r1 and spot < r1 and (upper_wick >= 0.30 * b_range or bear_body):
                        c_dir = "PE"
                        c_pb = "Telegram R1 Resistance Reversal"
                        c_cat = "BOUNCE"

                    # R2 Exhaustion Reversal
                    if r2 and not c_dir:
                        tested_r2 = (b_high >= r2 >= b_low) or (b_high >= r2 * 0.999 and spot <= r2)
                        if tested_r2 and spot < r2 and (upper_wick >= 0.30 * b_range or bear_body):
                            c_dir = "PE"
                            c_pb = "Telegram R2 Exhaustion Reversal"
                            c_cat = "BOUNCE"

                # --- 2. BREAKOUT / MOMENTUM LOGIC ---
                if mode in ["BREAKOUT", "HYBRID"] and not c_dir:
                    # R1 Breakout
                    if prev_c <= r1 and spot > r1 and bull_body:
                        c_dir = "CE"
                        c_pb = "Telegram R1 Breakout Long"
                        c_cat = "BREAKOUT"

                    # S1 Breakdown
                    elif prev_c >= s1 and spot < s1 and bear_body:
                        c_dir = "PE"
                        c_pb = "Telegram S1 Breakdown Short"
                        c_cat = "BREAKOUT"

                    # R2 Expansion
                    elif r2 and prev_c <= r2 and spot > r2 and bull_body:
                        c_dir = "CE"
                        c_pb = "Telegram R2 Expansion Long"
                        c_cat = "BREAKOUT"

                    # S2 Flush
                    elif s2 and prev_c >= s2 and spot < s2 and bear_body:
                        c_dir = "PE"
                        c_pb = "Telegram S2 Flush Breakdown"
                        c_cat = "BREAKOUT"

                if c_dir:
                    in_trade = True
                    trade_dir = c_dir
                    playbook = c_pb
                    category = c_cat
                    strike = int(round(spot / 50) * 50)
                    is_call = (trade_dir == "CE")
                    entry_prem = BlackScholesPricing.calculate_price(spot, strike, dte, 0.135, is_call=is_call)
                    curr_sl = max(0.5, entry_prem - sl_pts)
                    curr_tp = entry_prem + tp_pts
                    entry_time = t
                    continue

    df_res = pd.DataFrame(all_trades)
    return df_res

def evaluate_metrics(df_res, label="Strategy"):
    if df_res is None or len(df_res) == 0:
        return {"Mode": label, "Trades": 0, "Win_Rate": "0%", "Net_PnL": 0.0, "PF": 0.0, "Max_DD": 0.0}

    total_trades = len(df_res)
    wins = (df_res["Net_PnL"] > 0).sum()
    losses = (df_res["Net_PnL"] <= 0).sum()
    win_rate = (wins / total_trades) * 100.0
    net_pnl = df_res["Net_PnL"].sum()
    gross_win = df_res[df_res["Net_PnL"] > 0]["Net_PnL"].sum()
    gross_loss = abs(df_res[df_res["Net_PnL"] <= 0]["Net_PnL"].sum())
    pf = (gross_win / gross_loss) if gross_loss > 0 else 99.0

    peak = df_res["Capital"].cummax()
    max_dd = abs((df_res["Capital"] - peak).min())
    avg_trade = df_res["Net_PnL"].mean()

    return {
        "Mode": label,
        "Trades": total_trades,
        "Wins": wins,
        "Losses": losses,
        "Win_Rate": f"{win_rate:.1f}%",
        "Net_PnL": round(net_pnl, 2),
        "PF": round(pf, 2),
        "Max_DD": round(max_dd, 2),
        "Avg_Trade": round(avg_trade, 2)
    }

if __name__ == "__main__":
    print("=================================================================")
    print("BACKTESTING TELEGRAM INTRADAY LEVELS (@FlyingcallsArjun)")
    print("=================================================================")
    
    results = []
    configs = [
        ("BOUNCE (S&R Mean Reversion)", "BOUNCE", 35.0, 3.0),
        ("BOUNCE (Tight 30pt SL, 1:3 RR)", "BOUNCE", 30.0, 3.0),
        ("BOUNCE (40pt SL, 1:2.5 RR)", "BOUNCE", 40.0, 2.5),
        ("BREAKOUT (Momentum Beyond S1/R1)", "BREAKOUT", 35.0, 3.0),
        ("BREAKOUT (40pt SL, 1:3 RR)", "BREAKOUT", 40.0, 3.0),
        ("HYBRID (Bounce + Breakout Combined)", "HYBRID", 35.0, 3.0),
        ("HYBRID (40pt SL, 1:3 RR)", "HYBRID", 40.0, 3.0),
    ]

    best_df = None
    best_pnl = -999999
    best_label = ""

    for label, mode, sl, rr in configs:
        df_trades = run_backtest(mode=mode, sl_pts=sl, rr=rr)
        met = evaluate_metrics(df_trades, label=label)
        results.append(met)
        print(f"[{label}] Trades: {met['Trades']} | WR: {met['Win_Rate']} | Net PnL: Rs {met['Net_PnL']:,} | PF: {met['PF']} | MaxDD: Rs {met['Max_DD']:,}")
        
        if met["Net_PnL"] > best_pnl:
            best_pnl = met["Net_PnL"]
            best_df = df_trades
            best_label = label

    summary_df = pd.DataFrame(results)
    summary_df.to_csv("telegram_levels_backtest_summary.csv", index=False)
    print("\n================== SUMMARY COMPARISON ==================")
    print(summary_df.to_string(index=False))

    if best_df is not None:
        best_df.to_csv("telegram_levels_best_trades.csv", index=False)
        print(f"\nBest Performing Strategy: {best_label}")
        print(f"Exported all trades to telegram_levels_best_trades.csv")
