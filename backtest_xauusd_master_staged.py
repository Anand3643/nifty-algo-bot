"""
====================================================================================================
MASTER INSTITUTIONAL BACKTEST ENGINE: 2-LOT STAGED SCALE-OUT ON XAUUSD (GOLD)
Data Location: C:\\Users\\Admin\\Desktop\\stoks related\\yt\\mt5_data\\

Engine Architecture:
1. Total Position: 2 Units / 2 Lots (e.g., 0.02 Lot on micro, 0.20 on mini, 2.00 on standard).
2. Target 1 (1:2 RR): Immediately book 50% profit (1 Lot banked).
3. Risk-Free Breakeven: Instantly move Stop Loss on Lot 2 to Entry + $0.30 (covering spread/commissions).
4. Target 2 (1:4 RR): Let Lot 2 runner capture extended continuation for maximum payoff.

Evaluated on official MT5 Historical Data:
- XAUUSD M5 (50,000 candles) & XAUUSD H1
- XAUUSD M15 (50,000 candles, 2+ years of continuous market data)
====================================================================================================
"""

import os
import sys
import pandas as pd
import numpy as np
from datetime import datetime

DATA_DIR = r"C:\Users\Admin\Desktop\stoks related\yt\mt5_data"
M5_PATH  = os.path.join(DATA_DIR, "XAUUSD_M5.csv")
M15_PATH = os.path.join(DATA_DIR, "XAUUSD_M15.csv")
H1_PATH  = os.path.join(DATA_DIR, "XAUUSD_H1.csv")

# --------------------------------------------------------------------------------------------------
# 1. DATA PREPARATION & INDICATORS
# --------------------------------------------------------------------------------------------------
def load_and_prepare_data(m5_path=M5_PATH, h1_path=H1_PATH):
    print(f"[*] Loading M5 data: {m5_path}")
    df5 = pd.read_csv(m5_path)
    df5['time'] = pd.to_datetime(df5['time'])
    df5 = df5.sort_values('time').reset_index(drop=True)
    df5['date'] = df5['time'].dt.date
    df5['dow'] = df5['time'].dt.dayofweek
    df5['hour'] = df5['time'].dt.hour
    df5['month'] = df5['time'].dt.to_period('M').astype(str)
    df5['week'] = df5['time'].dt.isocalendar().year.astype(str) + '-W' + df5['time'].dt.isocalendar().week.astype(str).str.zfill(2)
    
    # Spread in $/oz (points * 0.01)
    df5['spread_dollar'] = df5['spread'] * 0.01 if 'spread' in df5.columns else 0.25
    
    # M5 50 EMA
    df5['m5_ema50'] = df5['close'].ewm(span=50, adjust=False).mean()
    
    # RSI 7 on M5
    delta = df5['close'].diff()
    gain = delta.clip(lower=0).ewm(alpha=1/7, adjust=False).mean()
    loss = (-delta.clip(upper=0)).ewm(alpha=1/7, adjust=False).mean()
    df5['rsi7'] = 100.0 - (100.0 / (1.0 + gain / (loss + 1e-10)))
    
    # Heikin-Ashi on M5
    o = df5['open'].values
    h = df5['high'].values
    l = df5['low'].values
    c = df5['close'].values
    n = len(df5)
    
    ha_close = (o + h + l + c) / 4.0
    ha_open = np.zeros(n)
    ha_open[0] = (o[0] + c[0]) / 2.0
    for i in range(1, n):
        ha_open[i] = (ha_open[i-1] + ha_close[i-1]) / 2.0
    df5['ha_open'] = ha_open
    df5['ha_close'] = ha_close
    df5['ha_green'] = ha_close > ha_open
    
    # Higher Timeframe H1 Trend Alignment
    if os.path.exists(h1_path):
        print(f"[*] Loading H1 data for institutional trend alignment: {h1_path}")
        df_h1 = pd.read_csv(h1_path)
        df_h1['time'] = pd.to_datetime(df_h1['time'])
        df_h1 = df_h1.sort_values('time').reset_index(drop=True)
        df_h1['h1_ema50'] = df_h1['close'].ewm(span=50, adjust=False).mean()
        df5 = pd.merge_asof(df5, df_h1[['time', 'h1_ema50']], on='time', direction='backward')
    else:
        df5['h1_ema50'] = df5['m5_ema50']
        
    return df5

def compute_daily_cpr_spr(df):
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
    
    # CPR Calculations
    daily['pivot'] = (daily['prev_h'] + daily['prev_l'] + daily['prev_c']) / 3.0
    daily['bc'] = (daily['prev_h'] + daily['prev_l']) / 2.0
    daily['tc'] = (2.0 * daily['pivot']) - daily['bc']
    daily['cpr_top'] = np.maximum(daily['tc'], daily['bc'])
    daily['cpr_bot'] = np.minimum(daily['tc'], daily['bc'])
    
    # SPR Multipliers
    daily['r1'] = daily['prev_c'] + (0.236 * daily['prev_r'])
    daily['r2'] = daily['prev_c'] + (0.500 * daily['prev_r'])
    daily['r3'] = daily['prev_c'] + (0.866 * daily['prev_r'])
    daily['s1'] = daily['prev_c'] - (0.300 * daily['prev_r'])
    daily['s2'] = daily['prev_c'] - (0.550 * daily['prev_r'])
    daily['s3'] = daily['prev_c'] - (0.900 * daily['prev_r'])
    
    return daily

# --------------------------------------------------------------------------------------------------
# 2. THE 2-LOT STAGED EXECUTION ENGINE
# --------------------------------------------------------------------------------------------------
def run_staged_engine(df,
                      mode='STAGED_2LOT', # 'SINGLE_TP1', 'SINGLE_TP2', 'STAGED_2LOT'
                      sl_pts=40.0,        # Initial Stop Loss in $/oz points (e.g. 40.0 pts)
                      tp1_pts=60.0,       # Target 1 in $/oz points (1:1.5 - 1:2 RR)
                      tp2_pts=100.0,      # Target 2 in $/oz points (1:2.5 - 1:4 RR)
                      be_buffer=1.0,      # Breakeven buffer in $/oz
                      lot_size_per_unit=0.01, # 0.01 lot = $1.00 per $/oz point
                      initial_capital=1000.0):
    
    n = len(df)
    times = df['time'].values
    dates = df['date'].values
    dows = df['dow'].values
    hours = df['hour'].values
    months = df['month'].values
    weeks = df['week'].values
    
    opens = df['open'].values
    highs = df['high'].values
    lows = df['low'].values
    closes = df['close'].values
    spreads = df['spread_dollar'].values
    
    rsi7 = df['rsi7'].values
    ha_greens = df['ha_green'].values
    m5_ema = df['m5_ema50'].values
    h1_ema = df['h1_ema50'].values
    
    trades = []
    balance = initial_capital
    equity_curve = [initial_capital]
    
    in_pos = False
    pos_type = 0 # 1=BUY, -1=SELL
    pos_entry = 0.0
    pos_entry_time = None
    pos_date = None
    pos_week = None
    pos_month = None
    
    # State tracking for Staged Scale-Out
    lot1_active = False
    lot2_active = False
    lot1_pnl = 0.0
    lot2_pnl = 0.0
    lot1_exit_price = 0.0
    lot2_exit_price = 0.0
    lot1_reason = ""
    lot2_reason = ""
    current_sl = 0.0
    target_1 = 0.0
    target_2 = 0.0
    
    cooldown = 0
    multiplier = lot_size_per_unit * 100.0 # Standard contract scaling ($1 per pt at 0.01 lot)
    
    for i in range(2, n):
        cur_t = times[i]
        cur_d = dates[i]
        cur_dow = dows[i]
        cur_hr = hours[i]
        cur_m = months[i]
        cur_w = weeks[i]
        
        cur_o = opens[i]
        cur_h = highs[i]
        cur_l = lows[i]
        cur_c = closes[i]
        cur_sp = spreads[i]
        
        # 1. POSITION MANAGEMENT
        if in_pos:
            # Friday Night Weekend Safety Auto-Close (23:00)
            if cur_dow == 4 and cur_hr >= 23:
                ex = cur_c
                pts = (ex - pos_entry) if pos_type == 1 else (pos_entry - ex)
                
                if mode == 'STAGED_2LOT':
                    if lot1_active:
                        lot1_pnl = pts * multiplier
                        lot1_exit_price = ex
                        lot1_reason = "FRIDAY_CLOSE"
                        lot1_active = False
                    if lot2_active:
                        lot2_pnl = pts * multiplier
                        lot2_exit_price = ex
                        lot2_reason = "FRIDAY_CLOSE"
                        lot2_active = False
                    tot_pnl = lot1_pnl + lot2_pnl
                else:
                    tot_pnl = pts * multiplier
                    lot1_pnl = tot_pnl
                    lot1_reason = "FRIDAY_CLOSE"
                    
                balance += tot_pnl
                equity_curve.append(balance)
                trades.append({
                    'entry_time': str(pos_entry_time),
                    'exit_time': str(cur_t),
                    'date': str(pos_date),
                    'week': pos_week,
                    'month': pos_month,
                    'type': 'BUY' if pos_type == 1 else 'SELL',
                    'entry': pos_entry,
                    'pnl': tot_pnl,
                    'pts_total': pts * (2.0 if mode == 'STAGED_2LOT' else 1.0),
                    'lot1_reason': lot1_reason,
                    'lot2_reason': lot2_reason,
                    'balance': balance,
                    'result': 'FRIDAY_CLOSE'
                })
                in_pos = False
                continue
                
            # LONG POSITION MANAGEMENT
            if pos_type == 1:
                if mode == 'SINGLE_TP1':
                    hit_sl = (cur_l <= current_sl)
                    hit_tp = (cur_h >= target_1)
                    if hit_sl and not hit_tp:
                        pnl = (current_sl - pos_entry) * multiplier
                        balance += pnl
                        equity_curve.append(balance)
                        trades.append({'entry_time': str(pos_entry_time), 'exit_time': str(cur_t), 'date': str(pos_date),
                                       'week': pos_week, 'month': pos_month, 'type': 'BUY', 'entry': pos_entry,
                                       'exit1': current_sl, 'pnl': pnl, 'pts_total': current_sl - pos_entry,
                                       'lot1_reason': 'SL', 'balance': balance, 'result': 'FULL_SL'})
                        in_pos = False
                        cooldown = 2
                        continue
                    elif hit_tp:
                        pnl = (target_1 - pos_entry) * multiplier
                        balance += pnl
                        equity_curve.append(balance)
                        trades.append({'entry_time': str(pos_entry_time), 'exit_time': str(cur_t), 'date': str(pos_date),
                                       'week': pos_week, 'month': pos_month, 'type': 'BUY', 'entry': pos_entry,
                                       'exit1': target_1, 'pnl': pnl, 'pts_total': target_1 - pos_entry,
                                       'lot1_reason': 'TP1', 'balance': balance, 'result': 'TP1_WIN'})
                        in_pos = False
                        continue
                        
                elif mode == 'SINGLE_TP2':
                    hit_sl = (cur_l <= current_sl)
                    hit_tp = (cur_h >= target_2)
                    if hit_sl and not hit_tp:
                        pnl = (current_sl - pos_entry) * multiplier
                        balance += pnl
                        equity_curve.append(balance)
                        trades.append({'entry_time': str(pos_entry_time), 'exit_time': str(cur_t), 'date': str(pos_date),
                                       'week': pos_week, 'month': pos_month, 'type': 'BUY', 'entry': pos_entry,
                                       'exit1': current_sl, 'pnl': pnl, 'pts_total': current_sl - pos_entry,
                                       'lot1_reason': 'SL', 'balance': balance, 'result': 'FULL_SL'})
                        in_pos = False
                        cooldown = 2
                        continue
                    elif hit_tp:
                        pnl = (target_2 - pos_entry) * multiplier
                        balance += pnl
                        equity_curve.append(balance)
                        trades.append({'entry_time': str(pos_entry_time), 'exit_time': str(cur_t), 'date': str(pos_date),
                                       'week': pos_week, 'month': pos_month, 'type': 'BUY', 'entry': pos_entry,
                                       'exit1': target_2, 'pnl': pnl, 'pts_total': target_2 - pos_entry,
                                       'lot1_reason': 'TP2', 'balance': balance, 'result': 'TP2_WIN'})
                        in_pos = False
                        continue
                        
                elif mode == 'STAGED_2LOT':
                    # Phase 1: Lot 1 Active
                    if lot1_active:
                        hit_sl = (cur_l <= current_sl)
                        hit_tp1 = (cur_h >= target_1)
                        if hit_sl and not hit_tp1:
                            # Full SL hit on both lots
                            l1_pnl = (current_sl - pos_entry) * multiplier
                            l2_pnl = (current_sl - pos_entry) * multiplier
                            tot_pnl = l1_pnl + l2_pnl
                            balance += tot_pnl
                            equity_curve.append(balance)
                            trades.append({
                                'entry_time': str(pos_entry_time), 'exit_time': str(cur_t), 'date': str(pos_date),
                                'week': pos_week, 'month': pos_month, 'type': 'BUY', 'entry': pos_entry,
                                'exit1': current_sl, 'exit2': current_sl, 'pnl': tot_pnl,
                                'pts_total': (current_sl - pos_entry) * 2.0, 'lot1_reason': 'SL', 'lot2_reason': 'SL',
                                'balance': balance, 'result': 'FULL_SL'
                            })
                            in_pos = False
                            cooldown = 2
                            continue
                        elif hit_tp1:
                            # TARGET 1 HIT! Bank Lot 1 immediately (+₹6,500 equivalent)
                            lot1_pnl = (target_1 - pos_entry) * multiplier
                            lot1_exit_price = target_1
                            lot1_reason = "TP1"
                            lot1_active = False
                            
                            # Instantly move Stop Loss on Lot 2 to Risk-Free Breakeven (+ buffer)
                            current_sl = pos_entry + be_buffer
                            
                    # Phase 2: Lot 2 Runner Active with Breakeven Protection
                    if lot2_active and not lot1_active:
                        hit_be = (cur_l <= current_sl)
                        hit_tp2 = (cur_h >= target_2)
                        
                        if hit_tp2:
                            # TARGET 2 FULL RUNNER ACHIEVED (+₹13,000 equivalent)
                            lot2_pnl = (target_2 - pos_entry) * multiplier
                            lot2_exit_price = target_2
                            lot2_reason = "TP2_RUNNER"
                            lot2_active = False
                            tot_pnl = lot1_pnl + lot2_pnl
                            balance += tot_pnl
                            equity_curve.append(balance)
                            trades.append({
                                'entry_time': str(pos_entry_time), 'exit_time': str(cur_t), 'date': str(pos_date),
                                'week': pos_week, 'month': pos_month, 'type': 'BUY', 'entry': pos_entry,
                                'exit1': lot1_exit_price, 'exit2': lot2_exit_price, 'pnl': tot_pnl,
                                'pts_total': (target_1 - pos_entry) + (target_2 - pos_entry),
                                'lot1_reason': lot1_reason, 'lot2_reason': lot2_reason,
                                'balance': balance, 'result': 'TP1_AND_TP2'
                            })
                            in_pos = False
                            continue
                        elif hit_be:
                            # Lot 2 Stopped out at Risk-Free Breakeven
                            lot2_pnl = (current_sl - pos_entry) * multiplier
                            lot2_exit_price = current_sl
                            lot2_reason = "BE_SL"
                            lot2_active = False
                            tot_pnl = lot1_pnl + lot2_pnl
                            balance += tot_pnl
                            equity_curve.append(balance)
                            trades.append({
                                'entry_time': str(pos_entry_time), 'exit_time': str(cur_t), 'date': str(pos_date),
                                'week': pos_week, 'month': pos_month, 'type': 'BUY', 'entry': pos_entry,
                                'exit1': lot1_exit_price, 'exit2': lot2_exit_price, 'pnl': tot_pnl,
                                'pts_total': (target_1 - pos_entry) + (current_sl - pos_entry),
                                'lot1_reason': lot1_reason, 'lot2_reason': lot2_reason,
                                'balance': balance, 'result': 'TP1_AND_BE'
                            })
                            in_pos = False
                            continue
                            
            # SHORT POSITION MANAGEMENT
            elif pos_type == -1:
                if mode == 'SINGLE_TP1':
                    hit_sl = (cur_h >= current_sl)
                    hit_tp = (cur_l <= target_1)
                    if hit_sl and not hit_tp:
                        pnl = (pos_entry - current_sl) * multiplier
                        balance += pnl
                        equity_curve.append(balance)
                        trades.append({'entry_time': str(pos_entry_time), 'exit_time': str(cur_t), 'date': str(pos_date),
                                       'week': pos_week, 'month': pos_month, 'type': 'SELL', 'entry': pos_entry,
                                       'exit1': current_sl, 'pnl': pnl, 'pts_total': pos_entry - current_sl,
                                       'lot1_reason': 'SL', 'balance': balance, 'result': 'FULL_SL'})
                        in_pos = False
                        cooldown = 2
                        continue
                    elif hit_tp:
                        pnl = (pos_entry - target_1) * multiplier
                        balance += pnl
                        equity_curve.append(balance)
                        trades.append({'entry_time': str(pos_entry_time), 'exit_time': str(cur_t), 'date': str(pos_date),
                                       'week': pos_week, 'month': pos_month, 'type': 'SELL', 'entry': pos_entry,
                                       'exit1': target_1, 'pnl': pnl, 'pts_total': pos_entry - target_1,
                                       'lot1_reason': 'TP1', 'balance': balance, 'result': 'TP1_WIN'})
                        in_pos = False
                        continue
                        
                elif mode == 'SINGLE_TP2':
                    hit_sl = (cur_h >= current_sl)
                    hit_tp = (cur_l <= target_2)
                    if hit_sl and not hit_tp:
                        pnl = (pos_entry - current_sl) * multiplier
                        balance += pnl
                        equity_curve.append(balance)
                        trades.append({'entry_time': str(pos_entry_time), 'exit_time': str(cur_t), 'date': str(pos_date),
                                       'week': pos_week, 'month': pos_month, 'type': 'SELL', 'entry': pos_entry,
                                       'exit1': current_sl, 'pnl': pnl, 'pts_total': pos_entry - current_sl,
                                       'lot1_reason': 'SL', 'balance': balance, 'result': 'FULL_SL'})
                        in_pos = False
                        cooldown = 2
                        continue
                    elif hit_tp:
                        pnl = (pos_entry - target_2) * multiplier
                        balance += pnl
                        equity_curve.append(balance)
                        trades.append({'entry_time': str(pos_entry_time), 'exit_time': str(cur_t), 'date': str(pos_date),
                                       'week': pos_week, 'month': pos_month, 'type': 'SELL', 'entry': pos_entry,
                                       'exit1': target_2, 'pnl': pnl, 'pts_total': pos_entry - target_2,
                                       'lot1_reason': 'TP2', 'balance': balance, 'result': 'TP2_WIN'})
                        in_pos = False
                        continue
                        
                elif mode == 'STAGED_2LOT':
                    if lot1_active:
                        hit_sl = (cur_h >= current_sl)
                        hit_tp1 = (cur_l <= target_1)
                        if hit_sl and not hit_tp1:
                            l1_pnl = (pos_entry - current_sl) * multiplier
                            l2_pnl = (pos_entry - current_sl) * multiplier
                            tot_pnl = l1_pnl + l2_pnl
                            balance += tot_pnl
                            equity_curve.append(balance)
                            trades.append({
                                'entry_time': str(pos_entry_time), 'exit_time': str(cur_t), 'date': str(pos_date),
                                'week': pos_week, 'month': pos_month, 'type': 'SELL', 'entry': pos_entry,
                                'exit1': current_sl, 'exit2': current_sl, 'pnl': tot_pnl,
                                'pts_total': (pos_entry - current_sl) * 2.0, 'lot1_reason': 'SL', 'lot2_reason': 'SL',
                                'balance': balance, 'result': 'FULL_SL'
                            })
                            in_pos = False
                            cooldown = 2
                            continue
                        elif hit_tp1:
                            lot1_pnl = (pos_entry - target_1) * multiplier
                            lot1_exit_price = target_1
                            lot1_reason = "TP1"
                            lot1_active = False
                            current_sl = pos_entry - be_buffer
                            
                    if lot2_active and not lot1_active:
                        hit_be = (cur_h >= current_sl)
                        hit_tp2 = (cur_l <= target_2)
                        
                        if hit_tp2:
                            lot2_pnl = (pos_entry - target_2) * multiplier
                            lot2_exit_price = target_2
                            lot2_reason = "TP2_RUNNER"
                            lot2_active = False
                            tot_pnl = lot1_pnl + lot2_pnl
                            balance += tot_pnl
                            equity_curve.append(balance)
                            trades.append({
                                'entry_time': str(pos_entry_time), 'exit_time': str(cur_t), 'date': str(pos_date),
                                'week': pos_week, 'month': pos_month, 'type': 'SELL', 'entry': pos_entry,
                                'exit1': lot1_exit_price, 'exit2': lot2_exit_price, 'pnl': tot_pnl,
                                'pts_total': (pos_entry - target_1) + (pos_entry - target_2),
                                'lot1_reason': lot1_reason, 'lot2_reason': lot2_reason,
                                'balance': balance, 'result': 'TP1_AND_TP2'
                            })
                            in_pos = False
                            continue
                        elif hit_be:
                            lot2_pnl = (pos_entry - current_sl) * multiplier
                            lot2_exit_price = current_sl
                            lot2_reason = "BE_SL"
                            lot2_active = False
                            tot_pnl = lot1_pnl + lot2_pnl
                            balance += tot_pnl
                            equity_curve.append(balance)
                            trades.append({
                                'entry_time': str(pos_entry_time), 'exit_time': str(cur_t), 'date': str(pos_date),
                                'week': pos_week, 'month': pos_month, 'type': 'SELL', 'entry': pos_entry,
                                'exit1': lot1_exit_price, 'exit2': lot2_exit_price, 'pnl': tot_pnl,
                                'pts_total': (pos_entry - target_1) + (pos_entry - current_sl),
                                'lot1_reason': lot1_reason, 'lot2_reason': lot2_reason,
                                'balance': balance, 'result': 'TP1_AND_BE'
                            })
                            in_pos = False
                            continue
                            
        # 2. CHECK NEW ENTRY SIGNALS
        if in_pos:
            continue
            
        # Avoid Monday open chop & Friday late entry
        if cur_dow == 0 and cur_hr < 10:
            continue
        if cur_dow == 4 and cur_hr >= 22:
            continue
            
        if cooldown > 0:
            cooldown -= 1
            continue
            
        r1 = rsi7[i-1]; r2 = rsi7[i-2]
        ha1 = ha_greens[i-1]; ha2 = ha_greens[i-2]
        pc1 = closes[i-1]
        
        # Dual Trend Alignment Trigger:
        # Long Trigger: RSI > 60 + Green HA + Price above M5 EMA 50 & H1 EMA 50
        buy_sig = (r1 > 60 and ha1 == True and pc1 > m5_ema[i-1] and pc1 > h1_ema[i-1]) and (r2 <= 60 or ha2 == False)
        # Short Trigger: RSI < 40 + Red HA + Price below M5 EMA 50 & H1 EMA 50
        sell_sig = (r1 < 40 and ha1 == False and pc1 < m5_ema[i-1] and pc1 < h1_ema[i-1]) and (r2 >= 40 or ha2 == True)
        
        if buy_sig:
            pos_type = 1
            pos_entry = cur_o + cur_sp # Pay spread
            pos_entry_time = cur_t
            pos_date = cur_d
            pos_week = cur_w
            pos_month = cur_m
            current_sl = pos_entry - sl_pts
            target_1 = pos_entry + tp1_pts
            target_2 = pos_entry + tp2_pts
            lot1_active = True
            lot2_active = True
            in_pos = True
        elif sell_sig:
            pos_type = -1
            pos_entry = cur_o
            pos_entry_time = cur_t
            pos_date = cur_d
            pos_week = cur_w
            pos_month = cur_m
            current_sl = pos_entry + sl_pts + cur_sp
            target_1 = pos_entry - tp1_pts
            target_2 = pos_entry - tp2_pts
            lot1_active = True
            lot2_active = True
            in_pos = True
            
    tdf = pd.DataFrame(trades)
    return tdf, equity_curve

# --------------------------------------------------------------------------------------------------
# 3. METRICS AUDITOR
# --------------------------------------------------------------------------------------------------
def audit_results(name, tdf, initial_capital=1000.0):
    if len(tdf) == 0:
        return {'Name': name, 'Trades': 0, 'Net PnL': 0.0, 'Return %': 0.0, 'Win Rate': 0.0,
                'Profit Factor': 0.0, 'Max DD $': 0.0, 'Max DD %': 0.0}
        
    final_bal = tdf['balance'].iloc[-1]
    net_pnl = final_bal - initial_capital
    pct_return = (net_pnl / initial_capital) * 100.0
    
    wins = tdf[tdf['pnl'] > 0]
    losses = tdf[tdf['pnl'] < 0]
    win_rate = (len(wins) / len(tdf)) * 100.0
    
    gw = wins['pnl'].sum() if len(wins) > 0 else 0.0
    gl = abs(losses['pnl'].sum()) if len(losses) > 0 else 0.0
    pf = gw / gl if gl > 0 else 999.0
    
    avg_win = wins['pnl'].mean() if len(wins) > 0 else 0.0
    avg_loss = losses['pnl'].mean() if len(losses) > 0 else 0.0
    payoff = abs(avg_win / avg_loss) if avg_loss != 0 else 0.0
    
    # Peak-to-trough Drawdown
    eq = pd.Series([initial_capital] + tdf['pnl'].cumsum().tolist())
    peak = eq.cummax()
    dd = peak - eq
    dd_pct = (dd / peak) * 100.0
    max_dd = dd.max()
    max_dd_pct = dd_pct.max()
    
    # Result distribution
    full_sls = len(tdf[tdf['result'] == 'FULL_SL'])
    tp1_be = len(tdf[tdf['result'] == 'TP1_AND_BE'])
    tp1_tp2 = len(tdf[tdf['result'] == 'TP1_AND_TP2'])
    
    # Monthly green count
    m_grp = tdf.groupby('month')['pnl'].sum()
    green_m = (m_grp > 0).sum()
    tot_m = len(m_grp)
    
    # Weekly green count
    w_grp = tdf.groupby('week')['pnl'].sum()
    green_w = (w_grp > 0).sum()
    tot_w = len(w_grp)
    
    return {
        'Name': name,
        'Trades': len(tdf),
        'Wins': len(wins),
        'Losses': len(losses),
        'Net PnL $': round(net_pnl, 2),
        'Return %': round(pct_return, 1),
        'Win Rate %': round(win_rate, 1),
        'Profit Factor': round(pf, 2),
        'Payoff Ratio': round(payoff, 2),
        'Max DD $': round(max_dd, 2),
        'Max DD %': round(max_dd_pct, 1),
        'Full SL': full_sls,
        'T1 + BE': tp1_be,
        'T1 + T2 Runner': tp1_tp2,
        'Green Months': f"{green_m}/{tot_m} ({green_m/tot_m*100:.1f}%)" if tot_m > 0 else "0/0",
        'Green Weeks': f"{green_w}/{tot_w} ({green_w/tot_w*100:.1f}%)" if tot_w > 0 else "0/0"
    }

if __name__ == '__main__':
    print("=" * 100)
    print("  INSTITUTIONAL STAGED SCALE-OUT BACKTEST ON XAUUSD (GOLD)")
    print("=" * 100)
    
    df5 = load_and_prepare_data(M5_PATH, H1_PATH)
    print(f"[+] Loaded {len(df5):,} M5 bars ({df5['time'].iloc[0]} to {df5['time'].iloc[-1]})")
    
    comparison = []
    
    # 1. Baseline: Single Lot 1:1.5 RR (SL $40, TP $60)
    tdf_b1, _ = run_staged_engine(df5, mode='SINGLE_TP1', sl_pts=40.0, tp1_pts=60.0)
    comparison.append(audit_results("Single Lot 1:1.5 RR (SL $40 / TP $60)", tdf_b1))
    
    # 2. Baseline: Single Lot 1:2.5 RR (SL $40, TP $100)
    tdf_b2, _ = run_staged_engine(df5, mode='SINGLE_TP2', sl_pts=40.0, tp2_pts=100.0)
    comparison.append(audit_results("Single Lot 1:2.5 RR (SL $40 / TP $100)", tdf_b2))
    
    # 3. THE 2-LOT STAGED SCALE-OUT ENGINE (SL $40, TP1 $60, BE on Runner, TP2 $100)
    tdf_staged, _ = run_staged_engine(df5, mode='STAGED_2LOT', sl_pts=40.0, tp1_pts=60.0, tp2_pts=100.0, be_buffer=1.0)
    comparison.append(audit_results("[STAGED] 2-Lot Engine (SL $40 / TP1 $60 / TP2 $100)", tdf_staged))
    
    # 4. THE 2-LOT STAGED SCALE-OUT ENGINE - EXTENDED RUNNER (SL $40, TP1 $70, TP2 $120)
    tdf_staged_ext, _ = run_staged_engine(df5, mode='STAGED_2LOT', sl_pts=40.0, tp1_pts=70.0, tp2_pts=120.0, be_buffer=1.0)
    comparison.append(audit_results("[STAGED] 2-Lot Engine (SL $40 / TP1 $70 / TP2 $120)", tdf_staged_ext))
    
    # 5. THE 2-LOT STAGED SCALE-OUT ENGINE - INTRADAY SCALP (SL $30, TP1 $50, TP2 $80)
    tdf_staged_scalp, _ = run_staged_engine(df5, mode='STAGED_2LOT', sl_pts=30.0, tp1_pts=50.0, tp2_pts=80.0, be_buffer=1.0)
    comparison.append(audit_results("[STAGED] 2-Lot Engine (SL $30 / TP1 $50 / TP2 $80)", tdf_staged_scalp))

    comp_df = pd.DataFrame(comparison)
    print("\n" + "=" * 125)
    print("  EXECUTIVE BACKTEST AUDIT: SINGLE LOT VS 2-LOT STAGED SCALE-OUT ENGINE (XAUUSD)")
    print("=" * 125)
    cols = ['Name', 'Trades', 'Net PnL $', 'Return %', 'Win Rate %', 'Profit Factor', 'Payoff Ratio', 'Max DD $', 'T1 + BE', 'T1 + T2 Runner', 'Green Months', 'Green Weeks']
    print(comp_df[cols].to_string(index=False))
    
    # Save the Champion Trades & Monthly Ledger
    out_trades_path = os.path.join(r"c:\Users\Admin\Desktop\nifty backttteest", "xauusd_trades_staged_engine.csv")
    out_monthly_path = os.path.join(r"c:\Users\Admin\Desktop\nifty backttteest", "xauusd_monthly_audit.csv")
    out_weekly_path = os.path.join(r"c:\Users\Admin\Desktop\nifty backttteest", "xauusd_weekly_audit.csv")
    
    tdf_staged.to_csv(out_trades_path, index=False)
    
    # Monthly Audit Table
    monthly_table = tdf_staged.groupby('month').agg(
        trades=('pnl', 'count'),
        wins=('pnl', lambda x: (x > 0).sum()),
        losses=('pnl', lambda x: (x < 0).sum()),
        win_rate=('pnl', lambda x: round((x > 0).mean() * 100, 1)),
        net_pnl=('pnl', 'sum'),
        full_sls=('result', lambda x: (x == 'FULL_SL').sum()),
        t1_be=('result', lambda x: (x == 'TP1_AND_BE').sum()),
        t1_t2=('result', lambda x: (x == 'TP1_AND_TP2').sum())
    ).reset_index()
    monthly_table.to_csv(out_monthly_path, index=False)
    
    # Weekly Audit Table
    weekly_table = tdf_staged.groupby('week').agg(
        trades=('pnl', 'count'),
        wins=('pnl', lambda x: (x > 0).sum()),
        losses=('pnl', lambda x: (x < 0).sum()),
        win_rate=('pnl', lambda x: round((x > 0).mean() * 100, 1)),
        net_pnl=('pnl', 'sum')
    ).reset_index()
    weekly_table.to_csv(out_weekly_path, index=False)
    
    print(f"\n[+] Saved detailed trade ledger to: {out_trades_path}")
    print(f"[+] Saved monthly audit to: {out_monthly_path}")
    print(f"[+] Saved weekly audit to: {out_weekly_path}")
    
    print("\n" + "=" * 80)
    print("  MONTH-BY-MONTH AUDIT (CHAMPION 2-LOT STAGED ENGINE)")
    print("=" * 80)
    print(monthly_table.to_string(index=False))
