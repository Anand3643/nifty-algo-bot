import os
import pandas as pd
from datetime import time
import numpy as np
from optimize_combined_strategy import NiftySREngine

def run_pure_nifty_2year():
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
        bars = [
            {"dt": r["datetime"], "time": r["datetime"].time(), "open": float(r["open"]), "high": float(r["high"]), "low": float(r["low"]), "close": float(r["close"])}
            for _, r in grp.iterrows()
        ]
        session_data.append({"date": current_date, "lvl": lvl, "day_open": float(grp["open"].iloc[0]), "bars": bars, "dow": dow})

    def sim_pure_nifty(sl_pts=50.0, rr=2.5, lot_size=65, allowed_pb=None, max_trades=1):
        tp_pts = sl_pts * rr
        trades = []
        equity = 100000.0  # Initial capital
        initial_capital = equity

        if allowed_pb is None:
            allowed_pb = ["S2 Flush Breakdown", "R1 Resistance Reversal", "R2 Exhaustion Reversal", "R1 Resistance Breakout", "S1 Support Breakdown"]

        for sess in session_data:
            lvl = sess["lvl"]
            bars = sess["bars"]
            current_date = sess["date"]
            in_trade = False
            trade_dir = None
            entry_spot = 0.0
            curr_sl = 0.0
            curr_tp = 0.0
            playbook = ""
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
                    is_long = (trade_dir == "BUY")
                    hit_tp = (b_high >= curr_tp) if is_long else (b_low <= curr_tp)
                    hit_sl = (b_low <= curr_sl) if is_long else (b_high >= curr_sl)
                    hit_eod = (t >= time(15, 0))

                    if hit_tp or hit_sl or hit_eod:
                        if hit_sl and hit_tp:
                            exit_price = curr_sl
                            reason = "STOP LOSS"
                        elif hit_tp:
                            exit_price = curr_tp
                            reason = f"TARGET 1:{rr:g} HIT"
                        elif hit_sl:
                            exit_price = curr_sl
                            reason = "STOP LOSS"
                        else:
                            exit_price = spot
                            reason = "EOD EXIT"

                        pts = (exit_price - entry_spot) if is_long else (entry_spot - exit_price)
                        pts_after_slip = pts - 1.0  # 1 pt realistic slippage
                        gross = pts_after_slip * lot_size

                        sell_turnover = (exit_price if is_long else entry_spot) * lot_size
                        buy_turnover = (entry_spot if is_long else exit_price) * lot_size
                        stt = sell_turnover * 0.0002
                        turnover_fees = (buy_turnover + sell_turnover) * 0.000019
                        brokerage = 40.0
                        gst = (brokerage + turnover_fees) * 0.18
                        costs = brokerage + stt + turnover_fees + gst
                        net = gross - costs
                        equity += net

                        trades.append({
                            "Date": current_date.strftime("%Y-%m-%d"),
                            "Time": entry_time.strftime("%H:%M") if entry_time else "09:15",
                            "Exit_Time": bar["dt"].strftime("%H:%M"),
                            "Instrument": "NIFTY 50",
                            "Playbook": playbook,
                            "Dir": trade_dir,
                            "Entry": round(entry_spot, 1),
                            "Exit": round(exit_price, 1),
                            "Pts": round(pts_after_slip, 1),
                            "Gross_PnL": round(gross, 2),
                            "Costs": round(costs, 2),
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
                    if s1_break: c_dir = "SELL"; c_pb = "S1 Support Breakdown"
                    elif r1_break: c_dir = "BUY"; c_pb = "R1 Resistance Breakout"
                    elif s1_bounce: c_dir = "BUY"; c_pb = "S1 Support Bounceback"
                    elif r1_fade: c_dir = "SELL"; c_pb = "R1 Resistance Reversal"
                    elif s2_break: c_dir = "SELL"; c_pb = "S2 Flush Breakdown"
                    elif r2_break: c_dir = "BUY"; c_pb = "R2 Expansion Breakout"
                    elif s2_bounce: c_dir = "BUY"; c_pb = "S2 Sweep Bounceback"
                    elif r2_fade: c_dir = "SELL"; c_pb = "R2 Exhaustion Reversal"

                    if c_dir and c_pb in allowed_pb:
                        in_trade = True
                        trade_dir = c_dir
                        playbook = c_pb
                        entry_spot = spot
                        curr_sl = entry_spot - sl_pts if trade_dir == "BUY" else entry_spot + sl_pts
                        curr_tp = entry_spot + tp_pts if trade_dir == "BUY" else entry_spot - tp_pts
                        entry_time = bar["dt"]
                        continue

        df_t = pd.DataFrame(trades)
        if len(df_t) == 0:
            return None
        wins = (df_t["Net_PnL"] > 0).sum()
        win_rate = wins / len(df_t) * 100.0
        total_net = df_t["Net_PnL"].sum()
        peak = df_t["Capital"].cummax()
        max_dd = abs((df_t["Capital"] - peak).min())
        gross_win = df_t[df_t["Net_PnL"] > 0]["Net_PnL"].sum()
        gross_loss = abs(df_t[df_t["Net_PnL"] <= 0]["Net_PnL"].sum())
        pf = (gross_win / gross_loss) if gross_loss > 0 else 99.0
        daily = df_t.groupby("Date")["Net_PnL"].sum()
        sharpe = (daily.mean() / daily.std()) * np.sqrt(252) if daily.std() > 0 else 0.0
        return {
            "trades": len(df_t),
            "wins": wins,
            "win_rate": win_rate,
            "net_pnl": total_net,
            "pf": pf,
            "sharpe": sharpe,
            "max_dd": max_dd,
            "df": df_t
        }

    print("=" * 105)
    print("   2-YEAR PURE NIFTY (FUTURES / SPOT POINTS) BACKTEST (1 LOT = 65 QTY | 492 SESSIONS)")
    print("=" * 105)
    
    top4 = ["S1 Support Breakdown", "R1 Resistance Reversal", "R2 Exhaustion Reversal", "R1 Resistance Breakout"]
    top5 = ["S2 Flush Breakdown", "R1 Resistance Reversal", "R2 Exhaustion Reversal", "R1 Resistance Breakout", "S1 Support Breakdown"]

    configs = [
        ("1. Pure NIFTY Top 5 (SL 40 pts, RR 1:2.0)", 40.0, 2.0, top5, 1),
        ("2. Pure NIFTY Top 5 (SL 50 pts, RR 1:2.0)", 50.0, 2.0, top5, 1),
        ("3. Pure NIFTY Top 5 (SL 50 pts, RR 1:2.5) ⭐", 50.0, 2.5, top5, 1),
        ("4. Pure NIFTY Top 5 (SL 50 pts, RR 1:3.0)", 50.0, 3.0, top5, 1),
        ("5. Pure NIFTY Top 5 (SL 60 pts, RR 1:2.5)", 60.0, 2.5, top5, 1),
        ("6. Pure NIFTY Top 4 (SL 50 pts, RR 1:2.5)", 50.0, 2.5, top4, 1),
        ("7. Pure NIFTY Top 5 (SL 50 pts, RR 1:2.5, 2 Tr/Day)", 50.0, 2.5, top5, 2),
    ]

    best_res = None
    for name, sl, rr, pb, max_tr in configs:
        res = sim_pure_nifty(sl_pts=sl, rr=rr, allowed_pb=pb, max_trades=max_tr)
        if res:
            roi = (res["net_pnl"] / 100000.0) * 100.0
            print(f"{name:50s} | Tr: {res['trades']:3d} | Win: {res['win_rate']:4.1f}% | Net: Rs {res['net_pnl']:+10,.2f} ({roi:+5.1f}%) | PF: {res['pf']:4.2f} | Sharpe: {res['sharpe']:4.2f} | Max DD: Rs {res['max_dd']:7,.0f}")
            if "⭐" in name:
                best_res = res

    # Save best pure NIFTY trades
    if best_res:
        csv_file = os.path.join(base_dir, "trades_2year_pure_nifty.csv")
        best_res["df"].to_csv(csv_file, index=False)
        print(f"\nSaved Best Pure NIFTY trades to: {csv_file}")
        
        # Yearly breakdown for Best Pure NIFTY
        df_b = best_res["df"]
        df_b["Year"] = pd.to_datetime(df_b["Date"]).dt.year
        yearly = df_b.groupby("Year").agg(
            Trades=("Net_PnL", "count"),
            Wins=("Net_PnL", lambda x: (x > 0).sum()),
            Win_Rate=("Net_PnL", lambda x: round((x > 0).mean() * 100, 1)),
            Net_PnL=("Net_PnL", lambda x: round(x.sum(), 2))
        ).reset_index()
        print("\nYEARLY BREAKDOWN (PURE NIFTY):")
        print(yearly.to_string(index=False))

if __name__ == "__main__":
    run_pure_nifty_2year()
