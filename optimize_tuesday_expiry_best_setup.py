"""
Comprehensive Multi-Year Optimization & Backtest: Tuesday Expiry Series
Analysis of Best Setup across 733 Trading Sessions (Nov 2023 - Oct 2026)
"""
import os
import sys
import datetime
from datetime import time, timedelta
import pandas as pd
import numpy as np

base_dir = r"c:\Users\Admin\Desktop\nifty backttteest"
sys.path.insert(0, base_dir)

from compare_halt_3year import session_data, BlackScholesPricing

# Re-compute DTE for all sessions using the TUESDAY EXPIRY CYCLE (weekday 1)
tuesday_sessions = []
for sess in session_data:
    s = dict(sess)
    dow = s["dow"]
    days_to_tue = (1 - dow) % 7
    if days_to_tue == 0:
        days_to_tue = 0.5
    s["dte"] = (days_to_tue + 0.5) / 365.0
    tuesday_sessions.append(s)

print(f"Loaded {len(tuesday_sessions)} sessions calibrated to Tuesday Expiry series.")

def run_simulation(
    strike_mode="OTM-1",
    sl_pts=50.0,
    tp1_pts=100.0,
    tp2_pts=200.0,
    be_buf=4.0,
    max_trades=2,
    cutoff_time=time(14, 0),
    no_duplicate_pb=True,
    stop_on_loss=False,
    initial_capital=50000.0
):
    lot_size = 65
    num_lots = 2
    total_qty = lot_size * num_lots # 130 Qty
    capital = initial_capital
    trades = []
    
    allowed_pbs = [
        "Gap-Up R1 Polarity Bounce", "Gap-Down S1 Polarity Rejection",
        "R1 Resistance Reversal", "R2 Exhaustion Reversal",
        "Gap-and-Go Bearish ORB", "S1 Support Breakdown"
    ]

    for sess in tuesday_sessions:
        lvl = sess["lvl"]
        bars = sess["bars"]
        current_date = sess["date"]
        d_str = str(current_date)
        dte = sess["dte"]
        day_open = sess["day_open"]
        orb_high = max(b["high"] for b in bars[:3])
        orb_low = min(b["low"] for b in bars[:3])

        trades_today = 0
        in_trade = False
        pos = None
        has_lost_today = False
        executed_pbs_today = set()

        for i in range(1, len(bars)):
            bar = bars[i]
            prev_bar = bars[i-1]
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

                # Phase 1: Both lots active
                if not pos["t1_hit"]:
                    hit_sl = (prem_low <= pos["sl_prem"])
                    hit_tp1 = (prem_high >= pos["tp1_prem"])

                    if hit_sl and not hit_tp1:
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
                        has_lost_today = True

                        trades.append({
                            "date": d_str,
                            "year": current_date.year,
                            "month": current_date.strftime("%Y-%m"),
                            "playbook": pos["playbook"],
                            "instrument": f"NIFTY {strike} {pos['type']}",
                            "net_pnl": net,
                            "pts": pts,
                            "is_win": False,
                            "result": "STOP LOSS HIT"
                        })
                        in_trade = False
                        pos = None
                        trades_today += 1
                        continue

                    elif hit_tp1:
                        pos["t1_hit"] = True
                        pos["exit_prem_1"] = pos["tp1_prem"]
                        pos["be_prem"] = fill_entry + be_buf

                        if prem_high >= pos["tp2_prem"]:
                            pos["t2_hit"] = True
                            fill_ex1 = max(0.5, pos["exit_prem_1"] * 0.995)
                            fill_ex2 = max(0.5, pos["tp2_prem"] * 0.995)
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

                            trades.append({
                                "date": d_str,
                                "year": current_date.year,
                                "month": current_date.strftime("%Y-%m"),
                                "playbook": pos["playbook"],
                                "instrument": f"NIFTY {strike} {pos['type']}",
                                "net_pnl": net,
                                "pts": (pts1 + pts2)/2,
                                "is_win": True,
                                "result": "T1+T2 FULL VICTORY"
                            })
                            in_trade = False
                            pos = None
                            trades_today += 1
                            continue

                    elif hit_eod:
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
                        if net < 0: has_lost_today = True

                        trades.append({
                            "date": d_str,
                            "year": current_date.year,
                            "month": current_date.strftime("%Y-%m"),
                            "playbook": pos["playbook"],
                            "instrument": f"NIFTY {strike} {pos['type']}",
                            "net_pnl": net,
                            "pts": pts,
                            "is_win": net > 0,
                            "result": "EOD SQUARE-OFF"
                        })
                        in_trade = False
                        pos = None
                        trades_today += 1
                        continue

                else:
                    # Phase 2: Lot 2 Runner
                    hit_tp2 = (prem_high >= pos["tp2_prem"])
                    hit_be = (prem_low <= pos["be_prem"])

                    if hit_tp2:
                        fill_ex1 = max(0.5, pos["exit_prem_1"] * 0.995)
                        fill_ex2 = max(0.5, pos["tp2_prem"] * 0.995)
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

                        trades.append({
                            "date": d_str,
                            "year": current_date.year,
                            "month": current_date.strftime("%Y-%m"),
                            "playbook": pos["playbook"],
                            "instrument": f"NIFTY {strike} {pos['type']}",
                            "net_pnl": net,
                            "pts": (pts1 + pts2)/2,
                            "is_win": True,
                            "result": "T1+T2 RUNNER VICTORY"
                        })
                        in_trade = False
                        pos = None
                        trades_today += 1
                        continue

                    elif hit_be or hit_eod:
                        fill_ex1 = max(0.5, pos["exit_prem_1"] * 0.995)
                        fill_ex2 = max(0.5, pos["be_prem"] * 0.995) if hit_be else max(0.5, prem_close * 0.995)
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

                        trades.append({
                            "date": d_str,
                            "year": current_date.year,
                            "month": current_date.strftime("%Y-%m"),
                            "playbook": pos["playbook"],
                            "instrument": f"NIFTY {strike} {pos['type']}",
                            "net_pnl": net,
                            "pts": (pts1 + pts2)/2,
                            "is_win": net > 0,
                            "result": "T1 + RUNNER BE (+4)" if hit_be else "T1 + RUNNER EOD"
                        })
                        in_trade = False
                        pos = None
                        trades_today += 1
                        continue

            # Signal Check
            if not in_trade:
                if trades_today >= max_trades:
                    continue
                if stop_on_loss and has_lost_today:
                    continue
                if t < time(9, 25) or t > cutoff_time:
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

                # Check Duplicate Playbook on Same Day
                if no_duplicate_pb and c_pb in executed_pbs_today:
                    continue

                if c_dir and c_pb in allowed_pbs:
                    atm_strike = int(round(spot / 50.0) * 50)
                    is_call = (c_dir == "CE")

                    if strike_mode == "OTM-1":
                        strike = (atm_strike + 50) if is_call else (atm_strike - 50)
                    elif strike_mode == "ATM":
                        strike = atm_strike
                    elif strike_mode == "ITM-1":
                        strike = (atm_strike - 50) if is_call else (atm_strike + 50)

                    entry_raw = BlackScholesPricing.calculate_price(spot, strike, dte, 0.135, is_call=is_call)
                    fill_entry = entry_raw * 1.005
                    pos = {
                        "playbook": c_pb,
                        "type": c_dir,
                        "strike": strike,
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
                    executed_pbs_today.add(c_pb)

    df = pd.DataFrame(trades)
    if df.empty:
        return {"net": 0, "wr": 0, "trades": 0, "pf": 0, "max_dd": 0, "calmar": 0}

    n = len(df)
    wins = int(df["is_win"].sum())
    losses = n - wins
    wr = (wins / n) * 100.0
    net = float(df["net_pnl"].sum())

    gross_wins = df[df["net_pnl"] > 0]["net_pnl"].sum()
    gross_loss = abs(df[df["net_pnl"] < 0]["net_pnl"].sum())
    pf = (gross_wins / gross_loss) if gross_loss > 0 else 99.0

    df["cum"] = df["net_pnl"].cumsum() + initial_capital
    df["peak"] = df["cum"].cummax()
    df["dd"] = df["peak"] - df["cum"]
    max_dd = float(df["dd"].max())
    ann_ret = net / 3.0
    calmar = (ann_ret / max_dd) if max_dd > 0 else 99.0

    return {
        "trades": n,
        "wins": wins,
        "losses": losses,
        "wr": round(wr, 1),
        "net": round(net, 2),
        "pf": round(pf, 2),
        "max_dd": round(max_dd, 2),
        "calmar": round(calmar, 2),
        "df": df
    }

# SYSTEMATIC GRID SWEEP
setups = [
    {"name": "Setup 1: Baseline 2-Lot Staged (OTM-1, 14:00 cutoff, No Filter)", "strike": "OTM-1", "cutoff": time(14,0), "no_dup": False, "sl": 50, "t1": 100, "t2": 200},
    {"name": "Setup 2: 2-Lot Staged + Duplicate Level Exhaustion Filter (Recommended)", "strike": "OTM-1", "cutoff": time(14,0), "no_dup": True, "sl": 50, "t1": 100, "t2": 200},
    {"name": "Setup 3: 2-Lot Staged + Duplicate Filter + 13:30 Cutoff (Chop Shield)", "strike": "OTM-1", "cutoff": time(13,30), "no_dup": True, "sl": 50, "t1": 100, "t2": 200},
    {"name": "Setup 4: 2-Lot Staged + Duplicate Filter + 13:00 Cutoff (Morning Trend Only)", "strike": "OTM-1", "cutoff": time(13,0), "no_dup": True, "sl": 50, "t1": 100, "t2": 200},
    {"name": "Setup 5: ATM 2-Lot Staged + Duplicate Filter (ATM Benchmark)", "strike": "ATM", "cutoff": time(14,0), "no_dup": True, "sl": 50, "t1": 100, "t2": 200},
    {"name": "Setup 6: ITM-1 2-Lot Staged + Duplicate Filter (Higher Delta)", "strike": "ITM-1", "cutoff": time(14,0), "no_dup": True, "sl": 50, "t1": 100, "t2": 200},
    {"name": "Setup 7: Tighter Risk 2-Lot Staged (SL 40, T1 80, T2 160)", "strike": "OTM-1", "cutoff": time(14,0), "no_dup": True, "sl": 40, "t1": 80, "t2": 160},
    {"name": "Setup 8: 1-Trade Daily Max (Stop after 1 trade regardless of outcome)", "strike": "OTM-1", "cutoff": time(14,0), "no_dup": True, "sl": 50, "t1": 100, "t2": 200, "max_trades": 1},
]

results = []
print("\n" + "="*95)
print("RUNNING SYSTEMATIC GRID OPTIMIZATION (TUESDAY EXPIRY SERIES - 733 SESSIONS)")
print("="*95)

for s in setups:
    max_tr = s.get("max_trades", 2)
    res = run_simulation(
        strike_mode=s["strike"],
        sl_pts=s["sl"],
        tp1_pts=s["t1"],
        tp2_pts=s["t2"],
        cutoff_time=s["cutoff"],
        no_duplicate_pb=s["no_dup"],
        max_trades=max_tr
    )
    results.append({
        "Setup": s["name"],
        "Trades": res["trades"],
        "Win Rate (%)": res["wr"],
        "Net P&L (Rs)": res["net"],
        "Profit Factor": res["pf"],
        "Max Drawdown (Rs)": res["max_dd"],
        "Calmar Ratio": res["calmar"]
    })
    print(f"-> {s['name'][:55]:<55} | WR: {res['wr']:>4}% | Net: Rs {res['net']:>10,.2f} | PF: {res['pf']:>4} | MaxDD: Rs {res['max_dd']:>8,.2f} | Calmar: {res['calmar']:>5}")

res_df = pd.DataFrame(results)
res_df.to_csv("tuesday_expiry_optimization_results.csv", index=False)
print("\nSaved optimization results to tuesday_expiry_optimization_results.csv")
