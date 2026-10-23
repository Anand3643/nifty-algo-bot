import os
import sys
import math
import calendar
import datetime
from datetime import time, timedelta
import pandas as pd
import numpy as np

base_dir = r"c:\Users\Admin\Desktop\nifty backttteest"
sys.path.insert(0, base_dir)

from optimize_combined_strategy import NiftySREngine, BlackScholesPricing

# 1. Load Data
c5m = os.path.join(base_dir, 'nifty_data', 'candles', 'NIFTY_5min.csv')
c1h = os.path.join(base_dir, 'nifty_data', 'candles', 'NIFTY_1hour.csv')
c1d = os.path.join(base_dir, 'nifty_data', 'candles', 'NIFTY_1day.csv')

df_5m = pd.read_csv(c5m)
df_5m['datetime'] = pd.to_datetime(df_5m['datetime'])
df_5m.sort_values('datetime', inplace=True)
df_5m.drop_duplicates(subset=['datetime'], inplace=True)
df_5m['date'] = df_5m['datetime'].dt.date
actual_5m_dates = set(df_5m['date'].unique())

df_1h = pd.read_csv(c1h)
df_1h['datetime'] = pd.to_datetime(df_1h['datetime'])
df_1h.sort_values('datetime', inplace=True)
df_1h['date'] = df_1h['datetime'].dt.date

df_1d = pd.read_csv(c1d)
df_1d['datetime'] = pd.to_datetime(df_1d['datetime']).dt.date
df_1d.drop_duplicates(subset=['datetime'], inplace=True)
df_1d.set_index('datetime', inplace=True)

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
            bars_5m.append({
                "dt": sub_dt, "time": sub_dt.time(),
                "open": round(p_sub, 1), "high": round(max(p_sub, p_sub + 3.0), 1),
                "low": round(min(p_sub, p_sub - 3.0), 1), "close": round(p_sub, 1)
            })
    return bars_5m

# Build 3-year session data
start_3y = datetime.date(2023, 10, 31)
end_3y = datetime.date(2026, 10, 21)

all_dates = sorted([d for d in set(df_1h['date']).union(actual_5m_dates) if start_3y <= d <= end_3y])
session_data = []

print(f"Building 3-Year Sessions from {start_3y} to {end_3y}...")
for current_date in all_dates:
    priors = [d for d in df_1d.index if d < current_date]
    if not priors: continue
    prev_row = df_1d.loc[priors[-1]]
    lvl = NiftySREngine.calculate_levels(float(prev_row["high"]), float(prev_row["low"]), float(prev_row["close"]))
    dow = current_date.weekday()
    dte = max(0.25, (3 - dow) % 7 + 0.5) / 365.0

    if current_date in actual_5m_dates:
        grp = df_5m[df_5m["date"] == current_date]
        if len(grp) < 3: continue
        bars = [
            {"dt": r["datetime"], "time": r["datetime"].time(), "open": float(r["open"]), "high": float(r["high"]), "low": float(r["low"]), "close": float(r["close"])}
            for _, r in grp.iterrows()
        ]
    else:
        grp = df_1h[df_1h["date"] == current_date]
        if len(grp) < 4: continue
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

print(f"Total 3-Year Sessions Built: {len(session_data)} trading days.")

# Simulation Engine with toggleable stop_on_loss
def run_3year_backtest(sl_pts=50.0, tp_pts=200.0, be_trigger=80.0, be_buf=4.0, trail_pts=15.0,
                       stop_on_loss=True, max_trades_per_day=2, cutoff_time=time(14, 0), eod_time=time(15, 0)):
    lot_size = 65
    initial_capital = 50000.0
    capital = initial_capital
    trades = []
    daily_stats = {}

    for sess in session_data:
        lvl = sess["lvl"]
        bars = sess["bars"]
        current_date = sess["date"]
        d_str = str(current_date)
        dte = sess["dte"]
        day_open = sess["day_open"]
        orb_high = max(b["high"] for b in bars[:3])
        orb_low = min(b["low"] for b in bars[:3])

        trades_today = 0
        in_trade = False
        pos = None
        has_lost_today = False

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
                is_call = (pos["type"] == "CE")
                strike = pos["strike"]
                prem_close = BlackScholesPricing.calculate_price(spot, strike, dte, 0.135, is_call=is_call)
                prem_high = BlackScholesPricing.calculate_price(b_high, strike, dte, 0.135, is_call=is_call) if is_call else BlackScholesPricing.calculate_price(b_low, strike, dte, 0.135, is_call=is_call)
                prem_low = BlackScholesPricing.calculate_price(b_low, strike, dte, 0.135, is_call=is_call) if is_call else BlackScholesPricing.calculate_price(b_high, strike, dte, 0.135, is_call=is_call)

                if prem_high > pos["max_ltp"]:
                    pos["max_ltp"] = prem_high

                # Smart BE Lock
                if be_trigger is not None and pos["max_ltp"] >= pos["entry_raw"] + be_trigger:
                    be_sl = pos["entry_raw"] + be_buf
                    if be_sl > pos["sl_prem"]:
                        pos["sl_prem"] = be_sl
                        pos["be_protected"] = True
                    if trail_pts is not None and trail_pts > 0:
                        trail_sl = pos["max_ltp"] - trail_pts
                        if trail_sl > pos["sl_prem"]:
                            pos["sl_prem"] = trail_sl
                            pos["trailed"] = True

                hit_tp = (prem_high >= pos["tp_prem"])
                hit_sl = (prem_low <= pos["sl_prem"])
                hit_eod = (t >= eod_time)

                if hit_tp or hit_sl or hit_eod:
                    if hit_tp:
                        exit_raw = pos["tp_prem"]
                        reason = "TARGET 1:4 HIT (+200 pts)" if tp_pts == 200 else "TARGET HIT"
                    elif hit_sl:
                        exit_raw = pos["sl_prem"]
                        if pos.get("trailed"):
                            reason = f"TRAILING STOP (Locked +{exit_raw - pos['entry_raw']:.1f} pts)"
                        elif pos.get("be_protected"):
                            reason = "BREAKEVEN PROTECTED (+4 pts)"
                        else:
                            reason = f"STOP LOSS (-{sl_pts:.0f} pts)"
                    else:
                        exit_raw = prem_close
                        reason = "EOD EXIT"

                    fill_exit = max(0.5, exit_raw * 0.995)
                    pts = fill_exit - pos["fill_entry"]
                    gross = pts * lot_size
                    stt = fill_exit * lot_size * 0.000625
                    txn = (pos["fill_entry"] + fill_exit) * lot_size * 0.00053
                    brokerage = 40.0
                    gst = (brokerage + txn) * 0.18
                    costs = brokerage + stt + txn + gst
                    net = gross - costs
                    capital += net

                    is_win = (net > 0)
                    if not is_win:
                        has_lost_today = True

                    trade_rec = {
                        "date": d_str,
                        "year": current_date.year,
                        "month": current_date.strftime("%Y-%m"),
                        "trade_num": trades_today + 1,
                        "entry_time": pos["entry_dt"].strftime("%H:%M"),
                        "exit_time": bar["dt"].strftime("%H:%M"),
                        "instrument": f"NIFTY {strike} {pos['type']}",
                        "playbook": pos["playbook"],
                        "entry_prem": round(pos["fill_entry"], 2),
                        "exit_prem": round(fill_exit, 2),
                        "pts": round(pts, 2),
                        "gross_pnl": round(gross, 2),
                        "costs": round(costs, 2),
                        "net_pnl": round(net, 2),
                        "capital": round(capital, 2),
                        "result": reason,
                        "is_win": is_win
                    }
                    trades.append(trade_rec)
                    in_trade = False
                    pos = None
                    trades_today += 1
                    continue

            # Signal Check
            if not in_trade:
                if trades_today >= max_trades_per_day:
                    continue
                # STOP ON LOSS FILTER
                if stop_on_loss and has_lost_today:
                    continue
                if t < time(9, 25) or t > cutoff_time:
                    continue
                if b_range < 5.0:
                    continue

                lower_wick = min(b_open, spot) - b_low
                upper_wick = b_high - max(b_open, spot)
                bull_body = (spot > b_open) and ((spot - b_open) >= 0.25 * b_range)
                bear_body = (spot < b_open) and ((b_open - spot) >= 0.25 * b_range)
                prev_c = prev_bar["close"]

                # Breakouts
                r1_break = (prev_c <= lvl["r1"]) and (spot > lvl["r1"]) and bull_body
                s1_break = (prev_c >= lvl["s1"]) and (spot < lvl["s1"]) and bear_body

                # Reversals
                tested_r1 = (b_high >= lvl["r1"] >= b_low) or (prev_bar["high"] >= lvl["r1"] and b_high >= lvl["r1"])
                r1_fade = tested_r1 and (spot < lvl["r1"]) and (upper_wick >= 0.25 * b_range)
                tested_r2 = (b_high >= lvl["r2"])
                r2_fade = tested_r2 and (spot < lvl["r2"]) and (upper_wick >= 0.25 * b_range)

                # Gap Retests
                gap_r1_retest = False
                gap_s1_retest = False
                if day_open >= lvl["r1"]:
                    tested = (b_low <= lvl["r1"] <= b_high) or (b_low <= lvl["r1"])
                    gap_r1_retest = tested and (spot > lvl["r1"]) and (lower_wick >= 0.25 * b_range)
                elif day_open <= lvl["s1"]:
                    tested = (b_low <= lvl["s1"] <= b_high) or (b_high >= lvl["s1"])
                    gap_s1_retest = tested and (spot < lvl["s1"]) and (upper_wick >= 0.25 * b_range)

                # ORB
                gap_orb_pe = False
                if i >= 3 and day_open <= lvl["s1"]:
                    gap_orb_pe = (prev_c >= orb_low) and (spot < orb_low) and bear_body

                c_dir = None
                c_pb = ""
                if gap_r1_retest: c_dir = "CE"; c_pb = "Gap-Up R1 Polarity Bounce"
                elif gap_s1_retest: c_dir = "PE"; c_pb = "Gap-Down S1 Polarity Rejection"
                elif r1_fade: c_dir = "PE"; c_pb = "R1 Resistance Reversal"
                elif r2_fade: c_dir = "PE"; c_pb = "R2 Exhaustion Reversal"
                elif gap_orb_pe: c_dir = "PE"; c_pb = "Gap-and-Go Bearish ORB"
                elif s1_break: c_dir = "PE"; c_pb = "S1 Support Breakdown"

                if c_dir:
                    strike = int(round(spot / 50.0) * 50)
                    is_call = (c_dir == "CE")
                    entry_raw = BlackScholesPricing.calculate_price(spot, strike, dte, 0.135, is_call=is_call)
                    fill_entry = entry_raw * 1.005
                    pos = {
                        "playbook": c_pb,
                        "type": c_dir,
                        "strike": strike,
                        "entry_spot": spot,
                        "entry_dt": bar["dt"],
                        "entry_raw": entry_raw,
                        "fill_entry": fill_entry,
                        "sl_prem": max(0.5, entry_raw - sl_pts),
                        "tp_prem": entry_raw + tp_pts,
                        "max_ltp": entry_raw,
                        "be_protected": False,
                        "trailed": False
                    }
                    in_trade = True

    df = pd.DataFrame(trades)
    if df.empty:
        return {}
    n = len(df)
    wins = int(df["is_win"].sum())
    losses = n - wins
    wr = (wins / n) * 100.0
    net = float(df["net_pnl"].sum())
    gross_w = float(df[df["net_pnl"] > 0]["net_pnl"].sum())
    gross_l = abs(float(df[df["net_pnl"] < 0]["net_pnl"].sum()))
    pf = gross_w / gross_l if gross_l > 0 else 99.0
    cum = df["net_pnl"].cumsum()
    peak = cum.cummax()
    dd = float((peak - cum).max())
    calmar = net / dd if dd > 0 else 99.0
    roi = (net / initial_capital) * 100.0
    avg_win = float(df[df["net_pnl"] > 0]["net_pnl"].mean()) if wins > 0 else 0
    avg_loss = abs(float(df[df["net_pnl"] < 0]["net_pnl"].mean())) if losses > 0 else 0

    # Trade 2 specifically after Trade 1 loss
    reentry_trades = df[df["trade_num"] == 2]
    reentry_wins = int(reentry_trades["is_win"].sum()) if not reentry_trades.empty else 0
    reentry_total = len(reentry_trades)
    reentry_pnl = float(reentry_trades["net_pnl"].sum()) if not reentry_trades.empty else 0.0

    return {
        "n": n, "wins": wins, "losses": losses, "wr": wr,
        "net_pnl": net, "pf": pf, "dd": dd, "calmar": calmar,
        "roi": roi, "avg_win": avg_win, "avg_loss": avg_loss,
        "reentry_total": reentry_total, "reentry_wins": reentry_wins, "reentry_pnl": reentry_pnl,
        "df": df
    }

print("\nRunning 3-Year Backtest: WITH HALT (DAILY_STOP_ON_LOSS = True)...")
res_halt = run_3year_backtest(stop_on_loss=True)

print("Running 3-Year Backtest: WITHOUT HALT (DAILY_STOP_ON_LOSS = False)...")
res_no_halt = run_3year_backtest(stop_on_loss=False)

print("\n" + "="*95)
print("       3-YEAR COMPREHENSIVE BACKTEST COMPARISON (31-OCT-2023 TO 21-OCT-2026)")
print("       DAILY_STOP_ON_LOSS = True (WITH HALT) vs. DAILY_STOP_ON_LOSS = False (WITHOUT HALT)")
print("="*95)
print(f"{'METRIC':<32} | {'WITH HALT (STOP ON LOSS)':<28} | {'WITHOUT HALT (ALLOW 2 TRADES)':<28}")
print("-"*95)
print(f"{'Total Trades':<32} | {res_halt['n']:<28} | {res_no_halt['n']:<28}")
print(f"{'Winning Trades':<32} | {res_halt['wins']} ({res_halt['wr']:.1f}%)" + " "*17 + f"| {res_no_halt['wins']} ({res_no_halt['wr']:.1f}%)")
print(f"{'Losing Trades':<32} | {res_halt['losses']:<28} | {res_no_halt['losses']:<28}")
print(f"{'Total Net P&L':<32} | Rs {res_halt['net_pnl']:+12,.2f}               | Rs {res_no_halt['net_pnl']:+12,.2f}")
print(f"{'Return on Capital (ROI)':<32} | {res_halt['roi']:+10.1f}%                 | {res_no_halt['roi']:+10.1f}%")
print(f"{'Profit Factor (PF)':<32} | {res_halt['pf']:<28.2f} | {res_no_halt['pf']:<28.2f}")
print(f"{'Max Peak Drawdown':<32} | Rs {res_halt['dd']:10,.2f}               | Rs {res_no_halt['dd']:10,.2f}")
print(f"{'Calmar Ratio':<32} | {res_halt['calmar']:<28.2f} | {res_no_halt['calmar']:<28.2f}")
print(f"{'Avg Winning Trade':<32} | Rs {res_halt['avg_win']:10,.2f}               | Rs {res_no_halt['avg_win']:10,.2f}")
print(f"{'Avg Losing Trade':<32} | Rs -{res_halt['avg_loss']:9,.2f}               | Rs -{res_no_halt['avg_loss']:9,.2f}")
print(f"{'Second Trades Taken':<32} | {'0 (Halted on Loss)':<28} | {res_no_halt['reentry_total']} Trades (P&L: Rs {res_no_halt['reentry_pnl']:+,.2f})")
print("="*95)

# Yearly Breakdown
y_halt = res_halt['df'].groupby('year').agg(Trades=('net_pnl','count'), Wins=('is_win','sum'), Net_PnL=('net_pnl','sum')).reset_index()
y_no_halt = res_no_halt['df'].groupby('year').agg(Trades=('net_pnl','count'), Wins=('is_win','sum'), Net_PnL=('net_pnl','sum')).reset_index()

print("\nYEAR-BY-YEAR BREAKDOWN:")
print(f"{'Year':<8} | {'WITH HALT (Trades / WR / Net P&L)':<40} | {'WITHOUT HALT (Trades / WR / Net P&L)'}")
print("-"*95)
for yr in sorted(list(set(y_halt['year']).union(set(y_no_halt['year'])))):
    r1 = y_halt[y_halt['year'] == yr]
    r2 = y_no_halt[y_no_halt['year'] == yr]
    t1 = r1['Trades'].iloc[0] if not r1.empty else 0
    w1 = r1['Wins'].iloc[0] if not r1.empty else 0
    p1 = r1['Net_PnL'].iloc[0] if not r1.empty else 0.0
    t2 = r2['Trades'].iloc[0] if not r2.empty else 0
    w2 = r2['Wins'].iloc[0] if not r2.empty else 0
    p2 = r2['Net_PnL'].iloc[0] if not r2.empty else 0.0
    wr1 = (w1/t1*100) if t1 > 0 else 0
    wr2 = (w2/t2*100) if t2 > 0 else 0
    print(f"{yr:<8} | {t1:3d} tr | {wr1:4.1f}% WR | Rs {p1:+10,.2f}          | {t2:3d} tr | {wr2:4.1f}% WR | Rs {p2:+10,.2f}")
print("="*95)

# Also save comparison to CSV
res_halt['df'].to_csv("trades_3year_with_halt.csv", index=False)
res_no_halt['df'].to_csv("trades_3year_without_halt.csv", index=False)
print("Saved trade logs: trades_3year_with_halt.csv and trades_3year_without_halt.csv")
