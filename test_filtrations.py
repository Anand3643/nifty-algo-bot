import os
import pandas as pd
import numpy as np
from datetime import time
import backtest_strike_expiry_sltp as b

base_dir = os.path.dirname(os.path.abspath(__file__))
session_data = b.load_all_sessions(base_dir)

elite_pbs = [
    'R1 Resistance Reversal', 'R2 Exhaustion Reversal', 'Gap-Up R1 Polarity Bounce',
    'S1 Support Breakdown', 'Gap-Down S1 Polarity Rejection', 'Gap-and-Go Bearish ORB'
]
raw_sigs = b.extract_trade_signals(session_data, allowed_pb=elite_pbs)
cache = b.precompute_all_option_trajectories(raw_sigs, ['ATM'], ['current_weekly', 'next_weekly'])

for i, s in enumerate(raw_sigs):
    s['orig_idx'] = i

def simulate(signals_to_run, be_trigger=None, use_next_wk_on_expiry=False, max_trades_per_day=99):
    lot_size = 65
    slippage = 0.005
    trades = []
    daily_count = {}
    
    for s_idx, sig in enumerate(signals_to_run):
        d_str = sig['date'].strftime('%Y-%m-%d')
        cnt = daily_count.get(d_str, 0)
        if cnt >= max_trades_per_day:
            continue
        daily_count[d_str] = cnt + 1
        
        is_expiry = (sig['date'].weekday() == 3 if sig['date'] < pd.Timestamp("2025-09-01").date() else sig['date'].weekday() == 1)
        exp_mode = 'next_weekly' if (use_next_wk_on_expiry and is_expiry) else 'current_weekly'
        tr = cache[(sig['orig_idx'], 'ATM', exp_mode)]
        entry_raw = tr['entry_raw']
        fill_entry = tr['fill_entry']
        highs, lows, closes, bar_dts = tr['highs'], tr['lows'], tr['closes'], tr['bar_dts']
        n_bars = len(highs)
        if n_bars == 0:
            continue
        
        initial_sl = max(0.5, entry_raw - 50.0)
        tp_prem = entry_raw + 200.0
        curr_sl = initial_sl
        max_fav = entry_raw
        
        exit_raw = closes[-1]
        exit_dt = bar_dts[-1]
        
        for b_idx in range(n_bars):
            ph = highs[b_idx]
            pl = lows[b_idx]
            dt = bar_dts[b_idx]
            if ph > max_fav:
                max_fav = ph
            
            if be_trigger is not None and max_fav >= entry_raw + be_trigger:
                be_level = entry_raw + 4.0
                if be_level > curr_sl:
                    curr_sl = be_level
                
            hit_tp = (ph >= tp_prem)
            hit_sl = (pl <= curr_sl)
            hit_eod = (dt.time() >= time(15, 10))
            
            if hit_tp or hit_sl or hit_eod:
                if hit_tp:
                    exit_raw = tp_prem
                elif hit_sl:
                    exit_raw = curr_sl
                else:
                    exit_raw = closes[b_idx]
                break
                
        fill_exit = max(0.5, exit_raw * (1.0 - slippage))
        pts_diff = fill_exit - fill_entry
        gross = pts_diff * lot_size
        buy_to = fill_entry * lot_size
        sell_to = fill_exit * lot_size
        brokerage = 40.0
        stt = sell_to * 0.000625
        txn = (buy_to + sell_to) * 0.00053
        gst = (brokerage + txn) * 0.18
        costs = brokerage + stt + txn + gst
        net = gross - costs
        is_expiry = (sig['date'].weekday() == 3 if sig['date'] < pd.Timestamp("2025-09-01").date() else sig['date'].weekday() == 1)
        trades.append({
            'date': sig['date'],
            'day_name': sig['date'].strftime('%A'),
            'net': net,
            'is_win': net > 0,
            'entry_time': sig['entry_time'].time(),
            'is_expiry': is_expiry,
            'playbook': sig['playbook']
        })
    df = pd.DataFrame(trades)
    if len(df) == 0:
        return None
    n = len(df)
    wins = df['is_win'].sum()
    wr = (wins / n) * 100
    pnl = df['net'].sum()
    gw = df[df['net'] > 0]['net'].sum()
    gl = abs(df[df['net'] < 0]['net'].sum())
    pf = gw / gl if gl > 0 else 99
    cum = df['net'].cumsum()
    dd = (cum.cummax() - cum).max()
    calmar = pnl / dd if dd > 0 else 99
    return {'n': n, 'wr': wr, 'pnl': pnl, 'pf': pf, 'dd': dd, 'calmar': calmar, 'df': df}

print("=== 1. BASELINE CHAMPION ===")
r_base = simulate(raw_sigs, be_trigger=None, use_next_wk_on_expiry=False)
print(f"Base: N={r_base['n']}, WR={r_base['wr']:.2f}%, PnL=Rs {r_base['pnl']:,.2f}, PF={r_base['pf']:.2f}, MaxDD=Rs {r_base['dd']:,.2f}, Calmar={r_base['calmar']:.2f}x")

print("\n=== 2. EXPIRY-DAY NEXT WEEK RULE ===")
r_exp = simulate(raw_sigs, be_trigger=None, use_next_wk_on_expiry=True)
print(f"NextWk on Expiry: N={r_exp['n']}, WR={r_exp['wr']:.2f}%, PnL=Rs {r_exp['pnl']:,.2f}, PF={r_exp['pf']:.2f}, MaxDD=Rs {r_exp['dd']:,.2f}, Calmar={r_exp['calmar']:.2f}x")

print("\n=== 3. 14:00 CUTOFF ===")
sigs_1400 = [s for s in raw_sigs if s['entry_time'].time() <= time(14, 0)]
r_1400 = simulate(sigs_1400, be_trigger=None, use_next_wk_on_expiry=False)
print(f"14:00 Cutoff: N={r_1400['n']}, WR={r_1400['wr']:.2f}%, PnL=Rs {r_1400['pnl']:,.2f}, PF={r_1400['pf']:.2f}, MaxDD=Rs {r_1400['dd']:,.2f}, Calmar={r_1400['calmar']:.2f}x")

print("\n=== 4. 14:00 CUTOFF + BE LOCKS ===")
for be in [60, 70, 75, 80, 100]:
    r = simulate(sigs_1400, be_trigger=be, use_next_wk_on_expiry=False)
    print(f"14:00 Cutoff + BE @ +{be} pts: N={r['n']}, WR={r['wr']:.2f}%, PnL=Rs {r['pnl']:,.2f}, PF={r['pf']:.2f}, MaxDD=Rs {r['dd']:,.2f}, Calmar={r['calmar']:.2f}x")

print("\n=== 5. 14:00 CUTOFF + MAX TRADES PER DAY ===")
for m in [1, 2, 3]:
    r = simulate(sigs_1400, be_trigger=None, max_trades_per_day=m)
    print(f"14:00 Cutoff + Max {m} Trade/Day: N={r['n']}, WR={r['wr']:.2f}%, PnL=Rs {r['pnl']:,.2f}, PF={r['pf']:.2f}, MaxDD=Rs {r['dd']:,.2f}, Calmar={r['calmar']:.2f}x")

print("\n=== 6. COMBINATION: 14:00 CUTOFF + EXPIRY-DAY NEXT WEEK ===")
r_combo = simulate(sigs_1400, be_trigger=None, use_next_wk_on_expiry=True)
print(f"14:00 + NextWk Expiry: N={r_combo['n']}, WR={r_combo['wr']:.2f}%, PnL=Rs {r_combo['pnl']:,.2f}, PF={r_combo['pf']:.2f}, MaxDD=Rs {r_combo['dd']:,.2f}, Calmar={r_combo['calmar']:.2f}x")

print("\n=== 7. COMBINATION: 14:00 CUTOFF + BE @ 80 + EXPIRY-DAY NEXT WEEK ===")
r_super = simulate(sigs_1400, be_trigger=80, use_next_wk_on_expiry=True)
print(f"14:00 + BE @ 80 + NextWk Expiry: N={r_super['n']}, WR={r_super['wr']:.2f}%, PnL=Rs {r_super['pnl']:,.2f}, PF={r_super['pf']:.2f}, MaxDD=Rs {r_super['dd']:,.2f}, Calmar={r_super['calmar']:.2f}x")
