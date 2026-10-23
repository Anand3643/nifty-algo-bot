import os
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

# Extract raw signals with allowed playbooks
raw_sigs = b.extract_trade_signals(session_data, allowed_pb=elite_pbs)
cache = b.precompute_all_option_trajectories(raw_sigs, ["ATM"], ["current_weekly"])

lot_size = 65
slippage = 0.005

def run_simulation(enable_1400_cutoff=True, be_threshold=80.0, stop_on_loss=True):
    trades = []
    daily_trades = {}
    
    for s_idx, sig in enumerate(raw_sigs):
        d_str = sig["date"].strftime("%Y-%m-%d")
        prior = daily_trades.get(d_str, [])
        
        # Filter 1: 14:00 Entry Cutoff
        if enable_1400_cutoff and sig["entry_time"].time() > time(14, 0):
            continue
            
        # Filter 3: Stop-On-Loss Rule (if trade 1 was loss, skip trade 2)
        if stop_on_loss and len(prior) == 1 and not prior[0]["is_win"]:
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
        reason = "EOD SQUARE-OFF (15:10)"
        
        for b_idx in range(n_bars):
            ph = highs[b_idx]
            pl = lows[b_idx]
            dt = bar_dts[b_idx]
            
            if ph > max_fav:
                max_fav = ph
                
            # Filter 2: Smart Breakeven Lock at +80 pts
            if be_threshold is not None and max_fav >= entry_raw + be_threshold:
                be_level = entry_raw + 4.0  # Entry + 4 pts buffer covering brokerage & taxes
                if be_level > curr_sl:
                    curr_sl = be_level
                    
            hit_tp = (ph >= tp_prem)
            hit_sl = (pl <= curr_sl)
            hit_eod = (dt.time() >= time(15, 10))
            
            if hit_tp or hit_sl or hit_eod:
                exit_dt = dt
                if hit_tp:
                    exit_raw = tp_prem
                    reason = "TARGET 1:4 HIT (+200 pts)"
                elif hit_sl:
                    exit_raw = curr_sl
                    reason = "BREAKEVEN PROTECTED (+4 pts)" if curr_sl > initial_sl else "STOP LOSS HIT (-50 pts)"
                else:
                    exit_raw = closes[b_idx]
                    reason = "EOD SQUARE-OFF (15:10)"
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
    
    n = len(df)
    wins = int(df["is_win"].sum())
    wr = (wins / n) * 100.0 if n > 0 else 0
    pnl = float(df["net_pnl"].sum())
    gw = float(df[df["net_pnl"] > 0]["net_pnl"].sum())
    gl = abs(float(df[df["net_pnl"] < 0]["net_pnl"].sum()))
    pf = gw / gl if gl > 0 else 99.0
    cum = df["net_pnl"].cumsum()
    dd = float((cum.cummax() - cum).max()) if n > 0 else 0
    calmar = pnl / dd if dd > 0 else 99.0
    
    stats = {
        "n": n, "wins": wins, "losses": n - wins, "wr": wr,
        "pnl": pnl, "pf": pf, "dd": dd, "calmar": calmar, "df": df
    }
    return stats

# 1. Base Champion
s_base = run_simulation(enable_1400_cutoff=False, be_threshold=None, stop_on_loss=False)
# 2. Level 1: + 14:00 Cutoff
s_l1 = run_simulation(enable_1400_cutoff=True, be_threshold=None, stop_on_loss=False)
# 3. Level 2: + Smart BE Lock @ 80
s_l2 = run_simulation(enable_1400_cutoff=True, be_threshold=80.0, stop_on_loss=False)
# 4. Level 3 (Champion Enhanced): + Stop-on-Loss Filter
s_l3 = run_simulation(enable_1400_cutoff=True, be_threshold=80.0, stop_on_loss=True)

print("="*80)
print(f"{'CONFIGURATION':<38} | {'TRADES':<6} | {'WIN %':<7} | {'NET P&L':<12} | {'PF':<5} | {'MAX DD':<10} | {'CALMAR'}")
print("="*80)
print(f"{'Baseline Champion':<38} | {s_base['n']:<6} | {s_base['wr']:5.2f}% | Rs {s_base['pnl']:9,.2f} | {s_base['pf']:4.2f} | Rs {s_base['dd']:8,.2f} | {s_base['calmar']:5.2f}x")
print(f"{'Level 1: + 14:00 IST Cutoff':<38} | {s_l1['n']:<6} | {s_l1['wr']:5.2f}% | Rs {s_l1['pnl']:9,.2f} | {s_l1['pf']:4.2f} | Rs {s_l1['dd']:8,.2f} | {s_l1['calmar']:5.2f}x")
print(f"{'Level 2: + 14:00 Cutoff & BE Lock':<38} | {s_l2['n']:<6} | {s_l2['wr']:5.2f}% | Rs {s_l2['pnl']:9,.2f} | {s_l2['pf']:4.2f} | Rs {s_l2['dd']:8,.2f} | {s_l2['calmar']:5.2f}x")
print(f"{'Level 3: Ultimate Triple Filtration':<38} | {s_l3['n']:<6} | {s_l3['wr']:5.2f}% | Rs {s_l3['pnl']:9,.2f} | {s_l3['pf']:4.2f} | Rs {s_l3['dd']:8,.2f} | {s_l3['calmar']:5.2f}x")
print("="*80)

# Save Master Enhanced Ledger CSV
csv_enhanced = os.path.join(base_dir, "trades_master_enhanced_setup_2year.csv")
s_l3["df"].to_csv(csv_enhanced, index=False)
print(f"Saved master enhanced trades to {csv_enhanced} ({len(s_l3['df'])} trades).")
