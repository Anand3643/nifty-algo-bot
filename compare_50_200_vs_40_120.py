import os
import sys
import datetime
from datetime import time
import pandas as pd
import numpy as np

base_dir = r"c:\Users\Admin\Desktop\nifty backttteest"
sys.path.insert(0, base_dir)

from compare_halt_3year import session_data, NiftySREngine, BlackScholesPricing

def run_simulation(sl_pts, tp_pts, be_trigger=None, be_buf=4.0, trail_pts=None,
                   stop_on_loss=False, max_trades=2, cutoff_time=time(14, 0), eod_time=time(15, 0),
                   allowed_pbs=None):
    if allowed_pbs is None:
        allowed_pbs = [
            "Gap-Up R1 Polarity Bounce", "Gap-Down S1 Polarity Rejection",
            "R1 Resistance Reversal", "R2 Exhaustion Reversal",
            "Gap-and-Go Bearish ORB", "S1 Support Breakdown"
        ]

    lot_size = 65
    initial_capital = 50000.0
    capital = initial_capital
    trades = []

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

                if prem_high > pos["max_ltp"]:
                    pos["max_ltp"] = prem_high

                # Smart BE Lock & Dynamic Trail
                if be_trigger is not None and pos["max_ltp"] >= pos["entry_raw"] + be_trigger:
                    be_sl = pos["entry_raw"] + be_buf
                    if be_sl > pos["sl_prem"]:
                        pos["sl_prem"] = be_sl
                        pos["be_protected"] = True
                    if trail_pts is not None and trail_pts > 0:
                        trail_sl = pos["max_ltp"] - trail_pts
                        if trail_sl > pos["sl_prem"]:
                            pos["sl_prem"] = trail_sl
                            pos["trailed"] = True

                hit_tp = (prem_high >= pos["tp_prem"])
                hit_sl = (prem_low <= pos["sl_prem"])
                hit_eod = (t >= eod_time)

                if hit_tp or hit_sl or hit_eod:
                    if hit_tp:
                        exit_raw = pos["tp_prem"]
                        reason = f"TARGET HIT (+{tp_pts:.0f} pts)"
                    elif hit_sl:
                        exit_raw = pos["sl_prem"]
                        if pos.get("trailed"):
                            reason = f"TRAILING STOP (Locked +{exit_raw - pos['entry_raw']:.1f} pts)"
                        elif pos.get("be_protected"):
                            reason = "BREAKEVEN PROTECTED (+4 pts)"
                        else:
                            reason = f"STOP LOSS (-{sl_pts:.0f} pts)"
                    else:
                        exit_raw = prem_close
                        reason = "EOD EXIT"

                    fill_exit = max(0.5, exit_raw * 0.995)
                    pts = fill_exit - pos["fill_entry"]
                    gross = pts * lot_size
                    stt = fill_exit * lot_size * 0.000625
                    txn = (pos["fill_entry"] + fill_exit) * lot_size * 0.00053
                    brokerage = 40.0
                    gst = (brokerage + txn) * 0.18
                    costs = brokerage + stt + txn + gst
                    net = gross - costs
                    capital += net

                    is_win = (net > 0)
                    if not is_win:
                        has_lost_today = True

                    trades.append({
                        "date": d_str,
                        "year": current_date.year,
                        "month": current_date.strftime("%Y-%m"),
                        "trade_num": trades_today + 1,
                        "entry_time": pos["entry_dt"].strftime("%H:%M"),
                        "exit_time": bar["dt"].strftime("%H:%M"),
                        "instrument": f"NIFTY {strike} {pos['type']}",
                        "playbook": pos["playbook"],
                        "entry_prem": round(pos["fill_entry"], 2),
                        "exit_prem": round(fill_exit, 2),
                        "pts": round(pts, 2),
                        "gross_pnl": round(gross, 2),
                        "costs": round(costs, 2),
                        "net_pnl": round(net, 2),
                        "capital": round(capital, 2),
                        "result": reason,
                        "is_win": is_win
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
                    strike = int(round(spot / 50.0) * 50)
                    is_call = (c_dir == "CE")
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
                        "tp_prem": entry_raw + tp_pts,
                        "max_ltp": entry_raw,
                        "be_protected": False,
                        "trailed": False
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
    rr_realized = avg_win / avg_loss if avg_loss > 0 else 0

    return {
        "n": n, "wins": wins, "losses": losses, "wr": wr,
        "net_pnl": net, "pf": pf, "dd": dd, "calmar": calmar,
        "roi": roi, "avg_win": avg_win, "avg_loss": avg_loss,
        "realized_rr": rr_realized, "df": df
    }

# Run 4 Configurations across 3 Years:
# 1. 50:200 with Smart BE & Dynamic Trail (Live Bot Strategy)
# 2. 50:200 Fixed (No Trailing)
# 3. 40:120 with Smart BE & Dynamic Trail
# 4. 40:120 Fixed (1:3 Pure Target Hit)
print("Running 3-Year Simulations (MAX_TRADES_PER_DAY = 2, stop_on_loss = False)...")

c1 = run_simulation(sl_pts=50.0, tp_pts=200.0, be_trigger=80.0, be_buf=4.0, trail_pts=15.0, stop_on_loss=False)
c2 = run_simulation(sl_pts=50.0, tp_pts=200.0, be_trigger=None, trail_pts=None, stop_on_loss=False)
c3 = run_simulation(sl_pts=40.0, tp_pts=120.0, be_trigger=60.0, be_buf=4.0, trail_pts=15.0, stop_on_loss=False)
c4 = run_simulation(sl_pts=40.0, tp_pts=120.0, be_trigger=None, trail_pts=None, stop_on_loss=False)

print("\n" + "="*110)
print("     3-YEAR HEAD-TO-HEAD BACKTEST: 50:200 (1:4 RR) VS 40:120 (1:3 RR)")
print("     Evaluation Period: 31-Oct-2023 to 21-Oct-2026 (733 Trading Days | Max Trades = 2)")
print("="*110)
header = f"{'METRIC':<28} | {'50:200 (TRAILED)':<18} | {'50:200 (FIXED)':<18} | {'40:120 (TRAILED)':<18} | {'40:120 (FIXED)'}"
print(header)
print("-"*110)
print(f"{'Total Trades':<28} | {c1['n']:<18} | {c2['n']:<18} | {c3['n']:<18} | {c4['n']}")
print(f"{'Win Rate (%)':<28} | {c1['wr']:<17.1f}% | {c2['wr']:<17.1f}% | {c3['wr']:<17.1f}% | {c4['wr']:.1f}%")
print(f"{'Wins / Losses':<28} | {c1['wins']}W / {c1['losses']}L" + " "*6 + f"| {c2['wins']}W / {c2['losses']}L" + " "*6 + f"| {c3['wins']}W / {c3['losses']}L" + " "*6 + f"| {c4['wins']}W / {c4['losses']}L")
print(f"{'Total Net P&L':<28} | Rs {c1['net_pnl']:+12,.2f}  | Rs {c2['net_pnl']:+12,.2f}  | Rs {c3['net_pnl']:+12,.2f}  | Rs {c4['net_pnl']:+12,.2f}")
print(f"{'Return on Capital (ROI)':<28} | {c1['roi']:+11.1f}%   | {c2['roi']:+11.1f}%   | {c3['roi']:+11.1f}%   | {c4['roi']:+11.1f}%")
print(f"{'Profit Factor (PF)':<28} | {c1['pf']:<18.2f} | {c2['pf']:<18.2f} | {c3['pf']:<18.2f} | {c4['pf']:.2f}")
print(f"{'Max Peak Drawdown':<28} | Rs {c1['dd']:9,.2f}   | Rs {c2['dd']:9,.2f}   | Rs {c3['dd']:9,.2f}   | Rs {c4['dd']:9,.2f}")
print(f"{'Calmar Ratio':<28} | {c1['calmar']:<18.2f} | {c2['calmar']:<18.2f} | {c3['calmar']:<18.2f} | {c4['calmar']:.2f}")
print(f"{'Avg Winning Trade':<28} | Rs {c1['avg_win']:9,.2f}   | Rs {c2['avg_win']:9,.2f}   | Rs {c3['avg_win']:9,.2f}   | Rs {c4['avg_win']:9,.2f}")
print(f"{'Avg Losing Trade':<28} | Rs -{c1['avg_loss']:8,.2f}   | Rs -{c2['avg_loss']:8,.2f}   | Rs -{c3['avg_loss']:8,.2f}   | Rs -{c4['avg_loss']:8,.2f}")
print(f"{'Realized Risk-Reward':<28} | {c1['realized_rr']:<18.2f} | {c2['realized_rr']:<18.2f} | {c3['realized_rr']:<18.2f} | {c4['realized_rr']:.2f}")
print("="*110)

# October 2026 Specific Comparison
def oct_metrics(res):
    d = res['df']
    oct_d = d[d['month'] == '2026-10']
    n = len(oct_d)
    w = int(oct_d['is_win'].sum())
    p = float(oct_d['net_pnl'].sum())
    wr = (w/n*100) if n>0 else 0
    return n, w, wr, p

o1 = oct_metrics(c1)
o2 = oct_metrics(c2)
o3 = oct_metrics(c3)
o4 = oct_metrics(c4)

print("\nOCTOBER 2026 (THIS MONTH MTD) COMPARISON:")
print(f"{'Config':<35} | {'Trades':<8} | {'Win Rate':<10} | {'Net P&L'}")
print("-"*75)
print(f"{'50:200 (Trailed - Live Bot Setup)':<35} | {o1[0]:<8} | {o1[2]:<9.1f}% | Rs {o1[3]:+10,.2f}")
print(f"{'50:200 (Fixed TP 200)':<35} | {o2[0]:<8} | {o2[2]:<9.1f}% | Rs {o2[3]:+10,.2f}")
print(f"{'40:120 (Trailed)':<35} | {o3[0]:<8} | {o3[2]:<9.1f}% | Rs {o3[3]:+10,.2f}")
print(f"{'40:120 (Fixed TP 120 - 1:3 RR)':<35} | {o4[0]:<8} | {o4[2]:<9.1f}% | Rs {o4[3]:+10,.2f}")
print("="*75)

# Save trades
c1['df'].to_csv("trades_3year_50_200_trailed.csv", index=False)
c4['df'].to_csv("trades_3year_40_120_fixed.csv", index=False)
print("Saved: trades_3year_50_200_trailed.csv and trades_3year_40_120_fixed.csv")
