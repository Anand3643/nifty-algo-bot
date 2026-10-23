"""
Comprehensive comparison: S1 Support Bounce (Reversal) vs S1 Support Breakdown (Break)
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

    bounces = []
    breakdowns = []

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

        s1 = lvl["s1"]
        s2 = lvl["s2"]
        pivot = lvl["pivot"]
        cpr_top = lvl["cpr_top"]

        bars = grp.to_dict(orient="records")
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

            # S1 Breakdown (close below S1 with bearish body)
            if (float(prev_b["close"]) >= s1) and (b_close < s1) and (b_open - b_close >= 0.35 * b_range):
                # Measure drop after breakdown
                rem = bars[i+1:]
                if rem:
                    min_low = min([float(x["low"]) for x in rem])
                    max_high = max([float(x["high"]) for x in rem])
                    drop = b_close - min_low
                    pullback = max_high - b_close
                    hit_s2 = min_low <= s2
                    breakdowns.append({
                        "date": current_date,
                        "time": t,
                        "s1": s1,
                        "entry": b_close,
                        "drop": round(drop, 1),
                        "pullback": round(pullback, 1),
                        "hit_s2": hit_s2
                    })
                break

            # S1 Bounce (tested S1 and closed bullishly above with wick)
            tested = (b_low <= s1 <= b_high) or (float(prev_b["low"]) <= s1 and b_low <= s1)
            lower_wick = min(b_open, b_close) - b_low
            is_bull_bounce = (b_close > s1) and ((b_close > b_open) or (lower_wick >= 0.35 * b_range))
            if tested and is_bull_bounce:
                rem = bars[i+1:]
                if rem:
                    max_high = max([float(x["high"]) for x in rem])
                    min_low = min([float(x["low"]) for x in rem])
                    rally = max_high - b_close
                    stop_drop = b_close - min_low
                    hit_piv = max_high >= pivot
                    hit_cpr = max_high >= cpr_top
                    bounces.append({
                        "date": current_date,
                        "time": t,
                        "s1": s1,
                        "entry": b_close,
                        "rally": round(rally, 1),
                        "drop": round(stop_drop, 1),
                        "hit_pivot": hit_piv,
                        "hit_cpr": hit_cpr
                    })
                break

    df_bnc = pd.DataFrame(bounces)
    df_brk = pd.DataFrame(breakdowns)

    print("=" * 80)
    print("      STATISTICAL BREAKDOWN: S1 SUPPORT BOUNCE VS S1 BREAKDOWN")
    print("=" * 80)
    print(f"Total S1 Breakdown Events : {len(df_brk)}")
    print(f"  - Average Post-Breakdown Drop   : -{df_brk['drop'].mean():.1f} index points")
    print(f"  - Max Post-Breakdown Drop       : -{df_brk['drop'].max():.1f} index points")
    print(f"  - Reached S2 Support Target     : {df_brk['hit_s2'].sum() / len(df_brk) * 100:.1f}% ({df_brk['hit_s2'].sum()}/{len(df_brk)})")
    print("-" * 80)
    print(f"Total S1 Support Bounce Events : {len(df_bnc)}")
    print(f"  - Average Post-Bounce Rally     : +{df_bnc['rally'].mean():.1f} index points")
    print(f"  - Max Post-Bounce Rally         : +{df_bnc['rally'].max():.1f} index points")
    print(f"  - Reached Central Pivot Target  : {df_bnc['hit_pivot'].sum() / len(df_bnc) * 100:.1f}% ({df_bnc['hit_pivot'].sum()}/{len(df_bnc)})")
    print(f"  - Reached Top CPR Boundary      : {df_bnc['hit_cpr'].sum() / len(df_bnc) * 100:.1f}% ({df_bnc['hit_cpr'].sum()}/{len(df_bnc)})")
    print("=" * 80)

if __name__ == "__main__":
    main()
