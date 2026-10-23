import os, pandas as pd, numpy as np
from datetime import time
from run_2year_banknifty_backtest import load_all_banknifty_sessions, BlackScholesPricingBN

def run_and_save():
    base_dir = os.path.dirname(os.path.abspath(__file__))
    sessions = load_all_banknifty_sessions()
    lot_size = 30
    slippage = 0.005
    eod_close_time = time(15, 0)
    be_trigger = 100.0
    be_buffer = 8.0
    trail_dist = 25.0
    initial_sl_pts = 70.0
    tp_pts = 280.0

    trades = []
    allowed_pbs = [
        'R1 Resistance Reversal',
        'S2 Sweep Bounceback',
        'S1 Support Breakdown',
        'R1 Resistance Breakout',
        'R2 Exhaustion Reversal'
    ]

    for sess in sessions:
        d_str = sess['date'].strftime('%Y-%m-%d')
        bars = sess['bars']
        lvl = sess['lvl']
        dte = sess['dte']
        
        trades_today = []
        in_trade = False
        trade_dir = None
        strike = 0
        entry_prem = 0.0
        curr_sl = 0.0
        curr_tp = 0.0
        max_fav = 0.0
        entry_raw = 0.0
        playbook = ''
        category = ''
        entry_time = None
        
        for i in range(1, len(bars)):
            bar = bars[i]
            prev_bar = bars[i-1]
            t = bar['time']
            spot = bar['close']
            b_open = bar['open']
            b_high = bar['high']
            b_low = bar['low']
            b_range = b_high - b_low
            
            if in_trade:
                is_call = (trade_dir == 'CE')
                prem_close = BlackScholesPricingBN.calculate_price(spot, strike, dte, is_call=is_call)
                prem_high = BlackScholesPricingBN.calculate_price(b_high, strike, dte, is_call=is_call) if is_call else BlackScholesPricingBN.calculate_price(b_low, strike, dte, is_call=is_call)
                prem_low = BlackScholesPricingBN.calculate_price(b_low, strike, dte, is_call=is_call) if is_call else BlackScholesPricingBN.calculate_price(b_high, strike, dte, is_call=is_call)
                
                if prem_high > max_fav:
                    max_fav = prem_high
                    
                # BE Buffer Lock
                if max_fav >= entry_raw + be_trigger:
                    be_level = entry_raw + be_buffer
                    if be_level > curr_sl:
                        curr_sl = be_level
                        
                # Dynamic Trailing SL 25 pts behind high
                if max_fav >= entry_raw + be_trigger:
                    t_sl = max_fav - trail_dist
                    if t_sl > curr_sl:
                        curr_sl = t_sl
                        
                hit_tp = (prem_high >= curr_tp)
                hit_sl = (prem_low <= curr_sl)
                hit_eod = (t >= eod_close_time)
                
                if hit_tp or hit_sl or hit_eod:
                    exit_raw = curr_tp if hit_tp else (curr_sl if hit_sl else prem_close)
                    fill_entry = entry_raw * (1.0 + slippage)
                    fill_exit = max(0.5, exit_raw * (1.0 - slippage))
                    pts = fill_exit - fill_entry
                    gross = pts * lot_size
                    stt = fill_exit * lot_size * 0.000625
                    txn = (fill_entry + fill_exit) * lot_size * 0.00053
                    brokerage = 40.0
                    gst = (brokerage + txn) * 0.18
                    costs = brokerage + stt + txn + gst
                    net = gross - costs
                    is_win = (net > 0)
                    
                    reason = "TARGET 1:4 HIT (+280 pts)" if hit_tp else ("STOP LOSS (-70 pts)" if (hit_sl and curr_sl <= entry_raw) else ("TRAILING STOP HIT" if hit_sl else "EOD SQUARE-OFF (15:00)"))
                    
                    t_rec = {
                        'date': d_str,
                        'entry_time': entry_time.strftime('%H:%M') if entry_time else "09:25",
                        'exit_time': bar['dt'].strftime('%H:%M'),
                        'instrument': f"BANKNIFTY {strike} {trade_dir}",
                        'trade_dir': trade_dir,
                        'playbook': playbook,
                        'strike': strike,
                        'entry_prem': round(fill_entry, 2),
                        'exit_prem': round(fill_exit, 2),
                        'pts': round(pts, 2),
                        'gross_pnl': round(gross, 2),
                        'costs': round(costs, 2),
                        'net_pnl': round(net, 2),
                        'result': reason,
                        'is_win': is_win
                    }
                    trades.append(t_rec)
                    trades_today.append(t_rec)
                    in_trade = False
                    continue
                    
            # Stop-on-loss rule
            if len(trades_today) == 1 and not trades_today[0]['is_win']:
                continue
            if len(trades_today) >= 2:
                continue
            if t > time(14, 0) or t >= eod_close_time or b_range < 15:
                continue
                
            lower_wick = min(b_open, spot) - b_low
            upper_wick = b_high - max(b_open, spot)
            bull_body = (spot > b_open) and ((spot - b_open) >= 0.35 * b_range)
            bear_body = (spot < b_open) and ((b_open - spot) >= 0.35 * b_range)
            prev_c = prev_bar['close']
            
            r1_break = (prev_c <= lvl['r1']) and (spot > lvl['r1']) and bull_body
            s1_break = (prev_c >= lvl['s1']) and (spot < lvl['s1']) and bear_body
            r2_break = (prev_c <= lvl['r2']) and (spot > lvl['r2']) and bull_body
            
            tested_s1 = (b_low <= lvl['s1'] <= b_high) or (prev_bar['low'] <= lvl['s1'] and b_low <= lvl['s1'])
            tested_r1 = (b_high >= lvl['r1'] >= b_low) or (prev_bar['high'] >= lvl['r1'] and b_high >= lvl['r1'])
            r1_fade = tested_r1 and (spot < lvl['r1']) and ((upper_wick >= 0.35 * b_range) or (spot < prev_bar['low'] and spot < b_open))
            tested_r2 = (b_high >= lvl['r2'])
            r2_fade = tested_r2 and (spot < lvl['r2']) and (upper_wick >= 0.35 * b_range)
            tested_s2 = (b_low <= lvl['s2'])
            s2_bounce = tested_s2 and (spot > lvl['s2']) and (lower_wick >= 0.35 * b_range)
            
            c_dir = None
            c_pb = ''
            if s1_break: c_dir = 'PE'; c_pb = 'S1 Support Breakdown'
            elif r1_fade: c_dir = 'PE'; c_pb = 'R1 Resistance Reversal'
            elif r2_fade: c_dir = 'PE'; c_pb = 'R2 Exhaustion Reversal'
            elif r1_break: c_dir = 'CE'; c_pb = 'R1 Resistance Breakout'
            elif s2_bounce: c_dir = 'CE'; c_pb = 'S2 Sweep Bounceback'
            
            if c_dir and c_pb in allowed_pbs:
                in_trade = True
                trade_dir = c_dir
                playbook = c_pb
                strike = int(round(spot / 100) * 100)
                is_call = (trade_dir == 'CE')
                entry_raw = BlackScholesPricingBN.calculate_price(spot, strike, dte, is_call=is_call)
                curr_sl = max(0.5, entry_raw - initial_sl_pts)
                curr_tp = entry_raw + tp_pts
                max_fav = entry_raw
                entry_time = bar['dt']
                continue

    df_bn = pd.DataFrame(trades)
    df_bn['cum_pnl'] = df_bn['net_pnl'].cumsum().round(2)
    out_file = os.path.join(base_dir, "trades_maximum_profit_banknifty_2year.csv")
    df_bn.to_csv(out_file, index=False)
    print(f"Saved {len(df_bn)} BankNifty Max Profit trades to {out_file}")

if __name__ == "__main__":
    run_and_save()
