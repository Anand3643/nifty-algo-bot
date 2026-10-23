"""
BANKNIFTY Comprehensive Options Backtest Engine
Applies Our Multi-Playbook Strategy (CPR + S&R Exhaustions + Breakouts) to BANKNIFTY
Across 7,678 5-Minute Candles (May 20, 2026 to October 15, 2026)

Contract Specifications:
- Instrument: BANKNIFTY ATM Options (1 Lot = 15 Qty)
- Strike Step: 100 points
- Weekly Expiry: Wednesday
- Starting Capital: Rs 50,000.00
- Realistic Cost Model: 0.5% slippage, STT (0.0625%), Turnover (0.053%), Rs 40 Brokerage + 18% GST.
"""
import os
import math
import numpy as np
import pandas as pd
from datetime import datetime, time

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

def load_banknifty_data():
    base_dir = os.path.dirname(os.path.abspath(__file__))
    candle_5m_path = os.path.join(base_dir, "banknifty_data", "candles", "BANKNIFTY_5min.csv")
    daily_path = os.path.join(base_dir, "banknifty_data", "candles", "BANKNIFTY_1day.csv")

    if not os.path.exists(candle_5m_path) or not os.path.exists(daily_path):
        from prepare_banknifty_data import prepare_banknifty_data
        prepare_banknifty_data()

    df_5m = pd.read_csv(candle_5m_path)
    df_d = pd.read_csv(daily_path)

    df_5m["datetime"] = pd.to_datetime(df_5m["datetime"])
    df_5m["date"] = df_5m["datetime"].dt.strftime("%Y-%m-%d")
    df_5m["time"] = df_5m["datetime"].dt.time
    df_5m.sort_values("datetime", inplace=True)

    df_d["date"] = pd.to_datetime(df_d["datetime"]).dt.strftime("%Y-%m-%d")
    df_d.set_index("date", inplace=True)

    return df_5m, df_d

def run_banknifty_backtest(
    sl_pts=70.0,
    rr=3.0,
    use_trail=True,
    trail_trigger=80.0,
    trail_lock=30.0,
    max_trades_per_day=2,
    date_filter_start="2026-07-03",
    date_filter_end="2026-10-15",
    level_source="OUR_STRATEGY" # "OUR_STRATEGY" or "ARJUN_TELEGRAM"
):
    df_5m, df_d = load_banknifty_data()
    tp_pts = sl_pts * rr
    lot_size = 15 # BankNifty lot size
    initial_capital = 50000.0
    capital = initial_capital
    all_trades = []

    # If testing Arjun's levels, load telegram_levels_banknifty.csv
    arjun_levels = {}
    if level_source == "ARJUN_TELEGRAM":
        arj_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), "telegram_levels_banknifty.csv")
        if os.path.exists(arj_file):
            df_arj = pd.read_csv(arj_file)
            for _, r in df_arj.iterrows():
                arjun_levels[r["date"]] = {
                    "s1": float(r["s1"]) if pd.notna(r["s1"]) else None,
                    "s2": float(r["s2"]) if pd.notna(r["s2"]) else None,
                    "r1": float(r["r1"]) if pd.notna(r["r1"]) else None,
                    "r2": float(r["r2"]) if pd.notna(r["r2"]) else None,
                    "pivot": float(r["pivot"]) if pd.notna(r["pivot"]) else None,
                }

    unique_dates = sorted(df_5m["date"].unique())
    filtered_dates = [d for d in unique_dates if date_filter_start <= d <= date_filter_end]

    for d in filtered_dates:
        # Determine levels
        if level_source == "OUR_STRATEGY":
            priors = [x for x in df_d.index if x < d]
            if not priors:
                continue
            prev_row = df_d.loc[priors[-1]]
            lvl = compute_banknifty_levels(float(prev_row["high"]), float(prev_row["low"]), float(prev_row["close"]))
            s1, s2, r1, r2 = lvl["s1"], lvl["s2"], lvl["r1"], lvl["r2"]
        else:
            if d not in arjun_levels:
                continue
            lvl = arjun_levels[d]
            s1, s2, r1, r2 = lvl["s1"], lvl["s2"], lvl["r1"], lvl["r2"]
            if not s1 or not r1:
                continue

        day_bars = df_5m[df_5m["date"] == d].copy().reset_index(drop=True)
        if len(day_bars) < 10:
            continue

        dt_obj = datetime.strptime(d, "%Y-%m-%d")
        dow = dt_obj.weekday()
        # Wednesday expiry for BankNifty (weekday 2)
        dte = max(0.5, (2 - dow) % 7 + 0.5) / 365.0

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

            # Check open trade exit
            if in_trade:
                is_call = (trade_dir == "CE")
                prem_close = BlackScholesPricingBN.calculate_price(spot, strike, dte, 0.155, is_call=is_call)
                prem_high = BlackScholesPricingBN.calculate_price(b_high, strike, dte, 0.155, is_call=is_call) if is_call else BlackScholesPricingBN.calculate_price(b_low, strike, dte, 0.155, is_call=is_call)
                prem_low = BlackScholesPricingBN.calculate_price(b_low, strike, dte, 0.155, is_call=is_call) if is_call else BlackScholesPricingBN.calculate_price(b_high, strike, dte, 0.155, is_call=is_call)

                if prem_high > max_fav:
                    max_fav = prem_high

                # Trailing stop
                if use_trail:
                    if not trailed and (max_fav - entry_prem) >= trail_trigger:
                        curr_sl = entry_prem + trail_lock
                        trailed = True
                    elif trailed and (max_fav - entry_prem) >= (trail_trigger + 40.0):
                        # Dynamic 25 pt trail behind high
                        dyn_sl = max_fav - 25.0
                        if dyn_sl > curr_sl:
                            curr_sl = dyn_sl

                hit_tp = (prem_high >= curr_tp)
                hit_sl = (prem_low <= curr_sl)
                hit_eod = (t >= time(15, 10))

                if hit_tp or hit_sl or hit_eod:
                    exit_raw = curr_tp if hit_tp else (curr_sl if hit_sl else prem_close)
                    fill_entry = entry_prem * 1.005 # 0.5% fill slippage
                    fill_exit = max(0.5, exit_raw * 0.995)
                    pts = fill_exit - fill_entry
                    gross = pts * lot_size
                    # Realistic Indian Options Cost Structure
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
                        reason = f"TRAILING STOP HIT (+{round(curr_sl - entry_prem, 1)} pts)"
                    elif hit_sl:
                        reason = "STOP LOSS"
                    else:
                        reason = "EOD 15:10 EXIT"

                    all_trades.append({
                        "Date": d,
                        "Time": entry_time.strftime("%H:%M") if hasattr(entry_time, "strftime") else str(entry_time),
                        "Exit_Time": t.strftime("%H:%M") if hasattr(t, "strftime") else str(t),
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
                        "Capital": round(capital, 2),
                        "Result": reason
                    })
                    in_trade = False
                    trades_today += 1
                    continue

            # Look for trade entry
            if not in_trade and trades_today < max_trades_per_day and time(9, 25) <= t <= time(14, 0):
                if b_range < 15: # BankNifty candle range threshold
                    continue
                lower_wick = min(b_open, spot) - b_low
                upper_wick = b_high - max(b_open, spot)
                bull_body = (spot > b_open) and ((spot - b_open) >= 0.35 * b_range)
                bear_body = (spot < b_open) and ((b_open - spot) >= 0.35 * b_range)
                prev_c = float(prev_bar["close"])

                c_dir = None
                c_pb = ""
                c_cat = ""

                # 1. R1 Resistance Reversal (Fade)
                tested_r1 = (b_high >= r1 >= b_low) or (b_high >= r1 * 0.999 and spot <= r1)
                if tested_r1 and spot < r1 and (upper_wick >= 0.30 * b_range or bear_body):
                    c_dir = "PE"; c_pb = "R1 Resistance Reversal"; c_cat = "BOUNCE"

                # 2. R2 Exhaustion Reversal (Fade)
                elif r2 and (b_high >= r2 >= b_low or b_high >= r2 * 0.999) and spot < r2 and (upper_wick >= 0.30 * b_range or bear_body):
                    c_dir = "PE"; c_pb = "R2 Exhaustion Reversal"; c_cat = "BOUNCE"

                # 3. R1 Breakout Long
                elif prev_c <= r1 and spot > r1 and bull_body:
                    c_dir = "CE"; c_pb = "R1 Resistance Breakout"; c_cat = "BREAKOUT"

                # 4. S1 Breakdown Short
                elif prev_c >= s1 and spot < s1 and bear_body:
                    c_dir = "PE"; c_pb = "S1 Support Breakdown"; c_cat = "BREAKOUT"

                # 5. S2 Flush Breakdown
                elif s2 and prev_c >= s2 and spot < s2 and bear_body:
                    c_dir = "PE"; c_pb = "S2 Flush Breakdown"; c_cat = "BREAKOUT"

                if c_dir:
                    in_trade = True
                    trade_dir = c_dir
                    playbook = c_pb
                    category = c_cat
                    strike = int(round(spot / 100) * 100) # BankNifty strike step 100
                    is_call = (trade_dir == "CE")
                    entry_prem = BlackScholesPricingBN.calculate_price(spot, strike, dte, 0.155, is_call=is_call)
                    curr_sl = max(1.0, entry_prem - sl_pts)
                    curr_tp = entry_prem + tp_pts
                    max_fav = entry_prem
                    trailed = False
                    entry_time = t
                    continue

    df_res = pd.DataFrame(all_trades)
    return df_res

def evaluate_metrics(df_res, label="BANKNIFTY Setup"):
    if df_res is None or len(df_res) == 0:
        return {"Mode": label, "Trades": 0, "Win_Rate": "0%", "Net_PnL": 0.0, "PF": 0.0, "Max_DD": 0.0, "Avg_Trade": 0.0}

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
    print("\n" + "="*85)
    print("BACKTESTING BANKNIFTY OPTIONS USING OUR INSTITUTIONAL STRATEGY")
    print("Period: 03-Jul-2026 to 15-Oct-2026 (Same Date Window) | 1 Lot = 15 Qty | Rs 50k Capital")
    print("="*85)

    tests = [
        # SL, RR, Trail, Trig, Lock, MaxT, Level Source
        ("Our Strategy (SL 70 pts | 1:3 RR | Trailing)", 70.0, 3.0, True, 80.0, 30.0, 2, "OUR_STRATEGY"),
        ("Our Strategy (SL 60 pts | 1:3 RR | Trailing)", 60.0, 3.0, True, 70.0, 25.0, 2, "OUR_STRATEGY"),
        ("Our Strategy (SL 80 pts | 1:3 RR | Trailing)", 80.0, 3.0, True, 90.0, 35.0, 2, "OUR_STRATEGY"),
        ("Our Strategy (SL 70 pts | 1:3.5 RR | Trailing)", 70.0, 3.5, True, 80.0, 30.0, 2, "OUR_STRATEGY"),
        ("Our Strategy (SL 70 pts | 1:3 RR | 1 Trade/Day)", 70.0, 3.0, True, 80.0, 30.0, 1, "OUR_STRATEGY"),
        ("Arjun Telegram Levels on BANKNIFTY (Same Rules)", 70.0, 3.0, True, 80.0, 30.0, 2, "ARJUN_TELEGRAM"),
    ]

    results = []
    best_df = None
    best_pnl = -999999
    best_lbl = ""

    for lbl, sl, rr, tr, trig, lock, max_t, src in tests:
        df = run_banknifty_backtest(
            sl_pts=sl,
            rr=rr,
            use_trail=tr,
            trail_trigger=trig,
            trail_lock=lock,
            max_trades_per_day=max_t,
            date_filter_start="2026-07-03",
            date_filter_end="2026-10-15",
            level_source=src
        )
        met = evaluate_metrics(df, label=lbl)
        results.append(met)
        print(f"[{lbl:<50}] Trades: {met['Trades']:>2} | WR: {met['Win_Rate']:>6} | Net PnL: Rs {met['Net_PnL']:>10,} | PF: {met['PF']:>4} | MaxDD: Rs {met['Max_DD']:>8,}")
        
        if met["Net_PnL"] > best_pnl and src == "OUR_STRATEGY":
            best_pnl = met["Net_PnL"]
            best_df = df
            best_lbl = lbl

    summary_df = pd.DataFrame(results)
    summary_df.to_csv("banknifty_backtest_summary.csv", index=False)
    print("\n======================= BANKNIFTY SUMMARY COMPARISON =======================")
    print(summary_df.to_string(index=False))

    if best_df is not None:
        best_df.to_csv("banknifty_best_trades.csv", index=False)
        print(f"\nSaved Champion Setup ({best_lbl}) Trades to banknifty_best_trades.csv")
