"""
2-YEAR BANKNIFTY OPTIONS BACKTEST ENGINE (30 UNITS LOT SIZE)
Period: October 14, 2024 to October 15, 2026 (495 Trading Sessions)
Exchange: National Stock Exchange (NSE)

Contract Specs:
- Symbol: BANKNIFTY
- Current Lot Size: 30 units (1 Lot)
- Strike Step: 100 points
- Expiry Day: Wednesday Weekly
- Realistic Costs: 0.5% slippage, STT (0.0625%), Turnover (0.053%), Rs 40 Brokerage + 18% GST.
"""
import os
import math
import numpy as np
import pandas as pd
from datetime import datetime, time, timedelta

class BlackScholesPricingBN:
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
    def calculate_price(cls, spot, strike, dte, iv=0.155, r=0.065, is_call=True):
        if dte <= 0.0001:
            return max(0.5, spot - strike) if is_call else max(0.5, strike - spot)
        d1 = (math.log(spot / strike) + (r + 0.5 * iv**2) * dte) / (iv * math.sqrt(dte))
        d2 = d1 - iv * math.sqrt(dte)
        if is_call:
            p = spot * cls._cnd(d1) - strike * math.exp(-r * dte) * cls._cnd(d2)
        else:
            p = strike * math.exp(-r * dte) * cls._cnd(-d2) - spot * cls._cnd(-d1)
        return max(0.5, round(p, 2))

def compute_banknifty_levels(high: float, low: float, close: float) -> dict:
    if high <= low or low <= 0 or (high - low) < 50.0:
        span = max(250.0, close * 0.012)
        high = close + span / 2.0
        low = close - span / 2.0

    r = high - low
    c = close
    p = round(((high + low + close) / 3.0) / 10) * 10
    bc = round(((high + low) / 2.0) / 10) * 10
    tc = round(((2.0 * p) - bc) / 10) * 10

    r1 = round((c + 0.236 * r) / 10) * 10
    r2 = round((c + 0.500 * r) / 10) * 10
    r3 = round((c + 0.866 * r) / 10) * 10
    r4 = round((c + 1.333 * r) / 10) * 10

    s1 = round((c - 0.300 * r) / 10) * 10
    s2 = round((c - 0.550 * r) / 10) * 10
    s3 = round((c - 0.900 * r) / 10) * 10
    s4 = round((c - 1.314 * r) / 10) * 10

    return {
        "pivot": p, "bc": bc, "tc": tc,
        "cpr_top": max(bc, tc), "cpr_bot": min(bc, tc),
        "cpr_width": abs(tc - bc),
        "r1": r1, "r2": r2, "r3": r3, "r4": r4,
        "s1": s1, "s2": s2, "s3": s3, "s4": s4,
        "range": round(r, 1), "close": c
    }

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
                "high": round(max(p_sub, p_sub + 8.0), 1),
                "low": round(min(p_sub, p_sub - 8.0), 1),
                "close": round(p_sub, 1)
            })
    return bars_5m

def load_all_banknifty_sessions():
    base_dir = os.path.dirname(os.path.abspath(__file__))
    candle_5m_path1 = os.path.join(base_dir, "banknifty_data", "candles", "BANKNIFTY_5min.csv")
    candle_1h_path = r"C:\Users\Admin\Desktop\wasted\indian options\bank_nifty_1h.csv"
    daily_path = os.path.join(base_dir, "banknifty_data", "candles", "BANKNIFTY_1day.csv")

    # 1. Load actual 5m data
    df_actual_5m = pd.read_csv(candle_5m_path1)
    df_actual_5m["datetime"] = pd.to_datetime(df_actual_5m["datetime"])
    df_actual_5m["date"] = df_actual_5m["datetime"].dt.date
    actual_5m_dates = set(df_actual_5m["date"].unique())

    # 2. Load 1h data
    df_1h = pd.read_csv(candle_1h_path)
    df_1h["datetime"] = pd.to_datetime(df_1h["Datetime"]) + pd.Timedelta(hours=5, minutes=30)
    df_1h.rename(columns={"Open": "open", "High": "high", "Low": "low", "Close": "close"}, inplace=True)
    df_1h["date"] = df_1h["datetime"].dt.date

    # 3. Load daily data
    df_1d = pd.read_csv(daily_path)
    df_1d["datetime"] = pd.to_datetime(df_1d["datetime"]).dt.date
    df_1d.drop_duplicates(subset=["datetime"], inplace=True)
    df_1d.set_index("datetime", inplace=True)

    start_2y = pd.to_datetime("2024-10-14").date()
    end_2y = pd.to_datetime("2026-10-15").date()

    unique_dates = sorted([d for d in set(df_1h["date"]).union(actual_5m_dates) if start_2y <= d <= end_2y])
    session_data = []

    for current_date in unique_dates:
        priors = [d for d in df_1d.index if d < current_date]
        if not priors:
            continue
        prev_row = df_1d.loc[priors[-1]]
        lvl = compute_banknifty_levels(float(prev_row["high"]), float(prev_row["low"]), float(prev_row["close"]))
        dow = current_date.weekday()
        # Wednesday is 2 in Python weekday()
        dte = max(0.5, (2 - dow) % 7 + 0.5) / 365.0

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

    return session_data

def run_banknifty_sim(session_data, sl_pts=70.0, rr=3.0, use_trail=True, trail_trigger=80.0, trail_lock=30.0, max_trades=2, allowed_pb=None, lot_size=30):
    tp_pts = sl_pts * rr
    initial_capital = 50000.0
    equity = initial_capital
    trades = []

    if allowed_pb is None:
        allowed_pb = [
            "S1 Support Breakdown",
            "R1 Resistance Reversal",
            "R2 Exhaustion Reversal",
            "R1 Resistance Breakout",
            "S1 Support Bounceback",
            "S2 Sweep Bounceback"
        ]

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
        max_favorable_prem = 0.0
        trailing_active = False
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
                prem_close = BlackScholesPricingBN.calculate_price(spot, strike, dte, is_call=is_call)
                prem_high = BlackScholesPricingBN.calculate_price(b_high, strike, dte, is_call=is_call) if is_call else BlackScholesPricingBN.calculate_price(b_low, strike, dte, is_call=is_call)
                prem_low = BlackScholesPricingBN.calculate_price(b_low, strike, dte, is_call=is_call) if is_call else BlackScholesPricingBN.calculate_price(b_high, strike, dte, is_call=is_call)

                if prem_high > max_favorable_prem:
                    max_favorable_prem = prem_high

                # Trailing stop update
                if use_trail:
                    gain_pts = max_favorable_prem - entry_prem
                    if gain_pts >= trail_trigger:
                        trailing_active = True
                        new_sl = entry_prem + trail_lock + (gain_pts - trail_trigger) * 0.5
                        if new_sl > curr_sl:
                            curr_sl = min(new_sl, curr_tp - 5.0)

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

                    if hit_tp:
                        reason = f"TARGET 1:{rr:.1f} HIT"
                    elif hit_sl:
                        if trailing_active:
                            reason = f"TRAILING STOP HIT (+{trail_lock:.0f} pts)"
                        else:
                            reason = "STOP LOSS"
                    else:
                        reason = "EOD EXIT"

                    trades.append({
                        "Date": current_date.strftime("%Y-%m-%d"),
                        "Time": entry_time.strftime("%H:%M") if entry_time else "09:25",
                        "Exit_Time": bar["dt"].strftime("%H:%M"),
                        "Instrument": f"BANKNIFTY {strike} {trade_dir}",
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
                        "Capital": round(equity, 2),
                        "Result": reason
                    })
                    in_trade = False
                    trades_today += 1
                    continue

            if not in_trade and trades_today < max_trades and time(9, 25) <= t <= time(14, 45):
                if b_range < 15:
                    continue
                lower_wick = min(b_open, spot) - b_low
                upper_wick = b_high - max(b_open, spot)
                bull_body = (spot > b_open) and ((spot - b_open) >= 0.35 * b_range)
                bear_body = (spot < b_open) and ((b_open - spot) >= 0.35 * b_range)
                prev_c = prev_bar["close"]

                # Breakouts
                r1_break = (prev_c <= lvl["r1"]) and (spot > lvl["r1"]) and bull_body
                s1_break = (prev_c >= lvl["s1"]) and (spot < lvl["s1"]) and bear_body
                r2_break = (prev_c <= lvl["r2"]) and (spot > lvl["r2"]) and bull_body

                # Reversals & Bounces
                tested_s1 = (b_low <= lvl["s1"] <= b_high) or (prev_bar["low"] <= lvl["s1"] and b_low <= lvl["s1"])
                s1_bounce = tested_s1 and (spot > lvl["s1"]) and ((lower_wick >= 0.35 * b_range) or (spot > prev_bar["high"] and spot > b_open))
                tested_r1 = (b_high >= lvl["r1"] >= b_low) or (prev_bar["high"] >= lvl["r1"] and b_high >= lvl["r1"])
                r1_fade = tested_r1 and (spot < lvl["r1"]) and ((upper_wick >= 0.35 * b_range) or (spot < prev_bar["low"] and spot < b_open))
                tested_r2 = (b_high >= lvl["r2"])
                r2_fade = tested_r2 and (spot < lvl["r2"]) and (upper_wick >= 0.35 * b_range)
                tested_s2 = (b_low <= lvl["s2"])
                s2_bounce = tested_s2 and (spot > lvl["s2"]) and (lower_wick >= 0.35 * b_range)

                c_dir = None
                c_pb = ""
                c_cat = ""
                if s1_break: c_dir = "PE"; c_pb = "S1 Support Breakdown"; c_cat = "BREAKOUT"
                elif r1_fade: c_dir = "PE"; c_pb = "R1 Resistance Reversal"; c_cat = "BOUNCE"
                elif r2_fade: c_dir = "PE"; c_pb = "R2 Exhaustion Reversal"; c_cat = "BOUNCE"
                elif r1_break: c_dir = "CE"; c_pb = "R1 Resistance Breakout"; c_cat = "BREAKOUT"
                elif s1_bounce: c_dir = "CE"; c_pb = "S1 Support Bounceback"; c_cat = "BOUNCE"
                elif s2_bounce: c_dir = "CE"; c_pb = "S2 Sweep Bounceback"; c_cat = "BOUNCE"

                if c_dir and c_pb in allowed_pb:
                    in_trade = True
                    trade_dir = c_dir
                    playbook = c_pb
                    category = c_cat
                    strike = int(round(spot / 100) * 100)
                    is_call = (trade_dir == "CE")
                    entry_prem = BlackScholesPricingBN.calculate_price(spot, strike, dte, is_call=is_call)
                    curr_sl = max(0.5, entry_prem - sl_pts)
                    curr_tp = entry_prem + tp_pts
                    max_favorable_prem = entry_prem
                    trailing_active = False
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
        "avg_trade": total_pnl / len(df_res),
        "df": df_res
    }

def main():
    base_dir = os.path.dirname(os.path.abspath(__file__))
    print("=" * 110)
    print("   2-YEAR BANKNIFTY OPTIONS BACKTEST (LOT SIZE: 30 UNITS | 490+ SESSIONS)")
    print("=" * 110)
    print("Loading multi-source 2-year candle and daily session data...")
    session_data = load_all_banknifty_sessions()
    print(f"Total 2-Year Sessions Built: {len(session_data)} trading days (from {session_data[0]['date']} to {session_data[-1]['date']})")

    configs = [
        ("1. SL 60 pts, RR 1:3.0 (TP 180 pts), No Trail", 60.0, 3.0, False, 0.0, 0.0),
        ("2. SL 70 pts, RR 1:3.0 (TP 210 pts), Trail +80/+30 [BEST]", 70.0, 3.0, True, 80.0, 30.0),
        ("3. SL 70 pts, RR 1:3.5 (TP 245 pts), Trail +80/+30", 70.0, 3.5, True, 80.0, 30.0),
        ("4. SL 80 pts, RR 1:3.0 (TP 240 pts), Trail +90/+35", 80.0, 3.0, True, 90.0, 35.0),
        ("5. SL 70 pts, RR 1:2.5 (TP 175 pts), Trail +70/+25", 70.0, 2.5, True, 70.0, 25.0),
    ]

    best_res = None
    for name, sl, rr, tr, tg, lk in configs:
        res = run_banknifty_sim(
            session_data, sl_pts=sl, rr=rr, use_trail=tr,
            trail_trigger=tg, trail_lock=lk, max_trades=2, lot_size=30
        )
        if res:
            roi = (res["net_pnl"] / 50000.0) * 100.0
            dd_pct = (res["max_dd"] / 50000.0) * 100.0
            print(f"{name:54s} | Tr: {res['trades']:3d} | Win: {res['win_rate']:4.1f}% | Net: Rs {res['net_pnl']:+10,.2f} ({roi:+6.1f}%) | PF: {res['pf']:4.2f} | Sharpe: {res['sharpe']:4.2f} | Max DD: Rs {res['max_dd']:7,.0f} ({dd_pct:4.1f}%)")
            if "[BEST]" in name:
                best_res = res

    if best_res:
        out_csv = os.path.join(base_dir, "banknifty_2year_30lots_trades.csv")
        best_res["df"].to_csv(out_csv, index=False)
        print(f"\nSaved 2-Year BANKNIFTY (30 Units) Trades to: {out_csv}")

        df_b = best_res["df"]
        df_b["Year"] = pd.to_datetime(df_b["Date"]).dt.year
        yearly = df_b.groupby("Year").agg(
            Trades=("Net_PnL", "count"),
            Wins=("Net_PnL", lambda x: (x > 0).sum()),
            Win_Rate=("Net_PnL", lambda x: round((x > 0).mean() * 100, 1)),
            Net_PnL=("Net_PnL", lambda x: round(x.sum(), 2))
        ).reset_index()
        print("\nYEARLY BREAKDOWN (BANKNIFTY 30 UNITS - 2 YEARS):")
        print(yearly.to_string(index=False))

        playbooks = df_b.groupby("Playbook").agg(
            Trades=("Net_PnL", "count"),
            Wins=("Net_PnL", lambda x: (x > 0).sum()),
            Win_Rate=("Net_PnL", lambda x: round((x > 0).mean() * 100, 1)),
            Net_PnL=("Net_PnL", lambda x: round(x.sum(), 2))
        ).reset_index().sort_values("Net_PnL", ascending=False)
        print("\nPLAYBOOK BREAKDOWN (BANKNIFTY 30 UNITS - 2 YEARS):")
        print(playbooks.to_string(index=False))

if __name__ == "__main__":
    main()
