"""
Analyze what happens when NIFTY takes support and reverses on S1:
1. Frequency: How often does NIFTY test S1 and reverse vs break down?
2. Upward Target Reach: Does it reach Pivot, CPR, R1, or R2?
3. Trade Simulation: What happens if you BUY ATM CE on S1 reversal?
   - Win Rate, Average Points, Risk-Reward 1:2 vs 1:3
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

    df_intra["date"] = df_intra["datetime"].dt.date

    s1_events = []
    bounce_trades = []

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

        s1 = lvl["s1"]
        pivot = lvl["pivot"]
        cpr_bot = lvl["cpr_bot"]
        cpr_top = lvl["cpr_top"]
        r1 = lvl["r1"]

        # Check if S1 was tested
        day_low = grp["low"].min()
        day_high = grp["high"].max()

        if day_low <= s1:
            # S1 was touched/tested today!
            # Did it bounce or break down?
            bars = grp.to_dict(orient="records")
            tested_idx = -1
            bounce_confirmed = False
            breakdown_confirmed = False
            bounce_bar = None

            for i in range(1, len(bars) - 1):
                b = bars[i]
                prev_b = bars[i - 1]
                t = b["datetime"].time()
                if t < time(9, 25) or t > time(14, 45):
                    continue

                b_low = float(b["low"])
                b_high = float(b["high"])
                b_open = float(b["open"])
                b_close = float(b["close"])
                b_range = b_high - b_low

                # S1 test condition: low dipped into or below S1
                if b_low <= s1 <= b_high or (prev_b["low"] <= s1 and b_low <= s1):
                    # Check if candle rejects S1 and closes above S1 with lower wick (Hammer/Rejection)
                    lower_wick = min(b_open, b_close) - b_low
                    is_bull_reject = (b_close > s1) and (lower_wick >= 0.35 * b_range)
                    is_bull_engulf = (b_close > b_open) and (b_close > prev_b["high"]) and (b_close > s1)

                    if (is_bull_reject or is_bull_engulf) and not bounce_confirmed and not breakdown_confirmed:
                        bounce_confirmed = True
                        bounce_bar = b
                        bounce_idx = i
                        break
                    
                    # Or was it a breakdown (closed below S1)?
                    if (b_close < s1) and (b_open - b_close >= 0.40 * b_range) and not bounce_confirmed and not breakdown_confirmed:
                        breakdown_confirmed = True
                        break

            if bounce_confirmed and bounce_bar:
                entry_spot = float(bounce_bar["close"])
                entry_time = bounce_bar["datetime"]
                # Subsequent bars: what did price do after S1 bounce?
                sub_bars = bars[bounce_idx+1:]
                if sub_bars:
                    max_high_after = max([float(x["high"]) for x in sub_bars])
                    min_low_after = min([float(x["low"]) for x in sub_bars])
                    eod_close = float(sub_bars[-1]["close"])

                    hit_pivot = max_high_after >= pivot
                    hit_cpr = max_high_after >= cpr_bot
                    hit_r1 = max_high_after >= r1

                    rally_pts = max_high_after - entry_spot
                    drop_pts = entry_spot - min_low_after

                    # Options simulation (Buy ATM CE)
                    strike = int(round(entry_spot / 50) * 50)
                    entry_prem = BlackScholesPricing.calculate_price(entry_spot, strike, dte, 0.135, is_call=True)

                    s1_events.append({
                        "date": current_date.strftime("%Y-%m-%d"),
                        "time": entry_time.strftime("%H:%M"),
                        "s1": s1,
                        "pivot": pivot,
                        "entry_spot": entry_spot,
                        "max_rally_spot": max_high_after,
                        "rally_pts": round(rally_pts, 1),
                        "drop_pts": round(drop_pts, 1),
                        "hit_pivot": hit_pivot,
                        "hit_cpr": hit_cpr,
                        "hit_r1": hit_r1,
                        "entry_prem": round(entry_prem, 2),
                        "strike": strike
                    })

    df_events = pd.DataFrame(s1_events)
    print("=" * 90)
    print("   NIFTY PRICE ACTION ANALYSIS: WHAT HAPPENS ON S1 SUPPORT BOUNCE?")
    print("=" * 90)
    print(f"Total Sessions where S1 was tested and confirmed Support Bounce: {len(df_events)}")
    print(f"Average Spot Rally after S1 Bounce    : +{df_events['rally_pts'].mean():.1f} index points")
    print(f"Max Spot Rally observed              : +{df_events['rally_pts'].max():.1f} index points")
    print(f"Percentage of Bounces reaching Pivot : {df_events['hit_pivot'].sum() / len(df_events) * 100:.1f}% ({df_events['hit_pivot'].sum()}/{len(df_events)})")
    print(f"Percentage of Bounces reaching CPR   : {df_events['hit_cpr'].sum() / len(df_events) * 100:.1f}% ({df_events['hit_cpr'].sum()}/{len(df_events)})")
    print(f"Percentage of Bounces reaching R1    : {df_events['hit_r1'].sum() / len(df_events) * 100:.1f}% ({df_events['hit_r1'].sum()}/{len(df_events)})")
    print("=" * 90)
    print("\nSAMPLE RECENT S1 BOUNCES:")
    print(df_events[["date", "time", "s1", "entry_spot", "rally_pts", "hit_pivot", "hit_r1"]].head(15).to_string(index=False))

if __name__ == "__main__":
    main()
