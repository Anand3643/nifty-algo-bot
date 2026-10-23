import os
import sys
import datetime
from datetime import time
import pandas as pd
import numpy as np

base_dir = r"c:\Users\Admin\Desktop\nifty backttteest"
sys.path.insert(0, base_dir)

from compare_halt_3year import session_data, BlackScholesPricing

def run_2lot_staged_backtest(strike_mode="OTM-1", sl_pts=50.0, tp1_pts=100.0, tp2_pts=200.0,
                             be_buf=4.0, max_trades=2, stop_on_loss=False,
                             initial_capital=50000.0):
    lot_size = 65
    num_lots = 2
    total_qty = lot_size * num_lots  # 130 Qty
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

                entry_raw = pos["entry_raw"]
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
                            "pts_lot1": round(pts, 2),
                            "pts_lot2": round(pts, 2),
                            "avg_pts": round(pts, 2),
                            "pnl_lot1": round((pts * lot_size) - (costs / 2.0), 2),
                            "pnl_lot2": round((pts * lot_size) - (costs / 2.0), 2),
                            "gross_pnl": round(gross, 2),
                            "costs": round(costs, 2),
                            "net_pnl": round(net, 2),
                            "capital": round(capital, 2),
                            "result": f"STOP LOSS (-{sl_pts:.0f} pts on 2 Lots)",
                            "is_win": False
                        })
                        in_trade = False
                        pos = None
                        trades_today += 1
                        continue

                    elif hit_tp1:
                        # Target 1 HIT (+100 pts on Lot 1)
                        pos["t1_hit"] = True
                        pos["exit_prem_1"] = pos["tp1_prem"]
                        pos["t1_time"] = bar["dt"]
                        # Move SL on Lot 2 to Entry + buffer (Risk-Free Breakeven)
                        pos["sl_prem"] = entry_raw + be_buf

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
                                "pts_lot1": round(pts1, 2),
                                "pts_lot2": round(pts2, 2),
                                "avg_pts": round((pts1 + pts2) / 2.0, 2),
                                "pnl_lot1": round((pts1 * lot_size) - (costs / 2.0), 2),
                                "pnl_lot2": round((pts2 * lot_size) - (costs / 2.0), 2),
                                "gross_pnl": round(gross, 2),
                                "costs": round(costs, 2),
                                "net_pnl": round(net, 2),
                                "capital": round(capital, 2),
                                "result": "TARGET 1 (+100) & TARGET 2 (+200) FULL VICTORY",
                                "is_win": True
                            })
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
                            "pts_lot1": round(pts, 2),
                            "pts_lot2": round(pts, 2),
                            "avg_pts": round(pts, 2),
                            "pnl_lot1": round((pts * lot_size) - (costs / 2.0), 2),
                            "pnl_lot2": round((pts * lot_size) - (costs / 2.0), 2),
                            "gross_pnl": round(gross, 2),
                            "costs": round(costs, 2),
                            "net_pnl": round(net, 2),
                            "capital": round(capital, 2),
                            "result": "EOD AUTO SQUARE-OFF (2 Lots)",
                            "is_win": is_win
                        })
                        in_trade = False
                        pos = None
                        trades_today += 1
                        continue

                # PHASE 2: Target 1 already hit in an earlier bar; managing Lot 2 Runner
                else:
                    hit_tp2 = (prem_high >= pos["tp2_prem"])
                    hit_be = (prem_low <= pos["sl_prem"])

                    if hit_tp2 or hit_be or hit_eod:
                        fill_ex1 = max(0.5, pos["exit_prem_1"] * 0.995)
                        if hit_tp2:
                            exit_raw_2 = pos["tp2_prem"]
                            reason = "TARGET 1 (+100) & TARGET 2 (+200) FULL VICTORY"
                        elif hit_be:
                            exit_raw_2 = pos["sl_prem"]
                            reason = "TARGET 1 (+100) & RUNNER BREAKEVEN (+4)"
                        else:
                            exit_raw_2 = prem_close
                            reason = "TARGET 1 (+100) & RUNNER EOD"

                        fill_ex2 = max(0.5, exit_raw_2 * 0.995)
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
                            "entry_time": pos["entry_dt"].strftime("%H:%M"),
                            "exit_time": bar["dt"].strftime("%H:%M"),
                            "instrument": f"NIFTY {strike} {pos['type']}",
                            "playbook": pos["playbook"],
                            "entry_prem": round(fill_entry, 2),
                            "exit_prem_1": round(fill_ex1, 2),
                            "exit_prem_2": round(fill_ex2, 2),
                            "pts_lot1": round(pts1, 2),
                            "pts_lot2": round(pts2, 2),
                            "avg_pts": round((pts1 + pts2) / 2.0, 2),
                            "pnl_lot1": round((pts1 * lot_size) - (costs / 2.0), 2),
                            "pnl_lot2": round((pts2 * lot_size) - (costs / 2.0), 2),
                            "gross_pnl": round(gross, 2),
                            "costs": round(costs, 2),
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

if __name__ == "__main__":
    print("=" * 110)
    print("      THE 2-LOT STAGED EXECUTION ENGINE: 3-YEAR & OCTOBER 2026 BACKTEST AUDIT")
    print("      Rules: 2 Lots Entry | T1 @ +100 pts (Book 1 Lot) | Move SL to BE+4 | T2 @ +200 pts (Runner)")
    print("      Period: 31-Oct-2023 to 21-Oct-2026 (733 Trading Days | Max 2 Trades/Day)")
    print("=" * 110)

    print("\nRunning Backtest 1: OTM-1 Strikes (OTM-1 Staged Scale-Out)...")
    res_otm1 = run_2lot_staged_backtest(strike_mode="OTM-1", sl_pts=50.0, tp1_pts=100.0, tp2_pts=200.0)

    print("Running Backtest 2: ATM Strikes (ATM Staged Scale-Out)...")
    res_atm = run_2lot_staged_backtest(strike_mode="ATM", sl_pts=50.0, tp1_pts=100.0, tp2_pts=200.0)

    print("\n" + "=" * 110)
    print(f"{'METRIC':<30} | {'2-LOT OTM-1 STAGED (CHAMPION)':<35} | {'2-LOT ATM STAGED'}")
    print("-" * 110)
    print(f"{'Total Trades Taken':<30} | {res_otm1['n']:<35} | {res_atm['n']}")
    print(f"{'Win Rate (%)':<30} | {res_otm1['wr']:<34.1f}% | {res_atm['wr']:.1f}%")
    print(f"{'Wins / Losses':<30} | {res_otm1['wins']}W / {res_otm1['losses']}L" + " "*20 + f"| {res_atm['wins']}W / {res_atm['losses']}L")
    print(f"{'Total Net Profit (P&L)':<30} | Rs {res_otm1['net_pnl']:+12,.2f}" + " "*17 + f"| Rs {res_atm['net_pnl']:+12,.2f}")
    print(f"{'Return on Capital (ROI)':<30} | {res_otm1['roi']:+11.1f}%" + " "*18 + f"| {res_atm['roi']:+11.1f}%")
    print(f"{'Profit Factor (PF)':<30} | {res_otm1['pf']:<35.2f} | {res_atm['pf']:.2f}")
    print(f"{'Max Peak Drawdown':<30} | Rs {res_otm1['dd']:9,.2f}" + " "*20 + f"| Rs {res_atm['dd']:9,.2f}")
    print(f"{'Calmar Ratio':<30} | {res_otm1['calmar']:<35.2f} | {res_atm['calmar']:.2f}")
    print(f"{'Avg Winning Trade':<30} | Rs {res_otm1['avg_win']:9,.2f}" + " "*20 + f"| Rs {res_atm['avg_win']:9,.2f}")
    print(f"{'Avg Losing Trade':<30} | Rs -{res_otm1['avg_loss']:8,.2f}" + " "*20 + f"| Rs -{res_atm['avg_loss']:8,.2f}")
    print("=" * 110)

    # Save CSVs
    res_otm1['df'].to_csv("trades_3year_2lot_staged_otm1.csv", index=False)
    res_atm['df'].to_csv("trades_3year_2lot_staged_atm.csv", index=False)
    print("\nSaved trade logs: trades_3year_2lot_staged_otm1.csv and trades_3year_2lot_staged_atm.csv")

    # October 2026 Trade Breakdown for OTM-1
    print("\n" + "=" * 110)
    print("             OCTOBER 2026 MONTH-TO-DATE (MTD) TRADE LEDGER: 2-LOT OTM-1 STAGED")
    print("=" * 110)
    oct_df = res_otm1['df'][res_otm1['df']['month'] == '2026-10']
    for idx, r in oct_df.iterrows():
        print(f"📅 {r['date']} | {r['entry_time']}->{r['exit_time']} | {r['instrument']} | {r['playbook']}")
        print(f"   Entry: Rs {r['entry_prem']:.2f} | Ex1: Rs {r['exit_prem_1']:.2f} (Lot 1) | Ex2: Rs {r['exit_prem_2']:.2f} (Lot 2)")
        print(f"   Pts: L1 {r['pts_lot1']:+.1f} pts, L2 {r['pts_lot2']:+.1f} pts | Net PnL: Rs {r['net_pnl']:+,.2f} | Result: {r['result']}")
        print("-" * 110)

    oct_net = oct_df['net_pnl'].sum()
    oct_wins = (oct_df['net_pnl'] > 0).sum()
    oct_losses = len(oct_df) - oct_wins
    print(f"OCTOBER 2026 SUMMARY: {len(oct_df)} Trades | {oct_wins}W / {oct_losses}L ({oct_wins/len(oct_df)*100:.1f}% WR) | Net P&L: Rs {oct_net:+,.2f}")
    print("=" * 110)
