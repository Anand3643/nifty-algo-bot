"""
Backtest Analysis for the Last Two Trading Days (and Today)
Strategy: 2-Lot Staged Execution Engine (OTM-1 & ATM Options)
Days Analyzed:
  - Day 1: Wednesday, 21-Oct-2026
  - Day 2: Thursday, 22-Oct-2026 (Weekly Expiry)
  - Bonus: Friday, 23-Oct-2026 (Today Live Session)
"""
import os
import sys
import datetime
from datetime import time, timedelta
import pandas as pd
import numpy as np
import yfinance as yf

base_dir = r"c:\Users\Admin\Desktop\nifty backttteest"
sys.path.insert(0, base_dir)

from optimize_combined_strategy import NiftySREngine, BlackScholesPricing

# 1. Fetch 5-minute candles and daily candles
print("Fetching real market data from Yahoo Finance...")
daily_df = yf.download('^NSEI', period='1mo', interval='1d', progress=False)
if isinstance(daily_df.columns, pd.MultiIndex):
    daily_df.columns = [c[0] for c in daily_df.columns]

m5_df = yf.download('^NSEI', period='5d', interval='5m', progress=False)
if isinstance(m5_df.columns, pd.MultiIndex):
    m5_df.columns = [c[0] for c in m5_df.columns]

# Ensure timezone is Asia/Kolkata
m5_df.index = m5_df.index.tz_convert('Asia/Kolkata')
m5_df['date_str'] = m5_df.index.strftime('%Y-%m-%d')
m5_df['time'] = m5_df.index.time
m5_df['dt'] = m5_df.index

target_dates = ['2026-10-21', '2026-10-22', '2026-10-23']

def run_backtest_for_days(strike_mode="OTM-1"):
    lot_size = 65
    num_lots = 2
    total_qty = lot_size * num_lots
    sl_pts = 50.0
    tp1_pts = 100.0
    tp2_pts = 200.0
    be_buf = 4.0
    capital = 50000.0
    all_trades = []

    allowed_pbs = [
        "Gap-Up R1 Polarity Bounce", "Gap-Down S1 Polarity Rejection",
        "R1 Resistance Reversal", "R2 Exhaustion Reversal",
        "Gap-and-Go Bearish ORB", "S1 Support Breakdown"
    ]

    for d_str in target_dates:
        curr_d = pd.to_datetime(d_str).date()
        # Find previous daily candle
        priors = [d for d in daily_df.index if d.date() < curr_d]
        if not priors:
            continue
        prev_row = daily_df.loc[priors[-1]]
        p_high = float(prev_row['High'])
        p_low = float(prev_row['Low'])
        p_close = float(prev_row['Close'])
        
        lvl = NiftySREngine.calculate_levels(p_high, p_low, p_close)
        dow = curr_d.weekday()
        # Days to expiry (Thursday is dow 3)
        dte = max(0.25, (3 - dow) % 7 + 0.5) / 365.0

        day_bars_df = m5_df[m5_df['date_str'] == d_str]
        if len(day_bars_df) < 3:
            continue

        bars = []
        for dt_idx, r in day_bars_df.iterrows():
            bars.append({
                "dt": dt_idx,
                "time": dt_idx.time(),
                "open": float(r["Open"]),
                "high": float(r["High"]),
                "low": float(r["Low"]),
                "close": float(r["Close"])
            })

        day_open = bars[0]["open"]
        orb_high = max(b["high"] for b in bars[:3])
        orb_low = min(b["low"] for b in bars[:3])

        trades_today = 0
        in_trade = False
        pos = None

        print(f"\n{'='*80}")
        print(f"TRADING SESSION: {d_str} ({curr_d.strftime('%A')}) | Spot Open: {day_open:,.2f}")
        print(f"Levels (from prev day H:{p_high:.1f} L:{p_low:.1f} C:{p_close:.1f}):")
        print(f"  Pivot: {lvl['pivot']} (CPR: {lvl['cpr_bot']} - {lvl['cpr_top']})")
        print(f"  Resistance: R1={lvl['r1']} | R2={lvl['r2']}")
        print(f"  Support:    S1={lvl['s1']} | S2={lvl['s2']}")
        print(f"{'='*80}")

        for i in range(1, len(bars)):
            bar = bars[i]
            prev_bar = bars[i - 1]
            t = bar["time"]
            spot = bar["close"]
            b_open = bar["open"]
            b_high = bar["high"]
            b_low = bar["low"]
            b_range = b_high - b_low

            if in_trade:
                is_call = (pos["type"] == "CE")
                strike = pos["strike"]
                prem_close = BlackScholesPricing.calculate_price(spot, strike, dte, 0.135, is_call=is_call)
                prem_high = BlackScholesPricing.calculate_price(b_high, strike, dte, 0.135, is_call=is_call) if is_call else BlackScholesPricing.calculate_price(b_low, strike, dte, 0.135, is_call=is_call)
                prem_low = BlackScholesPricing.calculate_price(b_low, strike, dte, 0.135, is_call=is_call) if is_call else BlackScholesPricing.calculate_price(b_high, strike, dte, 0.135, is_call=is_call)

                fill_entry = pos["fill_entry"]
                hit_eod = (t >= time(15, 0))

                # PHASE 1: Both Lots Active
                if not pos["t1_hit"]:
                    hit_sl = (prem_low <= pos["sl_prem"])
                    hit_tp1 = (prem_high >= pos["tp1_prem"])

                    if hit_sl and not hit_tp1:
                        # Full stop loss on 2 Lots (130 Qty)
                        exit_raw = pos["sl_prem"]
                        fill_exit = max(0.5, exit_raw * 0.995)
                        pts = fill_exit - fill_entry
                        gross = pts * total_qty
                        stt = fill_exit * total_qty * 0.000625
                        txn = (fill_entry + fill_exit) * total_qty * 0.00053
                        brokerage = 40.0
                        gst = (brokerage + txn) * 0.18
                        costs = brokerage + stt + txn + gst
                        net = gross - costs
                        capital += net

                        trade_record = {
                            "date": d_str,
                            "day": curr_d.strftime("%A"),
                            "playbook": pos["playbook"],
                            "instrument": f"NIFTY {strike} {pos['type']}",
                            "entry_time": pos["entry_dt"].strftime("%H:%M"),
                            "entry_prem": round(fill_entry, 2),
                            "exit_time": bar["dt"].strftime("%H:%M"),
                            "exit_prem_1": round(fill_exit, 2),
                            "exit_prem_2": round(fill_exit, 2),
                            "pts_lot1": round(pts, 2),
                            "pts_lot2": round(pts, 2),
                            "avg_pts": round(pts, 2),
                            "gross_pnl": round(gross, 2),
                            "costs": round(costs, 2),
                            "net_pnl": round(net, 2),
                            "result": "STOP LOSS (-50 pts on 2 Lots)",
                            "is_win": False
                        }
                        all_trades.append(trade_record)
                        print(f"  [EXIT SL] {trade_record['entry_time']} -> {trade_record['exit_time']} | {trade_record['instrument']} | P&L: Rs {net:,.2f} ({pts:.1f} pts)")
                        in_trade = False
                        pos = None
                        trades_today += 1
                        continue

                    elif hit_tp1:
                        # Target 1 Hit! Book 1 Lot (+100 pts)
                        pos["t1_hit"] = True
                        pos["exit_prem_1"] = pos["tp1_prem"]
                        pos["be_prem"] = fill_entry + be_buf
                        print(f"  [T1 BOOKED] {bar['dt'].strftime('%H:%M')} | Lot 1 booked @ {pos['tp1_prem']:.2f} (+100 pts banked). Lot 2 trailed to Breakeven {pos['be_prem']:.2f}")

                        # Check if Target 2 hit in this same bar
                        if prem_high >= pos["tp2_prem"]:
                            pos["t2_hit"] = True
                            pos["exit_prem_2"] = pos["tp2_prem"]

                            fill_ex1 = max(0.5, pos["exit_prem_1"] * 0.995)
                            fill_ex2 = max(0.5, pos["exit_prem_2"] * 0.995)
                            pts1 = fill_ex1 - fill_entry
                            pts2 = fill_ex2 - fill_entry
                            gross = (pts1 * lot_size) + (pts2 * lot_size)

                            stt = (fill_ex1 + fill_ex2) * lot_size * 0.000625
                            txn = (fill_entry * total_qty + (fill_ex1 + fill_ex2) * lot_size) * 0.00053
                            brokerage = 40.0
                            gst = (brokerage + txn) * 0.18
                            costs = brokerage + stt + txn + gst
                            net = gross - costs
                            capital += net

                            trade_record = {
                                "date": d_str,
                                "day": curr_d.strftime("%A"),
                                "playbook": pos["playbook"],
                                "instrument": f"NIFTY {strike} {pos['type']}",
                                "entry_time": pos["entry_dt"].strftime("%H:%M"),
                                "entry_prem": round(fill_entry, 2),
                                "exit_time": bar["dt"].strftime("%H:%M"),
                                "exit_prem_1": round(fill_ex1, 2),
                                "exit_prem_2": round(fill_ex2, 2),
                                "pts_lot1": round(pts1, 2),
                                "pts_lot2": round(pts2, 2),
                                "avg_pts": round((pts1 + pts2)/2.0, 2),
                                "gross_pnl": round(gross, 2),
                                "costs": round(costs, 2),
                                "net_pnl": round(net, 2),
                                "result": "TARGET 1 (+100) & TARGET 2 (+200) FULL VICTORY",
                                "is_win": True
                            }
                            all_trades.append(trade_record)
                            print(f"  [FULL VICTORY] {trade_record['entry_time']} -> {trade_record['exit_time']} | {trade_record['instrument']} | P&L: Rs {net:,.2f} (+{pts1:.1f} / +{pts2:.1f} pts)")
                            in_trade = False
                            pos = None
                            trades_today += 1
                            continue

                    elif hit_eod:
                        # Full EOD exit on 2 Lots
                        exit_raw = prem_close
                        fill_exit = max(0.5, exit_raw * 0.995)
                        pts = fill_exit - fill_entry
                        gross = pts * total_qty
                        stt = fill_exit * total_qty * 0.000625
                        txn = (fill_entry + fill_exit) * total_qty * 0.00053
                        brokerage = 40.0
                        gst = (brokerage + txn) * 0.18
                        costs = brokerage + stt + txn + gst
                        net = gross - costs
                        capital += net

                        trade_record = {
                            "date": d_str,
                            "day": curr_d.strftime("%A"),
                            "playbook": pos["playbook"],
                            "instrument": f"NIFTY {strike} {pos['type']}",
                            "entry_time": pos["entry_dt"].strftime("%H:%M"),
                            "entry_prem": round(fill_entry, 2),
                            "exit_time": bar["dt"].strftime("%H:%M"),
                            "exit_prem_1": round(fill_exit, 2),
                            "exit_prem_2": round(fill_exit, 2),
                            "pts_lot1": round(pts, 2),
                            "pts_lot2": round(pts, 2),
                            "avg_pts": round(pts, 2),
                            "gross_pnl": round(gross, 2),
                            "costs": round(costs, 2),
                            "net_pnl": round(net, 2),
                            "result": "EOD AUTO SQUARE-OFF (2 Lots)",
                            "is_win": net > 0
                        }
                        all_trades.append(trade_record)
                        print(f"  [EXIT EOD] {trade_record['entry_time']} -> {trade_record['exit_time']} | {trade_record['instrument']} | P&L: Rs {net:,.2f}")
                        in_trade = False
                        pos = None
                        trades_today += 1
                        continue

                else:
                    # PHASE 2: Lot 1 already booked at T1. Managing Lot 2 runner.
                    hit_tp2 = (prem_high >= pos["tp2_prem"])
                    hit_be = (prem_low <= pos["be_prem"])

                    if hit_tp2:
                        pos["t2_hit"] = True
                        pos["exit_prem_2"] = pos["tp2_prem"]
                        fill_ex1 = max(0.5, pos["exit_prem_1"] * 0.995)
                        fill_ex2 = max(0.5, pos["exit_prem_2"] * 0.995)
                        pts1 = fill_ex1 - fill_entry
                        pts2 = fill_ex2 - fill_entry
                        gross = (pts1 * lot_size) + (pts2 * lot_size)
                        stt = (fill_ex1 + fill_ex2) * lot_size * 0.000625
                        txn = (fill_entry * total_qty + (fill_ex1 + fill_ex2) * lot_size) * 0.00053
                        brokerage = 40.0
                        gst = (brokerage + txn) * 0.18
                        costs = brokerage + stt + txn + gst
                        net = gross - costs
                        capital += net

                        trade_record = {
                            "date": d_str,
                            "day": curr_d.strftime("%A"),
                            "playbook": pos["playbook"],
                            "instrument": f"NIFTY {strike} {pos['type']}",
                            "entry_time": pos["entry_dt"].strftime("%H:%M"),
                            "entry_prem": round(fill_entry, 2),
                            "exit_time": bar["dt"].strftime("%H:%M"),
                            "exit_prem_1": round(fill_ex1, 2),
                            "exit_prem_2": round(fill_ex2, 2),
                            "pts_lot1": round(pts1, 2),
                            "pts_lot2": round(pts2, 2),
                            "avg_pts": round((pts1 + pts2)/2.0, 2),
                            "gross_pnl": round(gross, 2),
                            "costs": round(costs, 2),
                            "net_pnl": round(net, 2),
                            "result": "TARGET 1 (+100) & TARGET 2 (+200) RUNNER VICTORY",
                            "is_win": True
                        }
                        all_trades.append(trade_record)
                        print(f"  [RUNNER HIT T2] {trade_record['entry_time']} -> {trade_record['exit_time']} | {trade_record['instrument']} | P&L: Rs {net:,.2f}")
                        in_trade = False
                        pos = None
                        trades_today += 1
                        continue

                    elif hit_be:
                        pos["exit_prem_2"] = pos["be_prem"]
                        fill_ex1 = max(0.5, pos["exit_prem_1"] * 0.995)
                        fill_ex2 = max(0.5, pos["exit_prem_2"] * 0.995)
                        pts1 = fill_ex1 - fill_entry
                        pts2 = fill_ex2 - fill_entry
                        gross = (pts1 * lot_size) + (pts2 * lot_size)
                        stt = (fill_ex1 + fill_ex2) * lot_size * 0.000625
                        txn = (fill_entry * total_qty + (fill_ex1 + fill_ex2) * lot_size) * 0.00053
                        brokerage = 40.0
                        gst = (brokerage + txn) * 0.18
                        costs = brokerage + stt + txn + gst
                        net = gross - costs
                        capital += net

                        trade_record = {
                            "date": d_str,
                            "day": curr_d.strftime("%A"),
                            "playbook": pos["playbook"],
                            "instrument": f"NIFTY {strike} {pos['type']}",
                            "entry_time": pos["entry_dt"].strftime("%H:%M"),
                            "entry_prem": round(fill_entry, 2),
                            "exit_time": bar["dt"].strftime("%H:%M"),
                            "exit_prem_1": round(fill_ex1, 2),
                            "exit_prem_2": round(fill_ex2, 2),
                            "pts_lot1": round(pts1, 2),
                            "pts_lot2": round(pts2, 2),
                            "avg_pts": round((pts1 + pts2)/2.0, 2),
                            "gross_pnl": round(gross, 2),
                            "costs": round(costs, 2),
                            "net_pnl": round(net, 2),
                            "result": "TARGET 1 (+100) & RUNNER BREAKEVEN (+4 pts)",
                            "is_win": True
                        }
                        all_trades.append(trade_record)
                        print(f"  [RUNNER BE] {trade_record['entry_time']} -> {trade_record['exit_time']} | {trade_record['instrument']} | P&L: Rs {net:,.2f}")
                        in_trade = False
                        pos = None
                        trades_today += 1
                        continue

                    elif hit_eod:
                        exit_raw = prem_close
                        fill_ex1 = max(0.5, pos["exit_prem_1"] * 0.995)
                        fill_ex2 = max(0.5, exit_raw * 0.995)
                        pts1 = fill_ex1 - fill_entry
                        pts2 = fill_ex2 - fill_entry
                        gross = (pts1 * lot_size) + (pts2 * lot_size)
                        stt = (fill_ex1 + fill_ex2) * lot_size * 0.000625
                        txn = (fill_entry * total_qty + (fill_ex1 + fill_ex2) * lot_size) * 0.00053
                        brokerage = 40.0
                        gst = (brokerage + txn) * 0.18
                        costs = brokerage + stt + txn + gst
                        net = gross - costs
                        capital += net

                        trade_record = {
                            "date": d_str,
                            "day": curr_d.strftime("%A"),
                            "playbook": pos["playbook"],
                            "instrument": f"NIFTY {strike} {pos['type']}",
                            "entry_time": pos["entry_dt"].strftime("%H:%M"),
                            "entry_prem": round(fill_entry, 2),
                            "exit_time": bar["dt"].strftime("%H:%M"),
                            "exit_prem_1": round(fill_ex1, 2),
                            "exit_prem_2": round(fill_ex2, 2),
                            "pts_lot1": round(pts1, 2),
                            "pts_lot2": round(pts2, 2),
                            "avg_pts": round((pts1 + pts2)/2.0, 2),
                            "gross_pnl": round(gross, 2),
                            "costs": round(costs, 2),
                            "net_pnl": round(net, 2),
                            "result": "TARGET 1 (+100) & RUNNER EOD SQUARE-OFF",
                            "is_win": True
                        }
                        all_trades.append(trade_record)
                        print(f"  [RUNNER EOD] {trade_record['entry_time']} -> {trade_record['exit_time']} | {trade_record['instrument']} | P&L: Rs {net:,.2f}")
                        in_trade = False
                        pos = None
                        trades_today += 1
                        continue

            # Signal Check
            if not in_trade:
                if trades_today >= 2:
                    continue
                if t < time(9, 25) or t > time(14, 0):
                    continue
                if b_range < 5.0:
                    continue

                lower_wick = min(b_open, spot) - b_low
                upper_wick = b_high - max(b_open, spot)
                bull_body = (spot > b_open) and ((spot - b_open) >= 0.25 * b_range)
                bear_body = (spot < b_open) and ((b_open - spot) >= 0.25 * b_range)
                prev_c = prev_bar["close"]

                # Breakouts
                r1_break = (prev_c <= lvl["r1"]) and (spot > lvl["r1"]) and bull_body
                s1_break = (prev_c >= lvl["s1"]) and (spot < lvl["s1"]) and bear_body

                # Reversals
                tested_r1 = (b_high >= lvl["r1"] >= b_low) or (prev_bar["high"] >= lvl["r1"] and b_high >= lvl["r1"])
                r1_fade = tested_r1 and (spot < lvl["r1"]) and (upper_wick >= 0.25 * b_range)
                tested_r2 = (b_high >= lvl["r2"])
                r2_fade = tested_r2 and (spot < lvl["r2"]) and (upper_wick >= 0.25 * b_range)

                # Gap Retests
                gap_r1_retest = False
                gap_s1_retest = False
                if day_open >= lvl["r1"]:
                    tested = (b_low <= lvl["r1"] <= b_high) or (b_low <= lvl["r1"])
                    gap_r1_retest = tested and (spot > lvl["r1"]) and (lower_wick >= 0.25 * b_range)
                elif day_open <= lvl["s1"]:
                    tested = (b_low <= lvl["s1"] <= b_high) or (b_high >= lvl["s1"])
                    gap_s1_retest = tested and (spot < lvl["s1"]) and (upper_wick >= 0.25 * b_range)

                # ORB
                gap_orb_pe = False
                if i >= 3 and day_open <= lvl["s1"]:
                    gap_orb_pe = (prev_c >= orb_low) and (spot < orb_low) and bear_body

                c_dir = None
                c_pb = ""
                if gap_r1_retest: c_dir = "CE"; c_pb = "Gap-Up R1 Polarity Bounce"
                elif gap_s1_retest: c_dir = "PE"; c_pb = "Gap-Down S1 Polarity Rejection"
                elif r1_fade: c_dir = "PE"; c_pb = "R1 Resistance Reversal"
                elif r2_fade: c_dir = "PE"; c_pb = "R2 Exhaustion Reversal"
                elif gap_orb_pe: c_dir = "PE"; c_pb = "Gap-and-Go Bearish ORB"
                elif s1_break: c_dir = "PE"; c_pb = "S1 Support Breakdown"

                if c_dir and c_pb in allowed_pbs:
                    atm_strike = int(round(spot / 50.0) * 50)
                    is_call = (c_dir == "CE")

                    if strike_mode == "OTM-1":
                        strike = (atm_strike + 50) if is_call else (atm_strike - 50)
                    elif strike_mode == "ATM":
                        strike = atm_strike

                    entry_raw = BlackScholesPricing.calculate_price(spot, strike, dte, 0.135, is_call=is_call)
                    fill_entry = entry_raw * 1.005
                    pos = {
                        "playbook": c_pb,
                        "type": c_dir,
                        "strike": strike,
                        "entry_spot": spot,
                        "entry_dt": bar["dt"],
                        "entry_raw": entry_raw,
                        "fill_entry": fill_entry,
                        "sl_prem": max(0.5, entry_raw - sl_pts),
                        "tp1_prem": entry_raw + tp1_pts,
                        "tp2_prem": entry_raw + tp2_pts,
                        "t1_hit": False,
                        "t2_hit": False,
                        "exit_prem_1": 0.0,
                        "exit_prem_2": 0.0
                    }
                    in_trade = True
                    print(f"  [ENTRY] {bar['dt'].strftime('%H:%M')} | Playbook: {c_pb} | Signal: {c_dir} | Spot: {spot:.2f} | Strike: NIFTY {strike} {c_dir} @ Rs {fill_entry:.2f}")

    return pd.DataFrame(all_trades)

if __name__ == "__main__":
    print("\n" + "="*80)
    print("RUNNING 2-LOT STAGED EXECUTION BACKTEST (OTM-1)")
    print("="*80)
    df_otm1 = run_backtest_for_days("OTM-1")
    
    print("\n" + "="*80)
    print("RUNNING 2-LOT STAGED EXECUTION BACKTEST (ATM)")
    print("="*80)
    df_atm = run_backtest_for_days("ATM")

    if not df_otm1.empty:
        df_otm1.to_csv("recent_two_days_otm1_trades.csv", index=False)
    if not df_atm.empty:
        df_atm.to_csv("recent_two_days_atm_trades.csv", index=False)
