import os
import json
import pandas as pd
import numpy as np
from datetime import time, timedelta, datetime
from optimize_combined_strategy import NiftySREngine, BlackScholesPricing

def run_2year_5m_backtest():
    base_dir = os.path.dirname(os.path.abspath(__file__))
    candle_5m_path1 = os.path.join(base_dir, "nifty_data", "candles", "NIFTY_5min.csv")
    candle_5m_path2 = r"C:\Users\Admin\Desktop\wasted\indian options\nifty_50_5m.csv"
    candle_1h_path = os.path.join(base_dir, "nifty_data", "candles", "NIFTY_1hour.csv")
    daily_path = os.path.join(base_dir, "nifty_data", "candles", "NIFTY_1day.csv")

    # 1. Load actual 5m data
    df1 = pd.read_csv(candle_5m_path1)
    df1["datetime"] = pd.to_datetime(df1["datetime"])
    df2 = pd.read_csv(candle_5m_path2)
    df2["datetime"] = pd.to_datetime(df2["Datetime"]) + pd.Timedelta(hours=5, minutes=30)
    df2.rename(columns={"Open": "open", "High": "high", "Low": "low", "Close": "close", "Volume": "volume"}, inplace=True)
    df_actual_5m = pd.concat([df1[["datetime", "open", "high", "low", "close"]], df2[["datetime", "open", "high", "low", "close"]]])
    df_actual_5m.drop_duplicates(subset=["datetime"], inplace=True)
    df_actual_5m.sort_values("datetime", inplace=True)
    df_actual_5m["date"] = df_actual_5m["datetime"].dt.date
    actual_5m_dates = set(df_actual_5m["date"].unique())

    # 2. Load 1h data for earlier periods
    df_1h = pd.read_csv(candle_1h_path)
    df_1h["datetime"] = pd.to_datetime(df_1h["datetime"])
    df_1h.sort_values("datetime", inplace=True)
    df_1h["date"] = df_1h["datetime"].dt.date

    # 3. Load daily data for S&R levels
    df_1d = pd.read_csv(daily_path)
    df_1d["datetime"] = pd.to_datetime(df_1d["datetime"]).dt.date
    df_1d.drop_duplicates(subset=["datetime"], inplace=True)
    df_1d.set_index("datetime", inplace=True)

    start_2y = pd.to_datetime("2024-10-14").date()
    end_2y = pd.to_datetime("2026-10-09").date()

    # Expand 1h candles into 5m candles
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
                    if t_rel < 0.25:
                        p_sub = O - (O - L) * (t_rel / 0.25)
                    elif t_rel < 0.8:
                        p_sub = L + (H - L) * ((t_rel - 0.25) / 0.55)
                    else:
                        p_sub = H - (H - C) * ((t_rel - 0.8) / 0.2)
                else:
                    if t_rel < 0.25:
                        p_sub = O + (H - O) * (t_rel / 0.25)
                    elif t_rel < 0.8:
                        p_sub = H - (H - L) * ((t_rel - 0.25) / 0.55)
                    else:
                        p_sub = L + (C - L) * ((t_rel - 0.8) / 0.2)

                bars_5m.append({
                    "dt": sub_dt,
                    "time": sub_dt.time(),
                    "open": round(p_sub, 1),
                    "high": round(max(p_sub, p_sub + 3.0), 1),
                    "low": round(min(p_sub, p_sub - 3.0), 1),
                    "close": round(p_sub, 1)
                })
        return bars_5m

    # Build 2-year 5m session data
    session_data = []
    unique_dates = sorted([d for d in set(df_1h["date"]).union(actual_5m_dates) if start_2y <= d <= end_2y])

    for current_date in unique_dates:
        priors = [d for d in df_1d.index if d < current_date]
        if not priors:
            continue
        prev_row = df_1d.loc[priors[-1]]
        lvl = NiftySREngine.calculate_levels(float(prev_row["high"]), float(prev_row["low"]), float(prev_row["close"]))
        dow = current_date.weekday()
        dte = max(0.5, (3 - dow) % 7 + 0.5) / 365.0

        if current_date in actual_5m_dates:
            grp = df_actual_5m[df_actual_5m["date"] == current_date]
            if len(grp) < 15:
                continue
            bars = [
                {"dt": r["datetime"], "time": r["datetime"].time(), "open": float(r["open"]), "high": float(r["high"]), "low": float(r["low"]), "close": float(r["close"])}
                for _, r in grp.iterrows()
            ]
        else:
            grp = df_1h[df_1h["date"] == current_date]
            if len(grp) < 4:
                continue
            bars_1h = [
                {"dt": r["datetime"], "time": r["datetime"].time(), "open": float(r["open"]), "high": float(r["high"]), "low": float(r["low"]), "close": float(r["close"])}
                for _, r in grp.iterrows()
            ]
            bars = expand_hour_to_5m(bars_1h)

        session_data.append({
            "date": current_date,
            "lvl": lvl,
            "dte": dte,
            "day_open": bars[0]["open"],
            "bars": bars,
            "dow": dow
        })

    print(f"Total 2-Year 5-Minute Sessions Built: {len(session_data)} sessions (from {session_data[0]['date']} to {session_data[-1]['date']})")

    # Run 5-Minute Backtest
    def sim_5m(sl_val=40.0, rr=3.0, max_trades=2, allowed_pb=None):
        tp_val = sl_val * rr
        lot_size = 65
        initial_capital = 50000.0
        equity = initial_capital
        trades = []

        if allowed_pb is None:
            allowed_pb = ["S2 Flush Breakdown", "R1 Resistance Reversal", "R2 Exhaustion Reversal", "R1 Resistance Breakout", "S1 Support Breakdown"]

        for sess in session_data:
            lvl = sess["lvl"]
            bars = sess["bars"]
            current_date = sess["date"]
            dte = sess["dte"]

            in_trade = False
            trade_dir = None
            strike = 0
            entry_prem = 0.0
            curr_sl = 0.0
            curr_tp = 0.0
            playbook = ""
            category = ""
            trades_today = 0
            entry_time = None

            for i in range(1, len(bars)):
                bar = bars[i]
                prev_bar = bars[i - 1]
                t = bar["time"]
                spot = bar["close"]
                b_open = bar["open"]
                b_high = bar["high"]
                b_low = bar["low"]
                b_range = b_high - b_low

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
                        equity += net
                        reason = "TARGET 1:3 HIT" if hit_tp else ("STOP LOSS" if hit_sl else "EOD EXIT")

                        trades.append({
                            "Date": current_date.strftime("%Y-%m-%d"),
                            "Time": entry_time.strftime("%H:%M") if entry_time else "09:25",
                            "Exit_Time": bar["dt"].strftime("%H:%M"),
                            "Instrument": f"NIFTY {strike} {trade_dir}",
                            "Category": category,
                            "Playbook": playbook,
                            "Type": trade_dir,
                            "Strike": strike,
                            "Entry_Prem": round(fill_entry, 2),
                            "Exit_Prem": round(fill_exit, 2),
                            "Prem_Pts": round(pts, 2),
                            "Gross_PnL": round(gross, 2),
                            "Costs": round(total_costs, 2),
                            "Net_PnL": round(net, 2),
                            "Capital": round(equity, 2),
                            "Result": reason
                        })
                        in_trade = False
                        trades_today += 1
                        continue

                if not in_trade and trades_today < max_trades and time(9, 25) <= t <= time(14, 45):
                    if b_range < 5:
                        continue
                    lower_wick = min(b_open, spot) - b_low
                    upper_wick = b_high - max(b_open, spot)
                    bull_body = (spot > b_open) and ((spot - b_open) >= 0.35 * b_range)
                    bear_body = (spot < b_open) and ((b_open - spot) >= 0.35 * b_range)
                    prev_c = prev_bar["close"]

                    r1_break = (prev_c <= lvl["r1"]) and (spot > lvl["r1"]) and bull_body
                    s1_break = (prev_c >= lvl["s1"]) and (spot < lvl["s1"]) and bear_body
                    r2_break = (prev_c <= lvl["r2"]) and (spot > lvl["r2"]) and bull_body
                    s2_break = (prev_c >= lvl["s2"]) and (spot < lvl["s2"]) and bear_body

                    tested_s1 = (b_low <= lvl["s1"] <= b_high) or (prev_bar["low"] <= lvl["s1"] and b_low <= lvl["s1"])
                    s1_bounce = tested_s1 and (spot > lvl["s1"]) and ((lower_wick >= 0.35 * b_range) or (spot > prev_bar["high"] and spot > b_open))
                    tested_r1 = (b_high >= lvl["r1"] >= b_low) or (prev_bar["high"] >= lvl["r1"] and b_high >= lvl["r1"])
                    r1_fade = tested_r1 and (spot < lvl["r1"]) and ((upper_wick >= 0.35 * b_range) or (spot < prev_bar["low"] and spot < b_open))
                    tested_s2 = (b_low <= lvl["s2"])
                    s2_bounce = tested_s2 and (spot > lvl["s2"]) and (lower_wick >= 0.35 * b_range)
                    tested_r2 = (b_high >= lvl["r2"])
                    r2_fade = tested_r2 and (spot < lvl["r2"]) and (upper_wick >= 0.35 * b_range)

                    c_dir = None
                    c_pb = ""
                    c_cat = ""
                    if s1_break: c_dir = "PE"; c_pb = "S1 Support Breakdown"; c_cat = "BREAKOUT"
                    elif r1_break: c_dir = "CE"; c_pb = "R1 Resistance Breakout"; c_cat = "BREAKOUT"
                    elif s1_bounce: c_dir = "CE"; c_pb = "S1 Support Bounceback"; c_cat = "BOUNCEBACK"
                    elif r1_fade: c_dir = "PE"; c_pb = "R1 Resistance Reversal"; c_cat = "BOUNCEBACK"
                    elif s2_break: c_dir = "PE"; c_pb = "S2 Flush Breakdown"; c_cat = "BREAKOUT"
                    elif r2_break: c_dir = "CE"; c_pb = "R2 Expansion Breakout"; c_cat = "BREAKOUT"
                    elif s2_bounce: c_dir = "CE"; c_pb = "S2 Sweep Bounceback"; c_cat = "BOUNCEBACK"
                    elif r2_fade: c_dir = "PE"; c_pb = "R2 Exhaustion Reversal"; c_cat = "BOUNCEBACK"

                    if c_dir and c_pb in allowed_pb:
                        in_trade = True
                        trade_dir = c_dir
                        playbook = c_pb
                        category = c_cat
                        strike = int(round(spot / 50) * 50)
                        is_call = (trade_dir == "CE")
                        entry_prem = BlackScholesPricing.calculate_price(spot, strike, dte, 0.135, is_call=is_call)
                        curr_sl = max(0.5, entry_prem - sl_val)
                        curr_tp = entry_prem + tp_val
                        entry_time = bar["dt"]
                        continue

        df_res = pd.DataFrame(trades)
        if len(df_res) == 0:
            return None
        wins = (df_res["Net_PnL"] > 0).sum()
        total_pnl = df_res["Net_PnL"].sum()
        win_rate = (wins / len(df_res)) * 100.0
        peak = df_res["Capital"].cummax()
        max_dd = abs((df_res["Capital"] - peak).min())
        gross_profit = df_res[df_res["Net_PnL"] > 0]["Net_PnL"].sum()
        gross_loss = abs(df_res[df_res["Net_PnL"] <= 0]["Net_PnL"].sum())
        pf = (gross_profit / gross_loss) if gross_loss > 0 else 99.0
        daily_ret = df_res.groupby("Date")["Net_PnL"].sum()
        sharpe = (daily_ret.mean() / daily_ret.std()) * np.sqrt(252) if daily_ret.std() > 0 else 0.0
        return {
            "trades": len(df_res),
            "wins": wins,
            "win_rate": win_rate,
            "net_pnl": total_pnl,
            "pf": pf,
            "sharpe": sharpe,
            "max_dd": max_dd,
            "df": df_res
        }

    print("\n" + "=" * 110)
    print("   2-YEAR 5-MINUTE CANDLE NIFTY OPTIONS BACKTEST (1 LOT = 65 QTY | 492 SESSIONS)")
    print("=" * 110)

    configs = [
        ("1. 5m Candles (SL 30 pts, RR 1:3.0, Max 1 Tr/Day)", 30.0, 3.0, 1),
        ("2. 5m Candles (SL 40 pts, RR 1:3.0, Max 1 Tr/Day)", 40.0, 3.0, 1),
        ("3. 5m Candles (SL 40 pts, RR 1:3.0, Max 2 Tr/Day) ⭐", 40.0, 3.0, 2),
        ("4. 5m Candles (SL 35 pts, RR 1:2.5, Max 2 Tr/Day)", 35.0, 2.5, 2),
    ]

    best_res = None
    for name, sl, rr, max_tr in configs:
        res = sim_5m(sl_val=sl, rr=rr, max_trades=max_tr)
        if res:
            roi = (res["net_pnl"] / 50000.0) * 100.0
            dd_pct = (res["max_dd"] / 50000.0) * 100.0
            trades_per_month = res["trades"] / 24.0
            print(f"{name:52s} | Tr: {res['trades']:3d} ({trades_per_month:4.1f}/mo) | Win: {res['win_rate']:4.1f}% | Net: Rs {res['net_pnl']:+10,.2f} ({roi:+5.1f}%) | PF: {res['pf']:4.2f} | Sharpe: {res['sharpe']:4.2f} | Max DD: Rs {res['max_dd']:7,.0f} ({dd_pct:4.1f}%)")
            if "⭐" in name:
                best_res = res

    # Save 2-year 5m trades
    if best_res:
        out_csv = os.path.join(base_dir, "trades_2year_5min_candles_nifty.csv")
        best_res["df"].to_csv(out_csv, index=False)
        print(f"\nSaved 2-Year 5m trades to: {out_csv}")

        # Yearly breakdown
        df_b = best_res["df"]
        df_b["Year"] = pd.to_datetime(df_b["Date"]).dt.year
        yearly = df_b.groupby("Year").agg(
            Trades=("Net_PnL", "count"),
            Wins=("Net_PnL", lambda x: (x > 0).sum()),
            Win_Rate=("Net_PnL", lambda x: round((x > 0).mean() * 100, 1)),
            Net_PnL=("Net_PnL", lambda x: round(x.sum(), 2))
        ).reset_index()
        print("\nYEARLY BREAKDOWN (2-YEAR 5-MINUTE CANDLES):")
        print(yearly.to_string(index=False))

        # Playbook breakdown
        playbooks = df_b.groupby("Playbook").agg(
            Trades=("Net_PnL", "count"),
            Wins=("Net_PnL", lambda x: (x > 0).sum()),
            Win_Rate=("Net_PnL", lambda x: round((x > 0).mean() * 100, 1)),
            Net_PnL=("Net_PnL", lambda x: round(x.sum(), 2))
        ).reset_index().sort_values("Net_PnL", ascending=False)
        print("\nPLAYBOOK BREAKDOWN (2-YEAR 5-MINUTE CANDLES):")
        print(playbooks.to_string(index=False))

if __name__ == "__main__":
    run_2year_5m_backtest()
