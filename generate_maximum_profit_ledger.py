import os
import json
import pandas as pd
import numpy as np
from datetime import time
import backtest_strike_expiry_sltp as b

base_dir = os.path.dirname(os.path.abspath(__file__))
session_data = b.load_all_sessions(base_dir)

elite_pbs = [
    "R1 Resistance Reversal", "R2 Exhaustion Reversal", "Gap-Up R1 Polarity Bounce",
    "S1 Support Breakdown", "Gap-Down S1 Polarity Rejection", "Gap-and-Go Bearish ORB"
]

raw_sigs = b.extract_trade_signals(session_data, allowed_pb=elite_pbs)
cache = b.precompute_all_option_trajectories(raw_sigs, ["ATM"], ["current_weekly"])

lot_size = 65
slippage = 0.005
eod_close_time = time(15, 0)
be_trigger = 80.0
be_buffer = 4.0
trail_dist = 15.0

trades = []
daily_trades = {}

for s_idx, sig in enumerate(raw_sigs):
    d_str = sig["date"].strftime("%Y-%m-%d")
    prior = daily_trades.get(d_str, [])
    
    # Filter 1: 14:00 Entry Cutoff
    if sig["entry_time"].time() > time(14, 0):
        continue
    # Cannot enter if already past EOD
    if sig["entry_time"].time() >= eod_close_time:
        continue
        
    # Filter 3: Stop-On-Loss Rule (if trade 1 was loss, skip trade 2)
    if len(prior) == 1 and not prior[0]["is_win"]:
        continue
    if len(prior) >= 2:
        continue
        
    tr = cache[(s_idx, "ATM", "current_weekly")]
    entry_raw = tr["entry_raw"]
    fill_entry = tr["fill_entry"]
    highs, lows, closes, bar_dts = tr["highs"], tr["lows"], tr["closes"], tr["bar_dts"]
    n_bars = len(highs)
    if n_bars == 0:
        continue
        
    initial_sl = max(0.5, entry_raw - 50.0)
    tp_prem = entry_raw + 200.0
    curr_sl = initial_sl
    max_fav = entry_raw
    exit_raw = closes[-1]
    exit_dt = bar_dts[-1]
    reason = "EOD SQUARE-OFF (15:00)"
    
    for b_idx in range(n_bars):
        ph = highs[b_idx]
        pl = lows[b_idx]
        dt = bar_dts[b_idx]
        
        if ph > max_fav:
            max_fav = ph
            
        # 1. BE Buffer Lock
        if be_trigger is not None and max_fav >= entry_raw + be_trigger:
            be_level = entry_raw + be_buffer
            if be_level > curr_sl:
                curr_sl = be_level
                
        # 2. Dynamic Trailing SL 15 pts behind high
        if trail_dist is not None and max_fav >= entry_raw + be_trigger:
            t_sl = max_fav - trail_dist
            if t_sl > curr_sl:
                curr_sl = t_sl
                
        hit_tp = (ph >= tp_prem)
        hit_sl = (pl <= curr_sl)
        hit_eod = (dt.time() >= eod_close_time)
        
        if hit_tp or hit_sl or hit_eod:
            exit_dt = dt
            if hit_tp:
                exit_raw = tp_prem
                reason = "TARGET 1:4 HIT (+200 pts)"
            elif hit_sl:
                exit_raw = curr_sl
                if curr_sl > entry_raw + be_buffer:
                    reason = f"TRAILING STOP HIT (Locked +{round(curr_sl - entry_raw, 1)} pts)"
                elif curr_sl > initial_sl:
                    reason = "BREAKEVEN PROTECTED (+4 pts)"
                else:
                    reason = "STOP LOSS HIT (-50 pts)"
            else:
                exit_raw = closes[b_idx]
                reason = "EOD SQUARE-OFF (15:00)"
            break
            
    fill_exit = max(0.5, exit_raw * (1.0 - slippage))
    pts_diff = fill_exit - fill_entry
    gross_pnl = pts_diff * lot_size
    
    buy_to = fill_entry * lot_size
    sell_to = fill_exit * lot_size
    brokerage = 40.0
    stt = sell_to * 0.000625
    txn = (buy_to + sell_to) * 0.00053
    gst = (brokerage + txn) * 0.18
    costs = brokerage + stt + txn + gst
    net_pnl = gross_pnl - costs
    is_win = (net_pnl > 0)
    
    t_record = {
        "trade_id": len(trades) + 1,
        "date": sig["date"].strftime("%Y-%m-%d"),
        "day_name": sig["date"].strftime("%A"),
        "entry_time": sig["entry_time"].strftime("%H:%M"),
        "exit_time": exit_dt.strftime("%H:%M"),
        "trade_dir": sig["trade_dir"],
        "playbook": sig["playbook"],
        "strike": tr["strike"],
        "entry_prem": round(fill_entry, 2),
        "exit_prem": round(fill_exit, 2),
        "pts": round(pts_diff, 2),
        "gross_pnl": round(gross_pnl, 2),
        "costs": round(costs, 2),
        "net_pnl": round(net_pnl, 2),
        "result": reason,
        "is_win": is_win
    }
    trades.append(t_record)
    if d_str not in daily_trades:
        daily_trades[d_str] = []
    daily_trades[d_str].append(t_record)

df = pd.DataFrame(trades)
df["cum_pnl"] = df["net_pnl"].cumsum().round(2)

csv_path = os.path.join(base_dir, "trades_maximum_profit_setup_2year.csv")
df.to_csv(csv_path, index=False)
print(f"Saved {len(df)} trades to {csv_path}")

# Performance Stats
n = len(df)
wins = int(df["is_win"].sum())
losses = n - wins
wr = (wins / n) * 100.0
pnl = float(df["net_pnl"].sum())
gw = float(df[df["net_pnl"] > 0]["net_pnl"].sum())
gl = abs(float(df[df["net_pnl"] < 0]["net_pnl"].sum()))
pf = gw / gl if gl > 0 else 99.0
cum = df["net_pnl"].cumsum()
dd = float((cum.cummax() - cum).max())
calmar = pnl / dd if dd > 0 else 99.0

print("\n" + "="*80)
print("MAXIMUM PROFIT SETUP SUMMARY (EOD 15:00 + TRAIL 15 PTS)")
print("="*80)
print(f"Total Trades:      {n}")
print(f"Wins / Losses:     {wins}W / {losses}L ({wr:.2f}% Win Rate)")
print(f"Net P&L:           Rs {pnl:,.2f} (+{pnl/50000.0*100:.1f}% ROI on Rs 50k)")
print(f"Profit Factor:     {pf:.2f}")
print(f"Max Drawdown:      Rs {dd:,.2f} ({dd/50000.0*100:.1f}% of Capital)")
print(f"Calmar Ratio:      {calmar:.2f}x")
print(f"Average Trade:     Rs {pnl/n:,.2f}")
print("="*80)

print("\n=== EXIT REASON DISTRIBUTION ===")
print(df["result"].value_counts())

print("\n=== PLAYBOOK PERFORMANCE ===")
pb_summary = df.groupby("playbook").agg(
    Trades=("net_pnl", "count"),
    WinRate=("is_win", lambda x: f"{x.mean()*100:.1f}%"),
    NetPnL=("net_pnl", "sum"),
    AvgTrade=("net_pnl", "mean")
).sort_values("NetPnL", ascending=False)
print(pb_summary)

print("\n=== DAY OF WEEK PERFORMANCE ===")
day_order = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday"]
day_summary = df.groupby("day_name").agg(
    Trades=("net_pnl", "count"),
    WinRate=("is_win", lambda x: f"{x.mean()*100:.1f}%"),
    NetPnL=("net_pnl", "sum"),
    AvgTrade=("net_pnl", "mean")
).reindex(day_order)
print(day_summary)

df["year"] = df["date"].str.slice(0, 4)
print("\n=== ANNUAL PERFORMANCE ===")
yr_summary = df.groupby("year").agg(
    Trades=("net_pnl", "count"),
    WinRate=("is_win", lambda x: f"{x.mean()*100:.1f}%"),
    NetPnL=("net_pnl", "sum")
)
print(yr_summary)
