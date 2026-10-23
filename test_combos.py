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

def evaluate_setup(eod_time, be_trigger, be_buffer, trail_dist=None):
    lot_size = 65
    slippage = 0.005
    trades = []
    daily_trades = {}
    
    for s_idx, sig in enumerate(raw_sigs):
        d_str = sig['date'].strftime('%Y-%m-%d')
        prior = daily_trades.get(d_str, [])
        if sig['entry_time'].time() > time(14, 0):
            continue
        if sig['entry_time'].time() >= eod_time:
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
        reason = 'EOD'
        
        for b_idx in range(len(highs)):
            ph = highs[b_idx]
            pl = lows[b_idx]
            dt = bar_dts[b_idx]
            if ph > max_fav:
                max_fav = ph
            
            if be_trigger is not None and max_fav >= entry_raw + be_trigger:
                be_level = entry_raw + be_buffer
                if be_level > curr_sl:
                    curr_sl = be_level
                
            if trail_dist is not None and max_fav >= entry_raw + be_trigger:
                t_sl = max_fav - trail_dist
                if t_sl > curr_sl:
                    curr_sl = t_sl
                
            hit_tp = (ph >= tp_prem)
            hit_sl = (pl <= curr_sl)
            hit_eod = (dt.time() >= eod_time)
            
            if hit_tp or hit_sl or hit_eod:
                if hit_tp:
                    exit_raw = tp_prem
                    reason = 'TP'
                elif hit_sl:
                    exit_raw = curr_sl
                    reason = 'BE' if curr_sl > initial_sl else 'SL'
                else:
                    exit_raw = closes[b_idx]
                    reason = 'EOD'
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
        
        t_rec = {'date': d_str, 'net': net, 'is_win': is_win, 'reason': reason}
        trades.append(t_rec)
        if d_str not in daily_trades:
            daily_trades[d_str] = []
        daily_trades[d_str].append(t_rec)
        
    df = pd.DataFrame(trades)
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
    return {'n': n, 'wr': wr, 'pnl': pnl, 'pf': pf, 'dd': dd, 'calmar': calmar}

combos = [
    ('Current: EOD 15:10, BE Lock @ +80 (+4 pts buffer)', time(15, 10), 80.0, 4.0, None),
    ('Option A: EOD 15:10, BE Lock @ +80 (+10 pts buffer)', time(15, 10), 80.0, 10.0, None),
    ('Option B: EOD 15:10, BE Lock @ +80 (+15 pts buffer)', time(15, 10), 80.0, 15.0, None),
    ('Option C: EOD 15:10, BE Lock @ +80 (+20 pts buffer)', time(15, 10), 80.0, 20.0, None),
    ('Option D: EOD 15:00, BE Lock @ +80 (+4 pts buffer)', time(15, 0), 80.0, 4.0, None),
    ('Option E: EOD 15:00, BE Lock @ +80 (+10 pts buffer)', time(15, 0), 80.0, 10.0, None),
    ('Option F: EOD 15:00, BE Lock @ +80 (+16 pts buffer)', time(15, 0), 80.0, 16.0, None),
    ('Option G: EOD 15:00, BE Lock @ +80 (+20 pts buffer)', time(15, 0), 80.0, 20.0, None),
    ('Option H: EOD 15:10, Trail by 10 pts after +80', time(15, 10), 80.0, 4.0, 10.0),
    ('Option I: EOD 15:10, Trail by 15 pts after +80', time(15, 10), 80.0, 4.0, 15.0),
    ('Option J: EOD 15:10, Trail by 20 pts after +80', time(15, 10), 80.0, 4.0, 20.0),
    ('Option K: EOD 15:00, Trail by 15 pts after +80', time(15, 0), 80.0, 4.0, 15.0),
]

print(f"{'CONFIGURATION':<50} | {'TRADES':<6} | {'WIN %':<7} | {'NET P&L':<13} | {'PF':<5} | {'MAX DD':<11} | {'CALMAR'}")
print('='*102)
for name, t_val, trig, buf, dist in combos:
    r = evaluate_setup(t_val, trig, buf, dist)
    print(f"{name:<50} | {r['n']:^6} | {r['wr']:5.2f}% | Rs {r['pnl']:10,.2f} | {r['pf']:4.2f} | Rs {r['dd']:9,.2f} | {r['calmar']:5.2f}x")
print('='*102)
