"""
Optimization & Trend Filtering for Telegram Channel Levels (@FlyingcallsArjun)
Tests:
- EMA 9/21 Trend Alignment
- Candle Body Strength Filter
- Dynamic Trailing Stop Loss
- Risk-Reward ratios (1:2, 1:2.5, 1:3, 1:4)
"""
import os
import math
import numpy as np
import pandas as pd
from datetime import datetime, time
from backtest_telegram_levels import BlackScholesPricing, load_data, evaluate_metrics

def run_filtered_backtest(
    mode="BREAKOUT",
    use_ema=True,
    use_trail=True,
    sl_pts=35.0,
    rr=2.5,
    trail_trigger=50.0,
    trail_lock=25.0,
    max_trades_per_day=1
):
    df_candles, level_dict, common_dates = load_data()
    tp_pts = sl_pts * rr
    lot_size = 65
    initial_capital = 50000.0
    capital = initial_capital
    all_trades = []

    # Calculate EMA 9 and EMA 21 on the full candle series
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

                # Check trailing stop trigger
                if use_trail and not trailed:
                    if (prem_high - entry_prem) >= trail_trigger:
                        curr_sl = entry_prem + trail_lock
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
                        reason = f"TARGET 1:{rr} HIT"
                    elif hit_sl and trailed:
                        reason = "TRAILED PROFIT HIT"
                    elif hit_sl:
                        reason = "STOP LOSS"
                    else:
                        reason = "EOD EXIT"

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

            # Entry condition
            if not in_trade and trades_today < max_trades_per_day and time(9, 25) <= t <= time(14, 45):
                if b_range < 5:
                    continue
                bull_body = (spot > b_open) and ((spot - b_open) >= 0.40 * b_range)
                bear_body = (spot < b_open) and ((b_open - spot) >= 0.40 * b_range)
                prev_c = float(prev_bar["close"])

                c_dir = None
                c_pb = ""
                c_cat = ""

                # Breakout logic
                if mode == "BREAKOUT":
                    # Long Breakout above R1 (Confirmed by EMA 9 > 21)
                    if prev_c <= r1 and spot > r1 and bull_body:
                        if not use_ema or (ema9 >= ema21):
                            c_dir = "CE"
                            c_pb = "Telegram R1 Breakout Long"
                            c_cat = "BREAKOUT"

                    # Short Breakdown below S1 (Confirmed by EMA 9 < 21)
                    elif prev_c >= s1 and spot < s1 and bear_body:
                        if not use_ema or (ema9 <= ema21):
                            c_dir = "PE"
                            c_pb = "Telegram S1 Breakdown Short"
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
                    trailed = False
                    entry_time = t
                    continue

    return pd.DataFrame(all_trades)

if __name__ == "__main__":
    print("\n=======================================================")
    print("PARAMETRIC SWEEP ON ARJUN TELEGRAM LEVELS (@FlyingcallsArjun)")
    print("=======================================================")
    results = []
    best_df = None
    best_pnl = -999999
    best_lbl = ""

    for max_t in [1, 2]:
        for sl in [30.0, 35.0, 40.0]:
            for rr in [2.5, 3.0, 3.5]:
                for trail in [True, False]:
                    lbl = f"MaxT={max_t} | SL={int(sl)} | RR=1:{rr} | Trail={'Yes' if trail else 'No'}"
                    df = run_filtered_backtest(
                        mode="BREAKOUT",
                        use_ema=True,
                        use_trail=trail,
                        sl_pts=sl,
                        rr=rr,
                        trail_trigger=40.0,
                        trail_lock=20.0,
                        max_trades_per_day=max_t
                    )
                    met = evaluate_metrics(df, label=lbl)
                    results.append(met)
                    print(f"[{lbl:<38}] Trades: {met['Trades']:>2} | WR: {met['Win_Rate']:>6} | PnL: Rs {met['Net_PnL']:>9} | PF: {met['PF']:>4} | MaxDD: Rs {met['Max_DD']:>8}")
                    if met["Net_PnL"] > best_pnl:
                        best_pnl = met["Net_PnL"]
                        best_df = df
                        best_lbl = lbl

    res_df = pd.DataFrame(results)
    res_df.sort_values("Net_PnL", ascending=False, inplace=True)
    res_df.to_csv("telegram_levels_sweep_results.csv", index=False)
    print("\nTop 5 Setups:")
    print(res_df.head(5).to_string(index=False))

    if best_df is not None:
        best_df.to_csv("telegram_levels_best_trades.csv", index=False)
        print(f"\nSaved best setup ({best_lbl}) trades to telegram_levels_best_trades.csv")

