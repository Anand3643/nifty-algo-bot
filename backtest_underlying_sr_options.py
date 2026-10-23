"""
Institutional NIFTY Options Backtest:
- S&R Levels continue to S2, R2, S3, R3
- OPTIONS ARE ONLY CLOSED BASED ON THE NIFTY UNDERLYING (SPOT)
  * Target: Underlying touches target level (R2, S2, R3, S3) or Spot 1:2/1:3 RR
  * Stop Loss: Underlying breaches stop level on Spot chart
  * All exits executed at prevailing Black-Scholes ATM option premium
- 1 Lot = 65 Qty with full realistic statutory costs & slippage
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

def run_underlying_backtest(
    session_data,
    exit_rule="next_level", # "next_level" (R2/S2), "rr_1_2", "rr_1_3"
    spot_sl_pts=20.0,       # Stop loss in index spot points
    trail_underlying=False, # Trail spot SL to breakeven after 1:1 on spot
    lot_size=65,
    initial_capital=50000.0,
    slippage=0.005,
    vol=0.135
):
    BROKERAGE_ORDER = 20.0
    STT_RATE = 0.000625
    EXCHANGE_TXN_RATE = 0.00053
    GST_RATE = 0.18

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
        spot_sl = 0.0
        spot_target = 0.0
        entry_time = None
        playbook = ""
        trades_today = 0
        max_fav_spot = 0.0

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
            # EXIT CHECK: STRICTLY BASED ON NIFTY UNDERLYING (SPOT)
            # -------------------------------------------------------------
            if in_trade:
                is_call = (trade_dir == "CE")

                # Track underlying extremes for exit triggers
                if is_call:
                    hit_target = (b_high >= spot_target)
                    hit_sl = (b_low <= spot_sl)
                    fav_pts = b_high - entry_spot
                    max_fav_spot = max(max_fav_spot, b_high)
                else: # PE
                    hit_target = (b_low <= spot_target)
                    hit_sl = (b_high >= spot_sl)
                    fav_pts = entry_spot - b_low
                    max_fav_spot = max(max_fav_spot, entry_spot - b_low)

                # Underlying Trailing SL logic:
                if trail_underlying:
                    risk_pts = abs(entry_spot - spot_sl)
                    if max_fav_spot >= risk_pts:
                        # Move spot SL to entry breakeven + 3 pts
                        if is_call:
                            spot_sl = max(spot_sl, entry_spot + 3.0)
                        else:
                            spot_sl = min(spot_sl, entry_spot - 3.0)

                hit_eod = (t >= time(15, 10))

                if hit_target or hit_sl or hit_eod:
                    if hit_target:
                        exit_spot = spot_target
                        reason = "TARGET HIT (UNDERLYING LEVEL)"
                    elif hit_sl:
                        exit_spot = spot_sl
                        reason = "STOP LOSS (UNDERLYING BREACH)"
                    else:
                        exit_spot = spot
                        reason = "EOD EXIT"

                    # Calculate option premium at the underlying exit spot
                    exit_prem_raw = BlackScholesPricing.calculate_price(exit_spot, strike, dte, vol, is_call=is_call)
                    
                    fill_entry = entry_prem * (1.0 + slippage)
                    fill_exit = max(0.5, exit_prem_raw * (1.0 - slippage))

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
                    spot_pts = (exit_spot - entry_spot) if is_call else (entry_spot - exit_spot)

                    trades.append({
                        "Date": current_date.strftime("%Y-%m-%d"),
                        "Time": entry_time.strftime("%H:%M"),
                        "Exit_Time": bar["dt"].strftime("%H:%M"),
                        "Instrument": f"NIFTY {strike} {trade_dir}",
                        "Type": trade_dir,
                        "Strike": strike,
                        "Playbook": playbook,
                        "Entry_Spot": round(entry_spot, 1),
                        "Exit_Spot": round(exit_spot, 1),
                        "Spot_Pts": round(spot_pts, 1),
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
            # ENTRY CHECK: SUPPORT & RESISTANCE (CONTINUING TO S2 & R2)
            # -------------------------------------------------------------
            if not in_trade and trades_today < 1:
                if t < time(9, 25) or t > time(14, 45):
                    continue
                if b_range < 5:
                    continue

                prev_c = prev_bar["close"]
                lower_wick = min(b_open, spot) - b_low
                upper_wick = b_high - max(b_open, spot)

                bull_body = (spot > b_open) and ((spot - b_open) >= 0.35 * b_range)
                bear_body = (spot < b_open) and ((b_open - spot) >= 0.35 * b_range)

                # --- 1. BREAKOUT CONTINUATION TO R2 & S2 ---
                # A. Break R1 -> Target R2 (Continuation)
                r1_break = (prev_c <= lvl["r1"]) and (spot > lvl["r1"]) and bull_body
                # B. Break R2 -> Target R3 (Expansion Continuation)
                r2_break = (prev_c <= lvl["r2"]) and (spot > lvl["r2"]) and bull_body

                # C. Break S1 -> Target S2 (Continuation)
                s1_break = (prev_c >= lvl["s1"]) and (spot < lvl["s1"]) and bear_body
                # D. Break S2 -> Target S3 (Flush Continuation)
                s2_break = (prev_c >= lvl["s2"]) and (spot < lvl["s2"]) and bear_body

                # --- 2. REVERSAL / BOUNCEBACK AT S1, S2, R1, R2 ---
                # E. S1 Bounce -> Target Pivot / CPR
                tested_s1 = (b_low <= lvl["s1"] <= b_high) or (prev_bar["low"] <= lvl["s1"] and b_low <= lvl["s1"])
                s1_bounce = tested_s1 and (spot > lvl["s1"]) and ((lower_wick >= 0.35 * b_range) or (spot > prev_bar["high"] and spot > b_open))

                # F. S2 Bounce -> Target S1 (Support Sweep)
                tested_s2 = (b_low <= lvl["s2"])
                s2_bounce = tested_s2 and (spot > lvl["s2"]) and (lower_wick >= 0.35 * b_range)

                # G. R1 Reversal -> Target Pivot / CPR
                tested_r1 = (b_high >= lvl["r1"] >= b_low) or (prev_bar["high"] >= lvl["r1"] and b_high >= lvl["r1"])
                r1_fade = tested_r1 and (spot < lvl["r1"]) and ((upper_wick >= 0.35 * b_range) or (spot < prev_bar["low"] and spot < b_open))

                # H. R2 Reversal -> Target R1 (Resistance Exhaustion)
                tested_r2 = (b_high >= lvl["r2"])
                r2_fade = tested_r2 and (spot < lvl["r2"]) and (upper_wick >= 0.35 * b_range)

                take_trade = False
                td = None
                pb = ""
                tgt_spot = 0.0
                sl_spot = 0.0

                if s1_break:
                    td = "PE"
                    pb = "S1 Breakout & Continue to S2"
                    take_trade = True
                    sl_spot = lvl["s1"] + spot_sl_pts
                    if exit_rule == "next_level":
                        tgt_spot = lvl["s2"]
                    elif exit_rule == "rr_1_2":
                        tgt_spot = spot - (2.0 * spot_sl_pts)
                    elif exit_rule == "rr_1_3":
                        tgt_spot = spot - (3.0 * spot_sl_pts)

                elif r1_break:
                    td = "CE"
                    pb = "R1 Breakout & Continue to R2"
                    take_trade = True
                    sl_spot = lvl["r1"] - spot_sl_pts
                    if exit_rule == "next_level":
                        tgt_spot = lvl["r2"]
                    elif exit_rule == "rr_1_2":
                        tgt_spot = spot + (2.0 * spot_sl_pts)
                    elif exit_rule == "rr_1_3":
                        tgt_spot = spot + (3.0 * spot_sl_pts)

                elif s2_break:
                    td = "PE"
                    pb = "S2 Flush & Continue to S3"
                    take_trade = True
                    sl_spot = lvl["s2"] + spot_sl_pts
                    if exit_rule == "next_level":
                        tgt_spot = lvl["s3"]
                    elif exit_rule == "rr_1_2":
                        tgt_spot = spot - (2.0 * spot_sl_pts)
                    elif exit_rule == "rr_1_3":
                        tgt_spot = spot - (3.0 * spot_sl_pts)

                elif r2_break:
                    td = "CE"
                    pb = "R2 Breakout & Continue to R3"
                    take_trade = True
                    sl_spot = lvl["r2"] - spot_sl_pts
                    if exit_rule == "next_level":
                        tgt_spot = lvl["r3"]
                    elif exit_rule == "rr_1_2":
                        tgt_spot = spot + (2.0 * spot_sl_pts)
                    elif exit_rule == "rr_1_3":
                        tgt_spot = spot + (3.0 * spot_sl_pts)

                elif s2_bounce:
                    td = "CE"
                    pb = "S2 Support Bounceback"
                    take_trade = True
                    sl_spot = lvl["s2"] - spot_sl_pts
                    if exit_rule == "next_level":
                        tgt_spot = lvl["s1"]
                    elif exit_rule == "rr_1_2":
                        tgt_spot = spot + (2.0 * spot_sl_pts)
                    elif exit_rule == "rr_1_3":
                        tgt_spot = spot + (3.0 * spot_sl_pts)

                elif r2_fade:
                    td = "PE"
                    pb = "R2 Resistance Reversal"
                    take_trade = True
                    sl_spot = lvl["r2"] + spot_sl_pts
                    if exit_rule == "next_level":
                        tgt_spot = lvl["r1"]
                    elif exit_rule == "rr_1_2":
                        tgt_spot = spot - (2.0 * spot_sl_pts)
                    elif exit_rule == "rr_1_3":
                        tgt_spot = spot - (3.0 * spot_sl_pts)

                elif r1_fade:
                    td = "PE"
                    pb = "R1 Resistance Reversal"
                    take_trade = True
                    sl_spot = lvl["r1"] + spot_sl_pts
                    if exit_rule == "next_level":
                        tgt_spot = lvl["pivot"]
                    elif exit_rule == "rr_1_2":
                        tgt_spot = spot - (2.0 * spot_sl_pts)
                    elif exit_rule == "rr_1_3":
                        tgt_spot = spot - (3.0 * spot_sl_pts)

                elif s1_bounce:
                    td = "CE"
                    pb = "S1 Support Bounceback"
                    take_trade = True
                    sl_spot = lvl["s1"] - spot_sl_pts
                    if exit_rule == "next_level":
                        tgt_spot = lvl["pivot"]
                    elif exit_rule == "rr_1_2":
                        tgt_spot = spot + (2.0 * spot_sl_pts)
                    elif exit_rule == "rr_1_3":
                        tgt_spot = spot + (3.0 * spot_sl_pts)

                if take_trade:
                    in_trade = True
                    trade_dir = td
                    playbook = pb
                    strike = int(round(spot / 50) * 50)
                    entry_spot = spot
                    spot_target = tgt_spot
                    spot_sl = sl_spot
                    is_call = (trade_dir == "CE")
                    entry_prem = BlackScholesPricing.calculate_price(spot, strike, dte, vol, is_call=is_call)
                    entry_time = bar["dt"]
                    max_fav_spot = 0.0
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
    total_spot_pts = df_res["Spot_Pts"].sum()

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
    eod_exits = len(df_res[df_res["Result"].str.contains("EOD EXIT")])

    return {
        "exit_rule": exit_rule,
        "spot_sl_pts": spot_sl_pts,
        "trail_underlying": trail_underlying,
        "trades": total_trades,
        "wins": len(wins),
        "losses": len(losses),
        "win_rate": win_rate,
        "total_pts": total_pts,
        "total_spot_pts": total_spot_pts,
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
        bars = [
            {"dt": r["datetime"], "time": r["datetime"].time(), "open": float(r["open"]), "high": float(r["high"]), "low": float(r["low"]), "close": float(r["close"])}
            for _, r in grp.iterrows()
        ]
        session_data.append({"date": current_date, "lvl": lvl, "dte": dte, "day_open": float(grp["open"].iloc[0]), "bars": bars})

    print("=" * 115)
    print("   BACKTEST: S&R CONTINUATION TO S2 & R2 WITH EXITS STRICTLY GOVERNED BY NIFTY UNDERLYING")
    print(f"   Sessions: {len(session_data)} | 1 Lot = 65 Qty NIFTY Options | Spot-Governed SL/TP")
    print("=" * 115)

    results = []
    for exit_rule in ["next_level", "rr_1_2", "rr_1_3"]:
        for sl_pts in [15.0, 20.0, 25.0]:
            for trail in [False, True]:
                res = run_underlying_backtest(session_data, exit_rule=exit_rule, spot_sl_pts=sl_pts, trail_underlying=trail)
                if res:
                    results.append(res)

    df_summary = pd.DataFrame([{
        "Exit_Rule": r["exit_rule"],
        "Spot_SL": f"{r['spot_sl_pts']:.0f} pts",
        "Trail_Spot": "Yes" if r["trail_underlying"] else "No",
        "Trades": r["trades"],
        "Win_Rate": f"{r['win_rate']:.1f}%",
        "Wins": r["wins"],
        "Losses": r["losses"],
        "Tgt_Hits": r["target_hits"],
        "SL_Hits": r["sl_hits"],
        "EOD_Exits": r["eod_exits"],
        "Prem_Pts": f"{r['total_pts']:+.1f}",
        "Spot_Pts": f"{r['total_spot_pts']:+.1f}",
        "Net_PnL": f"Rs {r['total_net']:+,.2f}",
        "PF": f"{r['profit_factor']:.2f}",
        "Sharpe": f"{r['sharpe']:.2f}",
        "Max_DD": f"Rs {r['max_dd']:,.0f} ({r['max_dd_pct']:.1f}%)",
        "_pnl_val": r["total_net"]
    } for r in results])

    df_summary.sort_values("_pnl_val", ascending=False, inplace=True)
    df_summary.to_csv(os.path.join(base_dir, "underlying_sr_results.csv"), index=False)

    cols = ["Exit_Rule", "Spot_SL", "Trail_Spot", "Trades", "Win_Rate", "Wins", "Losses", "Tgt_Hits", "SL_Hits", "Prem_Pts", "Spot_Pts", "Net_PnL", "PF", "Sharpe", "Max_DD"]
    print("\nRESULTS: S&R CONTINUATION TO S2 & R2 (OPTIONS CLOSED ON UNDERLYING SPOT):")
    print(df_summary[cols].head(18).to_string(index=False))

    # Save top trade files
    for r in results:
        if r["exit_rule"] == "next_level" and r["spot_sl_pts"] == 20.0 and not r["trail_underlying"]:
            r["trades_df"].to_csv(os.path.join(base_dir, "trades_underlying_next_level_sl20.csv"), index=False)
        if r["exit_rule"] == "rr_1_2" and r["spot_sl_pts"] == 20.0 and not r["trail_underlying"]:
            r["trades_df"].to_csv(os.path.join(base_dir, "trades_underlying_rr1_2_sl20.csv"), index=False)
        if r["exit_rule"] == "rr_1_3" and r["spot_sl_pts"] == 20.0 and not r["trail_underlying"]:
            r["trades_df"].to_csv(os.path.join(base_dir, "trades_underlying_rr1_3_sl20.csv"), index=False)

if __name__ == "__main__":
    main()
