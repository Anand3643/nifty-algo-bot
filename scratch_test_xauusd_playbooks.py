"""
Exact NIFTY Algo Bot Playbook Architecture Applied to XAUUSD (Gold)
Data: C:\\Users\\Admin\\Desktop\\stoks related\\yt\\mt5_data\\XAUUSD_M5.csv and XAUUSD_M15.csv

Playbooks evaluated:
1. Gap-Up R1 Polarity Bounce (BUY)
2. Gap-Down S1 Polarity Rejection (SELL)
3. R1 Resistance Reversal (SELL)
4. R2 Exhaustion Reversal (SELL)
5. Gap-and-Go Bearish ORB (SELL)
6. S1 Support Breakdown (SELL)
+ Bullish S1 Reversal, S2 Exhaustion, R1 Breakout

Staged 2-Lot Scale-Out Engine:
- Target 1 (1:2 RR): Book Lot 1
- SL on Lot 2: Move to Risk-Free Breakeven (+ buffer)
- Target 2 (1:4 RR): Book Lot 2 runner
"""

import os
import pandas as pd
import numpy as np
from datetime import time

DATA_DIR = r"C:\Users\Admin\Desktop\stoks related\yt\mt5_data"
M5_FILE = os.path.join(DATA_DIR, "XAUUSD_M5.csv")
M15_FILE = os.path.join(DATA_DIR, "XAUUSD_M15.csv")

def run_playbook_backtest(csv_path, tf_name="M5",
                          sl_dollars=5.0,
                          tp1_dollars=10.0,
                          tp2_dollars=20.0,
                          be_buf=0.30,
                          allow_all_directions=True,
                          orb_bars=3,
                          session_start_hour=8,
                          session_end_hour=21):
    
    df = pd.read_csv(csv_path)
    df['time'] = pd.to_datetime(df['time'])
    df = df.sort_values('time').reset_index(drop=True)
    df['date'] = df['time'].dt.date
    df['t_time'] = df['time'].dt.time
    df['hour'] = df['time'].dt.hour
    df['spread_dollar'] = df['spread'] * 0.01 if 'spread' in df.columns else 0.25
    
    # Compute daily levels (Previous Day High, Low, Close, Range)
    daily = df.groupby('date').agg(
        high=('high', 'max'),
        low=('low', 'min'),
        close=('close', 'last'),
        open=('open', 'first')
    ).reset_index()
    daily['range'] = daily['high'] - daily['low']
    daily = daily[daily['range'] > 2.0].reset_index(drop=True)
    
    daily['prev_h'] = daily['high'].shift(1)
    daily['prev_l'] = daily['low'].shift(1)
    daily['prev_c'] = daily['close'].shift(1)
    daily['prev_r'] = daily['range'].shift(1)
    daily = daily.dropna().reset_index(drop=True)
    
    # CPR & SPR calculations exactly as in nifty_algo_bot.py
    daily['pivot'] = (daily['prev_h'] + daily['prev_l'] + daily['prev_c']) / 3.0
    daily['bc'] = (daily['prev_h'] + daily['prev_l']) / 2.0
    daily['tc'] = (2.0 * daily['pivot']) - daily['bc']
    daily['cpr_top'] = np.maximum(daily['tc'], daily['bc'])
    daily['cpr_bot'] = np.minimum(daily['tc'], daily['bc'])
    
    # Multipliers
    daily['r1'] = daily['prev_c'] + (0.236 * daily['prev_r'])
    daily['r2'] = daily['prev_c'] + (0.500 * daily['prev_r'])
    daily['r3'] = daily['prev_c'] + (0.866 * daily['prev_r'])
    daily['r4'] = daily['prev_c'] + (1.333 * daily['prev_r'])
    
    daily['s1'] = daily['prev_c'] - (0.300 * daily['prev_r'])
    daily['s2'] = daily['prev_c'] - (0.550 * daily['prev_r'])
    daily['s3'] = daily['prev_c'] - (0.900 * daily['prev_r'])
    daily['s4'] = daily['prev_c'] - (1.314 * daily['prev_r'])
    
    daily_dict = daily.set_index('date').to_dict(orient='index')
    
    trades = []
    lot_size = 1.0 # 1 oz per unit (0.01 standard lot = $1/pt)
    
    # Iterate by trading day
    grouped = df.groupby('date')
    
    for dt, day_df in grouped:
        if dt not in daily_dict:
            continue
            
        lvl = daily_dict[dt]
        day_bars = day_df.to_dict(orient='records')
        if len(day_bars) < orb_bars + 2:
            continue
            
        orb_high = max(b['high'] for b in day_bars[:orb_bars])
        orb_low  = min(b['low'] for b in day_bars[:orb_bars])
        day_open = day_bars[0]['open']
        
        trades_today = 0
        in_trade = False
        pos = None
        
        for i in range(1, len(day_bars)):
            bar = day_bars[i]
            prev_bar = day_bars[i-1]
            b_hour = bar['hour']
            
            spot = bar['close']
            b_open = bar['open']
            b_high = bar['high']
            b_low = bar['low']
            b_range = b_high - b_low
            spread = bar['spread_dollar']
            
            # 1. POSITION MANAGEMENT
            if in_trade:
                is_buy = (pos['dir'] == "BUY")
                fill_entry = pos['fill_entry']
                
                # PHASE 1: Neither target hit yet
                if not pos['t1_hit']:
                    hit_sl = (b_low <= pos['sl']) if is_buy else (b_high >= pos['sl'])
                    hit_tp1 = (b_high >= pos['tp1']) if is_buy else (b_low <= pos['tp1'])
                    
                    if hit_sl and not hit_tp1:
                        # Full stop loss on 2 units
                        fill_exit = pos['sl']
                        pts = (fill_exit - fill_entry) if is_buy else (fill_entry - fill_exit)
                        total_pnl = pts * 2.0 * lot_size
                        trades.append({
                            'date': str(dt),
                            'entry_time': pos['entry_time'],
                            'exit_time': bar['time'],
                            'playbook': pos['playbook'],
                            'dir': pos['dir'],
                            'entry': fill_entry,
                            'exit1': fill_exit,
                            'exit2': fill_exit,
                            'pnl': total_pnl,
                            'pts1': pts,
                            'pts2': pts,
                            'result': 'FULL_SL'
                        })
                        in_trade = False
                        pos = None
                        trades_today += 1
                        continue
                        
                    elif hit_tp1:
                        # Target 1 Achieved (+1:2 RR)
                        pos['t1_hit'] = True
                        pos['exit1'] = pos['tp1']
                        pos['pts1'] = (pos['tp1'] - fill_entry) if is_buy else (fill_entry - pos['tp1'])
                        
                        # Instantly move SL on Lot 2 to Breakeven (+ buffer)
                        pos['sl'] = (fill_entry + be_buf) if is_buy else (fill_entry - be_buf)
                        
                        # Check if Target 2 hit in this same bar
                        hit_tp2 = (b_high >= pos['tp2']) if is_buy else (b_low <= pos['tp2'])
                        if hit_tp2:
                            pos['exit2'] = pos['tp2']
                            pos['pts2'] = (pos['tp2'] - fill_entry) if is_buy else (fill_entry - pos['tp2'])
                            total_pnl = (pos['pts1'] + pos['pts2']) * lot_size
                            trades.append({
                                'date': str(dt),
                                'entry_time': pos['entry_time'],
                                'exit_time': bar['time'],
                                'playbook': pos['playbook'],
                                'dir': pos['dir'],
                                'entry': fill_entry,
                                'exit1': pos['exit1'],
                                'exit2': pos['exit2'],
                                'pnl': total_pnl,
                                'pts1': pos['pts1'],
                                'pts2': pos['pts2'],
                                'result': 'TP1_AND_TP2'
                            })
                            in_trade = False
                            pos = None
                            trades_today += 1
                            continue
                            
                # PHASE 2: Target 1 already banked; managing Lot 2 Runner
                else:
                    hit_tp2 = (b_high >= pos['tp2']) if is_buy else (b_low <= pos['tp2'])
                    hit_be  = (b_low <= pos['sl']) if is_buy else (b_high >= pos['sl'])
                    
                    if hit_tp2:
                        pos['exit2'] = pos['tp2']
                        pos['pts2'] = (pos['tp2'] - fill_entry) if is_buy else (fill_entry - pos['tp2'])
                        total_pnl = (pos['pts1'] + pos['pts2']) * lot_size
                        trades.append({
                            'date': str(dt),
                            'entry_time': pos['entry_time'],
                            'exit_time': bar['time'],
                            'playbook': pos['playbook'],
                            'dir': pos['dir'],
                            'entry': fill_entry,
                            'exit1': pos['exit1'],
                            'exit2': pos['exit2'],
                            'pnl': total_pnl,
                            'pts1': pos['pts1'],
                            'pts2': pos['pts2'],
                            'result': 'TP1_AND_TP2'
                        })
                        in_trade = False
                        pos = None
                        trades_today += 1
                        continue
                    elif hit_be:
                        pos['exit2'] = pos['sl']
                        pos['pts2'] = (pos['sl'] - fill_entry) if is_buy else (fill_entry - pos['sl'])
                        total_pnl = (pos['pts1'] + pos['pts2']) * lot_size
                        trades.append({
                            'date': str(dt),
                            'entry_time': pos['entry_time'],
                            'exit_time': bar['time'],
                            'playbook': pos['playbook'],
                            'dir': pos['dir'],
                            'entry': fill_entry,
                            'exit1': pos['exit1'],
                            'exit2': pos['exit2'],
                            'pnl': total_pnl,
                            'pts1': pos['pts1'],
                            'pts2': pos['pts2'],
                            'result': 'TP1_AND_BE'
                        })
                        in_trade = False
                        pos = None
                        trades_today += 1
                        continue
                        
            # 2. CHECK ENTRY CONDITIONS
            if not in_trade:
                if trades_today >= 2:
                    continue
                if b_hour < session_start_hour or b_hour >= session_end_hour:
                    continue
                if b_range < 0.50:
                    continue
                    
                lower_wick = min(b_open, spot) - b_low
                upper_wick = b_high - max(b_open, spot)
                bull_body = (spot > b_open) and ((spot - b_open) >= 0.25 * b_range)
                bear_body = (spot < b_open) and ((b_open - spot) >= 0.25 * b_range)
                prev_c = prev_bar['close']
                
                # Signal logic from NIFTY Algo Bot
                r1_break = (prev_c <= lvl['r1']) and (spot > lvl['r1']) and bull_body
                s1_break = (prev_c >= lvl['s1']) and (spot < lvl['s1']) and bear_body
                
                tested_r1 = (b_high >= lvl['r1'] >= b_low) or (prev_bar['high'] >= lvl['r1'] and b_high >= lvl['r1'])
                r1_fade = tested_r1 and (spot < lvl['r1']) and (upper_wick >= 0.25 * b_range)
                
                tested_r2 = (b_high >= lvl['r2'])
                r2_fade = tested_r2 and (spot < lvl['r2']) and (upper_wick >= 0.25 * b_range)
                
                # Symmetrical Bullish Reversals
                tested_s1 = (b_low <= lvl['s1'] <= b_high) or (prev_bar['low'] <= lvl['s1'] and b_low <= lvl['s1'])
                s1_fade = tested_s1 and (spot > lvl['s1']) and (lower_wick >= 0.25 * b_range)
                
                tested_s2 = (b_low <= lvl['s2'])
                s2_fade = tested_s2 and (spot > lvl['s2']) and (lower_wick >= 0.25 * b_range)
                
                # Gap Retests
                gap_r1_retest = False
                gap_s1_retest = False
                if day_open >= lvl['r1']:
                    tested = (b_low <= lvl['r1'] <= b_high) or (b_low <= lvl['r1'])
                    gap_r1_retest = tested and (spot > lvl['r1']) and (lower_wick >= 0.25 * b_range)
                elif day_open <= lvl['s1']:
                    tested = (b_low <= lvl['s1'] <= b_high) or (b_high >= lvl['s1'])
                    gap_s1_retest = tested and (spot < lvl['s1']) and (upper_wick >= 0.25 * b_range)
                    
                # ORB
                gap_orb_pe = False
                gap_orb_ce = False
                if i >= orb_bars:
                    if day_open <= lvl['s1']:
                        gap_orb_pe = (prev_c >= orb_low) and (spot < orb_low) and bear_body
                    elif day_open >= lvl['r1']:
                        gap_orb_ce = (prev_c <= orb_high) and (spot > orb_high) and bull_body
                        
                c_dir = None
                c_pb = ""
                
                if gap_r1_retest:
                    c_dir = "BUY"; c_pb = "Gap-Up R1 Polarity Bounce"
                elif gap_s1_retest:
                    c_dir = "SELL"; c_pb = "Gap-Down S1 Polarity Rejection"
                elif r1_fade:
                    c_dir = "SELL"; c_pb = "R1 Resistance Reversal"
                elif r2_fade:
                    c_dir = "SELL"; c_pb = "R2 Exhaustion Reversal"
                elif gap_orb_pe:
                    c_dir = "SELL"; c_pb = "Gap-and-Go Bearish ORB"
                elif s1_break:
                    c_dir = "SELL"; c_pb = "S1 Support Breakdown"
                elif allow_all_directions:
                    if s1_fade:
                        c_dir = "BUY"; c_pb = "S1 Support Reversal"
                    elif s2_fade:
                        c_dir = "BUY"; c_pb = "S2 Exhaustion Reversal"
                    elif r1_break:
                        c_dir = "BUY"; c_pb = "R1 Breakout"
                    elif gap_orb_ce:
                        c_dir = "BUY"; c_pb = "Gap-and-Go Bullish ORB"
                        
                if c_dir:
                    entry_price = (spot + spread) if c_dir == "BUY" else spot
                    pos = {
                        'playbook': c_pb,
                        'dir': c_dir,
                        'entry_time': bar['time'],
                        'fill_entry': entry_price,
                        'sl': (entry_price - sl_dollars) if c_dir == "BUY" else (entry_price + sl_dollars),
                        'tp1': (entry_price + tp1_dollars) if c_dir == "BUY" else (entry_price - tp1_dollars),
                        'tp2': (entry_price + tp2_dollars) if c_dir == "BUY" else (entry_price - tp2_dollars),
                        't1_hit': False,
                        'exit1': 0.0,
                        'exit2': 0.0,
                        'pts1': 0.0,
                        'pts2': 0.0
                    }
                    in_trade = True
                    
    tdf = pd.DataFrame(trades)
    return tdf

if __name__ == '__main__':
    print("Testing M15 XAUUSD with Bot Playbooks...")
    tdf15 = run_playbook_backtest(M15_FILE, tf_name="M15", sl_dollars=6.0, tp1_dollars=12.0, tp2_dollars=24.0)
    print(f"Total M15 trades: {len(tdf15)}")
    if len(tdf15) > 0:
        wins = tdf15[tdf15['pnl'] > 0]
        losses = tdf15[tdf15['pnl'] < 0]
        wr = len(wins) / len(tdf15) * 100
        gross_w = wins['pnl'].sum()
        gross_l = abs(losses['pnl'].sum())
        pf = gross_w / gross_l if gross_l > 0 else 999
        print(f"Net PnL: ${tdf15['pnl'].sum():.2f} | Win Rate: {wr:.1f}% | PF: {pf:.2f}")
        print("Playbook breakdown:\n", tdf15.groupby('playbook').agg(trades=('pnl', 'count'), pnl=('pnl', 'sum'), wr=('pnl', lambda x: (x > 0).mean() * 100)))
        print("Result breakdown:\n", tdf15['result'].value_counts())
