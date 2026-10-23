import yfinance as yf
import pandas as pd
from datetime import time
from optimize_combined_strategy import BlackScholesPricing

# 1. Load Thursday 5m candles
m5 = yf.download('^NSEI', period='5d', interval='5m', progress=False)
if isinstance(m5.columns, pd.MultiIndex):
    m5.columns = [c[0] for c in m5.columns]
m5.index = m5.index.tz_convert('Asia/Kolkata')
thu = m5[m5.index.strftime('%Y-%m-%d') == '2026-10-22']

# EXACT TELEGRAM POST FROM @FlyingcallsArjun ON THURSDAY 22-OCT-2026 AT 09:18 AM:
# NIFTY SPOT INTRADAY LEVELS
# SUP 22765 22710 22650 22550
# RES 22865 22930 23020 23120
lvl = {
    's1': 22765,
    's2': 22710,
    's3': 22650,
    's4': 22550,
    'r1': 22865,
    'r2': 22930,
    'r3': 23020,
    'r4': 23120,
    'pivot': 22815
}

dte = 5.5 / 365.0  # Tuesday 27OCT Expiry (5.5 days life)
bars = []
for dt_idx, r in thu.iterrows():
    bars.append({
        'dt': dt_idx,
        'time': dt_idx.time(),
        'open': float(r['Open']),
        'high': float(r['High']),
        'low': float(r['Low']),
        'close': float(r['Close'])
    })

day_open = bars[0]['open']
orb_high = max(b['high'] for b in bars[:3])
orb_low = min(b['low'] for b in bars[:3])

print("="*80)
print("BACKTEST: THURSDAY, 22-OCT-2026 BASED ON EXACT TELEGRAM LEVELS")
print(f"Channel: @FlyingcallsArjun (Posted 09:18 AM IST)")
print(f"Spot Open: {day_open:,.2f}")
print(f"Telegram Support Levels:    S1={lvl['s1']} | S2={lvl['s2']} | S3={lvl['s3']} | S4={lvl['s4']}")
print(f"Telegram Resistance Levels: R1={lvl['r1']} | R2={lvl['r2']} | R3={lvl['r3']} | R4={lvl['r4']}")
print("="*80)

def simulate(strike_mode="OTM-1"):
    in_trade = False
    pos = None
    trades = []
    lot_size = 65
    num_lots = 2
    total_qty = 130
    sl_pts = 50.0
    tp1_pts = 100.0
    tp2_pts = 200.0

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
            is_call = (pos['type'] == 'CE')
            strike = pos['strike']
            prem_close = BlackScholesPricing.calculate_price(spot, strike, dte, 0.135, is_call=is_call)
            prem_high = BlackScholesPricing.calculate_price(b_high, strike, dte, 0.135, is_call=is_call) if is_call else BlackScholesPricing.calculate_price(b_low, strike, dte, 0.135, is_call=is_call)
            prem_low = BlackScholesPricing.calculate_price(b_low, strike, dte, 0.135, is_call=is_call) if is_call else BlackScholesPricing.calculate_price(b_high, strike, dte, 0.135, is_call=is_call)

            hit_sl = (prem_low <= pos['sl_prem'])
            hit_tp1 = (prem_high >= pos['tp1_prem'])
            hit_eod = (t >= time(15, 0))

            if not pos['t1_hit']:
                if hit_sl and not hit_tp1:
                    fill_exit = max(0.5, pos['sl_prem'] * 0.995)
                    pts = fill_exit - pos['fill_entry']
                    gross = pts * total_qty
                    costs = 40 + (fill_exit * total_qty * 0.000625) + ((pos['fill_entry'] + fill_exit) * total_qty * 0.00053) * 1.18
                    net = gross - costs
                    trades.append({
                        'entry_time': pos['entry_time'], 'exit_time': bar['dt'].strftime('%H:%M'),
                        'pb': pos['pb'], 'strike': strike, 'type': pos['type'],
                        'entry_prem': pos['fill_entry'], 'exit_prem': fill_exit,
                        'pts': pts, 'net': net, 'result': 'STOP LOSS HIT (-50 pts)'
                    })
                    print(f"  [EXIT SL] {pos['entry_time']} -> {bar['dt'].strftime('%H:%M')} | {pos['pb']} | NIFTY {strike} {pos['type']} | Entry: Rs {pos['fill_entry']:.2f} | Exit: Rs {fill_exit:.2f} | Pts: {pts:.1f} | Net P&L: Rs {net:,.2f}")
                    in_trade = False
                    pos = None
                    continue

                elif hit_tp1:
                    pos['t1_hit'] = True
                    pos['exit_prem_1'] = pos['tp1_prem']
                    print(f"  [T1 HIT] {bar['dt'].strftime('%H:%M')} | Target 1 Booked (+100 pts on Lot 1 @ Rs {pos['tp1_prem']:.2f}). Trailing Lot 2...")

                    # Check Target 2
                    if prem_high >= pos['tp2_prem']:
                        fill_ex1 = max(0.5, pos['exit_prem_1'] * 0.995)
                        fill_ex2 = max(0.5, pos['tp2_prem'] * 0.995)
                        pts1 = fill_ex1 - pos['fill_entry']
                        pts2 = fill_ex2 - pos['fill_entry']
                        gross = (pts1 * lot_size) + (pts2 * lot_size)
                        costs = 40 + ((fill_ex1 + fill_ex2) * lot_size * 0.000625) + ((pos['fill_entry'] * total_qty + (fill_ex1 + fill_ex2) * lot_size) * 0.00053) * 1.18
                        net = gross - costs
                        trades.append({
                            'entry_time': pos['entry_time'], 'exit_time': bar['dt'].strftime('%H:%M'),
                            'pb': pos['pb'], 'strike': strike, 'type': pos['type'],
                            'entry_prem': pos['fill_entry'], 'exit_prem': fill_ex2,
                            'pts': (pts1 + pts2)/2, 'net': net, 'result': 'T1+T2 FULL VICTORY (+300 pts)'
                        })
                        print(f"  [FULL VICTORY] {pos['entry_time']} -> {bar['dt'].strftime('%H:%M')} | {pos['pb']} | Net P&L: Rs {net:,.2f}")
                        in_trade = False
                        pos = None
                        continue

                elif hit_eod:
                    fill_exit = max(0.5, prem_close * 0.995)
                    pts = fill_exit - pos['fill_entry']
                    gross = pts * total_qty
                    costs = 40 + (fill_exit * total_qty * 0.000625) + ((pos['fill_entry'] + fill_exit) * total_qty * 0.00053) * 1.18
                    net = gross - costs
                    trades.append({
                        'entry_time': pos['entry_time'], 'exit_time': bar['dt'].strftime('%H:%M'),
                        'pb': pos['pb'], 'strike': strike, 'type': pos['type'],
                        'entry_prem': pos['fill_entry'], 'exit_prem': fill_exit,
                        'pts': pts, 'net': net, 'result': 'EOD AUTO SQUARE-OFF'
                    })
                    print(f"  [EXIT EOD] {pos['entry_time']} -> {bar['dt'].strftime('%H:%M')} | {pos['pb']} | NIFTY {strike} {pos['type']} | Entry: Rs {pos['fill_entry']:.2f} | Exit: Rs {fill_exit:.2f} | Pts: {pts:.1f} | Net P&L: Rs {net:,.2f}")
                    in_trade = False
                    pos = None
                    continue

            else:
                # Lot 2 runner management
                hit_tp2 = (prem_high >= pos['tp2_prem'])
                hit_be = (prem_low <= pos['be_prem'])

                if hit_tp2:
                    fill_ex1 = max(0.5, pos['exit_prem_1'] * 0.995)
                    fill_ex2 = max(0.5, pos['tp2_prem'] * 0.995)
                    pts1 = fill_ex1 - pos['fill_entry']
                    pts2 = fill_ex2 - pos['fill_entry']
                    gross = (pts1 * lot_size) + (pts2 * lot_size)
                    costs = 40 + ((fill_ex1 + fill_ex2) * lot_size * 0.000625) + ((pos['fill_entry'] * total_qty + (fill_ex1 + fill_ex2) * lot_size) * 0.00053) * 1.18
                    net = gross - costs
                    trades.append({
                        'entry_time': pos['entry_time'], 'exit_time': bar['dt'].strftime('%H:%M'),
                        'pb': pos['pb'], 'strike': strike, 'type': pos['type'],
                        'entry_prem': pos['fill_entry'], 'exit_prem': fill_ex2,
                        'pts': (pts1 + pts2)/2, 'net': net, 'result': 'T1+T2 RUNNER HIT (+300 pts)'
                    })
                    print(f"  [RUNNER HIT T2] {pos['entry_time']} -> {bar['dt'].strftime('%H:%M')} | {pos['pb']} | Net P&L: Rs {net:,.2f}")
                    in_trade = False
                    pos = None
                    continue

                elif hit_be or hit_eod:
                    fill_ex1 = max(0.5, pos['exit_prem_1'] * 0.995)
                    fill_ex2 = max(0.5, pos['be_prem'] * 0.995) if hit_be else max(0.5, prem_close * 0.995)
                    pts1 = fill_ex1 - pos['fill_entry']
                    pts2 = fill_ex2 - pos['fill_entry']
                    gross = (pts1 * lot_size) + (pts2 * lot_size)
                    costs = 40 + ((fill_ex1 + fill_ex2) * lot_size * 0.000625) + ((pos['fill_entry'] * total_qty + (fill_ex1 + fill_ex2) * lot_size) * 0.00053) * 1.18
                    net = gross - costs
                    reason = 'TARGET 1 + RUNNER BE (+4 pts)' if hit_be else 'TARGET 1 + RUNNER EOD'
                    trades.append({
                        'entry_time': pos['entry_time'], 'exit_time': bar['dt'].strftime('%H:%M'),
                        'pb': pos['pb'], 'strike': strike, 'type': pos['type'],
                        'entry_prem': pos['fill_entry'], 'exit_prem': fill_ex2,
                        'pts': (pts1 + pts2)/2, 'net': net, 'result': reason
                    })
                    print(f"  [{reason}] {pos['entry_time']} -> {bar['dt'].strftime('%H:%M')} | {pos['pb']} | Net P&L: Rs {net:,.2f}")
                    in_trade = False
                    pos = None
                    continue

        # Signal evaluation
        if not in_trade and len(trades) < 2:
            if t < time(9, 25) or t > time(14, 0):
                continue
            if b_range < 5.0:
                continue

            lower_wick = min(b_open, spot) - b_low
            upper_wick = b_high - max(b_open, spot)
            bull_body = (spot > b_open) and ((spot - b_open) >= 0.25 * b_range)
            bear_body = (spot < b_open) and ((b_open - spot) >= 0.25 * b_range)
            prev_c = prev_bar['close']

            # Telegram S1 Breakdown: Spot drops below S1 (22765)
            s1_break = (prev_c >= lvl['s1']) and (spot < lvl['s1']) and bear_body
            
            # Telegram S2 Breakdown: Spot drops below S2 (22710)
            s2_break = (prev_c >= lvl['s2']) and (spot < lvl['s2']) and bear_body

            # Telegram R1 Breakout: Spot breaks above R1 (22865)
            r1_break = (prev_c <= lvl['r1']) and (spot > lvl['r1']) and bull_body

            # Telegram Polarity / Gap Retest:
            # Spot opened at 22687 (which is below S1 22765 and S2 22710)
            # Rejection from S1 or S2
            gap_s1_retest = False
            gap_s2_retest = False
            if day_open <= lvl['s1']:
                tested_s1 = (b_low <= lvl['s1'] <= b_high) or (b_high >= lvl['s1'])
                gap_s1_retest = tested_s1 and (spot < lvl['s1']) and (upper_wick >= 0.25 * b_range)
            if day_open <= lvl['s2']:
                tested_s2 = (b_low <= lvl['s2'] <= b_high) or (b_high >= lvl['s2'])
                gap_s2_retest = tested_s2 and (spot < lvl['s2']) and (upper_wick >= 0.25 * b_range)

            c_dir = None
            c_pb = ""

            if gap_s1_retest:
                c_dir = "PE"
                c_pb = "Gap-Down S1 Polarity Rejection"
            elif gap_s2_retest:
                c_dir = "PE"
                c_pb = "Gap-Down S2 Polarity Rejection"
            elif s1_break:
                c_dir = "PE"
                c_pb = "S1 Support Breakdown"
            elif s2_break:
                c_dir = "PE"
                c_pb = "S2 Support Breakdown"
            elif r1_break:
                c_dir = "CE"
                c_pb = "R1 Resistance Breakout"

            if c_dir:
                atm_strike = int(round(spot / 50.0) * 50)
                is_call = (c_dir == "CE")
                if strike_mode == "OTM-1":
                    strike = (atm_strike + 50) if is_call else (atm_strike - 50)
                else:
                    strike = atm_strike

                entry_raw = BlackScholesPricing.calculate_price(spot, strike, dte, 0.135, is_call=is_call)
                fill_entry = entry_raw * 1.005
                pos = {
                    'pb': c_pb, 'type': c_dir, 'strike': strike,
                    'entry_time': bar['dt'].strftime('%H:%M'),
                    'fill_entry': fill_entry,
                    'sl_prem': max(0.5, entry_raw - sl_pts),
                    'tp1_prem': entry_raw + tp1_pts,
                    'tp2_prem': entry_raw + tp2_pts,
                    'be_prem': fill_entry + 4.0,
                    't1_hit': False
                }
                in_trade = True
                print(f"  [ENTRY] {bar['dt'].strftime('%H:%M')} | Playbook: {c_pb} | Signal: {c_dir} | Spot: {spot:.2f} | Strike: NIFTY {strike} {c_dir} @ Rs {fill_entry:.2f}")

    df = pd.DataFrame(trades)
    return df

print("\n--- OTM-1 Options Simulation (2-Lot Staged) ---")
df_otm = simulate("OTM-1")
print(f"Total OTM-1 Net P&L: Rs {df_otm['net'].sum() if not df_otm.empty else 0:,.2f}")

print("\n--- ATM Options Simulation (2-Lot Staged) ---")
df_atm = simulate("ATM")
print(f"Total ATM Net P&L: Rs {df_atm['net'].sum() if not df_atm.empty else 0:,.2f}")
