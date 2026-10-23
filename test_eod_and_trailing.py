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
cache = b.precompute_all_option_trajectories(raw_sigs, ['ATM'], ['current_weekly'])

def sim_trail(eod_close_time, be_trigger=80.0, be_buffer=4.0, trail_distance=None):
    lot_size = 65
    slippage = 0.005
    trades = []
    daily_trades = {}
    
    for s_idx, sig in enumerate(raw_sigs):
        d_str = sig['date'].strftime('%Y-%m-%d')
        prior = daily_trades.get(d_str, [])
        if sig['entry_time'].time() > time(14, 0):
            continue
        if sig['entry_time'].time() >= eod_close_time:
            continue
        if len(prior) == 1 and not prior[0]['is_win']:
            continue
        if len(prior) >= 2:
            continue
        
        tr = cache[(s_idx, 'ATM', 'current_weekly')]
        entry_raw = tr['entry_raw']
        fill_entry = tr['fill_entry']
        highs, lows, closes, bar_dts = tr['highs'], tr['lows'], tr['closes'], tr['bar_dts']
        if len(highs) == 0:
            continue
        
        initial_sl = max(0.5, entry_raw - 50.0)
        tp_prem = entry_raw + 200.0
        curr_sl = initial_sl
        max_fav = entry_raw
        exit_raw = closes[-1]
        
        for b_idx in range(len(highs)):
            ph = highs[b_idx]
            pl = lows[b_idx]
            dt = bar_dts[b_idx]
            if ph > max_fav:
                max_fav = ph
            
            # 1. BE Lock Buffer
            if be_trigger is not None and max_fav >= entry_raw + be_trigger:
                be_level = entry_raw + be_buffer
                if be_level > curr_sl:
                    curr_sl = be_level
                
            # 2. Continuous Trailing behind peak (if enabled)
            if trail_distance is not None and max_fav >= entry_raw + be_trigger:
                t_sl = max_fav - trail_distance
                if t_sl > curr_sl:
                    curr_sl = t_sl
                
            hit_tp = (ph >= tp_prem)
            hit_sl = (pl <= curr_sl)
            hit_eod = (dt.time() >= eod_close_time)
            
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
        is_win = (net > 0)
        
        t_rec = {'date': d_str, 'net': net, 'is_win': is_win}
        trades.append(t_rec)
        if d_str not in daily_trades:
            daily_trades[d_str] = []
        daily_trades[d_str].append(t_rec)
        
    df = pd.DataFrame(trades)
    n = len(df)
    if n == 0:
        return None
    wins = df['is_win'].sum()
    wr = (wins / n) * 100
    pnl = df['net'].sum()
    gw = df[df['net'] > 0]['net'].sum()
    gl = abs(df[df['net'] < 0]['net'].sum())
    pf = gw / gl if gl > 0 else 99
    cum = df['net'].cumsum()
    dd = (cum.cummax() - cum).max()
    calmar = pnl / dd if dd > 0 else 99
    return {'n': n, 'wr': wr, 'pnl': pnl, 'pf': pf, 'dd': dd, 'calmar': calmar}

print("="*85)
print("PART 1: DETAILED EOD CLOSE TIME SWEEP (14:00 to 15:20 IST)")
print("="*85)
for t_str, t_val in [
    ("14:00", time(14, 0)), ("14:15", time(14, 15)), ("14:30", time(14, 30)),
    ("14:45", time(14, 45)), ("15:00", time(15, 0)), ("15:05", time(15, 5)),
    ("15:10", time(15, 10)), ("15:15", time(15, 15)), ("15:20", time(15, 20))
]:
    r = sim_trail(t_val, be_trigger=80.0, be_buffer=4.0)
    print(f"EOD {t_str} | N={r['n']:<3} | WR={r['wr']:5.2f}% | Net PnL=Rs {r['pnl']:10,.2f} | PF={r['pf']:4.2f} | MaxDD=Rs {r['dd']:8,.2f} | Calmar={r['calmar']:5.2f}x")

print("\n" + "="*85)
print("PART 2: BE LOCK BUFFER SWEEP IN 4-20 RANGE (When LTP reaches Entry + 80 pts)")
print("="*85)
for buf in [4, 6, 8, 10, 12, 14, 16, 18, 20]:
    r = sim_trail(time(15, 10), be_trigger=80.0, be_buffer=buf)
    print(f"Buffer Entry+{buf:2d} pts (EOD 15:10) | WR={r['wr']:5.2f}% | Net PnL=Rs {r['pnl']:10,.2f} | PF={r['pf']:4.2f} | MaxDD=Rs {r['dd']:8,.2f} | Calmar={r['calmar']:5.2f}x")

print("\n" + "="*85)
print("PART 3: BE LOCK BUFFER SWEEP IN 4-20 RANGE (With EOD 15:00)")
print("="*85)
for buf in [4, 6, 8, 10, 12, 14, 16, 18, 20]:
    r = sim_trail(time(15, 0), be_trigger=80.0, be_buffer=buf)
    print(f"Buffer Entry+{buf:2d} pts (EOD 15:00) | WR={r['wr']:5.2f}% | Net PnL=Rs {r['pnl']:10,.2f} | PF={r['pf']:4.2f} | MaxDD=Rs {r['dd']:8,.2f} | Calmar={r['calmar']:5.2f}x")

print("\n" + "="*85)
print("PART 4: CONTINUOUS TRAILING SL IN 4-20 RANGE (Trail behind High once +80 pts reached)")
print("="*85)
for dist in [4, 6, 8, 10, 12, 14, 16, 18, 20]:
    r = sim_trail(time(15, 10), be_trigger=80.0, be_buffer=4.0, trail_distance=dist)
    print(f"Trail behind High by {dist:2d} pts | WR={r['wr']:5.2f}% | Net PnL=Rs {r['pnl']:10,.2f} | PF={r['pf']:4.2f} | MaxDD=Rs {r['dd']:8,.2f} | Calmar={r['calmar']:5.2f}x")

print("\n" + "="*85)
print("PART 5: EARLY TRAILING SL (Trail behind High once +40 pts reached by 4-20 pts)")
print("="*85)
for dist in [10, 15, 20]:
    r = sim_trail(time(15, 10), be_trigger=40.0, be_buffer=4.0, trail_distance=dist)
    print(f"Trigger +40, Trail by {dist:2d} pts | WR={r['wr']:5.2f}% | Net PnL=Rs {r['pnl']:10,.2f} | PF={r['pf']:4.2f} | MaxDD=Rs {r['dd']:8,.2f} | Calmar={r['calmar']:5.2f}x")
