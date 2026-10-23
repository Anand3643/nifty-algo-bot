"""
Complete Combined Engine: BREAKOUT + BOUNCEBACK (Reversal) on Support & Resistance
1. Breakout / Breakdown Playbooks:
   - R1 Resistance Breakout -> Buy ATM CE
   - S1 Support Breakdown -> Buy ATM PE
   - CPR Top Bullish Breakout -> Buy ATM CE
   - CPR Bottom Bearish Breakdown -> Buy ATM PE
2. Bounceback / Reversal Playbooks:
   - S1 Support Bounceback -> Buy ATM CE
   - R1 Resistance Reversal -> Buy ATM PE
   - S2 Panic Sweep Bounceback -> Buy ATM CE
   - R2 Resistance Exhaustion Fade -> Buy ATM PE
3. Evaluates 1:2 vs 1:3 Risk-Reward ratios for 1 Lot = 65 Qty NIFTY Options
"""
import os
import sys
import math
from datetime import datetime, time
import numpy as np
import pandas as pd

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

SQRT2 = math.sqrt(2.0)
def std_norm_cdf(x: float) -> float:
    return 0.5 * (1.0 + math.erf(x / SQRT2))

class BlackScholesPricing:
    @staticmethod
    def calculate_price(spot: float, strike: float, tte: float, vol: float, r: float = 0.065, is_call: bool = True) -> float:
        if tte <= 0.0001:
            return max(0.5, (spot - strike) if is_call else (strike - spot))
        denom = vol * math.sqrt(tte)
        d1 = (math.log(spot / strike) + (r + 0.5 * vol**2) * tte) / denom
        d2 = d1 - denom
        if is_call:
            p = spot * std_norm_cdf(d1) - strike * math.exp(-r * tte) * std_norm_cdf(d2)
        else:
            p = strike * math.exp(-r * tte) * std_norm_cdf(-d2) - spot * std_norm_cdf(-d1)
        return max(0.5, p)

class NiftySREngine:
    @staticmethod
    def calculate_levels(high: float, low: float, close: float) -> dict:
        r = high - low
        c = close
        p = round(((high + low + close) / 3.0) / 5) * 5
        bc = round(((high + low) / 2.0) / 5) * 5
        tc = round(((2.0 * p) - bc) / 5) * 5

        r1 = round((c + 0.236 * r) / 5) * 5
        r2 = round((c + 0.500 * r) / 5) * 5
        r3 = round((c + 0.866 * r) / 5) * 5
        r4 = round((c + 1.333 * r) / 5) * 5

        s1 = round((c - 0.300 * r) / 5) * 5
        s2 = round((c - 0.550 * r) / 5) * 5
        s3 = round((c - 0.900 * r) / 5) * 5
        s4 = round((c - 1.314 * r) / 5) * 5

        cpr_top = max(bc, tc)
        cpr_bot = min(bc, tc)

        return {
            "pivot": p, "bc": bc, "tc": tc,
            "cpr_top": cpr_top, "cpr_bot": cpr_bot,
            "r1": r1, "r2": r2, "r3": r3, "r4": r4,
            "s1": s1, "s2": s2, "s3": s3, "s4": s4,
            "range": r, "prev_close": c
        }

def run_simulation(
    session_data,
    sl_val=25.0,
    rr=2.0,
    trail=False,
    max_trades_per_day=1,
    sl_mode="points",
    lot_size=65,
    initial_capital=50000.0,
    slippage=0.005,
    vol=0.135
):
    BROKERAGE_ORDER = 20.0
    STT_RATE = 0.000625
    EXCHANGE_TXN_RATE = 0.00053
    GST_RATE = 0.18
    tp_val = sl_val * rr

    trades = []
    equity = initial_capital

    for sess in session_data:
        lvl = sess["lvl"]
        bars = sess["bars"]
        current_date = sess["date"]
        day_open = sess["day_open"]
        dte = sess["dte"]

        in_trade = False
        trade_dir = None
        strike = 0
        entry_spot = 0.0
        entry_prem = 0.0
        curr_sl_prem = 0.0
        tp_prem = 0.0
        entry_time = None
        playbook = ""
        category = "" # "BREAKOUT" or "BOUNCEBACK"
        trades_today = 0
        max_fav_prem = 0.0

        for i in range(1, len(bars) - 1):
            bar = bars[i]
            prev_bar = bars[i - 1]
            t = bar["time"]

            spot = bar["close"]
            b_open = bar["open"]
            b_high = bar["high"]
            b_low = bar["low"]
            b_range = b_high - b_low

            # -------------------------------------------------------------
            # EXIT CHECK
            # -------------------------------------------------------------
            if in_trade:
                is_call = (trade_dir == "CE")
                prem_close = BlackScholesPricing.calculate_price(spot, strike, dte, vol, is_call=is_call)
                prem_high = BlackScholesPricing.calculate_price(b_high, strike, dte, vol, is_call=is_call) if is_call else BlackScholesPricing.calculate_price(b_low, strike, dte, vol, is_call=is_call)
                prem_low = BlackScholesPricing.calculate_price(b_low, strike, dte, vol, is_call=is_call) if is_call else BlackScholesPricing.calculate_price(b_high, strike, dte, vol, is_call=is_call)

                max_fav_prem = max(max_fav_prem, prem_high)

                if trail:
                    if sl_mode == "points":
                        if max_fav_prem >= entry_prem + sl_val:
                            curr_sl_prem = max(curr_sl_prem, entry_prem + 4.0)
                        if max_fav_prem >= entry_prem + 2.0 * sl_val:
                            curr_sl_prem = max(curr_sl_prem, entry_prem + sl_val)
                    else:
                        if max_fav_prem >= entry_prem * (1.0 + sl_val):
                            curr_sl_prem = max(curr_sl_prem, entry_prem * 1.03)
                        if max_fav_prem >= entry_prem * (1.0 + 2.0 * sl_val):
                            curr_sl_prem = max(curr_sl_prem, entry_prem * (1.0 + sl_val))

                hit_tp = (prem_high >= tp_prem)
                hit_sl = (prem_low <= curr_sl_prem)
                hit_eod = (t >= time(15, 10))

                if hit_tp or hit_sl or hit_eod:
                    if hit_tp:
                        exit_raw = tp_prem
                        reason = f"TARGET 1:{rr:g} HIT"
                    elif hit_sl:
                        exit_raw = curr_sl_prem
                        initial_sl = (entry_prem - sl_val) if sl_mode == "points" else entry_prem * (1.0 - sl_val)
                        reason = "TRAILING SL" if (curr_sl_prem > initial_sl) else "STOP LOSS"
                    else:
                        exit_raw = prem_close
                        reason = "EOD EXIT"

                    fill_entry = entry_prem * (1.0 + slippage)
                    fill_exit = max(0.5, exit_raw * (1.0 - slippage))

                    pts_diff = fill_exit - fill_entry
                    gross_pnl = pts_diff * lot_size

                    sell_turnover = fill_exit * lot_size
                    buy_turnover = fill_entry * lot_size
                    stt = sell_turnover * STT_RATE
                    txn_charges = (buy_turnover + sell_turnover) * EXCHANGE_TXN_RATE
                    brokerage = 2 * BROKERAGE_ORDER
                    gst = (brokerage + txn_charges) * GST_RATE
                    total_costs = brokerage + stt + txn_charges + gst

                    net_pnl = gross_pnl - total_costs
                    equity += net_pnl
                    ret_pct = (pts_diff / fill_entry) * 100.0

                    trades.append({
                        "Date": current_date.strftime("%Y-%m-%d"),
                        "Time": entry_time.strftime("%H:%M"),
                        "Exit_Time": bar["dt"].strftime("%H:%M"),
                        "Instrument": f"NIFTY {strike} {trade_dir}",
                        "Type": trade_dir,
                        "Strike": strike,
                        "Category": category,
                        "Playbook": playbook,
                        "Entry_Spot": round(entry_spot, 1),
                        "Exit_Spot": round(spot, 1),
                        "Entry_Prem": round(fill_entry, 2),
                        "Exit_Prem": round(fill_exit, 2),
                        "Prem_Pts": round(pts_diff, 2),
                        "Gross_PnL": round(gross_pnl, 2),
                        "Costs": round(total_costs, 2),
                        "Net_PnL": round(net_pnl, 2),
                        "Capital": round(equity, 2),
                        "Result": reason
                    })

                    in_trade = False
                    trades_today += 1
                    continue

            # -------------------------------------------------------------
            # ENTRY CHECK: BREAKOUT & BOUNCEBACK
            # -------------------------------------------------------------
            if not in_trade and trades_today < max_trades_per_day:
                if t < time(9, 25) or t > time(14, 45):
                    continue
                if b_range < 5:
                    continue

                prev_c = prev_bar["close"]
                lower_wick = min(b_open, spot) - b_low
                upper_wick = b_high - max(b_open, spot)

                bull_body = (spot > b_open) and ((spot - b_open) >= 0.35 * b_range)
                bear_body = (spot < b_open) and ((b_open - spot) >= 0.35 * b_range)

                # =========================================================
                # 1. BREAKOUT PLAYBOOKS (Momentum through levels)
                # =========================================================
                # R1 Breakout -> Buy CE
                r1_break = (prev_c <= lvl["r1"]) and (spot > lvl["r1"]) and bull_body
                # S1 Breakdown -> Buy PE
                s1_break = (prev_c >= lvl["s1"]) and (spot < lvl["s1"]) and bear_body
                # R2 Expansion -> Buy CE
                r2_break = (prev_c <= lvl["r2"]) and (spot > lvl["r2"]) and bull_body
                # S2 Flush -> Buy PE
                s2_break = (prev_c >= lvl["s2"]) and (spot < lvl["s2"]) and bear_body
                # CPR Top Breakout -> Buy CE
                cpr_up = (prev_c <= lvl["cpr_top"]) and (spot > lvl["cpr_top"]) and bull_body and (day_open >= lvl["cpr_bot"])
                # CPR Bot Breakdown -> Buy PE
                cpr_dn = (prev_c >= lvl["cpr_bot"]) and (spot < lvl["cpr_bot"]) and bear_body and (day_open <= lvl["cpr_top"])

                # =========================================================
                # 2. BOUNCEBACK PLAYBOOKS (Reversals off defended levels)
                # =========================================================
                # S1 Support Bounceback -> Buy CE (Rejects S1 and closes above S1 with hammer/bullish candle)
                tested_s1 = (b_low <= lvl["s1"] <= b_high) or (prev_bar["low"] <= lvl["s1"] and b_low <= lvl["s1"])
                s1_bounce = tested_s1 and (spot > lvl["s1"]) and ((lower_wick >= 0.35 * b_range) or (spot > prev_bar["high"] and spot > b_open))

                # R1 Resistance Reversal -> Buy PE (Rejects R1 and closes below R1 with shooting star/bearish candle)
                tested_r1 = (b_high >= lvl["r1"] >= b_low) or (prev_bar["high"] >= lvl["r1"] and b_high >= lvl["r1"])
                r1_fade = tested_r1 and (spot < lvl["r1"]) and ((upper_wick >= 0.35 * b_range) or (spot < prev_bar["low"] and spot < b_open))

                # S2 Sweep Bounceback -> Buy CE (Sweeps S2 panic and snaps back)
                tested_s2 = (b_low <= lvl["s2"])
                s2_bounce = tested_s2 and (spot > lvl["s2"]) and (lower_wick >= 0.35 * b_range)

                # R2 Resistance Exhaustion -> Buy PE (Tests R2 and fades)
                tested_r2 = (b_high >= lvl["r2"])
                r2_fade = tested_r2 and (spot < lvl["r2"]) and (upper_wick >= 0.35 * b_range)

                # Evaluate Signal Priority:
                cand_dir = None
                cand_pb = ""
                cand_cat = ""

                # Prioritize Primary Breakouts & Support Bouncebacks
                if s1_break:
                    cand_dir = "PE"; cand_pb = "S1 Support Breakdown"; cand_cat = "BREAKOUT"
                elif r1_break:
                    cand_dir = "CE"; cand_pb = "R1 Resistance Breakout"; cand_cat = "BREAKOUT"
                elif s1_bounce:
                    cand_dir = "CE"; cand_pb = "S1 Support Bounceback"; cand_cat = "BOUNCEBACK"
                elif r1_fade:
                    cand_dir = "PE"; cand_pb = "R1 Resistance Reversal"; cand_cat = "BOUNCEBACK"
                elif s2_break:
                    cand_dir = "PE"; cand_pb = "S2 Flush Breakdown"; cand_cat = "BREAKOUT"
                elif r2_break:
                    cand_dir = "CE"; cand_pb = "R2 Expansion Breakout"; cand_cat = "BREAKOUT"
                elif s2_bounce:
                    cand_dir = "CE"; cand_pb = "S2 Sweep Bounceback"; cand_cat = "BOUNCEBACK"
                elif r2_fade:
                    cand_dir = "PE"; cand_pb = "R2 Exhaustion Reversal"; cand_cat = "BOUNCEBACK"
                elif cpr_up:
                    cand_dir = "CE"; cand_pb = "CPR Top Breakout"; cand_cat = "BREAKOUT"
                elif cpr_dn:
                    cand_dir = "PE"; cand_pb = "CPR Bot Breakdown"; cand_cat = "BREAKOUT"

                if cand_dir:
                    in_trade = True
                    trade_dir = cand_dir
                    playbook = cand_pb
                    category = cand_cat
                    strike = int(round(spot / 50) * 50)
                    entry_spot = spot
                    is_call = (trade_dir == "CE")
                    entry_prem = BlackScholesPricing.calculate_price(spot, strike, dte, vol, is_call=is_call)
                    if sl_mode == "points":
                        curr_sl_prem = max(0.5, entry_prem - sl_val)
                        tp_prem = entry_prem + tp_val
                    else:
                        curr_sl_prem = entry_prem * (1.0 - sl_val)
                        tp_prem = entry_prem * (1.0 + tp_val)
                    entry_time = bar["dt"]
                    max_fav_prem = entry_prem
                    continue

    df_res = pd.DataFrame(trades)
    if len(df_res) == 0:
        return None

    wins = df_res[df_res["Net_PnL"] > 0]
    losses = df_res[df_res["Net_PnL"] <= 0]
    total_trades = len(df_res)
    win_rate = len(wins) / total_trades * 100.0

    total_gross = df_res["Gross_PnL"].sum()
    total_net = df_res["Net_PnL"].sum()
    total_costs = df_res["Costs"].sum()
    total_pts = df_res["Prem_Pts"].sum()

    gross_profit = wins["Gross_PnL"].sum() if len(wins) else 0.0
    gross_loss = abs(losses["Gross_PnL"].sum()) if len(losses) else 0.0
    profit_factor = (gross_profit / gross_loss) if gross_loss > 0 else 99.0

    avg_win = wins["Net_PnL"].mean() if len(wins) else 0.0
    avg_loss = abs(losses["Net_PnL"].mean()) if len(losses) else 0.0
    realized_rr = (avg_win / avg_loss) if avg_loss > 0 else 0.0

    peak = df_res["Capital"].cummax()
    drawdown = df_res["Capital"] - peak
    max_dd = abs(drawdown.min())
    max_dd_pct = (max_dd / initial_capital) * 100.0

    daily_ret = df_res.groupby("Date")["Net_PnL"].sum()
    sharpe = (daily_ret.mean() / daily_ret.std()) * np.sqrt(252) if daily_ret.std() > 0 else 0.0

    target_hits = len(df_res[df_res["Result"].str.contains("TARGET")])
    sl_hits = len(df_res[df_res["Result"].str.contains("STOP LOSS")])
    trail_hits = len(df_res[df_res["Result"].str.contains("TRAILING SL")])
    eod_exits = len(df_res[df_res["Result"].str.contains("EOD EXIT")])

    return {
        "sl_val": sl_val,
        "rr": rr,
        "trail": trail,
        "max_trades": max_trades_per_day,
        "trades": total_trades,
        "wins": len(wins),
        "losses": len(losses),
        "win_rate": win_rate,
        "total_pts": total_pts,
        "total_net": total_net,
        "total_costs": total_costs,
        "profit_factor": profit_factor,
        "avg_win": avg_win,
        "avg_loss": avg_loss,
        "realized_rr": realized_rr,
        "sharpe": sharpe,
        "max_dd": max_dd,
        "max_dd_pct": max_dd_pct,
        "target_hits": target_hits,
        "sl_hits": sl_hits,
        "trail_hits": trail_hits,
        "eod_exits": eod_exits,
        "trades_df": df_res
    }

def main():
    base_dir = os.path.dirname(os.path.abspath(__file__))
    candle_path = os.path.join(base_dir, "nifty_data", "candles", "NIFTY_5min.csv")
    daily_path = os.path.join(base_dir, "nifty_data", "candles", "NIFTY_1day.csv")

    df_intra = pd.read_csv(candle_path)
    df_intra["datetime"] = pd.to_datetime(df_intra["datetime"])
    df_intra.sort_values("datetime", inplace=True)

    df_1d = pd.read_csv(daily_path)
    df_1d["datetime"] = pd.to_datetime(df_1d["datetime"]).dt.date
    df_1d.drop_duplicates(subset=["datetime"], inplace=True)
    df_1d.set_index("datetime", inplace=True)

    session_data = []
    df_intra["date"] = df_intra["datetime"].dt.date

    for current_date, grp in df_intra.groupby("date"):
        if len(grp) < 12:
            continue
        priors = [d for d in df_1d.index if d < current_date]
        if not priors:
            continue
        prev_row = df_1d.loc[priors[-1]]
        lvl = NiftySREngine.calculate_levels(
            float(prev_row["high"]), float(prev_row["low"]), float(prev_row["close"])
        )
        dow = current_date.weekday()
        dte = max(0.5, (3 - dow) % 7 + 0.5) / 365.0
        day_open = float(grp["open"].iloc[0])

        bars = []
        for _, row in grp.iterrows():
            dt = row["datetime"]
            bars.append({
                "dt": dt,
                "time": dt.time(),
                "open": float(row["open"]),
                "high": float(row["high"]),
                "low": float(row["low"]),
                "close": float(row["close"])
            })

        session_data.append({
            "date": current_date,
            "lvl": lvl,
            "dte": dte,
            "day_open": day_open,
            "bars": bars
        })

    print("=" * 115)
    print("   BACKTESTING COMBINATION OF BREAKOUT + BOUNCEBACK (REVERSAL) ON NIFTY S&R")
    print(f"   Sessions: {len(session_data)} | 1 Lot = 65 Qty | Testing 1:2 vs 1:3 RR")
    print("=" * 115)

    results = []
    for m_trades in [1, 2]:
        for trail in [False, True]:
            for sl in [25.0, 30.0]:
                for rr in [1.5, 2.0, 2.5, 3.0]:
                    r = run_simulation(session_data, sl_val=sl, rr=rr, trail=trail, max_trades_per_day=m_trades)
                    if r:
                        results.append(r)

    df_summary = pd.DataFrame([{
        "MaxT": r["max_trades"],
        "SL": f"{r['sl_val']:.0f} pts",
        "Target": f"{r['sl_val']*r['rr']:.0f} pts",
        "RR": f"1:{r['rr']:g}",
        "Trail": "Yes" if r["trail"] else "No",
        "Trades": r["trades"],
        "Win_Rate": f"{r['win_rate']:.1f}%",
        "Wins": r["wins"],
        "Losses": r["losses"],
        "Tgt_Hits": r["target_hits"],
        "SL_Hits": r["sl_hits"],
        "Net_PnL": f"Rs {r['total_net']:+,.2f}",
        "PF": f"{r['profit_factor']:.2f}",
        "Sharpe": f"{r['sharpe']:.2f}",
        "Max_DD": f"Rs {r['max_dd']:,.0f} ({r['max_dd_pct']:.1f}%)",
        "_pnl_val": r["total_net"]
    } for r in results])

    df_summary.sort_values("_pnl_val", ascending=False, inplace=True)
    df_summary.to_csv(os.path.join(base_dir, "combo_breakout_bounceback_results.csv"), index=False)

    cols = ["MaxT", "SL", "Target", "RR", "Trail", "Trades", "Win_Rate", "Wins", "Losses", "Tgt_Hits", "SL_Hits", "Net_PnL", "PF", "Sharpe", "Max_DD"]
    print("\nTOP RESULTS FOR COMBINED (BREAKOUT + BOUNCEBACK) STRATEGY:")
    print(df_summary[cols].head(20).to_string(index=False))

    # Also save the specific runs for 1:2 and 1:3
    for r in results:
        if r["max_trades"] == 1 and r["sl_val"] == 25.0 and r["rr"] == 2.0 and not r["trail"]:
            r["trades_df"].to_csv(os.path.join(base_dir, "trades_combo_sl25_rr1_2.csv"), index=False)
        if r["max_trades"] == 1 and r["sl_val"] == 25.0 and r["rr"] == 3.0 and not r["trail"]:
            r["trades_df"].to_csv(os.path.join(base_dir, "trades_combo_sl25_rr1_3.csv"), index=False)
        if r["max_trades"] == 1 and r["sl_val"] == 25.0 and r["rr"] == 2.0 and r["trail"]:
            r["trades_df"].to_csv(os.path.join(base_dir, "trades_combo_sl25_rr1_2_trail.csv"), index=False)

if __name__ == "__main__":
    main()
