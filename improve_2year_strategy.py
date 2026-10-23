import os
import pandas as pd
from datetime import time
import numpy as np
from optimize_combined_strategy import NiftySREngine, BlackScholesPricing

def run_experiments():
    base_dir = os.path.dirname(os.path.abspath(__file__))
    candle_path = os.path.join(base_dir, "nifty_data", "candles", "NIFTY_1hour.csv")
    daily_path = os.path.join(base_dir, "nifty_data", "candles", "NIFTY_1day.csv")

    df_intra = pd.read_csv(candle_path)
    df_intra["datetime"] = pd.to_datetime(df_intra["datetime"])
    df_intra.sort_values("datetime", inplace=True)
    df_1d = pd.read_csv(daily_path)
    df_1d["datetime"] = pd.to_datetime(df_1d["datetime"]).dt.date
    df_1d.drop_duplicates(subset=["datetime"], inplace=True)
    df_1d.set_index("datetime", inplace=True)
    df_intra["date"] = df_intra["datetime"].dt.date

    start_2y = pd.to_datetime("2024-10-12").date()
    session_data = []

    for current_date, grp in df_intra.groupby("date"):
        if current_date < start_2y:
            continue
        if len(grp) < 4:
            continue
        priors = [d for d in df_1d.index if d < current_date]
        if not priors:
            continue
        prev_row = df_1d.loc[priors[-1]]
        lvl = NiftySREngine.calculate_levels(float(prev_row["high"]), float(prev_row["low"]), float(prev_row["close"]))
        dow = current_date.weekday()
        dte = max(0.5, (3 - dow) % 7 + 0.5) / 365.0
        bars = [
            {"dt": r["datetime"], "time": r["datetime"].time(), "open": float(r["open"]), "high": float(r["high"]), "low": float(r["low"]), "close": float(r["close"])}
            for _, r in grp.iterrows()
        ]
        session_data.append({"date": current_date, "lvl": lvl, "dte": dte, "day_open": float(grp["open"].iloc[0]), "bars": bars, "dow": dow})

    def run_sim(skip_wed=False, allowed_pb=None, sl_val=40.0, rr=3.0, trail=False, max_trades=1, trend_filter=False):
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
            dow = sess["dow"]
            day_open = sess["day_open"]

            if skip_wed and dow == 2:  # Wednesday is dow 2
                continue

            in_trade = False
            trade_dir = None
            strike = 0
            entry_prem = 0.0
            curr_sl = 0.0
            curr_tp = 0.0
            playbook = ""
            trades_today = 0
            max_fav = 0.0

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
                    max_fav = max(max_fav, prem_high)

                    if trail:
                        if max_fav >= entry_prem + 1.0 * sl_val:
                            curr_sl = max(curr_sl, entry_prem + 4.0)
                        if max_fav >= entry_prem + 2.0 * sl_val:
                            curr_sl = max(curr_sl, entry_prem + sl_val)

                    hit_tp = (prem_high >= curr_tp)
                    hit_sl = (prem_low <= curr_sl)
                    hit_eod = (t >= time(15, 0))

                    if hit_tp or hit_sl or hit_eod:
                        if hit_sl and hit_tp:
                            exit_raw = curr_sl
                            reason = "STOP LOSS"
                        elif hit_tp:
                            exit_raw = curr_tp
                            reason = f"TARGET 1:{rr:g} HIT"
                        elif hit_sl:
                            exit_raw = curr_sl
                            reason = "TRAILING SL" if curr_sl > entry_prem - sl_val else "STOP LOSS"
                        else:
                            exit_raw = prem_close
                            reason = "EOD EXIT"

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

                        trades.append({
                            "Date": current_date.strftime("%Y-%m-%d"),
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

                if not in_trade and trades_today < max_trades and t < time(14, 0):
                    if b_range < 15:
                        continue
                    lower_wick = min(b_open, spot) - b_low
                    upper_wick = b_high - max(b_open, spot)
                    bull_body = (spot > b_open) and ((spot - b_open) >= 0.30 * b_range)
                    bear_body = (spot < b_open) and ((b_open - spot) >= 0.30 * b_range)
                    prev_c = prev_bar["close"]

                    r1_break = (prev_c <= lvl["r1"]) and (spot > lvl["r1"]) and bull_body
                    s1_break = (prev_c >= lvl["s1"]) and (spot < lvl["s1"]) and bear_body
                    r2_break = (prev_c <= lvl["r2"]) and (spot > lvl["r2"]) and bull_body
                    s2_break = (prev_c >= lvl["s2"]) and (spot < lvl["s2"]) and bear_body

                    tested_s1 = (b_low <= lvl["s1"] <= b_high)
                    s1_bounce = tested_s1 and (spot > lvl["s1"]) and (lower_wick >= 0.30 * b_range)
                    tested_r1 = (b_high >= lvl["r1"] >= b_low)
                    r1_fade = tested_r1 and (spot < lvl["r1"]) and (upper_wick >= 0.30 * b_range)
                    tested_s2 = (b_low <= lvl["s2"])
                    s2_bounce = tested_s2 and (spot > lvl["s2"]) and (lower_wick >= 0.30 * b_range)
                    tested_r2 = (b_high >= lvl["r2"])
                    r2_fade = tested_r2 and (spot < lvl["r2"]) and (upper_wick >= 0.30 * b_range)

                    c_dir = None
                    c_pb = ""
                    if s1_break: c_dir = "PE"; c_pb = "S1 Support Breakdown"
                    elif r1_break: c_dir = "CE"; c_pb = "R1 Resistance Breakout"
                    elif s1_bounce: c_dir = "CE"; c_pb = "S1 Support Bounceback"
                    elif r1_fade: c_dir = "PE"; c_pb = "R1 Resistance Reversal"
                    elif s2_break: c_dir = "PE"; c_pb = "S2 Flush Breakdown"
                    elif r2_break: c_dir = "CE"; c_pb = "R2 Expansion Breakout"
                    elif s2_bounce: c_dir = "CE"; c_pb = "S2 Sweep Bounceback"
                    elif r2_fade: c_dir = "PE"; c_pb = "R2 Exhaustion Reversal"

                    if trend_filter and c_dir:
                        if c_dir == "CE" and day_open < lvl["pivot"]:
                            continue
                        if c_dir == "PE" and day_open > lvl["pivot"]:
                            continue

                    if c_dir and c_pb in allowed_pb:
                        in_trade = True
                        trade_dir = c_dir
                        playbook = c_pb
                        strike = int(round(spot / 50) * 50)
                        is_call = (trade_dir == "CE")
                        entry_prem = BlackScholesPricing.calculate_price(spot, strike, dte, 0.135, is_call=is_call)
                        curr_sl = max(0.5, entry_prem - sl_val)
                        curr_tp = entry_prem + tp_val
                        max_fav = entry_prem
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

    e1 = run_sim()  # Benchmark
    e2 = run_sim(skip_wed=True)  # Skip Wednesday
    top4 = ["S1 Support Breakdown", "R1 Resistance Reversal", "R2 Exhaustion Reversal", "R1 Resistance Breakout"]
    e3 = run_sim(skip_wed=True, allowed_pb=top4)  # Skip Wed + Drop S2 Flush
    e4 = run_sim(skip_wed=True, allowed_pb=top4, rr=3.5)  # 1:3.5 RR
    e5 = run_sim(skip_wed=True, allowed_pb=top4, rr=4.0)  # 1:4.0 RR
    e6 = run_sim(skip_wed=True, allowed_pb=top4, trail=True)  # Trailing SL
    e7 = run_sim(skip_wed=True, allowed_pb=top4, rr=3.5, max_trades=2)  # Multi-Wave 2 Tr/Day + 1:3.5 RR

    models = [
        ("1. 2-Year Benchmark (Top 5, SL 40, RR 3.0)", e1),
        ("2. Filter Wednesday Expiry Decay (Skip Wed)", e2),
        ("3. Filter Wed + Focus Top 4 Playbooks", e3),
        ("4. Filter Wed + Top 4 + Extended 1:3.5 RR", e4),
        ("5. Filter Wed + Top 4 + Extended 1:4.0 RR", e5),
        ("6. Filter Wed + Top 4 + Trailing SL to BE", e6),
        ("7. Supreme Engine: Wed Filter + 1:3.5 RR (2 Tr/Day) ⭐", e7),
    ]

    print("=" * 110)
    print("   2-YEAR STRATEGY OPTIMIZATION RESULTS (OCT 2024 - OCT 2026 | 492 SESSIONS)")
    print("=" * 110)
    for name, r in models:
        roi = (r["net_pnl"] / 50000.0) * 100.0
        dd_pct = (r["max_dd"] / 50000.0) * 100.0
        print(f"{name:55s} | Tr: {r['trades']:3d} | Win: {r['win_rate']:4.1f}% | Net: Rs {r['net_pnl']:+10,.2f} ({roi:+5.1f}%) | PF: {r['pf']:4.2f} | Sharpe: {r['sharpe']:4.2f} | Max DD: Rs {r['max_dd']:7,.0f} ({dd_pct:4.1f}%)")

    # Save Supreme Engine trades
    e7["df"].to_csv(os.path.join(base_dir, "trades_2year_supreme_engine.csv"), index=False)
    print(f"\nSaved Supreme Engine trades to trades_2year_supreme_engine.csv")

if __name__ == "__main__":
    run_experiments()
