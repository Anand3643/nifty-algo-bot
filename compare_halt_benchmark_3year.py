import os
import sys
import datetime
from datetime import time
import pandas as pd
import numpy as np

base_dir = r"c:\Users\Admin\Desktop\nifty backttteest"
sys.path.insert(0, base_dir)

from compare_halt_3year import session_data, NiftySREngine, BlackScholesPricing

def run_3year_5m_benchmark(stop_on_loss=True, sl_val=40.0, rr=3.0, max_trades=2):
    tp_val = sl_val * rr
    lot_size = 65
    initial_capital = 50000.0
    capital = initial_capital
    trades = []
    allowed_pb = ["S2 Flush Breakdown", "R1 Resistance Reversal", "R2 Exhaustion Reversal", "R1 Resistance Breakout", "S1 Support Breakdown"]

    for sess in session_data:
        lvl = sess["lvl"]
        bars = sess["bars"]
        current_date = sess["date"]
        d_str = str(current_date)
        dte = sess["dte"]

        in_trade = False
        trade_dir = None
        strike = 0
        entry_prem = 0.0
        curr_sl = 0.0
        curr_tp = 0.0
        playbook = ""
        trades_today = 0
        entry_time = None
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
                is_call = (trade_dir == "CE")
                prem_close = BlackScholesPricing.calculate_price(spot, strike, dte, 0.135, is_call=is_call)
                prem_high = BlackScholesPricing.calculate_price(b_high, strike, dte, 0.135, is_call=is_call) if is_call else BlackScholesPricing.calculate_price(b_low, strike, dte, 0.135, is_call=is_call)
                prem_low = BlackScholesPricing.calculate_price(b_low, strike, dte, 0.135, is_call=is_call) if is_call else BlackScholesPricing.calculate_price(b_high, strike, dte, 0.135, is_call=is_call)

                hit_tp = (prem_high >= curr_tp)
                hit_sl = (prem_low <= curr_sl)
                hit_eod = (t >= time(15, 10))

                if hit_tp or hit_sl or hit_eod:
                    exit_raw = curr_tp if hit_tp else (curr_sl if hit_sl else prem_close)
                    fill_entry = entry_prem * 1.005
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
                    reason = "TARGET 1:3 HIT" if hit_tp else ("STOP LOSS" if hit_sl else "EOD EXIT")

                    is_win = (net > 0)
                    if not is_win:
                        has_lost_today = True

                    trades.append({
                        "date": d_str,
                        "year": current_date.year,
                        "month": current_date.strftime("%Y-%m"),
                        "trade_num": trades_today + 1,
                        "entry_time": entry_time.strftime("%H:%M") if entry_time else "09:25",
                        "exit_time": bar["dt"].strftime("%H:%M"),
                        "instrument": f"NIFTY {strike} {trade_dir}",
                        "playbook": playbook,
                        "pts": round(pts, 2),
                        "net_pnl": round(net, 2),
                        "capital": round(capital, 2),
                        "result": reason,
                        "is_win": is_win
                    })
                    in_trade = False
                    trades_today += 1
                    continue

            if not in_trade:
                if trades_today >= max_trades:
                    continue
                if stop_on_loss and has_lost_today:
                    continue
                if t < time(9, 25) or t > time(14, 45):
                    continue
                if b_range < 5:
                    continue

                lower_wick = min(b_open, spot) - b_low
                upper_wick = b_high - max(b_open, spot)
                bull_body = (spot > b_open) and ((spot - b_open) >= 0.35 * b_range)
                bear_body = (spot < b_open) and ((b_open - spot) >= 0.35 * b_range)
                prev_c = prev_bar["close"]

                r1_break = (prev_c <= lvl["r1"]) and (spot > lvl["r1"]) and bull_body
                s1_break = (prev_c >= lvl["s1"]) and (spot < lvl["s1"]) and bear_body
                r2_break = (prev_c <= lvl["r2"]) and (spot > lvl["r2"]) and bull_body
                s2_break = (prev_c >= lvl["s2"]) and (spot < lvl["s2"]) and bear_body

                tested_s1 = (b_low <= lvl["s1"] <= b_high) or (prev_bar["low"] <= lvl["s1"] and b_low <= lvl["s1"])
                s1_bounce = tested_s1 and (spot > lvl["s1"]) and ((lower_wick >= 0.35 * b_range) or (spot > prev_bar["high"] and spot > b_open))
                tested_r1 = (b_high >= lvl["r1"] >= b_low) or (prev_bar["high"] >= lvl["r1"] and b_high >= lvl["r1"])
                r1_fade = tested_r1 and (spot < lvl["r1"]) and ((upper_wick >= 0.35 * b_range) or (spot < prev_bar["low"] and spot < b_open))
                tested_s2 = (b_low <= lvl["s2"])
                s2_bounce = tested_s2 and (spot > lvl["s2"]) and (lower_wick >= 0.35 * b_range)
                tested_r2 = (b_high >= lvl["r2"])
                r2_fade = tested_r2 and (spot < lvl["r2"]) and (upper_wick >= 0.35 * b_range)

                c_dir = None
                c_pb = ""
                if s1_break: c_dir = "PE"; c_pb = "S1 Support Breakdown"
                elif r1_break: c_dir = "CE"; c_pb = "R1 Resistance Breakout"
                elif s1_bounce: c_dir = "CE"; c_pb = "S1 Support Bounceback"
                elif r1_fade: c_dir = "PE"; c_pb = "R1 Resistance Reversal"
                elif s2_break: c_dir = "PE"; c_pb = "S2 Flush Breakdown"
                elif r2_break: c_dir = "CE"; c_pb = "R2 Expansion Breakout"
                elif s2_bounce: c_dir = "CE"; c_pb = "S2 Sweep Bounceback"
                elif r2_fade: c_dir = "PE"; c_pb = "R2 Exhaustion Reversal"

                if c_dir and c_pb in allowed_pb:
                    in_trade = True
                    trade_dir = c_dir
                    playbook = c_pb
                    strike = int(round(spot / 50) * 50)
                    is_call = (trade_dir == "CE")
                    entry_prem = BlackScholesPricing.calculate_price(spot, strike, dte, 0.135, is_call=is_call)
                    curr_sl = max(0.5, entry_prem - sl_val)
                    curr_tp = entry_prem + tp_val
                    entry_time = bar["dt"]
                    continue

    df = pd.DataFrame(trades)
    n = len(df)
    wins = int(df["is_win"].sum())
    wr = (wins / n) * 100.0 if n > 0 else 0
    net = float(df["net_pnl"].sum())
    cum = df["net_pnl"].cumsum()
    peak = cum.cummax()
    dd = float((peak - cum).max()) if n > 0 else 0
    gw = float(df[df["net_pnl"] > 0]["net_pnl"].sum())
    gl = abs(float(df[df["net_pnl"] < 0]["net_pnl"].sum()))
    pf = gw / gl if gl > 0 else 99.0
    calmar = net / dd if dd > 0 else 99.0
    return {"n": n, "wins": wins, "wr": wr, "net": net, "pf": pf, "dd": dd, "calmar": calmar, "df": df}

b_halt = run_3year_5m_benchmark(stop_on_loss=True)
b_no_halt = run_3year_5m_benchmark(stop_on_loss=False)

print("="*95)
print("  3-YEAR BENCHMARK ENGINE (40pt SL | 1:3 RR): WITH HALT vs WITHOUT HALT")
print("="*95)
print(f"WITH HALT:    Trades: {b_halt['n']} | WR: {b_halt['wr']:.1f}% | Net PnL: Rs {b_halt['net']:+,.2f} | PF: {b_halt['pf']:.2f} | Max DD: Rs {b_halt['dd']:,.2f}")
print(f"WITHOUT HALT: Trades: {b_no_halt['n']} | WR: {b_no_halt['wr']:.1f}% | Net PnL: Rs {b_no_halt['net']:+,.2f} | PF: {b_no_halt['pf']:.2f} | Max DD: Rs {b_no_halt['dd']:,.2f}")
