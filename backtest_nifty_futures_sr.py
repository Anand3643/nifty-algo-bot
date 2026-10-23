"""
NIFTY Futures (1 Lot) Support & Resistance Institutional Backtesting Engine
Executes intraday trading for NIFTY FUTURES (1 Lot = 25 Qty) using:
1. Verified Step Delta Levels & Locked SPR Levels
2. Central Pivot Range (CPR: Pivot, TC, BC)
3. 5 Institutional Execution Playbooks:
   - Playbook 1: Bullish Support Bounce (S1 / CPR Rebound)
   - Playbook 2: Bearish Resistance Reversal (R2 / R3 Fade)
   - Playbook 3: Bearish Support Breakdown Flush (S1 Breakdown)
   - Playbook 4: Bullish Breakout Continuation (R1 Retest)
   - Playbook 5: S2 Panic Sweep Reversal
4. Realistic Futures Transaction Cost Model (Brokerage, STT, Exchange Txn, GST, Stamp Duty, Slippage)
5. Standalone Interactive Visual HTML Dashboard Generator
"""
import os
import sys
import json
import argparse
from datetime import datetime, time
import numpy as np
import pandas as pd

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

class NiftyFuturesSREngine:
    @staticmethod
    def calculate_levels(high: float, low: float, close: float, model: str = "formula") -> dict:
        r = high - low
        c = close
        p = round(((high + low + close) / 3.0) / 5) * 5
        bc = round(((high + low) / 2.0) / 5) * 5
        tc = round(((2.0 * p) - bc) / 5) * 5

        if model == "step":
            # Verified Base Step Delta Model
            r1 = round((c + 50) / 5) * 5
            r2 = round((c + 115) / 5) * 5
            r3 = round((c + 180) / 5) * 5
            r4 = round((c + 260) / 5) * 5

            s1 = round((c - 50) / 5) * 5
            s2 = round((c - 100) / 5) * 5
            s3 = round((c - 170) / 5) * 5
            s4 = round((c - 260) / 5) * 5
        else:
            # Locked SPR Multipliers
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

def run_nifty_futures_backtest(
    timeframe: str = "5m",
    model: str = "formula",
    max_trades_per_day: int = 1,
    initial_capital: float = 150000.0,
    lot_size: int = 25,
    slippage_pts: float = 0.8
):
    base_dir = os.path.dirname(os.path.abspath(__file__))
    nifty_dir = os.path.join(base_dir, "nifty_data")

    candle_file = "NIFTY_5min.csv" if timeframe == "5m" else "NIFTY_15min.csv"
    candle_path = os.path.join(nifty_dir, "candles", candle_file)
    daily_path = os.path.join(nifty_dir, "candles", "NIFTY_1day.csv")

    if not os.path.exists(candle_path):
        raise FileNotFoundError(f"Intraday candle data not found: {candle_path}")

    # Load intraday candles
    df_intra = pd.read_csv(candle_path)
    df_intra["datetime"] = pd.to_datetime(df_intra["datetime"])
    df_intra.sort_values("datetime", inplace=True)
    df_intra.set_index("datetime", inplace=True)

    # Load daily bars
    df_1d = pd.read_csv(daily_path)
    df_1d["datetime"] = pd.to_datetime(df_1d["datetime"]).dt.date
    df_1d.drop_duplicates(subset=["datetime"], inplace=True)
    df_1d.set_index("datetime", inplace=True)

    # Load OI summary if available
    oi_summary_path = os.path.join(nifty_dir, "options", "NIFTY_options_summary.csv")
    df_oi = None
    if os.path.exists(oi_summary_path):
        df_oi = pd.read_csv(oi_summary_path)
        df_oi["date"] = pd.to_datetime(df_oi["date"]).dt.date
        df_oi.drop_duplicates(subset=["date"], inplace=True)
        df_oi.set_index("date", inplace=True)

    unique_dates = sorted(list(set(df_intra.index.date)))
    print("=" * 80)
    print("   NIFTY FUTURES 1 LOT (25 QTY) SUPPORT & RESISTANCE BACKTEST")
    print(f"   Model: {model.upper()} | Timeframe: {timeframe.upper()} | Capital: Rs {initial_capital:,.2f}")
    print(f"   Sessions: {len(unique_dates)} from {unique_dates[0]} to {unique_dates[-1]}")
    print("=" * 80)

    # 1 Lot specifications
    QUANTITY = lot_size  # 25 qty
    BROKERAGE_ORDER = 20.0  # Rs 20/order flat discount broker
    STT_RATE = 0.000125     # 0.0125% on sell side turnover
    EXCHANGE_TXN_RATE = 0.0000173  # 0.00173% of turnover
    GST_RATE = 0.18         # 18% on (Brokerage + Txn charges)
    STAMP_DUTY_RATE = 0.00002 # 0.002% on buy turnover

    trades = []
    equity = initial_capital
    level_interactions = {
        "S1_tests": 0, "S1_bounces": 0, "S1_breaks": 0,
        "R1_tests": 0, "R1_rejects": 0, "R1_breaks": 0,
        "R2_tests": 0, "R2_rejects": 0
    }

    for current_date in unique_dates:
        priors = [d for d in df_1d.index if d < current_date]
        if not priors:
            continue
        prev_date = priors[-1]
        prev_row = df_1d.loc[prev_date]

        lvl = NiftyFuturesSREngine.calculate_levels(
            float(prev_row["high"]), float(prev_row["low"]), float(prev_row["close"]), model=model
        )

        day_bars = df_intra[df_intra.index.date == current_date]
        min_bars_needed = 6 if timeframe == "15m" else 12
        if len(day_bars) < min_bars_needed:
            continue

        day_open = float(day_bars["open"].iloc[0])
        day_high = float(day_bars["high"].max())
        day_low = float(day_bars["low"].min())
        day_close = float(day_bars["close"].iloc[-1])

        # Track level interactions
        if day_low <= lvl["s1"]:
            level_interactions["S1_tests"] += 1
            if day_close > lvl["s1"]: level_interactions["S1_bounces"] += 1
            else: level_interactions["S1_breaks"] += 1

        if day_high >= lvl["r1"]:
            level_interactions["R1_tests"] += 1
            if day_close < lvl["r1"]: level_interactions["R1_rejects"] += 1
            else: level_interactions["R1_breaks"] += 1

        if day_high >= lvl["r2"]:
            level_interactions["R2_tests"] += 1
            if day_close < lvl["r2"]: level_interactions["R2_rejects"] += 1

        pcr = 1.0
        if df_oi is not None and prev_date in df_oi.index:
            pcr_val = df_oi.loc[prev_date].get("pcr_oi", 1.0)
            if not pd.isna(pcr_val):
                pcr = float(pcr_val)

        in_trade = False
        trade_dir = None
        entry_price = 0.0
        sl_price = 0.0
        tgt_price = 0.0
        entry_time = None
        playbook = ""
        trades_today = 0

        for i in range(1, len(day_bars) - 1):
            bar = day_bars.iloc[i]
            prev_bar = day_bars.iloc[i - 1]
            t = bar.name.time()

            spot = float(bar["close"])
            b_open = float(bar["open"])
            b_high = float(bar["high"])
            b_low = float(bar["low"])
            b_range = b_high - b_low

            # -------------------------------------------------------------
            # EXIT CHECK
            # -------------------------------------------------------------
            if in_trade:
                hit_sl = (b_low <= sl_price) if trade_dir == "LONG" else (b_high >= sl_price)
                hit_tgt = (b_high >= tgt_price) if trade_dir == "LONG" else (b_low <= tgt_price)
                hit_eod = (t >= time(15, 10))

                if hit_sl or hit_tgt or hit_eod:
                    exit_price = sl_price if hit_sl else (tgt_price if hit_tgt else spot)
                    reason = "STOP LOSS" if hit_sl else ("TARGET HIT" if hit_tgt else "EOD EXIT")

                    # Points calculation with slippage
                    fill_entry = entry_price + slippage_pts if trade_dir == "LONG" else entry_price - slippage_pts
                    fill_exit = exit_price - slippage_pts if trade_dir == "LONG" else exit_price + slippage_pts

                    pts = (fill_exit - fill_entry) if trade_dir == "LONG" else (fill_entry - fill_exit)
                    gross_pnl = pts * QUANTITY

                    # Exact Indian Futures Cost Structure
                    turnover = (fill_entry + fill_exit) * QUANTITY
                    sell_turnover = fill_exit * QUANTITY if trade_dir == "LONG" else fill_entry * QUANTITY
                    stt = sell_turnover * STT_RATE
                    txn_charges = turnover * EXCHANGE_TXN_RATE
                    brokerage = 2 * BROKERAGE_ORDER
                    gst = (brokerage + txn_charges) * GST_RATE
                    stamp_duty = (fill_entry * QUANTITY) * STAMP_DUTY_RATE
                    total_costs = brokerage + stt + txn_charges + gst + stamp_duty

                    net_pnl = gross_pnl - total_costs
                    equity += net_pnl

                    trades.append({
                        "Date": current_date.strftime("%Y-%m-%d"),
                        "Time": entry_time.strftime("%H:%M"),
                        "Exit_Time": bar.name.strftime("%H:%M"),
                        "Playbook": playbook,
                        "Type": f"FUTURES {trade_dir}",
                        "Lots": 1,
                        "Qty": QUANTITY,
                        "Entry_Price": round(fill_entry, 2),
                        "Exit_Price": round(fill_exit, 2),
                        "Points": round(pts, 2),
                        "Gross_PnL": round(gross_pnl, 2),
                        "Brokerage": round(brokerage, 2),
                        "Taxes_Charges": round(total_costs - brokerage, 2),
                        "Total_Costs": round(total_costs, 2),
                        "Net_PnL": round(net_pnl, 2),
                        "Return_Pct": round((pts / fill_entry) * 100, 2),
                        "Capital": round(equity, 2),
                        "Result": reason,
                        "PCR": round(pcr, 2),
                        "Pivot": lvl["pivot"],
                        "R1": lvl["r1"], "R2": lvl["r2"],
                        "S1": lvl["s1"], "S2": lvl["s2"]
                    })
                    in_trade = False
                    trades_today += 1
                    continue

            # -------------------------------------------------------------
            # ENTRY CHECK (5 PLAYBOOKS)
            # -------------------------------------------------------------
            if not in_trade and trades_today < max_trades_per_day:
                if t < time(9, 25) or t > time(14, 45):
                    continue
                if b_range < 5:
                    continue

                # PLAYBOOK 1: Bullish Support Bounce (S1 / CPR Rebound)
                tested_sup = (b_low <= lvl["cpr_top"] <= b_high) or (b_low <= lvl["s1"] <= b_high)
                bull_rej = (spot > max(lvl["s1"], lvl["cpr_top"])) and ((min(b_open, spot) - b_low) >= 0.38 * b_range)
                if tested_sup and bull_rej and (day_open >= lvl["cpr_bot"]):
                    in_trade = True
                    trade_dir = "LONG"
                    entry_price = spot
                    sl_price = b_low - 8
                    tgt_price = lvl["r1"] if lvl["r1"] > spot + 22 else lvl["r2"]
                    entry_time = bar.name
                    playbook = "Bullish Support Bounce (CPR/S1)"
                    continue

                # PLAYBOOK 2: Bearish Resistance Reversal (R2 / R3 Fade)
                tested_res = (b_high >= lvl["r2"])
                bear_rej = (spot < lvl["r2"]) and ((b_high - max(b_open, spot)) >= 0.38 * b_range)
                if tested_res and bear_rej:
                    in_trade = True
                    trade_dir = "SHORT"
                    entry_price = spot
                    sl_price = b_high + 8
                    tgt_price = lvl["r1"] if spot - lvl["r1"] >= 20 else lvl["pivot"]
                    entry_time = bar.name
                    playbook = "R2 Resistance Reversal"
                    continue

                # PLAYBOOK 3: Bearish Support Breakdown Flush (S1 Breakdown)
                s1_break = (prev_bar["close"] >= lvl["s1"]) and (spot < lvl["s1"])
                bear_body = (b_open - spot) >= 0.45 * b_range
                if s1_break and bear_body and (day_open <= lvl["cpr_top"]):
                    in_trade = True
                    trade_dir = "SHORT"
                    entry_price = spot
                    sl_price = lvl["s1"] + 12
                    tgt_price = lvl["s2"]
                    entry_time = bar.name
                    playbook = "S1 Breakdown Flush"
                    continue

                # PLAYBOOK 4: S2 Panic Sweep Reversal
                tested_s2 = (b_low <= lvl["s2"])
                s2_bull = (spot > lvl["s2"]) and ((min(b_open, spot) - b_low) >= 0.38 * b_range)
                if tested_s2 and s2_bull:
                    in_trade = True
                    trade_dir = "LONG"
                    entry_price = spot
                    sl_price = b_low - 8
                    tgt_price = lvl["s1"]
                    entry_time = bar.name
                    playbook = "S2 Sweep Reversal"
                    continue

    df_trades = pd.DataFrame(trades)
    output_csv = os.path.join(base_dir, "trades_nifty_futures_1lot.csv")
    df_trades.to_csv(output_csv, index=False)

    # Performance Metrics
    total_trades = len(df_trades)
    if total_trades == 0:
        print("[!] No trades executed.")
        return

    wins = df_trades[df_trades["Net_PnL"] > 0]
    losses = df_trades[df_trades["Net_PnL"] <= 0]
    win_rate = (len(wins) / total_trades) * 100.0
    total_pts = df_trades["Points"].sum()
    total_gross = df_trades["Gross_PnL"].sum()
    total_costs = df_trades["Total_Costs"].sum()
    total_net = df_trades["Net_PnL"].sum()
    roi_pct = (total_net / initial_capital) * 100.0

    gross_profit = wins["Gross_PnL"].sum() if len(wins) else 0.0
    gross_loss = abs(losses["Gross_PnL"].sum()) if len(losses) else 0.0
    profit_factor = (gross_profit / gross_loss) if gross_loss > 0 else 99.0

    avg_win_pts = wins["Points"].mean() if len(wins) else 0.0
    avg_loss_pts = abs(losses["Points"].mean()) if len(losses) else 0.0
    rr_ratio = (avg_win_pts / avg_loss_pts) if avg_loss_pts > 0 else 0.0

    cum_equity = df_trades["Capital"].tolist()
    peak = df_trades["Capital"].cummax()
    drawdown = df_trades["Capital"] - peak
    max_dd_val = abs(drawdown.min())
    max_dd_pct = (max_dd_val / initial_capital) * 100.0

    daily_ret = df_trades.groupby("Date")["Net_PnL"].sum()
    sharpe = (daily_ret.mean() / daily_ret.std()) * np.sqrt(252) if daily_ret.std() > 0 else 0.0

    print("\n" + "=" * 55)
    print("      NIFTY FUTURES (1 LOT) BACKTEST RESULTS")
    print("=" * 55)
    print(f"Contract Traded        : NIFTY FUTURES (1 Lot = {lot_size} Qty)")
    print(f"Total Completed Trades : {total_trades}")
    print(f"Winning Trades         : {len(wins)} ({win_rate:.1f}%)")
    print(f"Losing Trades          : {len(losses)} ({100-win_rate:.1f}%)")
    print(f"Total Index Points     : {total_pts:+.1f} pts (Avg {total_pts/total_trades:+.1f} pts/trade)")
    print(f"Gross P&L              : Rs {total_gross:+,.2f}")
    print(f"Total Costs & Taxes    : Rs {total_costs:,.2f} (Avg Rs {total_costs/total_trades:.1f}/trade)")
    print(f"Total Net PnL (Rs)     : Rs {total_net:+,.2f} ({roi_pct:+.2f}%)")
    print(f"Profit Factor          : {profit_factor:.2f}")
    print(f"Average Win / Loss     : +{avg_win_pts:.1f} pts / -{avg_loss_pts:.1f} pts (RR: {rr_ratio:.2f}:1)")
    print(f"Max Peak Drawdown      : Rs {max_dd_val:,.2f} (-{max_dd_pct:.2f}%)")
    print(f"Sharpe Ratio (Ann.)    : {sharpe:.2f}")
    print("=" * 55)

    print("\n[+] Breakdown by Playbook:")
    for pb, g in df_trades.groupby("Playbook"):
        w = len(g[g["Net_PnL"] > 0])
        pnl = g["Net_PnL"].sum()
        pts = g["Points"].sum()
        print(f"  - {pb:32s}: {len(g):2d} trades | Net PnL: Rs {pnl:+9,.2f} ({pts:+6.1f} pts) | Win: {w/len(g)*100:5.1f}%")

    # Generate Interactive HTML Report
    generate_html_report(
        df_trades=df_trades,
        summary={
            "total_trades": total_trades,
            "wins": len(wins),
            "losses": len(losses),
            "win_rate": win_rate,
            "total_pts": total_pts,
            "gross_pnl": total_gross,
            "total_costs": total_costs,
            "net_pnl": total_net,
            "roi_pct": roi_pct,
            "profit_factor": profit_factor,
            "max_dd_val": max_dd_val,
            "max_dd_pct": max_dd_pct,
            "sharpe": sharpe,
            "rr_ratio": rr_ratio,
            "avg_trade_pts": total_pts / total_trades,
            "initial_capital": initial_capital,
            "final_capital": equity,
            "lot_size": lot_size,
            "timeframe": timeframe,
            "model": model
        },
        output_file=os.path.join(base_dir, "report_nifty_futures_1lot.html")
    )

def generate_html_report(df_trades: pd.DataFrame, summary: dict, output_file: str):
    cum_equity = [summary["initial_capital"]] + df_trades["Capital"].tolist()
    trade_labels = ["Start"] + [f"T{i+1}: {r['Date']}" for i, r in df_trades.iterrows()]
    
    # Calculate drawdown curve
    peak_series = [summary["initial_capital"]]
    dd_pct = [0.0]
    curr_peak = summary["initial_capital"]
    for cap in df_trades["Capital"]:
        curr_peak = max(curr_peak, cap)
        peak_series.append(curr_peak)
        dd_pct.append(((cap - curr_peak) / curr_peak) * 100.0)

    # Daily PnL for chart
    daily_pnl = df_trades.groupby("Date")["Net_PnL"].sum()
    daily_dates = daily_pnl.index.tolist()
    daily_vals = daily_pnl.values.tolist()
    daily_colors = ["#10B981" if v > 0 else "#EF4444" for v in daily_vals]

    # Convert trades to dict list
    trades_list = df_trades.to_dict(orient="records")

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>NIFTY Futures (1 Lot) Support & Resistance Backtest Report</title>
    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&family=JetBrains+Mono:wght@400;500;600;700&display=swap" rel="stylesheet">
    <script src="https://cdn.plot.ly/plotly-2.35.2.min.js"></script>
    <style>
        :root {{
            --bg-base: #0B0F19;
            --bg-card: #111827;
            --border: rgba(255, 255, 255, 0.08);
            --text-primary: #F9FAFB;
            --text-secondary: #94A3B8;
            --accent: #6366F1;
            --green: #10B981;
            --red: #EF4444;
            --amber: #F59E0B;
        }}
        * {{ box-sizing: border-box; margin: 0; padding: 0; }}
        body {{
            background: var(--bg-base);
            color: var(--text-primary);
            font-family: 'Inter', sans-serif;
            padding: 24px 32px;
            min-height: 100vh;
        }}
        .header {{
            background: var(--bg-card);
            border: 1px solid var(--border);
            border-radius: 16px;
            padding: 24px 32px;
            margin-bottom: 24px;
            display: flex;
            justify-content: space-between;
            align-items: center;
        }}
        .header h1 {{ font-size: 24px; font-weight: 800; }}
        .header .sub {{ font-size: 13px; color: var(--text-secondary); margin-top: 4px; }}
        .badge {{
            display: inline-block;
            padding: 6px 14px;
            border-radius: 9999px;
            font-size: 12px;
            font-weight: 700;
            background: rgba(99, 102, 241, 0.15);
            color: #818CF8;
            border: 1px solid rgba(99, 102, 241, 0.3);
        }}
        .kpi-row {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
            gap: 16px;
            margin-bottom: 24px;
        }}
        .kpi-card {{
            background: var(--bg-card);
            border: 1px solid var(--border);
            border-radius: 12px;
            padding: 18px 20px;
        }}
        .kpi-label {{ font-size: 11px; text-transform: uppercase; color: var(--text-secondary); font-weight: 600; letter-spacing: 0.5px; }}
        .kpi-val {{ font-size: 22px; font-weight: 800; font-family: 'JetBrains Mono', monospace; margin-top: 6px; }}
        .grid-2 {{
            display: grid;
            grid-template-columns: 2fr 1fr;
            gap: 24px;
            margin-bottom: 24px;
        }}
        @media (max-width: 1024px) {{ .grid-2 {{ grid-template-columns: 1fr; }} }}
        .card {{
            background: var(--bg-card);
            border: 1px solid var(--border);
            border-radius: 16px;
            padding: 24px;
            margin-bottom: 24px;
        }}
        .card-title {{ font-size: 16px; font-weight: 700; margin-bottom: 16px; display: flex; justify-content: space-between; align-items: center; }}
        .table-wrap {{ overflow-x: auto; max-height: 480px; }}
        table {{
            width: 100%;
            border-collapse: collapse;
            font-size: 12px;
            font-family: 'JetBrains Mono', monospace;
        }}
        th, td {{
            padding: 10px 14px;
            text-align: left;
            border-bottom: 1px solid var(--border);
            white-space: nowrap;
        }}
        th {{
            background: rgba(255, 255, 255, 0.02);
            color: var(--text-secondary);
            font-size: 11px;
            text-transform: uppercase;
            position: sticky;
            top: 0;
            z-index: 2;
        }}
        .pill-win {{ background: rgba(16, 185, 129, 0.15); color: #34D399; padding: 2px 8px; border-radius: 4px; font-weight: 600; }}
        .pill-loss {{ background: rgba(239, 68, 68, 0.15); color: #F87171; padding: 2px 8px; border-radius: 4px; font-weight: 600; }}
        .pill-long {{ background: rgba(59, 130, 246, 0.15); color: #60A5FA; padding: 2px 6px; border-radius: 4px; }}
        .pill-short {{ background: rgba(245, 158, 11, 0.15); color: #FBBF24; padding: 2px 6px; border-radius: 4px; }}
    </style>
</head>
<body>
    <div class="header">
        <div>
            <h1>NIFTY Futures (1 Lot) Support & Resistance Backtest</h1>
            <div class="sub">1 Lot = {summary['lot_size']} Qty | Timeframe: {summary['timeframe'].upper()} | Model: {summary['model'].upper()} S&R</div>
        </div>
        <div>
            <span class="badge">NIFTY FUTURES 1 LOT</span>
        </div>
    </div>

    <!-- KPI ROW -->
    <div class="kpi-row">
        <div class="kpi-card">
            <div class="kpi-label">Total Net PnL</div>
            <div class="kpi-val" style="color: {'#10B981' if summary['net_pnl'] > 0 else '#EF4444'};">Rs {summary['net_pnl']:+,.2f}</div>
            <div style="font-size: 11px; color: var(--text-secondary); margin-top: 4px;">ROI: {summary['roi_pct']:+.2f}%</div>
        </div>
        <div class="kpi-card">
            <div class="kpi-label">Total Index Points</div>
            <div class="kpi-val" style="color: #60A5FA;">{summary['total_pts']:+.1f} pts</div>
            <div style="font-size: 11px; color: var(--text-secondary); margin-top: 4px;">Avg {summary['avg_trade_pts']:+.1f} pts/trade</div>
        </div>
        <div class="kpi-card">
            <div class="kpi-label">Win Rate</div>
            <div class="kpi-val" style="color: #FBBF24;">{summary['win_rate']:.1f}%</div>
            <div style="font-size: 11px; color: var(--text-secondary); margin-top: 4px;">{summary['wins']} Wins / {summary['losses']} Losses</div>
        </div>
        <div class="kpi-card">
            <div class="kpi-label">Profit Factor</div>
            <div class="kpi-val" style="color: #A78BFA;">{summary['profit_factor']:.2f}</div>
            <div style="font-size: 11px; color: var(--text-secondary); margin-top: 4px;">RR: {summary['rr_ratio']:.2f} : 1</div>
        </div>
        <div class="kpi-card">
            <div class="kpi-label">Max Drawdown</div>
            <div class="kpi-val" style="color: #EF4444;">Rs {summary['max_dd_val']:,.2f}</div>
            <div style="font-size: 11px; color: var(--text-secondary); margin-top: 4px;">Peak DD: -{summary['max_dd_pct']:.2f}%</div>
        </div>
        <div class="kpi-card">
            <div class="kpi-label">Sharpe Ratio</div>
            <div class="kpi-val" style="color: #34D399;">{summary['sharpe']:.2f}</div>
            <div style="font-size: 11px; color: var(--text-secondary); margin-top: 4px;">Annualized</div>
        </div>
    </div>

    <!-- CHARTS -->
    <div class="card">
        <div class="card-title">
            <span>📈 Cumulative Equity Curve (Nifty Futures 1 Lot)</span>
            <span style="font-size: 12px; color: var(--text-secondary);">Start: Rs {summary['initial_capital']:,.0f} &rarr; End: Rs {summary['final_capital']:,.0f}</span>
        </div>
        <div id="equityChart" style="height: 380px;"></div>
    </div>

    <div class="grid-2">
        <div class="card">
            <div class="card-title">📊 Daily PnL Distribution (Rs)</div>
            <div id="dailyChart" style="height: 300px;"></div>
        </div>
        <div class="card">
            <div class="card-title">📉 Underwater Drawdown Curve (%)</div>
            <div id="ddChart" style="height: 300px;"></div>
        </div>
    </div>

    <!-- TRADE LOG -->
    <div class="card">
        <div class="card-title">
            <span>📋 Trade Execution Journal ({summary['total_trades']} Completed Trades)</span>
            <span style="font-size: 12px; color: var(--text-secondary);">Exported to: trades_nifty_futures_1lot.csv</span>
        </div>
        <div class="table-wrap">
            <table>
                <thead>
                    <tr>
                        <th>#</th>
                        <th>Date</th>
                        <th>Time</th>
                        <th>Exit Time</th>
                        <th>Direction</th>
                        <th>Playbook</th>
                        <th>Entry</th>
                        <th>Exit</th>
                        <th>Points</th>
                        <th>Gross PnL</th>
                        <th>Taxes & Costs</th>
                        <th>Net PnL</th>
                        <th>Result</th>
                    </tr>
                </thead>
                <tbody>
                    {"".join([f'''
                    <tr>
                        <td>{i+1}</td>
                        <td>{r['Date']}</td>
                        <td>{r['Time']}</td>
                        <td>{r['Exit_Time']}</td>
                        <td><span class="{'pill-long' if 'LONG' in r['Type'] else 'pill-short'}">{r['Type']}</span></td>
                        <td>{r['Playbook']}</td>
                        <td>{r['Entry_Price']}</td>
                        <td>{r['Exit_Price']}</td>
                        <td style="color: {'#34D399' if r['Points'] > 0 else '#F87171'}; font-weight: bold;">{r['Points']:+.1f}</td>
                        <td>Rs {r['Gross_PnL']:+,.0f}</td>
                        <td>Rs {r['Total_Costs']:.0f}</td>
                        <td style="color: {'#34D399' if r['Net_PnL'] > 0 else '#F87171'}; font-weight: bold;">Rs {r['Net_PnL']:+,.0f}</td>
                        <td><span class="{'pill-win' if r['Net_PnL'] > 0 else 'pill-loss'}">{r['Result']}</span></td>
                    </tr>
                    ''' for i, r in enumerate(trades_list)])}
                </tbody>
            </table>
        </div>
    </div>

    <script>
        const eqData = {json.dumps(cum_equity)};
        const labels = {json.dumps(trade_labels)};
        const ddData = {json.dumps(dd_pct)};
        const dDates = {json.dumps(daily_dates)};
        const dVals = {json.dumps(daily_vals)};
        const dCols = {json.dumps(daily_colors)};

        // 1. Equity Curve
        Plotly.newPlot('equityChart', [{{
            x: labels,
            y: eqData,
            type: 'scatter',
            mode: 'lines',
            line: {{ color: '#6366F1', width: 2.5 }},
            fill: 'tozeroy',
            fillcolor: 'rgba(99, 102, 241, 0.05)'
        }}], {{
            paper_bgcolor: 'transparent',
            plot_bgcolor: 'transparent',
            margin: {{ l: 60, r: 30, t: 10, b: 30 }},
            xaxis: {{ gridcolor: 'rgba(255, 255, 255, 0.05)', showticklabels: false }},
            yaxis: {{ gridcolor: 'rgba(255, 255, 255, 0.05)', tickformat: ',.0f', tickprefix: 'Rs ', font: {{ family: 'JetBrains Mono', color: '#94A3B8' }} }}
        }}, {{ responsive: true, displayModeBar: false }});

        // 2. Daily PnL
        Plotly.newPlot('dailyChart', [{{
            x: dDates,
            y: dVals,
            type: 'bar',
            marker: {{ color: dCols }}
        }}], {{
            paper_bgcolor: 'transparent',
            plot_bgcolor: 'transparent',
            margin: {{ l: 50, r: 20, t: 10, b: 40 }},
            xaxis: {{ gridcolor: 'rgba(255, 255, 255, 0.05)', font: {{ family: 'Inter', color: '#94A3B8', size: 10 }} }},
            yaxis: {{ gridcolor: 'rgba(255, 255, 255, 0.05)', tickformat: ',.0f', tickprefix: 'Rs ', font: {{ family: 'JetBrains Mono', color: '#94A3B8' }} }}
        }}, {{ responsive: true, displayModeBar: false }});

        // 3. Drawdown Chart
        Plotly.newPlot('ddChart', [{{
            x: labels,
            y: ddData,
            type: 'scatter',
            mode: 'lines',
            line: {{ color: '#EF4444', width: 1.8 }},
            fill: 'tozeroy',
            fillcolor: 'rgba(239, 68, 68, 0.1)'
        }}], {{
            paper_bgcolor: 'transparent',
            plot_bgcolor: 'transparent',
            margin: {{ l: 50, r: 20, t: 10, b: 30 }},
            xaxis: {{ gridcolor: 'rgba(255, 255, 255, 0.05)', showticklabels: false }},
            yaxis: {{ gridcolor: 'rgba(255, 255, 255, 0.05)', tickformat: '.1f', ticksuffix: '%', font: {{ family: 'JetBrains Mono', color: '#94A3B8' }} }}
        }}, {{ responsive: true, displayModeBar: false }});
    </script>
</body>
</html>
"""
    with open(output_file, "w", encoding="utf-8") as f:
        f.write(html)
    print(f"\n[+] Interactive Report successfully generated at: {output_file}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="NIFTY Futures 1 Lot S&R Backtest")
    parser.add_argument("--timeframe", type=str, default="5m", choices=["5m", "15m"], help="Candle timeframe (5m or 15m)")
    parser.add_argument("--model", type=str, default="formula", choices=["formula", "step"], help="S&R level model (formula or step)")
    parser.add_argument("--trades", type=int, default=1, help="Max trades per day (default: 1)")
    parser.add_argument("--capital", type=float, default=150000.0, help="Initial capital in Rs")
    args = parser.parse_args()

    run_nifty_futures_backtest(
        timeframe=args.timeframe,
        model=args.model,
        max_trades_per_day=args.trades,
        initial_capital=args.capital
    )
