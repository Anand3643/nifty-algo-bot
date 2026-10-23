"""
Exact-Condition Audit: Applying Our Bot's Ruleset Directly to Arjun's Levels
Rules applied:
- 40-point options premium Stop Loss
- 1:3 Risk-to-Reward Target (120 points)
- Trailing Stop Loss (Locks +20 pts at +40 gain; or dynamic 15 pt trail after +80)
- Hard EOD cut-off at 15:10
- Max 2 trades/day
- Same cost model: 65 qty ATM, 0.5% slippage, STT, turnover charges, Rs 40 brokerage + 18% GST.
"""
import os
import math
import numpy as np
import pandas as pd
from datetime import datetime, time
from backtest_telegram_levels import BlackScholesPricing, load_data

def run_exact_arjun_test(mode="BREAKOUT", use_ema=False, trail_mode="LOCK20"):
    df_candles, level_dict, common_dates = load_data()
    
    sl_pts = 40.0
    tp_pts = 120.0 # 1:3 RR
    lot_size = 65
    initial_capital = 50000.0
    capital = initial_capital
    all_trades = []

    df_candles["ema9"] = df_candles["close"].ewm(span=9, adjust=False).mean()
    df_candles["ema21"] = df_candles["close"].ewm(span=21, adjust=False).mean()

    for d in common_dates:
        lvl = level_dict[d]
        s1, s2, r1, r2 = lvl["s1"], lvl["s2"], lvl["r1"], lvl["r2"]
        if not s1 or not r1:
            continue

        day_bars = df_candles[df_candles["date"] == d].copy().reset_index(drop=True)
        if len(day_bars) < 10:
            continue

        dt_obj = datetime.strptime(d, "%Y-%m-%d")
        dow = dt_obj.weekday()
        dte = max(0.5, (3 - dow) % 7 + 0.5) / 365.0

        in_trade = False
        trade_dir = None
        strike = 0
        entry_prem = 0.0
        curr_sl = 0.0
        curr_tp = 0.0
        max_fav = 0.0
        trailed = False
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
            ema9 = float(bar["ema9"])
            ema21 = float(bar["ema21"])

            # In trade check
            if in_trade:
                is_call = (trade_dir == "CE")
                prem_close = BlackScholesPricing.calculate_price(spot, strike, dte, 0.135, is_call=is_call)
                prem_high = BlackScholesPricing.calculate_price(b_high, strike, dte, 0.135, is_call=is_call) if is_call else BlackScholesPricing.calculate_price(b_low, strike, dte, 0.135, is_call=is_call)
                prem_low = BlackScholesPricing.calculate_price(b_low, strike, dte, 0.135, is_call=is_call) if is_call else BlackScholesPricing.calculate_price(b_high, strike, dte, 0.135, is_call=is_call)

                if prem_high > max_fav:
                    max_fav = prem_high

                # Trailing Logic
                if trail_mode == "LOCK20":
                    # Lock +20 pts once +40 pts gained
                    if not trailed and (max_fav - entry_prem) >= 40.0:
                        curr_sl = entry_prem + 20.0
                        trailed = True
                elif trail_mode == "BOT_TRAIL":
                    # Bot Smart BE (+80 pts gain -> BE, and dynamic 15 pt trail behind high)
                    if (max_fav - entry_prem) >= 80.0:
                        dynamic_sl = max_fav - 15.0
                        if dynamic_sl > curr_sl:
                            curr_sl = dynamic_sl
                            trailed = True
                    elif (max_fav - entry_prem) >= 40.0 and not trailed:
                        curr_sl = entry_prem + 10.0 # Early lock
                        trailed = True

                hit_tp = (prem_high >= curr_tp)
                hit_sl = (prem_low <= curr_sl)
                hit_eod = (t >= time(15, 10))

                if hit_tp or hit_sl or hit_eod:
                    exit_raw = curr_tp if hit_tp else (curr_sl if hit_sl else prem_close)
                    fill_entry = entry_prem * 1.005
                    fill_exit = max(0.5, exit_raw * 0.995)
                    pts = fill_exit - fill_entry
                    gross = pts * lot_size
                    stt = fill_exit * lot_size * 0.000625
                    txn = (fill_entry + fill_exit) * lot_size * 0.00053
                    brokerage = 40.0
                    gst = (brokerage + txn) * 0.18
                    total_costs = brokerage + stt + txn + gst
                    net = gross - total_costs
                    capital += net

                    if hit_tp:
                        reason = "TARGET 1:3 HIT"
                    elif hit_sl and trailed:
                        reason = f"TRAILING STOP HIT (+{round(curr_sl - entry_prem, 1)} pts)"
                    elif hit_sl:
                        reason = "STOP LOSS (-40 pts)"
                    else:
                        reason = "EOD 15:10 EXIT"

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
            if not in_trade and trades_today < 2 and time(9, 25) <= t <= time(14, 45):
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

                # --- 1. BOUNCE / MEAN REVERSION ---
                if mode in ["BOUNCE", "HYBRID"]:
                    # S1 Support Bounce
                    tested_s1 = (b_low <= s1 <= b_high) or (b_low <= s1 * 1.001 and spot >= s1)
                    if tested_s1 and spot > s1 and (lower_wick >= 0.30 * b_range or bull_body):
                        if not use_ema or (ema9 >= ema21):
                            c_dir = "CE"; c_pb = "Telegram S1 Support Bounce"; c_cat = "BOUNCE"

                    # R1 Resistance Reversal
                    tested_r1 = (b_high >= r1 >= b_low) or (b_high >= r1 * 0.999 and spot <= r1)
                    if tested_r1 and spot < r1 and (upper_wick >= 0.30 * b_range or bear_body):
                        if not use_ema or (ema9 <= ema21):
                            c_dir = "PE"; c_pb = "Telegram R1 Resistance Reversal"; c_cat = "BOUNCE"

                # --- 2. BREAKOUT / MOMENTUM ---
                if mode in ["BREAKOUT", "HYBRID"] and not c_dir:
                    # R1 Breakout Long
                    if prev_c <= r1 and spot > r1 and bull_body:
                        if not use_ema or (ema9 >= ema21):
                            c_dir = "CE"; c_pb = "Telegram R1 Breakout Long"; c_cat = "BREAKOUT"

                    # S1 Breakdown Short
                    elif prev_c >= s1 and spot < s1 and bear_body:
                        if not use_ema or (ema9 <= ema21):
                            c_dir = "PE"; c_pb = "Telegram S1 Breakdown Short"; c_cat = "BREAKOUT"

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
                    max_fav = entry_prem
                    trailed = False
                    entry_time = t
                    continue

    return pd.DataFrame(all_trades)

if __name__ == "__main__":
    from backtest_telegram_levels import evaluate_metrics

    print("\n" + "="*80)
    print("APPLYING OUR EXACT BOT CONDITIONS (40pt SL, 1:3 RR, Trailing, 15:10 EOD)")
    print("TO ARJUN'S TELEGRAM LEVELS (@FlyingcallsArjun) [03-Jul-2026 to 15-Oct-2026]")
    print("="*80)

    configs = [
        ("Arjun Breakout (No Trail)", "BREAKOUT", False, "NONE"),
        ("Arjun Breakout + Lock +20 Trail", "BREAKOUT", False, "LOCK20"),
        ("Arjun Breakout + Bot Dynamic Trail", "BREAKOUT", False, "BOT_TRAIL"),
        ("Arjun Breakout + EMA Filter + Lock +20", "BREAKOUT", True, "LOCK20"),
        ("Arjun Breakout + EMA Filter + Bot Dynamic Trail", "BREAKOUT", True, "BOT_TRAIL"),
        ("Arjun Bounce / Mean Reversion (Exact Rules)", "BOUNCE", False, "LOCK20"),
        ("Arjun Hybrid (Bounce + Breakout with Exact Rules)", "HYBRID", True, "LOCK20"),
    ]

    res = []
    for lbl, mode, ema, trail in configs:
        df = run_exact_arjun_test(mode=mode, use_ema=ema, trail_mode=trail)
        m = evaluate_metrics(df, label=lbl)
        res.append(m)
        print(f"[{lbl:<48}] Trades: {m['Trades']:>2} | WR: {m['Win_Rate']:>6} | Net PnL: Rs {m['Net_PnL']:>10,} | PF: {m['PF']:>4} | MaxDD: Rs {m['Max_DD']:>8,}")

    df_comp = pd.DataFrame(res)
    df_comp.to_csv("arjun_exact_bot_conditions_results.csv", index=False)
