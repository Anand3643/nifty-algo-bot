"""
Institutional Staged Scale-Out Engine Backtest on XAUUSD (Gold)
Data Source: MT5 Historical Gold Bars from C:\\Users\\Admin\\Desktop\\stoks related\\yt

Mechanics:
- 2-Lot / 2-Unit Staged Execution Engine:
  * Lot 1 Target (1:2 RR): Book 50% Profit immediately banked.
  * Stop Loss on Lot 2: Instantly moved to Risk-Free Breakeven (Entry + Spread Buffer).
  * Lot 2 Target (1:4 RR): Let Lot 2 runner capture extended trend extension.
- Strategy Logic:
  * Institutional CPR (Pivot, BC, TC) & SPR Support/Resistance Levels.
  * 50 EMA Trend Filter.
  * Support Bounce / Resistance Bounce / Breakout triggers.
  * London / NY session filtering.
"""

import os
import pandas as pd
import numpy as np

DATA_DIR = r"C:\Users\Admin\Desktop\stoks related\yt"
M15_PATH = os.path.join(DATA_DIR, "mt5_data", "XAUUSD_M15.csv")
M5_PATH  = os.path.join(DATA_DIR, "mt5_data", "XAUUSD_M5.csv")
GOLD_M15_PATH = os.path.join(DATA_DIR, "GOLD_M15_mt5.csv")

def load_and_preprocess(filepath):
    print(f"[*] Loading data from: {filepath}")
    df = pd.read_csv(filepath)
    time_col = [c for c in df.columns if 'time' in c.lower() or 'date' in c.lower()][0]
    df['time'] = pd.to_datetime(df[time_col])
    df = df.sort_values('time').reset_index(drop=True)
    df['date'] = df['time'].dt.date
    df['hour'] = df['time'].dt.hour
    df['day_of_week'] = df['time'].dt.dayofweek
    
    # 50 EMA
    df['ema50'] = df['close'].ewm(span=50, adjust=False).mean()
    
    # Spread in dollars (if spread column is in points, e.g. 20 = $0.20)
    if 'spread' in df.columns:
        df['spread_dollar'] = df['spread'] * 0.01
    else:
        df['spread_dollar'] = 0.25 # default 25 cents
        
    return df

def compute_daily_cpr_spr(df, profile='NIFTY'):
    daily = df.groupby('date').agg(
        high=('high', 'max'),
        low=('low', 'min'),
        close=('close', 'last'),
        open=('open', 'first')
    ).reset_index()
    
    daily['range'] = daily['high'] - daily['low']
    # Filter out Sunday / holiday micro-bars
    daily = daily[daily['range'] > 2.0].reset_index(drop=True)
    
    # Shift by 1 day so today trades purely on previous day's completed close
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
    daily['cpr_bottom'] = np.minimum(daily['tc'], daily['bc'])
    daily['cpr_width'] = np.abs(daily['tc'] - daily['bc'])
    
    # SPR Multipliers
    if profile.upper() == 'BANKNIFTY':
        daily['res1'] = daily['prev_c'] + (0.200 * daily['prev_r'])
        daily['res2'] = daily['prev_c'] + (0.468 * daily['prev_r'])
        daily['res3'] = daily['prev_c'] + (0.840 * daily['prev_r'])
        daily['res4'] = daily['res3']
        daily['sup1'] = daily['prev_c'] - (0.258 * daily['prev_r'])
        daily['sup2'] = daily['prev_c'] - (0.516 * daily['prev_r'])
        daily['sup3'] = daily['prev_c'] - (0.823 * daily['prev_r'])
        daily['sup4'] = daily['sup3']
    else: # NIFTY profile
        daily['res1'] = daily['prev_c'] + (0.236 * daily['prev_r'])
        daily['res2'] = daily['prev_c'] + (0.500 * daily['prev_r'])
        daily['res3'] = daily['prev_c'] + (0.866 * daily['prev_r'])
        daily['res4'] = daily['prev_c'] + (1.333 * daily['prev_r'])
        daily['sup1'] = daily['prev_c'] - (0.300 * daily['prev_r'])
        daily['sup2'] = daily['prev_c'] - (0.550 * daily['prev_r'])
        daily['sup3'] = daily['prev_c'] - (0.900 * daily['prev_r'])
        daily['sup4'] = daily['prev_c'] - (1.314 * daily['prev_r'])
        
    return daily

def run_simulation(df, daily_df,
                   execution_mode='STAGED_2LOT', # 'SINGLE_TP1', 'SINGLE_TP2', 'STAGED_2LOT'
                   sl_dollar=6.0,
                   tp1_dollar=12.0, # 1:2 RR
                   tp2_dollar=24.0, # 1:4 RR
                   be_buffer=0.30,  # $0.30 risk-free buffer covering spread
                   trade_direction='BOTH', # 'BOTH', 'LONG_ONLY', 'SHORT_ONLY'
                   strategy_mode='BOUNCE', # 'BOUNCE', 'BREAKOUT', 'ADAPTIVE'
                   use_ema_filter=True,
                   session_hours=(8, 21), # London to NY overlap
                   max_trades_per_day=2,
                   friday_close_hour=23,
                   lot_size_per_unit=0.01,
                   initial_capital=1000.0):
    
    # Merge daily CPR & SPR
    daily_cols = ['date', 'pivot', 'bc', 'tc', 'cpr_top', 'cpr_bottom', 'cpr_width',
                  'res1', 'res2', 'res3', 'res4', 'sup1', 'sup2', 'sup3', 'sup4']
    merged = pd.merge(df, daily_df[daily_cols], on='date', how='inner')
    
    n = len(merged)
    opens = merged['open'].values
    highs = merged['high'].values
    lows = merged['low'].values
    closes = merged['close'].values
    spreads = merged['spread_dollar'].values
    hours = merged['hour'].values
    dows = merged['day_of_week'].values
    dates = merged['date'].values
    times = merged['time'].values
    ema50 = merged['ema50'].values
    
    pivots = merged['pivot'].values
    cpr_tops = merged['cpr_top'].values
    cpr_bottoms = merged['cpr_bottom'].values
    cpr_widths = merged['cpr_width'].values
    res1s = merged['res1'].values
    res2s = merged['res2'].values
    sup1s = merged['sup1'].values
    sup2s = merged['sup2'].values
    
    # State tracking
    trades = []
    in_pos = False
    pos_type = 0 # 1=BUY, -1=SELL
    pos_entry = 0.0
    pos_entry_time = None
    
    # Staged scale-out state
    lot1_active = False
    lot2_active = False
    lot1_exit_price = 0.0
    lot1_exit_time = None
    lot1_pnl = 0.0
    lot1_reason = ""
    
    lot2_exit_price = 0.0
    lot2_exit_time = None
    lot2_pnl = 0.0
    lot2_reason = ""
    
    current_sl = 0.0
    target_1 = 0.0
    target_2 = 0.0
    
    current_date = None
    trades_today = 0
    balance = initial_capital
    equity_curve = [initial_capital]
    
    start_h, end_h = session_hours
    
    for i in range(2, n):
        b_date = dates[i]
        b_time = times[i]
        
        if b_date != current_date:
            current_date = b_date
            trades_today = 0
            
        b_open = opens[i]
        b_high = highs[i]
        b_low = lows[i]
        b_close = closes[i]
        b_hour = hours[i]
        b_dow = dows[i]
        b_spread = spreads[i]
        
        # 1. MANAGE ACTIVE POSITION
        if in_pos:
            # Check Friday auto-close
            if b_dow == 4 and b_hour >= friday_close_hour:
                exit_price = b_close
                if pos_type == 1:
                    pnl_per_dollar = (exit_price - pos_entry)
                else:
                    pnl_per_dollar = (pos_entry - exit_price)
                    
                # Close remaining active lots
                if execution_mode == 'STAGED_2LOT':
                    if lot1_active:
                        lot1_pnl = pnl_per_dollar * (lot_size_per_unit * 100.0)
                        lot1_exit_price = exit_price
                        lot1_exit_time = b_time
                        lot1_reason = "FRIDAY_CLOSE"
                        lot1_active = False
                    if lot2_active:
                        lot2_pnl = pnl_per_dollar * (lot_size_per_unit * 100.0)
                        lot2_exit_price = exit_price
                        lot2_exit_time = b_time
                        lot2_reason = "FRIDAY_CLOSE"
                        lot2_active = False
                    total_trade_pnl = lot1_pnl + lot2_pnl
                else:
                    total_trade_pnl = pnl_per_dollar * (lot_size_per_unit * 100.0)
                    lot1_pnl = total_trade_pnl
                    lot1_reason = "FRIDAY_CLOSE"
                    
                balance += total_trade_pnl
                equity_curve.append(balance)
                trades.append({
                    'entry_time': pos_entry_time,
                    'exit_time': b_time,
                    'type': 'BUY' if pos_type == 1 else 'SELL',
                    'entry': pos_entry,
                    'pnl': total_trade_pnl,
                    'lot1_pnl': lot1_pnl,
                    'lot2_pnl': lot2_pnl,
                    'lot1_reason': lot1_reason,
                    'lot2_reason': lot2_reason,
                    'balance': balance,
                    'mode': execution_mode
                })
                in_pos = False
                continue
                
            # LONG POSITION MANAGEMENT
            if pos_type == 1:
                if execution_mode == 'SINGLE_TP1':
                    if b_low <= current_sl:
                        pnl = (current_sl - pos_entry) * (lot_size_per_unit * 100.0)
                        balance += pnl
                        equity_curve.append(balance)
                        trades.append({'entry_time': pos_entry_time, 'exit_time': b_time, 'type': 'BUY',
                                       'entry': pos_entry, 'exit': current_sl, 'pnl': pnl, 'balance': balance, 'reason': 'SL'})
                        in_pos = False
                        continue
                    elif b_high >= target_1:
                        pnl = (target_1 - pos_entry) * (lot_size_per_unit * 100.0)
                        balance += pnl
                        equity_curve.append(balance)
                        trades.append({'entry_time': pos_entry_time, 'exit_time': b_time, 'type': 'BUY',
                                       'entry': pos_entry, 'exit': target_1, 'pnl': pnl, 'balance': balance, 'reason': 'TP1'})
                        in_pos = False
                        continue
                        
                elif execution_mode == 'SINGLE_TP2':
                    if b_low <= current_sl:
                        pnl = (current_sl - pos_entry) * (lot_size_per_unit * 100.0)
                        balance += pnl
                        equity_curve.append(balance)
                        trades.append({'entry_time': pos_entry_time, 'exit_time': b_time, 'type': 'BUY',
                                       'entry': pos_entry, 'exit': current_sl, 'pnl': pnl, 'balance': balance, 'reason': 'SL'})
                        in_pos = False
                        continue
                    elif b_high >= target_2:
                        pnl = (target_2 - pos_entry) * (lot_size_per_unit * 100.0)
                        balance += pnl
                        equity_curve.append(balance)
                        trades.append({'entry_time': pos_entry_time, 'exit_time': b_time, 'type': 'BUY',
                                       'entry': pos_entry, 'exit': target_2, 'pnl': pnl, 'balance': balance, 'reason': 'TP2'})
                        in_pos = False
                        continue
                        
                elif execution_mode == 'STAGED_2LOT':
                    # Check Lot 1
                    if lot1_active:
                        if b_low <= current_sl:
                            # Full initial SL hit on both lots
                            l1_pnl = (current_sl - pos_entry) * (lot_size_per_unit * 100.0)
                            l2_pnl = (current_sl - pos_entry) * (lot_size_per_unit * 100.0)
                            total_pnl = l1_pnl + l2_pnl
                            balance += total_pnl
                            equity_curve.append(balance)
                            trades.append({
                                'entry_time': pos_entry_time, 'exit_time': b_time, 'type': 'BUY',
                                'entry': pos_entry, 'pnl': total_pnl, 'lot1_pnl': l1_pnl, 'lot2_pnl': l2_pnl,
                                'lot1_reason': 'SL', 'lot2_reason': 'SL', 'balance': balance, 'mode': execution_mode
                            })
                            in_pos = False
                            continue
                        elif b_high >= target_1:
                            # Target 1 Achieved! Book Lot 1 immediately
                            lot1_pnl = (target_1 - pos_entry) * (lot_size_per_unit * 100.0)
                            lot1_exit_price = target_1
                            lot1_exit_time = b_time
                            lot1_reason = "TP1"
                            lot1_active = False
                            
                            # Instantly move Stop Loss on Lot 2 to Risk-Free Breakeven
                            current_sl = pos_entry + be_buffer
                            
                    # Check Lot 2 (Runner)
                    if lot2_active and not lot1_active:
                        # Now running with Breakeven SL
                        if b_low <= current_sl:
                            lot2_pnl = (current_sl - pos_entry) * (lot_size_per_unit * 100.0)
                            lot2_exit_price = current_sl
                            lot2_exit_time = b_time
                            lot2_reason = "BE_SL"
                            lot2_active = False
                            
                            total_pnl = lot1_pnl + lot2_pnl
                            balance += total_pnl
                            equity_curve.append(balance)
                            trades.append({
                                'entry_time': pos_entry_time, 'exit_time': b_time, 'type': 'BUY',
                                'entry': pos_entry, 'pnl': total_pnl, 'lot1_pnl': lot1_pnl, 'lot2_pnl': lot2_pnl,
                                'lot1_reason': lot1_reason, 'lot2_reason': lot2_reason, 'balance': balance, 'mode': execution_mode
                            })
                            in_pos = False
                            continue
                        elif b_high >= target_2:
                            lot2_pnl = (target_2 - pos_entry) * (lot_size_per_unit * 100.0)
                            lot2_exit_price = target_2
                            lot2_exit_time = b_time
                            lot2_reason = "TP2_RUNNER"
                            lot2_active = False
                            
                            total_pnl = lot1_pnl + lot2_pnl
                            balance += total_pnl
                            equity_curve.append(balance)
                            trades.append({
                                'entry_time': pos_entry_time, 'exit_time': b_time, 'type': 'BUY',
                                'entry': pos_entry, 'pnl': total_pnl, 'lot1_pnl': lot1_pnl, 'lot2_pnl': lot2_pnl,
                                'lot1_reason': lot1_reason, 'lot2_reason': lot2_reason, 'balance': balance, 'mode': execution_mode
                            })
                            in_pos = False
                            continue
                            
            # SHORT POSITION MANAGEMENT
            elif pos_type == -1:
                if execution_mode == 'SINGLE_TP1':
                    if b_high >= current_sl:
                        pnl = (pos_entry - current_sl) * (lot_size_per_unit * 100.0)
                        balance += pnl
                        equity_curve.append(balance)
                        trades.append({'entry_time': pos_entry_time, 'exit_time': b_time, 'type': 'SELL',
                                       'entry': pos_entry, 'exit': current_sl, 'pnl': pnl, 'balance': balance, 'reason': 'SL'})
                        in_pos = False
                        continue
                    elif b_low <= target_1:
                        pnl = (pos_entry - target_1) * (lot_size_per_unit * 100.0)
                        balance += pnl
                        equity_curve.append(balance)
                        trades.append({'entry_time': pos_entry_time, 'exit_time': b_time, 'type': 'SELL',
                                       'entry': pos_entry, 'exit': target_1, 'pnl': pnl, 'balance': balance, 'reason': 'TP1'})
                        in_pos = False
                        continue
                        
                elif execution_mode == 'SINGLE_TP2':
                    if b_high >= current_sl:
                        pnl = (pos_entry - current_sl) * (lot_size_per_unit * 100.0)
                        balance += pnl
                        equity_curve.append(balance)
                        trades.append({'entry_time': pos_entry_time, 'exit_time': b_time, 'type': 'SELL',
                                       'entry': pos_entry, 'exit': current_sl, 'pnl': pnl, 'balance': balance, 'reason': 'SL'})
                        in_pos = False
                        continue
                    elif b_low <= target_2:
                        pnl = (pos_entry - target_2) * (lot_size_per_unit * 100.0)
                        balance += pnl
                        equity_curve.append(balance)
                        trades.append({'entry_time': pos_entry_time, 'exit_time': b_time, 'type': 'SELL',
                                       'entry': pos_entry, 'exit': target_2, 'pnl': pnl, 'balance': balance, 'reason': 'TP2'})
                        in_pos = False
                        continue
                        
                elif execution_mode == 'STAGED_2LOT':
                    # Check Lot 1
                    if lot1_active:
                        if b_high >= current_sl:
                            l1_pnl = (pos_entry - current_sl) * (lot_size_per_unit * 100.0)
                            l2_pnl = (pos_entry - current_sl) * (lot_size_per_unit * 100.0)
                            total_pnl = l1_pnl + l2_pnl
                            balance += total_pnl
                            equity_curve.append(balance)
                            trades.append({
                                'entry_time': pos_entry_time, 'exit_time': b_time, 'type': 'SELL',
                                'entry': pos_entry, 'pnl': total_pnl, 'lot1_pnl': l1_pnl, 'lot2_pnl': l2_pnl,
                                'lot1_reason': 'SL', 'lot2_reason': 'SL', 'balance': balance, 'mode': execution_mode
                            })
                            in_pos = False
                            continue
                        elif b_low <= target_1:
                            lot1_pnl = (pos_entry - target_1) * (lot_size_per_unit * 100.0)
                            lot1_exit_price = target_1
                            lot1_exit_time = b_time
                            lot1_reason = "TP1"
                            lot1_active = False
                            
                            # Instantly move Stop Loss on Lot 2 to Risk-Free Breakeven
                            current_sl = pos_entry - be_buffer
                            
                    # Check Lot 2 (Runner)
                    if lot2_active and not lot1_active:
                        if b_high >= current_sl:
                            lot2_pnl = (pos_entry - current_sl) * (lot_size_per_unit * 100.0)
                            lot2_exit_price = current_sl
                            lot2_exit_time = b_time
                            lot2_reason = "BE_SL"
                            lot2_active = False
                            
                            total_pnl = lot1_pnl + lot2_pnl
                            balance += total_pnl
                            equity_curve.append(balance)
                            trades.append({
                                'entry_time': pos_entry_time, 'exit_time': b_time, 'type': 'SELL',
                                'entry': pos_entry, 'pnl': total_pnl, 'lot1_pnl': lot1_pnl, 'lot2_pnl': lot2_pnl,
                                'lot1_reason': lot1_reason, 'lot2_reason': lot2_reason, 'balance': balance, 'mode': execution_mode
                            })
                            in_pos = False
                            continue
                        elif b_low <= target_2:
                            lot2_pnl = (pos_entry - target_2) * (lot_size_per_unit * 100.0)
                            lot2_exit_price = target_2
                            lot2_exit_time = b_time
                            lot2_reason = "TP2_RUNNER"
                            lot2_active = False
                            
                            total_pnl = lot1_pnl + lot2_pnl
                            balance += total_pnl
                            equity_curve.append(balance)
                            trades.append({
                                'entry_time': pos_entry_time, 'exit_time': b_time, 'type': 'SELL',
                                'entry': pos_entry, 'pnl': total_pnl, 'lot1_pnl': lot1_pnl, 'lot2_pnl': lot2_pnl,
                                'lot1_reason': lot1_reason, 'lot2_reason': lot2_reason, 'balance': balance, 'mode': execution_mode
                            })
                            in_pos = False
                            continue
                            
        # 2. CHECK NEW ENTRY SIGNALS
        if in_pos or trades_today >= max_trades_per_day:
            continue
            
        # Session Filter
        if b_hour < start_h or b_hour >= end_h:
            continue
            
        # Completed previous candle (Bar i-1)
        o1 = opens[i-1]
        h1 = highs[i-1]
        l1 = lows[i-1]
        c1 = closes[i-1]
        ema1 = ema50[i-1]
        
        # Two candles ago (Bar i-2)
        o2 = opens[i-2]
        c2 = closes[i-2]
        
        lvl_pivot = pivots[i]
        lvl_top   = cpr_tops[i]
        lvl_bot   = cpr_bottoms[i]
        lvl_w     = cpr_widths[i]
        lvl_r1    = res1s[i]
        lvl_r2    = res2s[i]
        lvl_s1    = sup1s[i]
        lvl_s2    = sup2s[i]
        
        is_narrow = (lvl_w <= 5.0)
        active_mode = strategy_mode
        if strategy_mode == 'ADAPTIVE':
            active_mode = 'BREAKOUT' if is_narrow else 'BOUNCE'
            
        buy_signal = False
        sell_signal = False
        
        # BOUNCE MODE
        if active_mode == 'BOUNCE':
            # Bullish Support Bounce: Low tested S1/S2/CPR Bottom and candle closed green
            test_s1 = (l1 <= lvl_s1 + 0.60 and c1 > lvl_s1 and c1 > o1)
            test_s2 = (l1 <= lvl_s2 + 0.60 and c1 > lvl_s2 and c1 > o1)
            test_cpr_bot = (l1 <= lvl_bot + 0.60 and c1 > lvl_bot and c1 > o1 and o1 < lvl_pivot)
            
            if test_s1 or test_s2 or test_cpr_bot:
                if not use_ema_filter or c1 >= ema1:
                    buy_signal = True
                    
            # Bearish Resistance Bounce: High tested R1/R2/CPR Top and candle closed red
            test_r1 = (h1 >= lvl_r1 - 0.60 and c1 < lvl_r1 and c1 < o1)
            test_r2 = (h1 >= lvl_r2 - 0.60 and c1 < lvl_r2 and c1 < o1)
            test_cpr_top = (h1 >= lvl_top - 0.60 and c1 < lvl_top and c1 < o1 and o1 > lvl_pivot)
            
            if test_r1 or test_r2 or test_cpr_top:
                if not use_ema_filter or c1 <= ema1:
                    sell_signal = True
                    
        # BREAKOUT MODE
        elif active_mode == 'BREAKOUT':
            bo_r1 = (c2 <= lvl_r1 and c1 > lvl_r1 and c1 > o1)
            bo_cpr = (c2 <= lvl_top and c1 > lvl_top and c1 > o1)
            if bo_r1 or bo_cpr:
                if not use_ema_filter or c1 >= ema1:
                    buy_signal = True
                    
            bo_s1 = (c2 >= lvl_s1 and c1 < lvl_s1 and c1 < o1)
            bo_cpr_b = (c2 >= lvl_bot and c1 < lvl_bot and c1 < o1)
            if bo_s1 or bo_cpr_b:
                if not use_ema_filter or c1 <= ema1:
                    sell_signal = True
                    
        # Direction Filter
        if trade_direction == 'LONG_ONLY':
            sell_signal = False
        elif trade_direction == 'SHORT_ONLY':
            buy_signal = False
            
        # EXECUTE ENTRY
        if buy_signal:
            pos_type = 1
            pos_entry = b_open + b_spread # Pay spread on long entry
            pos_entry_time = b_time
            current_sl = pos_entry - sl_dollar
            target_1 = pos_entry + tp1_dollar
            target_2 = pos_entry + tp2_dollar
            lot1_active = True
            lot2_active = True
            in_pos = True
            trades_today += 1
        elif sell_signal:
            pos_type = -1
            pos_entry = b_open # Short enters at bid
            pos_entry_time = b_time
            current_sl = pos_entry + sl_dollar + b_spread
            target_1 = pos_entry - tp1_dollar
            target_2 = pos_entry - tp2_dollar
            lot1_active = True
            lot2_active = True
            in_pos = True
            trades_today += 1
            
    tdf = pd.DataFrame(trades)
    return tdf, equity_curve

def analyze_performance(name, tdf, initial_capital=1000.0):
    if len(tdf) == 0:
        return {'Name': name, 'Trades': 0, 'Net PnL': 0.0, 'Return %': 0.0,
                'Win Rate': 0.0, 'Profit Factor': 0.0, 'Max DD': 0.0, 'Max DD %': 0.0}
        
    final_balance = tdf['balance'].iloc[-1]
    net_pnl = final_balance - initial_capital
    pct_return = (net_pnl / initial_capital) * 100.0
    
    wins = tdf[tdf['pnl'] > 0]
    losses = tdf[tdf['pnl'] < 0]
    win_rate = (len(wins) / len(tdf)) * 100.0
    
    gross_profit = wins['pnl'].sum() if len(wins) > 0 else 0.0
    gross_loss = abs(losses['pnl'].sum()) if len(losses) > 0 else 0.0
    pf = gross_profit / gross_loss if gross_loss > 0 else 999.0
    
    avg_win = wins['pnl'].mean() if len(wins) > 0 else 0.0
    avg_loss = losses['pnl'].mean() if len(losses) > 0 else 0.0
    payoff = abs(avg_win / avg_loss) if avg_loss != 0 else 0.0
    
    # Drawdown
    equity_series = pd.Series([initial_capital] + tdf['pnl'].cumsum().tolist())
    peak = equity_series.cummax()
    dd = peak - equity_series
    dd_pct = (dd / peak) * 100.0
    max_dd = dd.max()
    max_dd_pct = dd_pct.max()
    
    # Target breakdown for staged mode
    tp1_count = 0
    tp2_count = 0
    be_count = 0
    full_sl_count = 0
    if 'lot1_reason' in tdf.columns:
        tp1_count = len(tdf[tdf['lot1_reason'] == 'TP1'])
        tp2_count = len(tdf[tdf['lot2_reason'] == 'TP2_RUNNER'])
        be_count = len(tdf[tdf['lot2_reason'] == 'BE_SL'])
        full_sl_count = len(tdf[tdf['lot1_reason'] == 'SL'])
        
    return {
        'Name': name,
        'Trades': len(tdf),
        'Wins': len(wins),
        'Losses': len(losses),
        'Net PnL': net_pnl,
        'Return %': pct_return,
        'Gross Profit': gross_profit,
        'Gross Loss': gross_loss,
        'Win Rate': win_rate,
        'Profit Factor': pf,
        'Avg Win': avg_win,
        'Avg Loss': avg_loss,
        'Payoff Ratio': payoff,
        'Max DD $': max_dd,
        'Max DD %': max_dd_pct,
        'TP1 Banked': tp1_count,
        'TP2 Runners': tp2_count,
        'Breakevens': be_count,
        'Full SLs': full_sl_count
    }

if __name__ == '__main__':
    print("=" * 80)
    print("  INSTITUTIONAL STAGED SCALE-OUT BACKTEST ENGINE ON XAUUSD (GOLD)")
    print("=" * 80)
    
    # 1. Load M15 Data
    df_m15 = load_and_preprocess(M15_PATH)
    daily_m15 = compute_daily_cpr_spr(df_m15, profile='NIFTY')
    
    print(f"[+] Loaded {len(df_m15):,} M15 bars ({daily_m15['date'].iloc[0]} to {daily_m15['date'].iloc[-1]})")
    
    # Test suite
    results = []
    
    # Test 1: Baseline Single Lot (1:2 RR - $6 SL / $12 TP)
    tdf_base1, _ = run_simulation(df_m15, daily_m15, execution_mode='SINGLE_TP1', sl_dollar=6.0, tp1_dollar=12.0)
    results.append(analyze_performance("M15 Baseline Single 1:2 RR ($6 SL / $12 TP)", tdf_base1))
    
    # Test 2: Baseline Single Lot (1:4 RR - $6 SL / $24 TP)
    tdf_base2, _ = run_simulation(df_m15, daily_m15, execution_mode='SINGLE_TP2', sl_dollar=6.0, tp2_dollar=24.0)
    results.append(analyze_performance("M15 Baseline Single 1:4 RR ($6 SL / $24 TP)", tdf_base2))
    
    # Test 3: Staged 2-Lot Engine ($6 SL / $12 TP1 / $24 TP2) - Both Directions
    tdf_staged1, _ = run_simulation(df_m15, daily_m15, execution_mode='STAGED_2LOT', sl_dollar=6.0, tp1_dollar=12.0, tp2_dollar=24.0)
    results.append(analyze_performance("M15 Staged 2-Lot Engine ($6 SL / $12 TP1 / $24 TP2)", tdf_staged1))
    
    # Test 4: Staged 2-Lot Engine ($5 SL / $10 TP1 / $20 TP2 - 50/100/200 pts)
    tdf_staged2, _ = run_simulation(df_m15, daily_m15, execution_mode='STAGED_2LOT', sl_dollar=5.0, tp1_dollar=10.0, tp2_dollar=20.0)
    results.append(analyze_performance("M15 Staged 2-Lot Engine ($5 SL / $10 TP1 / $20 TP2)", tdf_staged2))
    
    # Test 5: Staged 2-Lot Engine ($8 SL / $16 TP1 / $32 TP2)
    tdf_staged3, _ = run_simulation(df_m15, daily_m15, execution_mode='STAGED_2LOT', sl_dollar=8.0, tp1_dollar=16.0, tp2_dollar=32.0)
    results.append(analyze_performance("M15 Staged 2-Lot Engine ($8 SL / $16 TP1 / $32 TP2)", tdf_staged3))
    
    # Test 6: Staged 2-Lot Engine - Long Only (Gold Structural Upward Edge)
    tdf_staged_long, _ = run_simulation(df_m15, daily_m15, execution_mode='STAGED_2LOT', sl_dollar=6.0, tp1_dollar=12.0, tp2_dollar=24.0, trade_direction='LONG_ONLY')
    results.append(analyze_performance("M15 Staged 2-Lot LONG ONLY ($6 SL / $12 TP1 / $24 TP2)", tdf_staged_long))

    # Test 7: Staged 2-Lot Engine - Long Only ($8 SL / $16 TP1 / $32 TP2)
    tdf_staged_long8, _ = run_simulation(df_m15, daily_m15, execution_mode='STAGED_2LOT', sl_dollar=8.0, tp1_dollar=16.0, tp2_dollar=32.0, trade_direction='LONG_ONLY')
    results.append(analyze_performance("M15 Staged 2-Lot LONG ONLY ($8 SL / $16 TP1 / $32 TP2)", tdf_staged_long8))

    # Test 8: Staged 2-Lot Engine - BankNifty SPR Multipliers
    daily_bn = compute_daily_cpr_spr(df_m15, profile='BANKNIFTY')
    tdf_staged_bn, _ = run_simulation(df_m15, daily_bn, execution_mode='STAGED_2LOT', sl_dollar=6.0, tp1_dollar=12.0, tp2_dollar=24.0)
    results.append(analyze_performance("M15 Staged 2-Lot BankNifty Profile ($6 SL / $12 / $24)", tdf_staged_bn))
    
    # 2. Load M5 Data
    if os.path.exists(M5_PATH):
        df_m5 = load_and_preprocess(M5_PATH)
        daily_m5 = compute_daily_cpr_spr(df_m5, profile='NIFTY')
        print(f"\n[+] Loaded {len(df_m5):,} M5 bars ({daily_m5['date'].iloc[0]} to {daily_m5['date'].iloc[-1]})")
        
        tdf_m5_staged, _ = run_simulation(df_m5, daily_m5, execution_mode='STAGED_2LOT', sl_dollar=5.0, tp1_dollar=10.0, tp2_dollar=20.0)
        results.append(analyze_performance("M5 Staged 2-Lot Engine ($5 SL / $10 TP1 / $20 TP2)", tdf_m5_staged))
        
        tdf_m5_long, _ = run_simulation(df_m5, daily_m5, execution_mode='STAGED_2LOT', sl_dollar=5.0, tp1_dollar=10.0, tp2_dollar=20.0, trade_direction='LONG_ONLY')
        results.append(analyze_performance("M5 Staged 2-Lot LONG ONLY ($5 SL / $10 TP1 / $20 TP2)", tdf_m5_long))

    res_df = pd.DataFrame(results)
    print("\n" + "=" * 110)
    print("  XAUUSD BACKTEST COMPARISON SUMMARY")
    print("=" * 110)
    print(res_df[['Name', 'Trades', 'Net PnL', 'Return %', 'Win Rate', 'Profit Factor', 'Payoff Ratio', 'Max DD $', 'TP1 Banked', 'TP2 Runners']].to_string(index=False))

