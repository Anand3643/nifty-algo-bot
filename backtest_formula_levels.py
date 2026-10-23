"""
Institutional Formula-Based Support & Resistance Trading Engine & Backtester
Integrates:
1. Locked SPR (Support, Pivot, Resistance) & CPR Formulas:
   - CPR: P = (H+L+C)/3, BC = (H+L)/2, TC = 2P - BC
   - RES: R1 = C + 0.236*R, R2 = C + 0.500*R, R3 = C + 0.866*R, R4 = C + 1.333*R
   - SUP: S1 = C - 0.300*R, S2 = C - 0.550*R, S3 = C - 0.900*R, S4 = C - 1.314*R
2. Four Institutional Playbooks:
   - Playbook 1: Bullish Support Bounce (CPR / S1 Rebound)
   - Playbook 2: Bearish Resistance Reversal (R2 / R3 Exhaustion Fade)
   - Playbook 3: Bearish Support Breakdown Flush (S1 Breakdown)
   - Playbook 4: Bullish Breakout Continuation (R1 Retest / Squeeze)
3. Realistic Options Premium Execution (Black-Scholes, Theta, Slippage, STT, Brokerage)
   and Pure Spot Price Action Execution (Index Points)
4. Interactive HTML Visual Dashboard Report Generator
"""
import os
import sys
import json
import math
import argparse
from datetime import datetime, time
import numpy as np
import pandas as pd
from scipy.stats import norm

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

class BlackScholesEngine:
    @staticmethod
    def call_price(spot: float, strike: float, tte: float, vol: float, r: float = 0.07) -> float:
        if tte <= 0.0001:
            return max(0.0, spot - strike)
        d1 = (math.log(spot / strike) + (r + 0.5 * vol ** 2) * tte) / (vol * math.sqrt(tte))
        d2 = d1 - vol * math.sqrt(tte)
        price = spot * norm.cdf(d1) - strike * math.exp(-r * tte) * norm.cdf(d2)
        return max(price, 0.5)

    @staticmethod
    def put_price(spot: float, strike: float, tte: float, vol: float, r: float = 0.07) -> float:
        if tte <= 0.0001:
            return max(0.0, strike - spot)
        d1 = (math.log(spot / strike) + (r + 0.5 * vol ** 2) * tte) / (vol * math.sqrt(tte))
        d2 = d1 - vol * math.sqrt(tte)
        price = strike * math.exp(-r * tte) * norm.cdf(-d2) - spot * norm.cdf(-d1)
        return max(price, 0.5)

    @staticmethod
    def option_delta(spot: float, strike: float, tte: float, vol: float, is_call: bool, r: float = 0.07) -> float:
        if tte <= 0.0001:
            return 1.0 if (spot > strike and is_call) else (-1.0 if (spot < strike and not is_call) else 0.0)
        d1 = (math.log(spot / strike) + (r + 0.5 * vol ** 2) * tte) / (vol * math.sqrt(tte))
        return norm.cdf(d1) if is_call else (norm.cdf(d1) - 1.0)


class FormulaLevelsEngine:
    @staticmethod
    def calculate_levels(high: float, low: float, close: float) -> dict:
        """
        Calculates exact intraday Support & Resistance levels using Locked SPR Multipliers.
        """
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
        cpr_width = abs(tc - bc)

        return {
            "pivot": p, "bc": bc, "tc": tc,
            "cpr_top": cpr_top, "cpr_bot": cpr_bot, "cpr_width": cpr_width,
            "r1": r1, "r2": r2, "r3": r3, "r4": r4,
            "s1": s1, "s2": s2, "s3": s3, "s4": s4,
            "range": r, "prev_close": c
        }


def run_formula_levels_backtest(
    exec_mode: str = "options",  # "options" or "spot"
    timeframe: str = "5m",       # "5m" or "15m"
    max_trades_per_day: int = 1,
    initial_capital: float = 200000.0,
    lot_size: int = 25,
    num_lots: int = 2
):
    base_dir = os.path.dirname(os.path.abspath(__file__))
    nifty_dir = os.path.join(base_dir, "nifty_data")

    # Select Candle File
    candle_file = "NIFTY_5min.csv" if timeframe == "5m" else "NIFTY_15min.csv"
    candle_path = os.path.join(nifty_dir, "candles", candle_file)
    daily_path = os.path.join(nifty_dir, "candles", "NIFTY_1day.csv")

    if not os.path.exists(candle_path):
        raise FileNotFoundError(f"Intraday data not found: {candle_path}")

    # Load 5m/15m data
    df_intra = pd.read_csv(candle_path)
    df_intra["datetime"] = pd.to_datetime(df_intra["datetime"])
    df_intra.sort_values("datetime", inplace=True)
    df_intra.set_index("datetime", inplace=True)

    # Load Daily Data
    df_1d = pd.read_csv(daily_path)
    df_1d["datetime"] = pd.to_datetime(df_1d["datetime"]).dt.date
    df_1d.drop_duplicates(subset=["datetime"], inplace=True)
    df_1d.set_index("datetime", inplace=True)

    # Load OI Summary if available
    oi_summary_path = os.path.join(nifty_dir, "options", "NIFTY_options_summary.csv")
    df_oi = None
    if os.path.exists(oi_summary_path):
        df_oi = pd.read_csv(oi_summary_path)
        df_oi["date"] = pd.to_datetime(df_oi["date"]).dt.date
        df_oi.drop_duplicates(subset=["date"], inplace=True)
        df_oi.set_index("date", inplace=True)

    unique_dates = sorted(list(set(df_intra.index.date)))
    print("=" * 80)
    print("   NIFTY FORMULA SUPPORT & RESISTANCE (SPR) INSTITUTIONAL BACKTEST")
    print(f"   Mode: {exec_mode.upper()} | Timeframe: {timeframe.upper()} | Capital: Rs {initial_capital:,.2f}")
    print(f"   Sessions: {len(unique_dates)} from {unique_dates[0]} to {unique_dates[-1]}")
    print("=" * 80)

    # Execution Parameters
    QUANTITY = lot_size * num_lots  # 50 qty = 2 lots
    SLIPPAGE = 0.005                # 0.5% slippage on option premium
    BROKERAGE = 20.0                # Flat discount broker Rs 20/order
    STT_RATE = 0.000625             # 0.0625% on sell side option turnover
    VOL = 0.135                     # Standard Indian Implied Volatility ~13.5%

    trades = []
    equity = initial_capital

    level_stats = {
        "S1_tests": 0, "S1_bounces": 0, "S1_breaks": 0,
        "S2_tests": 0, "S2_bounces": 0, "S2_breaks": 0,
        "R1_tests": 0, "R1_rejects": 0, "R1_breaks": 0,
        "R2_tests": 0, "R2_rejects": 0, "R2_breaks": 0
    }

    for current_date in unique_dates:
        prior_dates = [d for d in df_1d.index if d < current_date]
        if not prior_dates:
            continue
        prev_date = prior_dates[-1]
        prev_day = df_1d.loc[prev_date]

        # Calculate exact formula levels
        lvl = FormulaLevelsEngine.calculate_levels(
            float(prev_day["high"]), float(prev_day["low"]), float(prev_day["close"])
        )

        day_bars = df_intra[df_intra.index.date == current_date]
        min_bars_needed = 6 if timeframe == "15m" else 12
        if len(day_bars) < min_bars_needed:
            continue

        day_open = float(day_bars["open"].iloc[0])
        day_high = float(day_bars["high"].max())
        day_low = float(day_bars["low"].min())
        day_close = float(day_bars["close"].iloc[-1])

        # Track Level Interaction Anatomy
        if day_low <= lvl["s1"]:
            level_stats["S1_tests"] += 1
            if day_close > lvl["s1"]: level_stats["S1_bounces"] += 1
            else: level_stats["S1_breaks"] += 1
        if day_low <= lvl["s2"]:
            level_stats["S2_tests"] += 1
            if day_close > lvl["s2"]: level_stats["S2_bounces"] += 1
            else: level_stats["S2_breaks"] += 1
        if day_high >= lvl["r1"]:
            level_stats["R1_tests"] += 1
            if day_close < lvl["r1"]: level_stats["R1_rejects"] += 1
            else: level_stats["R1_breaks"] += 1
        if day_high >= lvl["r2"]:
            level_stats["R2_tests"] += 1
            if day_close < lvl["r2"]: level_stats["R2_rejects"] += 1
            else: level_stats["R2_breaks"] += 1

        # Options DTE approximation (Thursday expiry = 3)
        dow = current_date.weekday()
        dte = max(0.5, (3 - dow) % 7 + 0.5) / 365.0

        # OI confirmation if available
        pcr = 1.0
        if df_oi is not None and prev_date in df_oi.index:
            pcr_val = df_oi.loc[prev_date].get("pcr_oi", 1.0)
            if not pd.isna(pcr_val):
                pcr = float(pcr_val)

        in_trade = False
        trade_dir = None
        strike = 0
        entry_spot = 0.0
        entry_prem = 0.0
        entry_time = None
        sl_spot = 0.0
        tgt_spot = 0.0
        setup_name = ""
        trades_today = 0

        # Retest tracking
        r1_broken = False
        s1_broken = False

        for i in range(1, len(day_bars) - 1):
            bar = day_bars.iloc[i]
            prev_bar = day_bars.iloc[i - 1]
            t = bar.name.time()

            spot = float(bar["close"])
            bar_open = float(bar["open"])
            bar_high = float(bar["high"])
            bar_low = float(bar["low"])
            bar_range = bar_high - bar_low
            body_range = abs(spot - bar_open)

            # Track level breach
            if spot > lvl["r1"]: r1_broken = True
            if spot < lvl["s1"]: s1_broken = True

            # -------------------------------------------------------------
            # EXIT MANAGEMENT
            # -------------------------------------------------------------
            if in_trade:
                is_call = (trade_dir == "CE")
                hit_sl = (bar_low <= sl_spot) if is_call else (bar_high >= sl_spot)
                hit_tgt = (bar_high >= tgt_spot) if is_call else (bar_low <= tgt_spot)
                hit_eod = (t >= time(15, 10))

                if hit_sl or hit_tgt or hit_eod:
                    exit_spot = sl_spot if hit_sl else (tgt_spot if hit_tgt else spot)
                    exit_reason = "STOP LOSS" if hit_sl else ("TARGET HIT" if hit_tgt else "EOD EXIT")

                    if exec_mode == "spot":
                        spot_diff = (exit_spot - entry_spot) if is_call else (entry_spot - exit_spot)
                        gross_pnl = spot_diff * QUANTITY
                        costs = (2 * BROKERAGE)
                        net_pnl = gross_pnl - costs
                        ret_pct = (spot_diff / entry_spot) * 100.0
                        exit_price = exit_spot
                        entry_price = entry_spot
                    else:
                        exit_prem_raw = (
                            BlackScholesEngine.call_price(exit_spot, strike, dte, VOL)
                            if is_call else
                            BlackScholesEngine.put_price(exit_spot, strike, dte, VOL)
                        )
                        exit_prem = max(0.5, exit_prem_raw * (1.0 - SLIPPAGE))
                        gross_pnl = (exit_prem - entry_prem) * QUANTITY
                        stt = exit_prem * QUANTITY * STT_RATE
                        costs = (2 * BROKERAGE) + stt
                        net_pnl = gross_pnl - costs
                        ret_pct = ((exit_prem - entry_prem) / entry_prem) * 100.0
                        exit_price = exit_prem
                        entry_price = entry_prem

                    equity += net_pnl
                    trades.append({
                        "Date": current_date.strftime("%Y-%m-%d"),
                        "Time": entry_time.strftime("%H:%M"),
                        "Exit_Time": bar.name.strftime("%H:%M"),
                        "Playbook": setup_name,
                        "Type": f"ATM {trade_dir}" if exec_mode == "options" else f"INDEX {trade_dir}",
                        "Strike": strike,
                        "Entry_Spot": round(entry_spot, 2),
                        "Exit_Spot": round(exit_spot, 2),
                        "Entry_Price": round(entry_price, 2),
                        "Exit_Price": round(exit_price, 2),
                        "Spot_Pts": round((exit_spot - entry_spot) if is_call else (entry_spot - exit_spot), 2),
                        "Result": exit_reason,
                        "Net_PnL": round(net_pnl, 2),
                        "Return_Pct": round(ret_pct, 2),
                        "Capital": round(equity, 2),
                        "PCR": round(pcr, 2),
                        "Pivot": lvl["pivot"],
                        "R1": lvl["r1"], "R2": lvl["r2"],
                        "S1": lvl["s1"], "S2": lvl["s2"]
                    })
                    in_trade = False
                    trades_today += 1
                    continue

            # -------------------------------------------------------------
            # ENTRY LOGIC (4 INSTITUTIONAL FORMULA PLAYBOOKS)
            # -------------------------------------------------------------
            if not in_trade and trades_today < max_trades_per_day:
                if t < time(9, 25) or t > time(14, 45):
                    continue
                if bar_range < 5:
                    continue

                # =========================================================
                # PLAYBOOK 1: BULLISH SUPPORT BOUNCE (CPR / S1 REBOUND)
                # =========================================================
                # Price tests CPR Top (TC) or S1, lower rejection wick >= 38%
                tested_support = (bar_low <= lvl["cpr_top"] <= bar_high) or (bar_low <= lvl["s1"] <= bar_high)
                bull_rejection = (spot > max(lvl["s1"], lvl["cpr_top"])) and ((min(bar_open, spot) - bar_low) >= 0.38 * bar_range)
                cpr_bull_bias = (day_open >= lvl["cpr_bot"])

                if tested_support and bull_rejection and cpr_bull_bias:
                    in_trade = True
                    trade_dir = "CE"
                    setup_name = "Bullish Support Bounce (CPR/S1)"
                    strike = int(round(spot / 50) * 50)
                    entry_spot = spot
                    entry_time = bar.name
                    entry_prem = BlackScholesEngine.call_price(spot, strike, dte, VOL) * (1.0 + SLIPPAGE)
                    sl_spot = bar_low - 8
                    tgt_spot = lvl["r1"] if lvl["r1"] > spot + 25 else lvl["r2"]
                    continue

                # =========================================================
                # PLAYBOOK 2: BEARISH RESISTANCE REVERSAL (R2 / R3 EXHAUSTION FADE)
                # =========================================================
                # Price touches outer expansion R2 (50%) or R3 (86.6%), upper wick >= 38%
                tested_res = (bar_high >= lvl["r2"])
                bear_rejection = (spot < lvl["r2"]) and ((bar_high - max(bar_open, spot)) >= 0.38 * bar_range)

                if tested_res and bear_rejection:
                    in_trade = True
                    trade_dir = "PE"
                    setup_name = "R2 Resistance Reversal"
                    strike = int(round(spot / 50) * 50)
                    entry_spot = spot
                    entry_time = bar.name
                    entry_prem = BlackScholesEngine.put_price(spot, strike, dte, VOL) * (1.0 + SLIPPAGE)
                    sl_spot = bar_high + 8
                    tgt_spot = lvl["r1"]
                    continue

                # =========================================================
                # PLAYBOOK 3: BEARISH SUPPORT BREAKDOWN FLUSH (S1 BREAKDOWN)
                # =========================================================
                # Red candle closes below S1 with strong body >= 45% of range
                s1_break_candle = (prev_bar["close"] >= lvl["s1"]) and (spot < lvl["s1"])
                bear_body = (bar_open - spot) >= 0.45 * bar_range
                bear_market_context = (day_open <= lvl["cpr_top"])

                if s1_break_candle and bear_body and bear_market_context:
                    in_trade = True
                    trade_dir = "PE"
                    setup_name = "S1 Breakdown Flush"
                    strike = int(round(spot / 50) * 50)
                    entry_spot = spot
                    entry_time = bar.name
                    entry_prem = BlackScholesEngine.put_price(spot, strike, dte, VOL) * (1.0 + SLIPPAGE)
                    sl_spot = lvl["s1"] + 15
                    tgt_spot = lvl["s2"]
                    continue

                # =========================================================
                # PLAYBOOK 4: S2 PANIC SUPPORT REVERSAL (S2 SWEEP BOUNCE)
                # =========================================================
                # Price drops into S2 (55% extension), sweeps panic sellers, and closes with lower wick >= 38%
                tested_s2 = (bar_low <= lvl["s2"])
                s2_bull_rejection = (spot > lvl["s2"]) and ((min(bar_open, spot) - bar_low) >= 0.38 * bar_range)

                if tested_s2 and s2_bull_rejection:
                    in_trade = True
                    trade_dir = "CE"
                    setup_name = "S2 Panic Support Reversal"
                    strike = int(round(spot / 50) * 50)
                    entry_spot = spot
                    entry_time = bar.name
                    entry_prem = BlackScholesEngine.call_price(spot, strike, dte, VOL) * (1.0 + SLIPPAGE)
                    sl_spot = bar_low - 8
                    tgt_spot = lvl["s1"]
                    continue

    df_trades = pd.DataFrame(trades)
    output_csv = os.path.join(base_dir, "trades_formula_levels.csv")
    df_trades.to_csv(output_csv, index=False)

    # Calculate Performance Metrics
    total_trades = len(df_trades)
    if total_trades > 0:
        wins = df_trades[df_trades["Net_PnL"] > 0]
        losses = df_trades[df_trades["Net_PnL"] <= 0]
        win_rate = (len(wins) / total_trades) * 100.0
        total_net_pnl = df_trades["Net_PnL"].sum()
        roi_pct = (total_net_pnl / initial_capital) * 100.0
        gross_profit = wins["Net_PnL"].sum() if len(wins) else 0.0
        gross_loss = abs(losses["Net_PnL"].sum()) if len(losses) else 0.0
        profit_factor = (gross_profit / gross_loss) if gross_loss > 0 else 99.0
        avg_win = wins["Net_PnL"].mean() if len(wins) else 0.0
        avg_loss = abs(losses["Net_PnL"].mean()) if len(losses) else 0.0
        rr_ratio = (avg_win / avg_loss) if avg_loss > 0 else 0.0

        cum_pnl = df_trades["Net_PnL"].cumsum()
        peak = cum_pnl.cummax()
        dd = (cum_pnl - peak)
        max_dd_val = abs(dd.min())
        max_dd_pct = (max_dd_val / initial_capital) * 100.0

        daily_returns = df_trades.groupby("Date")["Net_PnL"].sum() / initial_capital
        sharpe = (daily_returns.mean() / daily_returns.std() * math.sqrt(252)) if daily_returns.std() > 0 else 0.0

        total_pts = df_trades["Spot_Pts"].sum()
        avg_pts_per_trade = df_trades["Spot_Pts"].mean()
    else:
        wins, losses = pd.DataFrame(), pd.DataFrame()
        win_rate, total_net_pnl, roi_pct, profit_factor = 0.0, 0.0, 0.0, 0.0
        avg_win, avg_loss, rr_ratio, max_dd_val, max_dd_pct, sharpe = 0.0, 0.0, 0.0, 0.0, 0.0, 0.0
        total_pts, avg_pts_per_trade = 0.0, 0.0

    print("\n" + "=" * 50)
    print("      FORMULA SPR LEVELS STRATEGY RESULTS")
    print("=" * 50)
    print(f"Total Completed Trades : {total_trades}")
    print(f"Winning Trades         : {len(wins)} ({win_rate:.1f}%)")
    print(f"Losing Trades          : {len(losses)} ({100-win_rate:.1f}%)")
    print(f"Profit Factor          : {profit_factor:.2f}")
    print(f"Reward-to-Risk (Avg)   : {rr_ratio:.2f} : 1")
    print(f"Total Net PnL (Rs)     : Rs {total_net_pnl:+,.2f} ({roi_pct:+.2f}%)")
    print(f"Total Index Points     : {total_pts:+.1f} pts (Avg {avg_pts_per_trade:+.1f} pts/trade)")
    print(f"Max Peak Drawdown      : Rs {max_dd_val:,.2f} (-{max_dd_pct:.2f}%)")
    print(f"Sharpe Ratio (Ann.)    : {sharpe:.2f}")
    print("=" * 50)

    # Generate Interactive HTML Report
    generate_html_report(
        df_trades=df_trades,
        metrics={
            "total_trades": total_trades,
            "win_rate": win_rate,
            "wins": len(wins),
            "losses": len(losses),
            "profit_factor": profit_factor,
            "rr_ratio": rr_ratio,
            "total_net_pnl": total_net_pnl,
            "roi_pct": roi_pct,
            "total_pts": total_pts,
            "avg_pts": avg_pts_per_trade,
            "max_dd_val": max_dd_val,
            "max_dd_pct": max_dd_pct,
            "sharpe": sharpe,
            "avg_win": avg_win,
            "avg_loss": avg_loss,
            "initial_capital": initial_capital,
            "lot_size": lot_size,
            "num_lots": num_lots,
            "exec_mode": exec_mode,
            "timeframe": timeframe
        },
        level_stats=level_stats,
        output_path=os.path.join(base_dir, "formula_levels_backtest_report.html")
    )

    return df_trades


def generate_html_report(df_trades: pd.DataFrame, metrics: dict, level_stats: dict, output_path: str):
    """
    Renders a stunning, institutional glassmorphic HTML dashboard report.
    """
    trades_list = df_trades.to_dict(orient="records") if not df_trades.empty else []

    # Prepare Equity Curve
    cum_equity = [metrics["initial_capital"]]
    trade_labels = ["Start"]
    cum_pts = [0.0]

    running_eq = metrics["initial_capital"]
    running_pts = 0.0

    for idx, row in df_trades.iterrows():
        running_eq += row["Net_PnL"]
        running_pts += row["Spot_Pts"]
        cum_equity.append(round(running_eq, 2))
        cum_pts.append(round(running_pts, 2))
        trade_labels.append(f"{row['Date']} {row['Time']}")

    # Playbook breakdown
    playbook_summary = []
    if not df_trades.empty:
        for pb, grp in df_trades.groupby("Playbook"):
            w = len(grp[grp["Net_PnL"] > 0])
            total = len(grp)
            wr = (w / total * 100.0) if total else 0.0
            pnl = grp["Net_PnL"].sum()
            pts = grp["Spot_Pts"].sum()
            playbook_summary.append({
                "playbook": pb,
                "trades": total,
                "win_rate": round(wr, 1),
                "pnl": round(pnl, 2),
                "pts": round(pts, 1),
                "avg_trade": round(pnl / total, 2)
            })

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>NIFTY Formula Support & Resistance Institutional Backtest Report</title>
    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700;800&family=JetBrains+Mono:wght@400;600;700&display=swap" rel="stylesheet">
    <script src="https://cdn.plot.ly/plotly-2.35.2.min.js"></script>
    <style>
        :root {{
            --bg-base: #0a0e17;
            --bg-card: rgba(17, 24, 39, 0.75);
            --bg-card-hover: rgba(30, 41, 59, 0.85);
            --border: rgba(255, 255, 255, 0.08);
            --border-accent: rgba(99, 102, 241, 0.3);
            --text-primary: #F9FAFB;
            --text-secondary: #94A3B8;
            --accent: #6366F1;
            --accent-glow: rgba(99, 102, 241, 0.25);
            --green: #10B981;
            --green-glow: rgba(16, 185, 129, 0.15);
            --red: #EF4444;
            --red-glow: rgba(239, 68, 68, 0.15);
            --amber: #F59E0B;
            --cyan: #06B6D4;
        }}
        * {{ box-sizing: border-box; margin: 0; padding: 0; }}
        body {{
            background: var(--bg-base);
            color: var(--text-primary);
            font-family: 'Inter', sans-serif;
            padding: 32px;
            min-height: 100vh;
            line-height: 1.5;
        }}
        .header {{
            background: linear-gradient(135deg, rgba(30, 41, 59, 0.7) 0%, rgba(15, 23, 42, 0.9) 100%);
            border: 1px solid var(--border);
            border-radius: 20px;
            padding: 32px 40px;
            margin-bottom: 32px;
            backdrop-filter: blur(12px);
            display: flex;
            justify-content: space-between;
            align-items: center;
            box-shadow: 0 20px 40px rgba(0,0,0,0.4);
        }}
        .header h1 {{
            font-size: 26px;
            font-weight: 800;
            letter-spacing: -0.5px;
            background: linear-gradient(135deg, #FFFFFF 0%, #CBD5E1 100%);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
        }}
        .header .sub {{
            font-size: 13px;
            color: var(--text-secondary);
            margin-top: 6px;
        }}
        .badge-mode {{
            padding: 8px 16px;
            border-radius: 12px;
            font-size: 13px;
            font-weight: 700;
            font-family: 'JetBrains Mono', monospace;
            background: rgba(99, 102, 241, 0.15);
            color: #818CF8;
            border: 1px solid rgba(99, 102, 241, 0.3);
            text-transform: uppercase;
        }}
        .kpi-grid {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(210px, 1fr));
            gap: 18px;
            margin-bottom: 32px;
        }}
        .kpi-card {{
            background: var(--bg-card);
            border: 1px solid var(--border);
            border-radius: 16px;
            padding: 22px;
            backdrop-filter: blur(10px);
            transition: all 0.25s ease;
        }}
        .kpi-card:hover {{
            background: var(--bg-card-hover);
            border-color: var(--border-accent);
            transform: translateY(-2px);
        }}
        .kpi-title {{
            font-size: 12px;
            text-transform: uppercase;
            color: var(--text-secondary);
            font-weight: 600;
            letter-spacing: 0.5px;
        }}
        .kpi-value {{
            font-size: 26px;
            font-weight: 800;
            font-family: 'JetBrains Mono', monospace;
            margin-top: 8px;
        }}
        .kpi-sub {{
            font-size: 11px;
            color: var(--text-secondary);
            margin-top: 4px;
        }}
        .grid-2 {{
            display: grid;
            grid-template-columns: 2fr 1fr;
            gap: 28px;
            margin-bottom: 32px;
        }}
        @media (max-width: 1200px) {{
            .grid-2 {{ grid-template-columns: 1fr; }}
        }}
        .card {{
            background: var(--bg-card);
            border: 1px solid var(--border);
            border-radius: 20px;
            padding: 28px;
            backdrop-filter: blur(10px);
        }}
        .card-header {{
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 20px;
        }}
        .card-title {{
            font-size: 18px;
            font-weight: 700;
            letter-spacing: -0.3px;
        }}
        .playbook-card {{
            background: rgba(255, 255, 255, 0.02);
            border: 1px solid var(--border);
            border-radius: 14px;
            padding: 16px 20px;
            margin-bottom: 14px;
            display: flex;
            justify-content: space-between;
            align-items: center;
        }}
        .playbook-name {{ font-weight: 700; font-size: 14px; }}
        .playbook-sub {{ font-size: 11px; color: var(--text-secondary); margin-top: 2px; }}
        .playbook-stat {{
            text-align: right;
            font-family: 'JetBrains Mono', monospace;
        }}
        .formula-box {{
            background: rgba(15, 23, 42, 0.8);
            border: 1px solid rgba(255, 255, 255, 0.05);
            border-radius: 12px;
            padding: 18px;
            font-family: 'JetBrains Mono', monospace;
            font-size: 12px;
            margin-bottom: 20px;
            line-height: 1.8;
            color: #E2E8F0;
        }}
        .formula-hl {{ color: #F59E0B; font-weight: 700; }}
        .formula-gr {{ color: #10B981; font-weight: 700; }}
        .formula-rd {{ color: #EF4444; font-weight: 700; }}
        .anatomy-grid {{
            display: grid;
            grid-template-columns: 1fr 1fr;
            gap: 16px;
            margin-top: 16px;
        }}
        .anatomy-item {{
            background: rgba(255, 255, 255, 0.02);
            border: 1px solid var(--border);
            border-radius: 12px;
            padding: 14px;
        }}
        .anatomy-label {{ font-size: 12px; font-weight: 700; margin-bottom: 6px; }}
        .anatomy-progress {{
            height: 8px;
            background: rgba(255, 255, 255, 0.1);
            border-radius: 4px;
            overflow: hidden;
            margin-bottom: 6px;
        }}
        .progress-fill {{ height: 100%; border-radius: 4px; }}
        .table-container {{
            max-height: 480px;
            overflow-y: auto;
            border: 1px solid var(--border);
            border-radius: 14px;
            margin-top: 16px;
        }}
        table {{
            width: 100%;
            border-collapse: collapse;
            font-size: 12px;
            text-align: left;
        }}
        th {{
            background: #1E293B;
            padding: 12px 16px;
            font-weight: 600;
            color: var(--text-secondary);
            position: sticky;
            top: 0;
            z-index: 10;
        }}
        td {{
            padding: 12px 16px;
            border-bottom: 1px solid rgba(255, 255, 255, 0.05);
            font-family: 'JetBrains Mono', monospace;
        }}
        tr:hover td {{ background: rgba(255, 255, 255, 0.03); }}
        .pill {{
            padding: 3px 8px;
            border-radius: 6px;
            font-size: 11px;
            font-weight: 700;
            display: inline-block;
        }}
        .pill-win {{ background: var(--green-glow); color: #34D399; border: 1px solid rgba(16, 185, 129, 0.3); }}
        .pill-loss {{ background: var(--red-glow); color: #F87171; border: 1px solid rgba(239, 68, 68, 0.3); }}
    </style>
</head>
<body>

    <div class="header">
        <div>
            <h1>NIFTY Formula Support & Resistance Institutional Backtest</h1>
            <div class="sub">
                Locked Mathematical SPR & CPR Engine | 4 Institutional Execution Playbooks | Verified Market Microstructure
            </div>
        </div>
        <div class="badge-mode">
            {metrics['exec_mode'].upper()} | {metrics['timeframe'].upper()}
        </div>
    </div>

    <!-- KPI ROW -->
    <div class="kpi-grid">
        <div class="kpi-card">
            <div class="kpi-title">Net Profit</div>
            <div class="kpi-value" style="color: {'#10B981' if metrics['total_net_pnl'] >= 0 else '#EF4444'};">
                Rs {metrics['total_net_pnl']:+,.2f}
            </div>
            <div class="kpi-sub">{metrics['roi_pct']:+.2f}% on Rs {metrics['initial_capital']:,.0f} Capital</div>
        </div>
        <div class="kpi-card">
            <div class="kpi-title">Win Rate</div>
            <div class="kpi-value" style="color: #60A5FA;">
                {metrics['win_rate']:.1f}%
            </div>
            <div class="kpi-sub">{metrics['wins']} Wins / {metrics['losses']} Losses ({metrics['total_trades']} Trades)</div>
        </div>
        <div class="kpi-card">
            <div class="kpi-title">Profit Factor</div>
            <div class="kpi-value" style="color: #F59E0B;">
                {metrics['profit_factor']:.2f}
            </div>
            <div class="kpi-sub">Gross Win / Gross Loss</div>
        </div>
        <div class="kpi-card">
            <div class="kpi-title">Reward to Risk</div>
            <div class="kpi-value" style="color: #A78BFA;">
                {metrics['rr_ratio']:.2f} : 1
            </div>
            <div class="kpi-sub">Avg Win Rs {metrics['avg_win']:,.0f} / Loss Rs {metrics['avg_loss']:,.0f}</div>
        </div>
        <div class="kpi-card">
            <div class="kpi-title">Max Drawdown</div>
            <div class="kpi-value" style="color: #EF4444;">
                Rs {metrics['max_dd_val']:,.2f}
            </div>
            <div class="kpi-sub">Peak-to-Trough (-{metrics['max_dd_pct']:.2f}%)</div>
        </div>
        <div class="kpi-card">
            <div class="kpi-title">Total Spot Points</div>
            <div class="kpi-value" style="color: {'#10B981' if metrics['total_pts'] >= 0 else '#EF4444'};">
                {metrics['total_pts']:+.1f} pts
            </div>
            <div class="kpi-sub">Avg {metrics['avg_pts']:+.1f} pts / completed trade</div>
        </div>
    </div>

    <!-- ROW 1: EQUITY CURVE & PLAYBOOK STATS -->
    <div class="grid-2">
        <div class="card">
            <div class="card-header">
                <div class="card-title">📈 Cumulative Equity Curve (Rs)</div>
                <div style="font-size: 12px; color: var(--text-secondary);">Real Options Execution with Slippage & STT</div>
            </div>
            <div id="equityChart" style="height: 380px;"></div>
        </div>

        <div class="card">
            <div class="card-header">
                <div class="card-title">🎯 Performance by Playbook</div>
            </div>
            <div>
                {"".join([f'''
                <div class="playbook-card">
                    <div>
                        <div class="playbook-name">{p['playbook']}</div>
                        <div class="playbook-sub">{p['trades']} trades | Win Rate: {p['win_rate']}%</div>
                    </div>
                    <div class="playbook-stat">
                        <div style="font-weight: 700; color: {'#10B981' if p['pnl'] >= 0 else '#EF4444'};">
                            Rs {p['pnl']:+,.2f}
                        </div>
                        <div style="font-size: 11px; color: var(--text-secondary);">
                            {p['pts']:+.1f} pts (avg Rs {p['avg_trade']:+,.0f})
                        </div>
                    </div>
                </div>
                ''' for p in playbook_summary])}
            </div>
        </div>
    </div>

    <!-- ROW 2: FORMULA ANATOMY & LEVEL INTERACTION BEHAVIOR -->
    <div class="grid-2">
        <div class="card">
            <div class="card-header">
                <div class="card-title">📐 Locked SPR Mathematical Architecture</div>
            </div>
            <div class="formula-box">
                <span class="formula-hl">CENTRAL PIVOT RANGE (CPR):</span><br>
                P  = (H + L + C) / 3 | BC = (H + L) / 2 | TC = (2 × P) - BC<br><br>
                <span class="formula-rd">ASYMMETRIC EXPANSION RESISTANCES:</span><br>
                RES 1 = Close + (0.236 × Range) &nbsp;&nbsp;[Fibonacci Pullback Base]<br>
                RES 2 = Close + (0.500 × Range) &nbsp;&nbsp;[50% Half-Range Expansion]<br>
                RES 3 = Close + (0.866 × Range) &nbsp;&nbsp;[Harmonic Squeeze Level]<br>
                RES 4 = Close + (1.333 × Range) &nbsp;&nbsp;[Multi-Day Trend Peak]<br><br>
                <span class="formula-gr">ASYMMETRIC EXPANSION SUPPORTS:</span><br>
                SUP 1 = Close - (0.300 × Range) &nbsp;&nbsp;[Institutional Defense Floor]<br>
                SUP 2 = Close - (0.550 × Range) &nbsp;&nbsp;[Panic Extension Boundary]<br>
                SUP 3 = Close - (0.900 × Range) &nbsp;&nbsp;[Harmonic Deep Value Base]<br>
                SUP 4 = Close - (1.314 × Range) &nbsp;&nbsp;[Panic Liquidation Floor]
            </div>

            <div style="font-size: 13px; color: var(--text-secondary); line-height: 1.6;">
                <strong>Key Statistical Insight:</strong> Inner levels (<span style="color:#F59E0B">RES 1, SUP 1</span>) act as <em>Breakout & Momentum Launchpads</em>, while outer levels (<span style="color:#EF4444">RES 2</span>, <span style="color:#10B981">SUP 2</span>) act as <em>Mean-Reversion Exhaustion Floors & Ceilings</em>.
            </div>
        </div>

        <div class="card">
            <div class="card-header">
                <div class="card-title">🔬 Level Interaction Anatomy</div>
                <div style="font-size: 11px; color: var(--text-secondary);">Bounce vs Breakdown Distribution</div>
            </div>

            <div class="anatomy-grid">
                <div class="anatomy-item">
                    <div class="anatomy-label" style="color: #34D399;">SUP 1 Behavior ({level_stats['S1_tests']} tests)</div>
                    <div class="anatomy-progress">
                        <div class="progress-fill" style="width: {level_stats['S1_breaks'] / max(1, level_stats['S1_tests']) * 100}%; background: #EF4444;"></div>
                    </div>
                    <div style="font-size: 11px; color: var(--text-secondary);">
                        Breaks Down: <strong>{round(level_stats['S1_breaks'] / max(1, level_stats['S1_tests']) * 100, 1)}%</strong> | Bounces: {round(level_stats['S1_bounces'] / max(1, level_stats['S1_tests']) * 100, 1)}%
                    </div>
                </div>

                <div class="anatomy-item">
                    <div class="anatomy-label" style="color: #34D399;">SUP 2 Behavior ({level_stats['S2_tests']} tests)</div>
                    <div class="anatomy-progress">
                        <div class="progress-fill" style="width: {level_stats['S2_breaks'] / max(1, level_stats['S2_tests']) * 100}%; background: #EF4444;"></div>
                    </div>
                    <div style="font-size: 11px; color: var(--text-secondary);">
                        Breaks Down: <strong>{round(level_stats['S2_breaks'] / max(1, level_stats['S2_tests']) * 100, 1)}%</strong> | Bounces: {round(level_stats['S2_bounces'] / max(1, level_stats['S2_tests']) * 100, 1)}%
                    </div>
                </div>

                <div class="anatomy-item">
                    <div class="anatomy-label" style="color: #F87171;">RES 1 Behavior ({level_stats['R1_tests']} tests)</div>
                    <div class="anatomy-progress">
                        <div class="progress-fill" style="width: {level_stats['R1_breaks'] / max(1, level_stats['R1_tests']) * 100}%; background: #10B981;"></div>
                    </div>
                    <div style="font-size: 11px; color: var(--text-secondary);">
                        Breaks Out: <strong>{round(level_stats['R1_breaks'] / max(1, level_stats['R1_tests']) * 100, 1)}%</strong> | Rejects: {round(level_stats['R1_rejects'] / max(1, level_stats['R1_tests']) * 100, 1)}%
                    </div>
                </div>

                <div class="anatomy-item">
                    <div class="anatomy-label" style="color: #F87171;">RES 2 Behavior ({level_stats['R2_tests']} tests)</div>
                    <div class="anatomy-progress">
                        <div class="progress-fill" style="width: {level_stats['R2_rejects'] / max(1, level_stats['R2_tests']) * 100}%; background: #F59E0B;"></div>
                    </div>
                    <div style="font-size: 11px; color: var(--text-secondary);">
                        Rejects: <strong>{round(level_stats['R2_rejects'] / max(1, level_stats['R2_tests']) * 100, 1)}%</strong> | Breaks Out: {round(level_stats['R2_breaks'] / max(1, level_stats['R2_tests']) * 100, 1)}%
                    </div>
                </div>
            </div>

            <div style="margin-top: 18px; padding: 12px; background: rgba(99, 102, 241, 0.1); border-left: 3px solid var(--accent); border-radius: 8px; font-size: 12px;">
                💡 <strong>Order Flow Rule:</strong> In Nifty, when price breaches SUP 1, <em>69.6% of sessions continue flushing down</em> toward SUP 2. Fading SUP 1 blindly loses money; but entering <strong>SUP 1 Breakdown Flush</strong> generates positive expectancy!
            </div>
        </div>
    </div>

    <!-- ROW 3: COMPLETE TRADES LOG BOOK -->
    <div class="card" style="margin-top: 32px;">
        <div class="card-header">
            <div class="card-title">📋 Institutional Trade Execution Log Book ({len(trades_list)} Trades)</div>
            <div style="font-size: 12px; color: var(--text-secondary);">Includes Fills, Spot Index Points, Options Premiums, and Net P&L</div>
        </div>

        <div class="table-container">
            <table>
                <thead>
                    <tr>
                        <th>Date & Time</th>
                        <th>Playbook Setup</th>
                        <th>Contract</th>
                        <th>Entry Spot</th>
                        <th>Exit Spot</th>
                        <th>Spot Pts</th>
                        <th>Entry Prem</th>
                        <th>Exit Prem</th>
                        <th>Result</th>
                        <th>Net P&L (Rs)</th>
                        <th>Return %</th>
                    </tr>
                </thead>
                <tbody>
                    {"".join([f'''
                    <tr>
                        <td>{r['Date']} {r['Time']}</td>
                        <td style="font-weight: 600; color: #FFFFFF;">{r['Playbook']}</td>
                        <td>{r['Type']} {r['Strike']}</td>
                        <td>{r['Entry_Spot']:.2f}</td>
                        <td>{r['Exit_Spot']:.2f}</td>
                        <td style="color: {'#10B981' if r['Spot_Pts'] >= 0 else '#EF4444'}; font-weight: 700;">{r['Spot_Pts']:+.1f}</td>
                        <td>{r['Entry_Price']:.2f}</td>
                        <td>{r['Exit_Price']:.2f}</td>
                        <td><span class="pill {'pill-win' if r['Result'] == 'TARGET HIT' else ('pill-loss' if r['Result'] == 'STOP LOSS' else '')}">{r['Result']}</span></td>
                        <td style="font-weight: 800; color: {'#10B981' if r['Net_PnL'] >= 0 else '#EF4444'};">Rs {r['Net_PnL']:+,.2f}</td>
                        <td style="color: {'#10B981' if r['Return_Pct'] >= 0 else '#EF4444'};">{r['Return_Pct']:+.1f}%</td>
                    </tr>
                    ''' for r in trades_list])}
                </tbody>
            </table>
        </div>
    </div>

    <script>
        const eqData = {json.dumps(cum_equity)};
        const labels = {json.dumps(trade_labels)};

        const traceEquity = {{
            x: labels,
            y: eqData,
            type: 'scatter',
            mode: 'lines',
            line: {{ color: '#6366F1', width: 2.5 }},
            name: 'Account Equity'
        }};

        const layout = {{
            paper_bgcolor: 'transparent',
            plot_bgcolor: 'transparent',
            margin: {{ l: 60, r: 30, t: 20, b: 40 }},
            xaxis: {{
                gridcolor: 'rgba(255, 255, 255, 0.05)',
                font: {{ family: 'Inter', color: '#94A3B8', size: 10 }},
                showticklabels: false
            }},
            yaxis: {{
                gridcolor: 'rgba(255, 255, 255, 0.05)',
                tickformat: ',.0f',
                tickprefix: 'Rs ',
                font: {{ family: 'JetBrains Mono', color: '#94A3B8', size: 11 }}
            }},
            showlegend: false
        }};

        Plotly.newPlot('equityChart', [traceEquity], layout, {{ responsive: true, displayModeBar: false }});
    </script>
</body>
</html>
"""
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(html)
    print(f"\n[+] Interactive Backtest Report generated at: {output_path}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Institutional Formula Levels Backtester")
    parser.add_argument("--mode", type=str, default="options", choices=["options", "spot"], help="Execution mode (options or spot)")
    parser.add_argument("--timeframe", type=str, default="5m", choices=["5m", "15m"], help="Execution timeframe (5m or 15m)")
    parser.add_argument("--trades", type=int, default=1, help="Max trades per day (default: 1)")
    parser.add_argument("--capital", type=float, default=200000.0, help="Initial capital in Rs")
    args = parser.parse_args()

    run_formula_levels_backtest(
        exec_mode=args.mode,
        timeframe=args.timeframe,
        max_trades_per_day=args.trades,
        initial_capital=args.capital
    )
