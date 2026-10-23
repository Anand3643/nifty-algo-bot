import os
import sys
import datetime
from datetime import time
import pandas as pd
import numpy as np

base_dir = r"c:\Users\Admin\Desktop\nifty backttteest"
sys.path.insert(0, base_dir)

from compare_halt_3year import session_data, NiftySREngine, BlackScholesPricing

def run_staged_backtest(strike_mode="OTM-1", sl_pts=50.0, tp1_pts=100.0, tp2_pts=200.0,
                        be_buf=4.0, max_trades=2, stop_on_loss=False,
                        cutoff_time=time(14, 0), eod_time=time(15, 0)):
    lot_size = 65
    initial_capital = 50000.0
    capital = initial_capital
    trades = []

    allowed_pbs = [
        "Gap-Up R1 Polarity Bounce", "Gap-Down S1 Polarity Rejection",
        "R1 Resistance Reversal", "R2 Exhaustion Reversal",
        "Gap-and-Go Bearish ORB", "S1 Support Breakdown"
    ]

    for sess in session_data:
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

                # Staged Execution Logic
                entry_raw = pos["entry_raw"]
                fill_entry = pos["fill_entry"]
                hit_eod = (t >= eod_time)

                if not pos["t1_hit"]:
                    # Neither target hit yet
                    hit_sl = (prem_low <= pos["sl_prem"])
                    hit_tp1 = (prem_high >= pos["tp1_prem"])

                    if hit_sl and not hit_tp1:
                        # Full stop loss hit on entire position
                        exit_raw = pos["sl_prem"]
                        fill_exit = max(0.5, exit_raw * 0.995)
                        pts = fill_exit - fill_entry
                        gross = pts * lot_size
                        stt = fill_exit * lot_size * 0.000625
                        txn = (fill_entry + fill_exit) * lot_size * 0.00053
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
                            "entry_time": pos["entry_dt"].strftime("%H:%M"),
                            "exit_time": bar["dt"].strftime("%H:%M"),
                            "instrument": f"NIFTY {strike} {pos['type']}",
                            "playbook": pos["playbook"],
                            "entry_prem": round(fill_entry, 2),
                            "exit_prem_1": round(fill_exit, 2),
                            "exit_prem_2": round(fill_exit, 2),
                            "pts": round(pts, 2),
                            "net_pnl": round(net, 2),
                            "capital": round(capital, 2),
                            "result": f"STOP LOSS (-{sl_pts:.0f} pts)",
                            "is_win": False
                        })
                        in_trade = False
                        pos = None
                        trades_today += 1
                        continue

                    elif hit_tp1:
                        # Target 1 HIT (+100 pts on 50% position!)
                        pos["t1_hit"] = True
                        pos["exit_prem_1"] = pos["tp1_prem"]
                        pos["t1_time"] = bar["dt"]
                        # Move stop loss on remaining 50% to Breakeven + buffer
                        pos["sl_prem"] = entry_raw + be_buf

                        # Check if Target 2 hit in the very same bar
                        if prem_high >= pos["tp2_prem"]:
                            pos["t2_hit"] = True
                            pos["exit_prem_2"] = pos["tp2_prem"]
                            # Complete trade exit
                            fill_ex1 = max(0.5, pos["exit_prem_1"] * 0.995)
                            fill_ex2 = max(0.5, pos["exit_prem_2"] * 0.995)
                            pts1 = fill_ex1 - fill_entry
                            pts2 = fill_ex2 - fill_entry
                            avg_pts = (pts1 + pts2) / 2.0
                            gross = avg_pts * lot_size
                            avg_exit = (fill_ex1 + fill_ex2) / 2.0
                            stt = avg_exit * lot_size * 0.000625
                            txn = (fill_entry + avg_exit) * lot_size * 0.00053
                            brokerage = 40.0
                            gst = (brokerage + txn) * 0.18
                            costs = brokerage + stt + txn + gst
                            net = gross - costs
                            capital += net

                            trades.append({
                                "date": d_str,
                                "year": current_date.year,
                                "month": current_date.strftime("%Y-%m"),
                                "entry_time": pos["entry_dt"].strftime("%H:%M"),
                                "exit_time": bar["dt"].strftime("%H:%M"),
                                "instrument": f"NIFTY {strike} {pos['type']}",
                                "playbook": pos["playbook"],
                                "entry_prem": round(fill_entry, 2),
                                "exit_prem_1": round(fill_ex1, 2),
                                "exit_prem_2": round(fill_ex2, 2),
                                "pts": round(avg_pts, 2),
                                "net_pnl": round(net, 2),
                                "capital": round(capital, 2),
                                "result": "TARGET 1 (+100) & TARGET 2 (+200) HIT",
                                "is_win": True
                            })
                            in_trade = False
                            pos = None
                            trades_today += 1
                            continue

                    elif hit_eod:
                        # Full EOD exit before T1 or SL
                        exit_raw = prem_close
                        fill_exit = max(0.5, exit_raw * 0.995)
                        pts = fill_exit - fill_entry
                        gross = pts * lot_size
                        stt = fill_exit * lot_size * 0.000625
                        txn = (fill_entry + fill_exit) * lot_size * 0.00053
                        brokerage = 40.0
                        gst = (brokerage + txn) * 0.18
                        costs = brokerage + stt + txn + gst
                        net = gross - costs
                        capital += net
                        is_win = (net > 0)
                        if not is_win: has_lost_today = True

                        trades.append({
                            "date": d_str,
                            "year": current_date.year,
                            "month": current_date.strftime("%Y-%m"),
                            "entry_time": pos["entry_dt"].strftime("%H:%M"),
                            "exit_time": bar["dt"].strftime("%H:%M"),
                            "instrument": f"NIFTY {strike} {pos['type']}",
                            "playbook": pos["playbook"],
                            "entry_prem": round(fill_entry, 2),
                            "exit_prem_1": round(fill_exit, 2),
                            "exit_prem_2": round(fill_exit, 2),
                            "pts": round(pts, 2),
                            "net_pnl": round(net, 2),
                            "capital": round(capital, 2),
                            "result": "EOD EXIT",
                            "is_win": is_win
                        })
                        in_trade = False
                        pos = None
                        trades_today += 1
                        continue

                else:
                    # Target 1 was ALREADY hit in an earlier bar; managing remaining 50%
                    hit_tp2 = (prem_high >= pos["tp2_prem"])
                    hit_be = (prem_low <= pos["sl_prem"])

                    if hit_tp2 or hit_be or hit_eod:
                        fill_ex1 = max(0.5, pos["exit_prem_1"] * 0.995)
                        if hit_tp2:
                            exit_raw_2 = pos["tp2_prem"]
                            reason = "TARGET 1 (+100) & TARGET 2 (+200) HIT"
                        elif hit_be:
                            exit_raw_2 = pos["sl_prem"]
                            reason = "TARGET 1 (+100) & RUNNER BREAKEVEN (+4)"
                        else:
                            exit_raw_2 = prem_close
                            reason = "TARGET 1 (+100) & RUNNER EOD"

                        fill_ex2 = max(0.5, exit_raw_2 * 0.995)
                        pts1 = fill_ex1 - fill_entry
                        pts2 = fill_ex2 - fill_entry
                        avg_pts = (pts1 + pts2) / 2.0
                        gross = avg_pts * lot_size
                        avg_exit = (fill_ex1 + fill_ex2) / 2.0
                        stt = avg_exit * lot_size * 0.000625
                        txn = (fill_entry + avg_exit) * lot_size * 0.00053
                        brokerage = 40.0
                        gst = (brokerage + txn) * 0.18
                        costs = brokerage + stt + txn + gst
                        net = gross - costs
                        capital += net

                        trades.append({
                            "date": d_str,
                            "year": current_date.year,
                            "month": current_date.strftime("%Y-%m"),
                            "entry_time": pos["entry_dt"].strftime("%H:%M"),
                            "exit_time": bar["dt"].strftime("%H:%M"),
                            "instrument": f"NIFTY {strike} {pos['type']}",
                            "playbook": pos["playbook"],
                            "entry_prem": round(fill_entry, 2),
                            "exit_prem_1": round(fill_ex1, 2),
                            "exit_prem_2": round(fill_ex2, 2),
                            "pts": round(avg_pts, 2),
                            "net_pnl": round(net, 2),
                            "capital": round(capital, 2),
                            "result": reason,
                            "is_win": net > 0
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

    df = pd.DataFrame(trades)
    if df.empty: return {}
    n = len(df)
    wins = int(df["is_win"].sum())
    losses = n - wins
    wr = (wins / n) * 100.0
    net = float(df["net_pnl"].sum())
    gw = float(df[df["net_pnl"] > 0]["net_pnl"].sum())
    gl = abs(float(df[df["net_pnl"] < 0]["net_pnl"].sum()))
    pf = gw / gl if gl > 0 else 99.0
    cum = df["net_pnl"].cumsum()
    peak = cum.cummax()
    dd = float((peak - cum).max())
    calmar = net / dd if dd > 0 else 99.0
    roi = (net / initial_capital) * 100.0
    avg_win = float(df[df["net_pnl"] > 0]["net_pnl"].mean()) if wins > 0 else 0
    avg_loss = abs(float(df[df["net_pnl"] < 0]["net_pnl"].mean())) if losses > 0 else 0

    return {
        "n": n, "wins": wins, "losses": losses, "wr": wr,
        "net_pnl": net, "pf": pf, "dd": dd, "calmar": calmar,
        "roi": roi, "avg_win": avg_win, "avg_loss": avg_loss,
        "df": df
    }

print("Running 3-Year Simulations:")
print("1. OTM-1 Staged Scale-Out (50% @ +100, 50% @ +200, SL=50)")
s_otm1 = run_staged_backtest(strike_mode="OTM-1", sl_pts=50.0, tp1_pts=100.0, tp2_pts=200.0)

print("2. ATM Staged Scale-Out (50% @ +100, 50% @ +200, SL=50)")
s_atm = run_staged_backtest(strike_mode="ATM", sl_pts=50.0, tp1_pts=100.0, tp2_pts=200.0)

print("3. ATM Baseline Fixed (100% @ +200, SL=50)")
from compare_50_200_vs_40_120 import run_simulation
s_base = run_simulation(sl_pts=50.0, tp_pts=200.0, be_trigger=80.0, be_buf=4.0, trail_pts=15.0, stop_on_loss=False)

print("\n" + "="*105)
print("     3-YEAR HEAD-TO-HEAD BACKTEST: STAGED SCALE-OUT (OTM-1 vs ATM vs BASELINE)")
print("     Evaluation Period: 31-Oct-2023 to 21-Oct-2026 (733 Trading Days | 1 Lot Max 2 Trades)")
print("="*105)
print(f"{'METRIC':<28} | {'OTM-1 STAGED (100/200)':<23} | {'ATM STAGED (100/200)':<23} | {'ATM BASELINE (TRAILED)'}")
print("-" * 105)
print(f"{'Total Trades':<28} | {s_otm1['n']:<23} | {s_atm['n']:<23} | {s_base['n']}")
print(f"{'Win Rate (%)':<28} | {s_otm1['wr']:<22.1f}% | {s_atm['wr']:<22.1f}% | {s_base['wr']:.1f}%")
print(f"{'Wins / Losses':<28} | {s_otm1['wins']}W / {s_otm1['losses']}L" + " "*10 + f"| {s_atm['wins']}W / {s_atm['losses']}L" + " "*10 + f"| {s_base['wins']}W / {s_base['losses']}L")
print(f"{'Total Net P&L':<28} | Rs {s_otm1['net_pnl']:+12,.2f}        | Rs {s_atm['net_pnl']:+12,.2f}        | Rs {s_base['net_pnl']:+12,.2f}")
print(f"{'Return on Capital (ROI)':<28} | {s_otm1['roi']:+11.1f}%         | {s_atm['roi']:+11.1f}%         | {s_base['roi']:+11.1f}%")
print(f"{'Profit Factor (PF)':<28} | {s_otm1['pf']:<23.2f} | {s_atm['pf']:<23.2f} | {s_base['pf']:.2f}")
print(f"{'Max Peak Drawdown':<28} | Rs {s_otm1['dd']:9,.2f}         | Rs {s_atm['dd']:9,.2f}         | Rs {s_base['dd']:9,.2f}")
print(f"{'Calmar Ratio':<28} | {s_otm1['calmar']:<23.2f} | {s_atm['calmar']:<23.2f} | {s_base['calmar']:.2f}")
print(f"{'Avg Winning Trade':<28} | Rs {s_otm1['avg_win']:9,.2f}         | Rs {s_atm['avg_win']:9,.2f}         | Rs {s_base['avg_win']:9,.2f}")
print(f"{'Avg Losing Trade':<28} | Rs -{s_otm1['avg_loss']:8,.2f}         | Rs -{s_atm['avg_loss']:8,.2f}         | Rs -{s_base['avg_loss']:8,.2f}")
print("="*105)

# October 2026 MTD Performance
def oct_breakdown(res, name):
    d = res['df']
    oct_d = d[d['month'] == '2026-10']
    n = len(oct_d)
    w = int(oct_d['is_win'].sum())
    p = float(oct_d['net_pnl'].sum())
    wr = (w/n*100) if n>0 else 0
    print(f"{name:<35} | {n:<8} | {wr:<9.1f}% | Rs {p:+10,.2f}")

print("\nOCTOBER 2026 (THIS MONTH MTD) BREAKDOWN:")
print(f"{'Configuration':<35} | {'Trades':<8} | {'Win Rate':<10} | {'Net P&L'}")
print("-" * 75)
oct_breakdown(s_otm1, "OTM-1 Staged (50% @ 100, 50% @ 200)")
oct_breakdown(s_atm, "ATM Staged (50% @ 100, 50% @ 200)")
oct_breakdown(s_base, "ATM Baseline (Trailed 50:200)")
print("=" * 75)

# Save trades
s_otm1['df'].to_csv("trades_3year_otm1_staged.csv", index=False)
s_atm['df'].to_csv("trades_3year_atm_staged.csv", index=False)
print("Saved: trades_3year_otm1_staged.csv and trades_3year_atm_staged.csv")
