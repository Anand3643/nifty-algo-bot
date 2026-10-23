import os
import json
import pandas as pd
import numpy as np
from datetime import time, timedelta
from optimize_combined_strategy import NiftySREngine, BlackScholesPricing

def analyze_and_solve_gaps():
    base_dir = os.path.dirname(os.path.abspath(__file__))
    candle_5m_path1 = os.path.join(base_dir, "nifty_data", "candles", "NIFTY_5min.csv")
    candle_5m_path2 = r"C:\Users\Admin\Desktop\wasted\indian options\nifty_50_5m.csv"
    candle_1h_path = os.path.join(base_dir, "nifty_data", "candles", "NIFTY_1hour.csv")
    daily_path = os.path.join(base_dir, "nifty_data", "candles", "NIFTY_1day.csv")

    df1 = pd.read_csv(candle_5m_path1); df1["datetime"] = pd.to_datetime(df1["datetime"])
    df2 = pd.read_csv(candle_5m_path2); df2["datetime"] = pd.to_datetime(df2["Datetime"]) + pd.Timedelta(hours=5, minutes=30)
    df2.rename(columns={"Open": "open", "High": "high", "Low": "low", "Close": "close", "Volume": "volume"}, inplace=True)
    df_actual_5m = pd.concat([df1[["datetime", "open", "high", "low", "close"]], df2[["datetime", "open", "high", "low", "close"]]])
    df_actual_5m.drop_duplicates(subset=["datetime"], inplace=True); df_actual_5m.sort_values("datetime", inplace=True)
    df_actual_5m["date"] = df_actual_5m["datetime"].dt.date
    actual_5m_dates = set(df_actual_5m["date"].unique())

    df_1h = pd.read_csv(candle_1h_path); df_1h["datetime"] = pd.to_datetime(df_1h["datetime"]); df_1h.sort_values("datetime", inplace=True); df_1h["date"] = df_1h["datetime"].dt.date
    df_1d = pd.read_csv(daily_path); df_1d["datetime"] = pd.to_datetime(df_1d["datetime"]).dt.date; df_1d.drop_duplicates(subset=["datetime"], inplace=True); df_1d.set_index("datetime", inplace=True)

    start_2y = pd.to_datetime("2024-10-14").date(); end_2y = pd.to_datetime("2026-10-09").date()

    def expand_hour_to_5m(bars_1h):
        bars_5m = []
        for b in bars_1h:
            dt = b["dt"]
            O, H, L, C = b["open"], b["high"], b["low"], b["close"]
            is_bull = (C >= O)
            for step in range(12):
                sub_dt = dt + timedelta(minutes=5 * step)
                t_rel = step / 11.0
                if is_bull:
                    if t_rel < 0.25: p_sub = O - (O - L) * (t_rel / 0.25)
                    elif t_rel < 0.8: p_sub = L + (H - L) * ((t_rel - 0.25) / 0.55)
                    else: p_sub = H - (H - C) * ((t_rel - 0.8) / 0.2)
                else:
                    if t_rel < 0.25: p_sub = O + (H - O) * (t_rel / 0.25)
                    elif t_rel < 0.8: p_sub = H - (H - L) * ((t_rel - 0.25) / 0.55)
                    else: p_sub = L + (C - L) * ((t_rel - 0.8) / 0.2)
                bars_5m.append({"dt": sub_dt, "time": sub_dt.time(), "open": round(p_sub, 1), "high": round(max(p_sub, p_sub + 3.0), 1), "low": round(min(p_sub, p_sub - 3.0), 1), "close": round(p_sub, 1)})
        return bars_5m

    session_data = []
    unique_dates = sorted([d for d in set(df_1h["date"]).union(actual_5m_dates) if start_2y <= d <= end_2y])
    for current_date in unique_dates:
        priors = [d for d in df_1d.index if d < current_date]
        if not priors: continue
        prev_row = df_1d.loc[priors[-1]]
        lvl = NiftySREngine.calculate_levels(float(prev_row["high"]), float(prev_row["low"]), float(prev_row["close"]))
        dow = current_date.weekday()
        dte = max(0.5, (3 - dow) % 7 + 0.5) / 365.0

        if current_date in actual_5m_dates:
            grp = df_actual_5m[df_actual_5m["date"] == current_date]
            if len(grp) < 15: continue
            bars = [{"dt": r["datetime"], "time": r["datetime"].time(), "open": float(r["open"]), "high": float(r["high"]), "low": float(r["low"]), "close": float(r["close"])} for _, r in grp.iterrows()]
        else:
            grp = df_1h[df_1h["date"] == current_date]
            if len(grp) < 4: continue
            bars_1h = [{"dt": r["datetime"], "time": r["datetime"].time(), "open": float(r["open"]), "high": float(r["high"]), "low": float(r["low"]), "close": float(r["close"])} for _, r in grp.iterrows()]
            bars = expand_hour_to_5m(bars_1h)

        session_data.append({"date": current_date, "lvl": lvl, "dte": dte, "day_open": bars[0]["open"], "bars": bars, "dow": dow})

    def run_gap_simulation(mode="baseline"):
        sl_val = 40.0
        rr = 3.0
        tp_val = sl_val * rr
        lot_size = 65
        equity = 50000.0
        trades = []
        body_thresh = 0.25

        for sess in session_data:
            lvl = sess["lvl"]; bars = sess["bars"]; current_date = sess["date"]; dte = sess["dte"]; day_open = sess["day_open"]
            in_trade = False; trade_dir = None; strike = 0; entry_prem = 0.0; curr_sl = 0.0; curr_tp = 0.0; playbook = ""; trades_today = 0
            entry_time = None

            # Track 15-min opening range for ORB
            orb_high = max(b["high"] for b in bars[:3])
            orb_low = min(b["low"] for b in bars[:3])

            for i in range(1, len(bars)):
                bar = bars[i]; prev_bar = bars[i - 1]; t = bar["time"]; spot = bar["close"]; b_open = bar["open"]; b_high = bar["high"]; b_low = bar["low"]; b_range = b_high - b_low

                if in_trade:
                    is_call = (trade_dir == "CE")
                    prem_close = BlackScholesPricing.calculate_price(spot, strike, dte, 0.135, is_call=is_call)
                    prem_high = BlackScholesPricing.calculate_price(b_high, strike, dte, 0.135, is_call=is_call) if is_call else BlackScholesPricing.calculate_price(b_low, strike, dte, 0.135, is_call=is_call)
                    prem_low = BlackScholesPricing.calculate_price(b_low, strike, dte, 0.135, is_call=is_call) if is_call else BlackScholesPricing.calculate_price(b_high, strike, dte, 0.135, is_call=is_call)

                    hit_tp = (prem_high >= curr_tp); hit_sl = (prem_low <= curr_sl); hit_eod = (t >= time(15, 10))
                    if hit_tp or hit_sl or hit_eod:
                        exit_raw = curr_tp if hit_tp else (curr_sl if hit_sl else prem_close)
                        fill_entry = entry_prem * 1.005; fill_exit = max(0.5, exit_raw * 0.995); pts = fill_exit - fill_entry; gross = pts * lot_size
                        stt = fill_exit * lot_size * 0.000625; txn = (fill_entry + fill_exit) * lot_size * 0.00053; brokerage = 40.0; gst = (brokerage + txn) * 0.18
                        net = gross - (brokerage + stt + txn + gst); equity += net
                        trades.append({
                            "Date": current_date.strftime("%Y-%m-%d"),
                            "Time": entry_time.strftime("%H:%M") if entry_time else "09:25",
                            "Playbook": playbook,
                            "Type": trade_dir,
                            "Strike": strike,
                            "Net_PnL": round(net, 2),
                            "Capital": round(equity, 2),
                            "Result": "TARGET 1:3 HIT" if hit_tp else ("STOP LOSS" if hit_sl else "EOD EXIT")
                        })
                        in_trade = False; trades_today += 1; continue

                if not in_trade and trades_today < 2 and time(9, 25) <= t <= time(14, 45):
                    if b_range < 5: continue
                    lower_wick = min(b_open, spot) - b_low; upper_wick = b_high - max(b_open, spot)
                    bull_body = (spot > b_open) and ((spot - b_open) >= body_thresh * b_range)
                    bear_body = (spot < b_open) and ((b_open - spot) >= body_thresh * b_range)
                    prev_c = prev_bar["close"]

                    # 1. Standard Crossovers (when price starts inside and crosses)
                    r1_break = (prev_c <= lvl["r1"]) and (spot > lvl["r1"]) and bull_body
                    s1_break = (prev_c >= lvl["s1"]) and (spot < lvl["s1"]) and bear_body

                    # 2. Reversals
                    tested_r1 = (b_high >= lvl["r1"] >= b_low) or (prev_bar["high"] >= lvl["r1"] and b_high >= lvl["r1"])
                    r1_fade = tested_r1 and (spot < lvl["r1"]) and (upper_wick >= body_thresh * b_range)
                    tested_r2 = (b_high >= lvl["r2"])
                    r2_fade = tested_r2 and (spot < lvl["r2"]) and (upper_wick >= body_thresh * b_range)

                    # 3. Next Level Expansion on Gap Days
                    r2_break = (prev_c <= lvl["r2"]) and (spot > lvl["r2"]) and bull_body
                    s2_break = (prev_c >= lvl["s2"]) and (spot < lvl["s2"]) and bear_body

                    # 4. GAP SOLUTIONS:
                    # Solution A: Gap Retest & Bounce
                    gap_r1_retest = False
                    gap_s1_retest = False
                    if "retest" in mode:
                        if day_open >= lvl["r1"]:
                            # Pulled back from above to test R1 as support and bounced
                            tested = (b_low <= lvl["r1"] <= b_high) or (b_low <= lvl["r1"])
                            gap_r1_retest = tested and (spot > lvl["r1"]) and (lower_wick >= body_thresh * b_range)
                        elif day_open <= lvl["s1"]:
                            # Bounced from below to test S1 as resistance and rejected
                            tested = (b_low <= lvl["s1"] <= b_high) or (b_high >= lvl["s1"])
                            gap_s1_retest = tested and (spot < lvl["s1"]) and (upper_wick >= body_thresh * b_range)

                    # Solution B: Gap-and-Go ORB (Opening Range Breakout)
                    gap_orb_ce = False
                    gap_orb_pe = False
                    if "orb" in mode and i >= 3:
                        if day_open >= lvl["r1"]:
                            gap_orb_ce = (prev_c <= orb_high) and (spot > orb_high) and bull_body
                        elif day_open <= lvl["s1"]:
                            gap_orb_pe = (prev_c >= orb_low) and (spot < orb_low) and bear_body

                    cand_dir = None
                    cand_pb = ""

                    if gap_r1_retest:
                        cand_dir = "CE"; cand_pb = "Gap-Up R1 Polarity Bounce"
                    elif gap_s1_retest:
                        cand_dir = "PE"; cand_pb = "Gap-Down S1 Polarity Rejection"
                    elif gap_orb_ce:
                        cand_dir = "CE"; cand_pb = "Gap-and-Go Bullish ORB"
                    elif gap_orb_pe:
                        cand_dir = "PE"; cand_pb = "Gap-and-Go Bearish ORB"
                    elif r2_break:
                        cand_dir = "CE"; cand_pb = "R2 Expansion Breakout"
                    elif s2_break:
                        cand_dir = "PE"; cand_pb = "S2 Flush Breakdown"
                    elif r1_fade:
                        cand_dir = "PE"; cand_pb = "R1 Resistance Reversal"
                    elif r2_fade:
                        cand_dir = "PE"; cand_pb = "R2 Exhaustion Reversal"
                    elif r1_break:
                        cand_dir = "CE"; cand_pb = "R1 Resistance Breakout"
                    elif s1_break:
                        cand_dir = "PE"; cand_pb = "S1 Support Breakdown"

                    if cand_dir:
                        in_trade = True; trade_dir = cand_dir; playbook = cand_pb
                        strike = int(round(spot / 50) * 50); is_call = (trade_dir == "CE")
                        entry_prem = BlackScholesPricing.calculate_price(spot, strike, dte, 0.135, is_call=is_call)
                        curr_sl = max(0.5, entry_prem - sl_val); curr_tp = entry_prem + tp_val
                        entry_time = bar["dt"]; continue

        df_res = pd.DataFrame(trades)
        if len(df_res) == 0: return None
        wins = (df_res["Net_PnL"] > 0).sum(); total_pnl = df_res["Net_PnL"].sum(); win_rate = wins / len(df_res) * 100.0
        peak = df_res["Capital"].cummax(); max_dd = abs((df_res["Capital"] - peak).min())
        gross_p = df_res[df_res["Net_PnL"] > 0]["Net_PnL"].sum(); gross_l = abs(df_res[df_res["Net_PnL"] <= 0]["Net_PnL"].sum())
        pf = (gross_p / gross_l) if gross_l > 0 else 99.0
        daily_ret = df_res.groupby("Date")["Net_PnL"].sum(); sharpe = (daily_ret.mean() / daily_ret.std()) * np.sqrt(252) if daily_ret.std() > 0 else 0.0
        return {"trades": len(df_res), "win_rate": win_rate, "net_pnl": total_pnl, "pf": pf, "sharpe": sharpe, "max_dd": max_dd, "df": df_res}

    print("=" * 115)
    print("   SOLVING GAP DAYS: 2-YEAR 5-MINUTE NIFTY OPTIONS BACKTEST (492 SESSIONS)")
    print("=" * 115)

    m_base = run_gap_simulation(mode="baseline")
    m_retest = run_gap_simulation(mode="retest")
    m_orb = run_gap_simulation(mode="orb")
    m_complete = run_gap_simulation(mode="retest_orb")

    models = [
        ("1. Before: Strict Crossover (Ignored Gaps)", m_base),
        ("2. Solution A: Gap Retest & Polarity Bounce", m_retest),
        ("3. Solution B: Gap-and-Go Opening Range Breakout", m_orb),
        ("4. Complete Gap Master Engine (Retest + ORB) ⭐", m_complete),
    ]

    for name, r in models:
        roi = (r["net_pnl"] / 50000.0) * 100.0
        dd_pct = (r["max_dd"] / 50000.0) * 100.0
        tr_mo = r["trades"] / 24.0
        print(f"{name:50s} | Tr: {r['trades']:3d} ({tr_mo:4.1f}/mo) | Win: {r['win_rate']:4.1f}% | Net: Rs {r['net_pnl']:+10,.2f} ({roi:+5.1f}%) | PF: {r['pf']:4.2f} | Sharpe: {r['sharpe']:4.2f} | Max DD: Rs {r['max_dd']:7,.0f} ({dd_pct:4.1f}%)")

    # Save Complete Gap Master trades
    csv_out = os.path.join(base_dir, "trades_2year_gap_master_nifty.csv")
    m_complete["df"].to_csv(csv_out, index=False)
    print(f"\nSaved Complete Gap Master trades to: {csv_out}")

    # Inspect the playbook breakdown of the Gap Master engine
    df_m = m_complete["df"]
    pb_breakdown = df_m.groupby("Playbook").agg(
        Trades=("Net_PnL", "count"),
        Wins=("Net_PnL", lambda x: (x > 0).sum()),
        Win_Rate=("Net_PnL", lambda x: round((x > 0).mean() * 100, 1)),
        Net_PnL=("Net_PnL", lambda x: round(x.sum(), 2))
    ).reset_index().sort_values("Net_PnL", ascending=False)
    print("\nPLAYBOOK BREAKDOWN (GAP MASTER ENGINE):")
    print(pb_breakdown.to_string(index=False))

    # Yearly breakdown
    df_m["Year"] = pd.to_datetime(df_m["Date"]).dt.year
    yearly = df_m.groupby("Year").agg(
        Trades=("Net_PnL", "count"),
        Wins=("Net_PnL", lambda x: (x > 0).sum()),
        Win_Rate=("Net_PnL", lambda x: round((x > 0).mean() * 100, 1)),
        Net_PnL=("Net_PnL", lambda x: round(x.sum(), 2))
    ).reset_index()
    print("\nYEARLY BREAKDOWN (GAP MASTER ENGINE):")
    print(yearly.to_string(index=False))

if __name__ == "__main__":
    analyze_and_solve_gaps()
