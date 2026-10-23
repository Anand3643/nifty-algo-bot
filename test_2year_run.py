import os
import pandas as pd
from datetime import time
import numpy as np
from optimize_combined_strategy import NiftySREngine, BlackScholesPricing

def run_2y_test():
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
        session_data.append({"date": current_date, "lvl": lvl, "dte": dte, "day_open": float(grp["open"].iloc[0]), "bars": bars})

    print(f"Total 2-Year Sessions: {len(session_data)} (from {session_data[0]['date']} to {session_data[-1]['date']})")

    def simulate(sl_val=40.0, rr=3.0, top_only=True, max_trades=1):
        tp_val = sl_val * rr
        lot_size = 65
        initial_capital = 50000.0
        equity = initial_capital
        trades = []
        top_playbooks = ["S2 Flush Breakdown", "R1 Resistance Reversal", "R2 Exhaustion Reversal", "R1 Resistance Breakout", "S1 Support Breakdown"]

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
            trades_today = 0

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
                            reason = "STOP LOSS"
                        else:
                            exit_raw = prem_close
                            reason = "EOD EXIT"

                        fill_entry = entry_prem * 1.005
                        fill_exit = max(0.5, exit_raw * 0.995)
                        pts = fill_exit - fill_entry
                        gross = pts * lot_size
                        # Costs: Brokerage 40, STT, Exchange, GST
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

                    if c_dir:
                        if top_only and c_pb not in top_playbooks:
                            continue
                        in_trade = True
                        trade_dir = c_dir
                        playbook = c_pb
                        strike = int(round(spot / 50) * 50)
                        is_call = (trade_dir == "CE")
                        entry_prem = BlackScholesPricing.calculate_price(spot, strike, dte, 0.135, is_call=is_call)
                        curr_sl = max(0.5, entry_prem - sl_val)
                        curr_tp = entry_prem + tp_val
                        continue

        df_res = pd.DataFrame(trades)
        if len(df_res) == 0:
            return None
        wins = (df_res["Net_PnL"] > 0).sum()
        total_pnl = df_res["Net_PnL"].sum()
        win_rate = (wins / len(df_res)) * 100.0
        peak = df_res["Capital"].cummax()
        max_dd = abs((df_res["Capital"] - peak).min())
        target_hits = (df_res["Result"].str.contains("TARGET")).sum()
        sl_hits = (df_res["Result"].str.contains("STOP LOSS")).sum()

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
            "roi": (total_pnl / 50000.0) * 100.0,
            "max_dd": max_dd,
            "max_dd_pct": (max_dd / 50000.0) * 100.0,
            "target_hits": target_hits,
            "sl_hits": sl_hits,
            "profit_factor": pf,
            "sharpe": sharpe,
            "df": df_res
        }

    # Test baseline vs top playbooks vs various RR over the 2-year period
    print("\n" + "=" * 90)
    print("   2-YEAR NIFTY OPTIONS BACKTEST (OCT 2024 - OCT 2026 | 492 TRADING SESSIONS)")
    print("=" * 90)

    configs = [
        ("1. Baseline (All Playbooks, SL 30, RR 3)", 30.0, 3.0, False, 1),
        ("2. Baseline (All Playbooks, SL 40, RR 3)", 40.0, 3.0, False, 1),
        ("3. Top 5 Playbooks (SL 30, RR 3)", 30.0, 3.0, True, 1),
        ("4. Top 5 Playbooks (SL 40, RR 3) ⭐", 40.0, 3.0, True, 1),
        ("5. Top 5 Playbooks (SL 40, RR 3, 2 Tr/Day)", 40.0, 3.0, True, 2),
        ("6. Top 5 Playbooks (SL 35, RR 2.5)", 35.0, 2.5, True, 1),
    ]

    for name, sl, rr, top_only, max_tr in configs:
        res = simulate(sl_val=sl, rr=rr, top_only=top_only, max_trades=max_tr)
        if res:
            print(f"{name:45s} | Tr: {res['trades']:3d} | Win: {res['win_rate']:4.1f}% | Net: Rs {res['net_pnl']:+10,.2f} ({res['roi']:+6.1f}%) | PF: {res['profit_factor']:.2f} | Sharpe: {res['sharpe']:.2f} | Max DD: Rs {res['max_dd']:7,.0f} ({res['max_dd_pct']:.1f}%)")

if __name__ == "__main__":
    run_2y_test()
