import os
import pandas as pd
import numpy as np
from datetime import time, timedelta
import backtest_strike_expiry_sltp as b

base_dir = os.path.dirname(os.path.abspath(__file__))
session_data = b.load_all_sessions(base_dir)

elite_pbs = [
    "R1 Resistance Reversal", "R2 Exhaustion Reversal", "Gap-Up R1 Polarity Bounce",
    "S1 Support Breakdown", "Gap-Down S1 Polarity Rejection", "Gap-and-Go Bearish ORB"
]

def extract_filtered_signals(min_bar_range=5.0, min_wick_ratio=0.25, entry_cutoff_time=time(14, 0), friday_trade_limit=2):
    trade_events = []
    for sess in session_data:
        lvl = sess["lvl"]
        bars = sess["bars"]
        current_date = sess["date"]
        day_open = sess["day_open"]
        is_friday = (sess["dow"] == 4)

        orb_high = max(b["high"] for b in bars[:3]) if len(bars) >= 3 else day_open + 20
        orb_low = min(b["low"] for b in bars[:3]) if len(bars) >= 3 else day_open - 20

        trades_today = 0
        in_trade = False
        trade_exit_bar_idx = -1
        max_trades = 1 if (is_friday and friday_trade_limit == 1) else 2

        for i in range(1, len(bars) - 1):
            if in_trade and i <= trade_exit_bar_idx:
                continue
            in_trade = False

            if trades_today >= max_trades:
                break

            bar = bars[i]
            prev_bar = bars[i - 1]
            t = bar["time"]

            if t < time(9, 25) or t > entry_cutoff_time:
                continue

            spot = bar["close"]
            b_open = bar["open"]
            b_high = bar["high"]
            b_low = bar["low"]
            b_range = b_high - b_low

            if b_range < min_bar_range:
                continue

            lower_wick = min(b_open, spot) - b_low
            upper_wick = b_high - max(b_open, spot)
            bull_body = (spot > b_open) and ((spot - b_open) >= 0.25 * b_range)
            bear_body = (spot < b_open) and ((b_open - spot) >= 0.25 * b_range)
            prev_c = prev_bar["close"]

            r1_fade = ((b_high >= lvl["r1"] >= b_low) or (prev_bar["high"] >= lvl["r1"] and b_high >= lvl["r1"])) and (spot < lvl["r1"]) and (upper_wick >= min_wick_ratio * b_range)
            r2_fade = (b_high >= lvl["r2"]) and (spot < lvl["r2"]) and (upper_wick >= min_wick_ratio * b_range)
            s1_break = (prev_c >= lvl["s1"]) and (spot < lvl["s1"]) and bear_body

            gap_r1_retest = False
            gap_s1_retest = False
            if day_open >= lvl["r1"]:
                tested = (b_low <= lvl["r1"] <= b_high) or (b_low <= lvl["r1"])
                gap_r1_retest = tested and (spot > lvl["r1"]) and (lower_wick >= min_wick_ratio * b_range)
            elif day_open <= lvl["s1"]:
                tested = (b_low <= lvl["s1"] <= b_high) or (b_high >= lvl["s1"])
                gap_s1_retest = tested and (spot < lvl["s1"]) and (upper_wick >= min_wick_ratio * b_range)

            gap_orb_pe = False
            if i >= 3 and day_open <= lvl["s1"]:
                gap_orb_pe = (prev_c >= orb_low) and (spot < orb_low) and bear_body

            cand_dir, cand_pb = None, ""
            if gap_r1_retest: cand_dir = "CE"; cand_pb = "Gap-Up R1 Polarity Bounce"
            elif gap_s1_retest: cand_dir = "PE"; cand_pb = "Gap-Down S1 Polarity Rejection"
            elif r1_fade: cand_dir = "PE"; cand_pb = "R1 Resistance Reversal"
            elif r2_fade: cand_dir = "PE"; cand_pb = "R2 Exhaustion Reversal"
            elif gap_orb_pe: cand_dir = "PE"; cand_pb = "Gap-and-Go Bearish ORB"
            elif s1_break: cand_dir = "PE"; cand_pb = "S1 Support Breakdown"

            if cand_dir and (cand_pb in elite_pbs):
                trade_events.append({
                    "id": len(trade_events),
                    "date": current_date,
                    "entry_time": bar["dt"],
                    "trade_dir": cand_dir,
                    "playbook": cand_pb,
                    "spot_entry": spot,
                    "dte_curr": sess["dte_curr"],
                    "dte_next": sess["dte_next"],
                    "dte_month": sess["dte_month"],
                    "forward_bars": bars[i:]
                })
                trades_today += 1
                in_trade = True
                trade_exit_bar_idx = min(i + 15, len(bars) - 1)

    return trade_events

print("=" * 80)
print("TESTING INDIVIDUAL FILTERS ON TOP OF CHAMPION SETUP (ATM, SL 50, TP 200)")
print("=" * 80)

# Baseline
base_sigs = extract_filtered_signals(min_bar_range=5.0, min_wick_ratio=0.25, entry_cutoff_time=time(14, 45), friday_trade_limit=2)
cache_base = b.precompute_all_option_trajectories(base_sigs, ["ATM"], ["current_weekly"])
t_base = b.fast_simulate_config(base_sigs, cache_base, "ATM", "current_weekly", "points", 50.0, 4.0, False)
df_base = pd.DataFrame(t_base)
pnl_b = float(df_base["net_pnl"].sum())
wr_b = (df_base["is_win"].mean()) * 100
pf_b = df_base[df_base["net_pnl"] > 0]["net_pnl"].sum() / abs(df_base[df_base["net_pnl"] < 0]["net_pnl"].sum())
dd_b = float((df_base["net_pnl"].cumsum().cummax() - df_base["net_pnl"].cumsum()).max())

print(f"BASELINE:             Trades={len(df_base):<3} | WR={wr_b:5.2f}% | Net PnL=Rs {pnl_b:>10,.2f} | PF={pf_b:4.2f} | Max DD=Rs {dd_b:>8,.2f}")

# Filter 1: Entry Cutoff at 13:30 IST (Avoid Afternoon Theta Trap)
f1_sigs = extract_filtered_signals(min_bar_range=5.0, min_wick_ratio=0.25, entry_cutoff_time=time(13, 30), friday_trade_limit=2)
c1 = b.precompute_all_option_trajectories(f1_sigs, ["ATM"], ["current_weekly"])
t1 = b.fast_simulate_config(f1_sigs, c1, "ATM", "current_weekly", "points", 50.0, 4.0, False)
df1 = pd.DataFrame(t1)
pnl1 = float(df1["net_pnl"].sum())
wr1 = df1["is_win"].mean() * 100
pf1 = df1[df1["net_pnl"] > 0]["net_pnl"].sum() / abs(df1[df1["net_pnl"] < 0]["net_pnl"].sum())
dd1 = float((df1["net_pnl"].cumsum().cummax() - df1["net_pnl"].cumsum()).max())
print(f"Filter 1 (Cutoff 13:30): Trades={len(df1):<3} | WR={wr1:5.2f}% | Net PnL=Rs {pnl1:>10,.2f} | PF={pf1:4.2f} | Max DD=Rs {dd1:>8,.2f}")

# Filter 2: Entry Cutoff at 14:00 IST
f2_sigs = extract_filtered_signals(min_bar_range=5.0, min_wick_ratio=0.25, entry_cutoff_time=time(14, 0), friday_trade_limit=2)
c2 = b.precompute_all_option_trajectories(f2_sigs, ["ATM"], ["current_weekly"])
t2 = b.fast_simulate_config(f2_sigs, c2, "ATM", "current_weekly", "points", 50.0, 4.0, False)
df2 = pd.DataFrame(t2)
pnl2 = float(df2["net_pnl"].sum())
wr2 = df2["is_win"].mean() * 100
pf2 = df2[df2["net_pnl"] > 0]["net_pnl"].sum() / abs(df2[df2["net_pnl"] < 0]["net_pnl"].sum())
dd2 = float((df2["net_pnl"].cumsum().cummax() - df2["net_pnl"].cumsum()).max())
print(f"Filter 2 (Cutoff 14:00): Trades={len(df2):<3} | WR={wr2:5.2f}% | Net PnL=Rs {pnl2:>10,.2f} | PF={pf2:4.2f} | Max DD=Rs {dd2:>8,.2f}")

# Filter 3: Minimum Rejection Wick 35% (Institutional Quality Wick)
f3_sigs = extract_filtered_signals(min_bar_range=5.0, min_wick_ratio=0.35, entry_cutoff_time=time(14, 45), friday_trade_limit=2)
c3 = b.precompute_all_option_trajectories(f3_sigs, ["ATM"], ["current_weekly"])
t3 = b.fast_simulate_config(f3_sigs, c3, "ATM", "current_weekly", "points", 50.0, 4.0, False)
df3 = pd.DataFrame(t3)
pnl3 = float(df3["net_pnl"].sum())
wr3 = df3["is_win"].mean() * 100
pf3 = df3[df3["net_pnl"] > 0]["net_pnl"].sum() / abs(df3[df3["net_pnl"] < 0]["net_pnl"].sum())
dd3 = float((df3["net_pnl"].cumsum().cummax() - df3["net_pnl"].cumsum()).max())
print(f"Filter 3 (Wick >= 35%):  Trades={len(df3):<3} | WR={wr3:5.2f}% | Net PnL=Rs {pnl3:>10,.2f} | PF={pf3:4.2f} | Max DD=Rs {dd3:>8,.2f}")

# Filter 4: Friday Max 1 Trade
f4_sigs = extract_filtered_signals(min_bar_range=5.0, min_wick_ratio=0.25, entry_cutoff_time=time(14, 45), friday_trade_limit=1)
c4 = b.precompute_all_option_trajectories(f4_sigs, ["ATM"], ["current_weekly"])
t4 = b.fast_simulate_config(f4_sigs, c4, "ATM", "current_weekly", "points", 50.0, 4.0, False)
df4 = pd.DataFrame(t4)
pnl4 = float(df4["net_pnl"].sum())
wr4 = df4["is_win"].mean() * 100
pf4 = df4[df4["net_pnl"] > 0]["net_pnl"].sum() / abs(df4[df4["net_pnl"] < 0]["net_pnl"].sum())
dd4 = float((df4["net_pnl"].cumsum().cummax() - df4["net_pnl"].cumsum()).max())
print(f"Filter 4 (Friday 1 Trade):Trades={len(df4):<3} | WR={wr4:5.2f}% | Net PnL=Rs {pnl4:>10,.2f} | PF={pf4:4.2f} | Max DD=Rs {dd4:>8,.2f}")

# Filter 5: Master Combo (Cutoff 13:45 + Wick >= 30% + Friday 1 Trade)
f5_sigs = extract_filtered_signals(min_bar_range=6.0, min_wick_ratio=0.30, entry_cutoff_time=time(13, 45), friday_trade_limit=1)
c5 = b.precompute_all_option_trajectories(f5_sigs, ["ATM"], ["current_weekly"])
t5 = b.fast_simulate_config(f5_sigs, c5, "ATM", "current_weekly", "points", 50.0, 4.0, False)
df5 = pd.DataFrame(t5)
pnl5 = float(df5["net_pnl"].sum())
wr5 = df5["is_win"].mean() * 100
pf5 = df5[df5["net_pnl"] > 0]["net_pnl"].sum() / abs(df5[df5["net_pnl"] < 0]["net_pnl"].sum())
dd5 = float((df5["net_pnl"].cumsum().cummax() - df5["net_pnl"].cumsum()).max())
print(f"Filter 5 (Master Combo): Trades={len(df5):<3} | WR={wr5:5.2f}% | Net PnL=Rs {pnl5:>10,.2f} | PF={pf5:4.2f} | Max DD=Rs {dd5:>8,.2f}")
