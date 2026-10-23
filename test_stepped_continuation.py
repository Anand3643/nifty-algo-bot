"""
Test Stepped S&R Continuation (R1 -> R2 -> R3, S1 -> S2 -> S3)
Options strictly closed when NIFTY Underlying hits the level!
"""
import os
import sys
import math
from datetime import datetime, time
import numpy as np
import pandas as pd

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

def run_stepped_test(session_data, spot_sl_pts=20.0, mode="trail_levels"):
    BROKERAGE_ORDER = 20.0
    STT_RATE = 0.000625
    EXCHANGE_TXN_RATE = 0.00053
    GST_RATE = 0.18
    lot_size = 65
    initial_capital = 50000.0
    slippage = 0.005
    vol = 0.135

    trades = []
    equity = initial_capital

    for sess in session_data:
        lvl = sess["lvl"]
        bars = sess["bars"]
        current_date = sess["date"]
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
        reached_stage = 1

        for i in range(1, len(bars) - 1):
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

                # Stepped Level Trailing logic
                if mode == "trail_levels":
                    if is_call:
                        if reached_stage == 1 and b_high >= lvl["r2"]:
                            reached_stage = 2
                            spot_sl = lvl["r1"] # lock breakeven at R1
                            spot_target = lvl["r3"] # target R3
                        elif reached_stage == 2 and b_high >= lvl["r3"]:
                            reached_stage = 3
                            spot_sl = lvl["r2"] # lock profit at R2
                            spot_target = lvl["r4"] # target R4
                    else: # PE
                        if reached_stage == 1 and b_low <= lvl["s2"]:
                            reached_stage = 2
                            spot_sl = lvl["s1"] # lock breakeven at S1
                            spot_target = lvl["s3"] # target S3
                        elif reached_stage == 2 and b_low <= lvl["s3"]:
                            reached_stage = 3
                            spot_sl = lvl["s2"] # lock profit at S2
                            spot_target = lvl["s4"] # target S4

                if is_call:
                    hit_target = (b_high >= spot_target)
                    hit_sl = (b_low <= spot_sl)
                else:
                    hit_target = (b_low <= spot_target)
                    hit_sl = (b_high >= spot_sl)

                hit_eod = (t >= time(15, 10))

                if hit_target or hit_sl or hit_eod:
                    if hit_target:
                        exit_spot = spot_target
                        reason = f"TARGET HIT (STAGE {reached_stage})"
                    elif hit_sl:
                        exit_spot = spot_sl
                        reason = f"TRAILING SL (STAGE {reached_stage})" if reached_stage > 1 else "STOP LOSS"
                    else:
                        exit_spot = spot
                        reason = "EOD EXIT"

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
                        "Stage": reached_stage,
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

            # ENTRY CHECK
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

                # R1 Breakout -> Target R2 (continue to R3)
                r1_break = (prev_c <= lvl["r1"]) and (spot > lvl["r1"]) and bull_body
                # S1 Breakdown -> Target S2 (continue to S3)
                s1_break = (prev_c >= lvl["s1"]) and (spot < lvl["s1"]) and bear_body

                # S2 Bounceback -> Target S1
                tested_s2 = (b_low <= lvl["s2"])
                s2_bounce = tested_s2 and (spot > lvl["s2"]) and (lower_wick >= 0.35 * b_range)

                # R2 Reversal -> Target R1
                tested_r2 = (b_high >= lvl["r2"])
                r2_fade = tested_r2 and (spot < lvl["r2"]) and (upper_wick >= 0.35 * b_range)

                take = False
                if s1_break:
                    trade_dir = "PE"
                    playbook = "S1 Breakdown & Continue to S2/S3"
                    spot_sl = lvl["s1"] + spot_sl_pts
                    spot_target = lvl["s2"]
                    take = True
                elif r1_break:
                    trade_dir = "CE"
                    playbook = "R1 Breakout & Continue to R2/R3"
                    spot_sl = lvl["r1"] - spot_sl_pts
                    spot_target = lvl["r2"]
                    take = True
                elif s2_bounce:
                    trade_dir = "CE"
                    playbook = "S2 Support Bounceback"
                    spot_sl = lvl["s2"] - spot_sl_pts
                    spot_target = lvl["s1"]
                    take = True
                elif r2_fade:
                    trade_dir = "PE"
                    playbook = "R2 Resistance Reversal"
                    spot_sl = lvl["r2"] + spot_sl_pts
                    spot_target = lvl["r1"]
                    take = True

                if take:
                    in_trade = True
                    strike = int(round(spot / 50) * 50)
                    entry_spot = spot
                    is_call = (trade_dir == "CE")
                    entry_prem = BlackScholesPricing.calculate_price(spot, strike, dte, vol, is_call=is_call)
                    entry_time = bar["dt"]
                    reached_stage = 1
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

    peak = df_res["Capital"].cummax()
    drawdown = df_res["Capital"] - peak
    max_dd = abs(drawdown.min())
    max_dd_pct = (max_dd / initial_capital) * 100.0

    daily_ret = df_res.groupby("Date")["Net_PnL"].sum()
    sharpe = (daily_ret.mean() / daily_ret.std()) * np.sqrt(252) if daily_ret.std() > 0 else 0.0

    target_hits = len(df_res[df_res["Result"].str.contains("TARGET")])
    sl_hits = len(df_res[df_res["Result"].str.contains("STOP LOSS")])
    trail_hits = len(df_res[df_res["Result"].str.contains("TRAILING SL")])

    return {
        "spot_sl_pts": spot_sl_pts,
        "mode": mode,
        "trades": total_trades,
        "wins": len(wins),
        "losses": len(losses),
        "win_rate": win_rate,
        "total_pts": total_pts,
        "total_spot_pts": total_spot_pts,
        "total_net": total_net,
        "profit_factor": profit_factor,
        "sharpe": sharpe,
        "max_dd": max_dd,
        "max_dd_pct": max_dd_pct,
        "target_hits": target_hits,
        "sl_hits": sl_hits,
        "trail_hits": trail_hits,
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

    print("=" * 105)
    print("   TESTING STEPPED LEVEL CONTINUATION (R1 -> R2 -> R3, S1 -> S2 -> S3)")
    print("   Options closed STRICTLY on NIFTY Underlying Level Triggers")
    print("=" * 105)

    for sl in [15.0, 20.0, 25.0]:
        res = run_stepped_test(session_data, spot_sl_pts=sl, mode="trail_levels")
        print(f"SL: {sl:.0f} pts | Trades: {res['trades']} | Win Rate: {res['win_rate']:.1f}% ({res['wins']}W/{res['losses']}L) | Net PnL: Rs {res['total_net']:+,.2f} | PF: {res['profit_factor']:.2f} | Sharpe: {res['sharpe']:.2f} | Max DD: Rs {res['max_dd']:,.0f} ({res['max_dd_pct']:.1f}%) | Targets: {res['target_hits']} | Trail Hits: {res['trail_hits']}")

if __name__ == "__main__":
    main()
