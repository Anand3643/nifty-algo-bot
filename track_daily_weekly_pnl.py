"""
========================================================================================
   DAILY & WEEKLY P&L TRACKING & REPORTING ENGINE — NIFTY OPTIONS ALGO
========================================================================================
Tracks, aggregates, and visualizes Daily P&L and Weekly P&L for both:
  1. Live Paper Trading Bot logs (`algo_paper_trades.csv`)
  2. 2-Year Benchmark Strategy (`trades_2year_gap_master_nifty.csv`)

CLI Usage:
  python track_daily_weekly_pnl.py                  # Full console summary & generates HTML report
  python track_daily_weekly_pnl.py --today          # Quick view of today and current week
  python track_daily_weekly_pnl.py --notify         # Send Daily & Weekly P&L alert to Telegram
  python track_daily_weekly_pnl.py --file <path>    # Custom trade CSV file
========================================================================================
"""
import os
import sys
import argparse
from datetime import datetime, timedelta

# Ensure UTF-8 output encoding for console
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

import pandas as pd
import numpy as np
import requests

# Default Telegram Credentials (GOLD Zone)
TELEGRAM_BOT_TOKEN = "8455004756:AAHzyPNLWJ2x_2aQAQTHdDDzWn5VGW7KLSU"
TELEGRAM_CHAT_ID = "-5077267080"
INITIAL_CAPITAL = 50000.0

def send_telegram_alert(text: str) -> bool:
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": text,
        "parse_mode": "HTML",
        "disable_web_page_preview": True
    }
    try:
        r = requests.post(url, json=payload, timeout=8)
        return r.status_code == 200
    except Exception as e:
        print(f"Telegram notification error: {e}")
        return False

def load_trades_data(file_path: str = None) -> tuple[pd.DataFrame, str]:
    if file_path and os.path.exists(file_path):
        source = file_path
    elif os.path.exists("algo_paper_trades.csv") and os.path.getsize("algo_paper_trades.csv") > 50:
        source = "algo_paper_trades.csv (Live Paper Trading)"
        file_path = "algo_paper_trades.csv"
    elif os.path.exists("trades_2year_gap_master_nifty.csv"):
        source = "trades_2year_gap_master_nifty.csv (2-Year Strategy Benchmark)"
        file_path = "trades_2year_gap_master_nifty.csv"
    else:
        raise FileNotFoundError("No trades data found in workspace!")

    df = pd.read_csv(file_path)
    df["Date"] = pd.to_datetime(df["Date"])
    df["Day_Name"] = df["Date"].dt.day_name()
    df["ISO_Year"] = df["Date"].dt.isocalendar().year
    df["ISO_Week"] = df["Date"].dt.isocalendar().week
    df["Year_Week"] = df["ISO_Year"].astype(str) + "-W" + df["ISO_Week"].astype(str).str.zfill(2)
    df["Year_Month"] = df["Date"].dt.strftime("%Y-%m")
    return df, source

def compute_daily_ledger(df: pd.DataFrame) -> pd.DataFrame:
    grouped = df.groupby(df["Date"].dt.date)
    records = []
    cum_cap = INITIAL_CAPITAL

    for d, g in grouped:
        t_count = len(g)
        wins = int((g["Net_PnL"] > 0).sum())
        losses = int((g["Net_PnL"] < 0).sum())
        wr = round((wins / t_count * 100), 1) if t_count > 0 else 0.0
        net_pnl = round(float(g["Net_PnL"].sum()), 2)
        gross_pnl = round(float(g["Gross_PnL"].sum()), 2) if "Gross_PnL" in g.columns else net_pnl
        costs = round(float(g["Costs"].sum()), 2) if "Costs" in g.columns else 0.0
        pts = round(float(g["Points"].sum()), 2) if "Points" in g.columns else 0.0
        cum_cap = round(cum_cap + net_pnl, 2)
        day_roi = round((net_pnl / (cum_cap - net_pnl)) * 100, 2) if (cum_cap - net_pnl) > 0 else 0.0

        records.append({
            "Date": str(d),
            "Day": g["Day_Name"].iloc[0],
            "Trades": t_count,
            "Wins": wins,
            "Losses": losses,
            "Win_Rate": wr,
            "Points": pts,
            "Gross_PnL": gross_pnl,
            "Costs": costs,
            "Net_PnL": net_pnl,
            "Capital": cum_cap,
            "Day_ROI": day_roi
        })

    return pd.DataFrame(records)

def compute_weekly_ledger(df: pd.DataFrame) -> pd.DataFrame:
    grouped = df.groupby("Year_Week")
    records = []
    cum_cap = INITIAL_CAPITAL

    for yw, g in grouped:
        start_d = g["Date"].min()
        monday = start_d - timedelta(days=start_d.weekday())
        friday = monday + timedelta(days=4)
        week_span = f"{monday.strftime('%d-%b')} to {friday.strftime('%d-%b-%Y')}"

        t_count = len(g)
        wins = int((g["Net_PnL"] > 0).sum())
        losses = int((g["Net_PnL"] < 0).sum())
        wr = round((wins / t_count * 100), 1) if t_count > 0 else 0.0
        net_pnl = round(float(g["Net_PnL"].sum()), 2)
        best_trade = round(float(g["Net_PnL"].max()), 2)
        worst_trade = round(float(g["Net_PnL"].min()), 2)
        days_traded = int(g["Date"].dt.date.nunique())
        cum_cap = round(cum_cap + net_pnl, 2)
        week_roi = round((net_pnl / (cum_cap - net_pnl)) * 100, 2) if (cum_cap - net_pnl) > 0 else 0.0

        records.append({
            "Year_Week": yw,
            "Week_Span": week_span,
            "Trades": t_count,
            "Wins": wins,
            "Losses": losses,
            "Win_Rate": wr,
            "Days_Traded": days_traded,
            "Best_Trade": best_trade,
            "Worst_Trade": worst_trade,
            "Net_PnL": net_pnl,
            "Capital": cum_cap,
            "Week_ROI": week_roi
        })

    return pd.DataFrame(records)

def compute_day_of_week_stats(daily_df: pd.DataFrame) -> pd.DataFrame:
    days_order = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday"]
    records = []
    for day in days_order:
        sub = daily_df[daily_df["Day"] == day]
        if sub.empty:
            continue
        days_cnt = len(sub)
        win_days = int((sub["Net_PnL"] > 0).sum())
        loss_days = int((sub["Net_PnL"] < 0).sum())
        wr = round(win_days / days_cnt * 100, 1)
        net_pnl = round(float(sub["Net_PnL"].sum()), 2)
        avg_day = round(float(sub["Net_PnL"].mean()), 2)
        records.append({
            "Day": day,
            "Total_Days": days_cnt,
            "Winning_Days": win_days,
            "Losing_Days": loss_days,
            "Day_Win_Rate": wr,
            "Net_PnL": net_pnl,
            "Avg_PnL": avg_day
        })
    return pd.DataFrame(records)

def compute_monthly_stats(df: pd.DataFrame) -> pd.DataFrame:
    grouped = df.groupby("Year_Month")
    records = []
    for ym, g in grouped:
        t_count = len(g)
        wins = int((g["Net_PnL"] > 0).sum())
        wr = round(wins / t_count * 100, 1) if t_count > 0 else 0.0
        net_pnl = round(float(g["Net_PnL"].sum()), 2)
        records.append({
            "Month": ym,
            "Trades": t_count,
            "Win_Rate": wr,
            "Net_PnL": net_pnl
        })
    return pd.DataFrame(records)

def print_console_summary(source: str, daily_df: pd.DataFrame, weekly_df: pd.DataFrame, dow_df: pd.DataFrame):
    print("\n" + "="*80)
    print("  NIFTY OPTIONS ALGO -- DAILY & WEEKLY P&L PERFORMANCE SUMMARY")
    print(f"  Data Source: {source}")
    print("="*80)

    total_net = weekly_df["Net_PnL"].sum()
    final_cap = weekly_df["Capital"].iloc[-1]
    roi = ((final_cap - INITIAL_CAPITAL) / INITIAL_CAPITAL) * 100

    print(f"\n  Capital Growth:     Rs {INITIAL_CAPITAL:,.2f}  --->  Rs {final_cap:,.2f}  ({roi:+.2f}%)")
    print(f"  Cumulative Net P&L: Rs {total_net:+,.2f}")

    # Weekly stats
    tot_weeks = len(weekly_df)
    win_weeks = int((weekly_df["Net_PnL"] > 0).sum())
    loss_weeks = int((weekly_df["Net_PnL"] < 0).sum())
    weekly_wr = (win_weeks / tot_weeks * 100) if tot_weeks > 0 else 0.0
    avg_week = weekly_df["Net_PnL"].mean()
    best_week = weekly_df["Net_PnL"].max()
    worst_week = weekly_df["Net_PnL"].min()

    print("\n" + "-"*80)
    print("[+] WEEKLY P&L METRICS:")
    print(f"  * Total Trading Weeks:     {tot_weeks} Weeks")
    print(f"  * Profitable Weeks:        {win_weeks} ({weekly_wr:.1f}% Weekly Win Rate)")
    print(f"  * Losing Weeks:            {loss_weeks} ({100 - weekly_wr:.1f}%)")
    print(f"  * Average Weekly P&L:      Rs {avg_week:+,.2f} / week")
    print(f"  * Best Week Ever:          Rs {best_week:+,.2f}")
    print(f"  * Worst Week Ever:         Rs {worst_week:+,.2f}")

    # Daily stats
    tot_days = len(daily_df)
    win_days = int((daily_df["Net_PnL"] > 0).sum())
    loss_days = int((daily_df["Net_PnL"] < 0).sum())
    daily_wr = (win_days / tot_days * 100) if tot_days > 0 else 0.0
    avg_day = daily_df["Net_PnL"].mean()
    best_day = daily_df["Net_PnL"].max()
    worst_day = daily_df["Net_PnL"].min()

    print("\n" + "-"*80)
    print("[+] DAILY P&L METRICS:")
    print(f"  * Total Active Trading Days: {tot_days} Days")
    print(f"  * Profitable Days:           {win_days} ({daily_wr:.1f}% Daily Win Rate)")
    print(f"  * Losing Days:               {loss_days} ({100 - daily_wr:.1f}%)")
    print(f"  * Average Daily P&L:         Rs {avg_day:+,.2f} / day")
    print(f"  * Best Day Ever:             Rs {best_day:+,.2f}")
    print(f"  * Worst Day Ever:            Rs {worst_day:+,.2f}")

    # Day of week
    print("\n" + "-"*80)
    print("[+] DAY-OF-WEEK PERFORMANCE BREAKDOWN:")
    print(f"  {'Day':<12} | {'Days':<6} | {'Win Rate':<10} | {'Net P&L (Rs)':<14} | {'Avg P&L (Rs)'}")
    print("  " + "-"*65)
    for _, r in dow_df.iterrows():
        pnl_str = f"Rs {r['Net_PnL']:+,.2f}"
        avg_str = f"Rs {r['Avg_PnL']:+,.2f}"
        print(f"  {r['Day']:<12} | {r['Total_Days']:<6} | {r['Day_Win_Rate']:>5.1f}%     | {pnl_str:<14} | {avg_str}")

    # Most recent 5 weeks
    print("\n" + "-"*80)
    print("[+] RECENT 5 WEEKS P&L LEDGER:")
    recent_w = weekly_df.tail(5)
    print(f"  {'Week':<10} | {'Span':<24} | {'Trades':<8} | {'Win%':<6} | {'Net P&L (Rs)':<14} | {'Capital'}")
    print("  " + "-"*75)
    for _, r in recent_w.iterrows():
        pnl_str = f"Rs {r['Net_PnL']:+,.2f}"
        cap_str = f"Rs {r['Capital']:,.2f}"
        print(f"  {r['Year_Week']:<10} | {r['Week_Span']:<24} | {r['Trades']:<8} | {r['Win_Rate']:>4.1f}% | {pnl_str:<14} | {cap_str}")
    print("="*80 + "\n")

def generate_interactive_html(source: str, daily_df: pd.DataFrame, weekly_df: pd.DataFrame, dow_df: pd.DataFrame, monthly_df: pd.DataFrame) -> str:
    total_net = weekly_df["Net_PnL"].sum()
    final_cap = weekly_df["Capital"].iloc[-1]
    roi = ((final_cap - INITIAL_CAPITAL) / INITIAL_CAPITAL) * 100

    tot_weeks = len(weekly_df)
    win_weeks = int((weekly_df["Net_PnL"] > 0).sum())
    loss_weeks = int((weekly_df["Net_PnL"] < 0).sum())
    weekly_wr = (win_weeks / tot_weeks * 100) if tot_weeks > 0 else 0.0
    avg_week = weekly_df["Net_PnL"].mean()
    best_week = weekly_df["Net_PnL"].max()
    worst_week = weekly_df["Net_PnL"].min()

    tot_days = len(daily_df)
    win_days = int((daily_df["Net_PnL"] > 0).sum())
    daily_wr = (win_days / tot_days * 100) if tot_days > 0 else 0.0
    avg_day = daily_df["Net_PnL"].mean()

    # Chart datasets
    week_labels = weekly_df["Year_Week"].tolist()
    week_pnls = weekly_df["Net_PnL"].tolist()
    week_caps = weekly_df["Capital"].tolist()

    dow_labels = dow_df["Day"].tolist()
    dow_pnls = dow_df["Net_PnL"].tolist()

    # Generate Weekly Table Rows
    weekly_rows = []
    for _, r in weekly_df.iterrows():
        badge = "badge-win" if r["Net_PnL"] > 0 else "badge-loss"
        pnl_cls = "text-profit" if r["Net_PnL"] > 0 else "text-loss"
        row = (
            f"<tr>"
            f"<td><strong>{r['Year_Week']}</strong></td>"
            f"<td>{r['Week_Span']}</td>"
            f"<td>{r['Trades']}</td>"
            f"<td>{r['Wins']}W / {r['Losses']}L</td>"
            f"<td><span class='{badge}'>{r['Win_Rate']:.1f}%</span></td>"
            f"<td>Rs {r['Best_Trade']:+,.2f}</td>"
            f"<td>Rs {r['Worst_Trade']:+,.2f}</td>"
            f"<td class='{pnl_cls}'><strong>Rs {r['Net_PnL']:+,.2f}</strong></td>"
            f"<td><strong>Rs {r['Capital']:,.2f}</strong></td>"
            f"<td class='{pnl_cls}'>{r['Week_ROI']:+.2f}%</td>"
            f"</tr>"
        )
        weekly_rows.append(row)
    weekly_rows_html = "\n".join(weekly_rows)

    # Generate Daily Table Rows (top 100 recent)
    daily_rows = []
    for _, r in daily_df.iloc[::-1].iterrows():
        badge = "badge-win" if r["Net_PnL"] > 0 else "badge-loss"
        pnl_cls = "text-profit" if r["Net_PnL"] > 0 else "text-loss"
        row = (
            f"<tr>"
            f"<td><strong>{r['Date']}</strong></td>"
            f"<td>{r['Day']}</td>"
            f"<td>{r['Trades']}</td>"
            f"<td>{r['Wins']}W / {r['Losses']}L</td>"
            f"<td><span class='{badge}'>{r['Win_Rate']:.1f}%</span></td>"
            f"<td>{r['Points']:+.1f} pts</td>"
            f"<td>Rs {r['Gross_PnL']:+,.2f}</td>"
            f"<td>Rs {r['Costs']:,.2f}</td>"
            f"<td class='{pnl_cls}'><strong>Rs {r['Net_PnL']:+,.2f}</strong></td>"
            f"<td><strong>Rs {r['Capital']:,.2f}</strong></td>"
            f"</tr>"
        )
        daily_rows.append(row)
    daily_rows_html = "\n".join(daily_rows)

    template = """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Daily & Weekly P&L Tracker | NIFTY Options Algo</title>
    <link href="https://fonts.googleapis.com/css2?family=Outfit:wght@300;400;500;600;700;800&family=JetBrains+Mono:wght@400;600&display=swap" rel="stylesheet">
    <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
    <style>
        :root {
            --bg: #0b0f19;
            --surface: #111827;
            --surface-hover: #1f2937;
            --border: #374151;
            --primary: #00f2fe;
            --accent: #4facfe;
            --success: #10b981;
            --danger: #ef4444;
            --warning: #f59e0b;
            --text-main: #f9fafb;
            --text-muted: #9ca3af;
        }
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body {
            background: var(--bg);
            color: var(--text-main);
            font-family: 'Outfit', sans-serif;
            padding: 24px;
            min-height: 100vh;
        }
        .header {
            background: linear-gradient(135deg, #1e1b4b 0%, #0f172a 100%);
            border: 1px solid rgba(255,255,255,0.1);
            padding: 28px;
            border-radius: 16px;
            margin-bottom: 24px;
            display: flex;
            justify-content: space-between;
            align-items: center;
            box-shadow: 0 10px 30px rgba(0,0,0,0.5);
        }
        .header h1 {
            font-size: 26px;
            font-weight: 800;
            background: linear-gradient(90deg, #00f2fe, #4facfe);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
        }
        .header p {
            color: var(--text-muted);
            font-size: 14px;
            margin-top: 4px;
        }
        .badge-live {
            background: rgba(16, 185, 129, 0.15);
            border: 1px solid #10b981;
            color: #10b981;
            padding: 6px 14px;
            border-radius: 20px;
            font-weight: 600;
            font-size: 13px;
        }
        .kpi-grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(210px, 1fr));
            gap: 16px;
            margin-bottom: 24px;
        }
        .kpi-card {
            background: var(--surface);
            border: 1px solid var(--border);
            padding: 20px;
            border-radius: 14px;
            transition: transform 0.2s;
        }
        .kpi-card:hover {
            transform: translateY(-3px);
            border-color: var(--primary);
        }
        .kpi-title {
            font-size: 13px;
            color: var(--text-muted);
            text-transform: uppercase;
            letter-spacing: 0.5px;
            font-weight: 600;
        }
        .kpi-val {
            font-size: 24px;
            font-weight: 700;
            margin-top: 8px;
            font-family: 'JetBrains Mono', monospace;
        }
        .kpi-sub {
            font-size: 12px;
            color: var(--text-muted);
            margin-top: 4px;
        }
        .text-profit { color: var(--success); }
        .text-loss { color: var(--danger); }
        .charts-row {
            display: grid;
            grid-template-columns: 2fr 1fr;
            gap: 20px;
            margin-bottom: 24px;
        }
        @media (max-width: 1024px) {
            .charts-row { grid-template-columns: 1fr; }
        }
        .chart-box {
            background: var(--surface);
            border: 1px solid var(--border);
            padding: 20px;
            border-radius: 14px;
        }
        .chart-box h3 {
            font-size: 16px;
            margin-bottom: 16px;
            color: #e5e7eb;
        }
        .table-section {
            background: var(--surface);
            border: 1px solid var(--border);
            border-radius: 14px;
            padding: 20px;
            margin-bottom: 24px;
        }
        .table-header {
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 16px;
        }
        .tabs {
            display: flex;
            gap: 8px;
        }
        .tab-btn {
            background: #1f2937;
            border: 1px solid #374151;
            color: #d1d5db;
            padding: 8px 16px;
            border-radius: 8px;
            cursor: pointer;
            font-weight: 600;
            font-size: 13px;
        }
        .tab-btn.active {
            background: var(--accent);
            color: #fff;
            border-color: var(--accent);
        }
        table {
            width: 100%;
            border-collapse: collapse;
            font-size: 13px;
        }
        th {
            background: #1e293b;
            color: #94a3b8;
            font-weight: 600;
            padding: 12px 14px;
            text-align: left;
            border-bottom: 1px solid var(--border);
        }
        td {
            padding: 12px 14px;
            border-bottom: 1px solid rgba(255,255,255,0.05);
            font-family: 'JetBrains Mono', monospace;
        }
        tr:hover td {
            background: var(--surface-hover);
        }
        .badge-win {
            background: rgba(16, 185, 129, 0.15);
            color: #10b981;
            padding: 2px 8px;
            border-radius: 6px;
            font-size: 11px;
            font-weight: 600;
        }
        .badge-loss {
            background: rgba(239, 68, 68, 0.15);
            color: #ef4444;
            padding: 2px 8px;
            border-radius: 6px;
            font-size: 11px;
            font-weight: 600;
        }
        .table-scroll {
            max-height: 480px;
            overflow-y: auto;
        }
    </style>
</head>
<body>
    <div class="header">
        <div>
            <h1>NIFTY OPTIONS ALGO — DAILY & WEEKLY P&L LEDGER</h1>
            <p>Underlying: NIFTY 50 Options (1 Lot = 65 Qty) | Source: __SOURCE__ | Updated: __DATETIME__</p>
        </div>
        <div class="badge-live">⚡ LIVE TRACKING ENGINE</div>
    </div>

    <div class="kpi-grid">
        <div class="kpi-card">
            <div class="kpi-title">Cumulative Net P&L</div>
            <div class="kpi-val text-profit">Rs __TOTAL_NET__</div>
            <div class="kpi-sub">ROI: __ROI__% on Rs 50k</div>
        </div>
        <div class="kpi-card">
            <div class="kpi-title">Weekly Win Rate</div>
            <div class="kpi-val text-profit">__WEEKLY_WR__%</div>
            <div class="kpi-sub">__WIN_WEEKS__ Win Weeks / __LOSS_WEEKS__ Loss Weeks</div>
        </div>
        <div class="kpi-card">
            <div class="kpi-title">Daily Win Rate</div>
            <div class="kpi-val text-profit">__DAILY_WR__%</div>
            <div class="kpi-sub">__WIN_DAYS__ Win Days / __LOSS_DAYS__ Loss Days</div>
        </div>
        <div class="kpi-card">
            <div class="kpi-title">Avg Weekly Profit</div>
            <div class="kpi-val text-profit">Rs __AVG_WEEK__</div>
            <div class="kpi-sub">Across __TOT_WEEKS__ active trading weeks</div>
        </div>
        <div class="kpi-card">
            <div class="kpi-title">Best Week Ever</div>
            <div class="kpi-val text-profit">Rs __BEST_WEEK__</div>
            <div class="kpi-sub">Worst Week: Rs __WORST_WEEK__</div>
        </div>
        <div class="kpi-card">
            <div class="kpi-title">Account Balance</div>
            <div class="kpi-val text-profit">Rs __FINAL_CAP__</div>
            <div class="kpi-sub">Initial Capital: Rs __INITIAL_CAPITAL__</div>
        </div>
    </div>

    <div class="charts-row">
        <div class="chart-box">
            <h3>📈 Week-by-Week Net P&L (Rs)</h3>
            <canvas id="weeklyPnlChart" height="130"></canvas>
        </div>
        <div class="chart-box">
            <h3>📆 Day of Week Distribution</h3>
            <canvas id="dowChart" height="130"></canvas>
        </div>
    </div>

    <div class="chart-box" style="margin-bottom: 24px;">
        <h3>💰 Cumulative Equity Curve (Weekly Progression)</h3>
        <canvas id="equityChart" height="90"></canvas>
    </div>

    <div class="table-section">
        <div class="table-header">
            <h3>📅 Performance Ledgers</h3>
            <div class="tabs">
                <button class="tab-btn active" onclick="switchTab('weekly')">Weekly Ledger (__TOT_WEEKS__ Weeks)</button>
                <button class="tab-btn" onclick="switchTab('daily')">Daily Ledger (__TOT_DAYS__ Days)</button>
            </div>
        </div>

        <div id="weekly-tab" class="table-scroll">
            <table>
                <thead>
                    <tr>
                        <th>Week</th>
                        <th>Span</th>
                        <th>Trades</th>
                        <th>W / L</th>
                        <th>Win Rate</th>
                        <th>Best Trade</th>
                        <th>Worst Trade</th>
                        <th>Net Weekly P&L</th>
                        <th>Capital</th>
                        <th>Weekly ROI</th>
                    </tr>
                </thead>
                <tbody>
                    __WEEKLY_ROWS__
                </tbody>
            </table>
        </div>

        <div id="daily-tab" class="table-scroll" style="display: none;">
            <table>
                <thead>
                    <tr>
                        <th>Date</th>
                        <th>Day</th>
                        <th>Trades</th>
                        <th>W / L</th>
                        <th>Win Rate</th>
                        <th>Points</th>
                        <th>Gross P&L</th>
                        <th>Friction/Tax</th>
                        <th>Net Daily P&L</th>
                        <th>Capital</th>
                    </tr>
                </thead>
                <tbody>
                    __DAILY_ROWS__
                </tbody>
            </table>
        </div>
    </div>

    <script>
        function switchTab(tab) {
            const wTab = document.getElementById('weekly-tab');
            const dTab = document.getElementById('daily-tab');
            const btns = document.querySelectorAll('.tab-btn');
            if (tab === 'weekly') {
                wTab.style.display = 'block';
                dTab.style.display = 'none';
                btns[0].classList.add('active');
                btns[1].classList.remove('active');
            } else {
                wTab.style.display = 'none';
                dTab.style.display = 'block';
                btns[0].classList.remove('active');
                btns[1].classList.add('active');
            }
        }

        // Weekly P&L Bar Chart
        const weekLabels = __WEEK_LABELS__;
        const weekPnls = __WEEK_PNLS__;
        const weekColors = weekPnls.map(v => v >= 0 ? '#10b981' : '#ef4444');

        new Chart(document.getElementById('weeklyPnlChart'), {
            type: 'bar',
            data: {
                labels: weekLabels,
                datasets: [{
                    label: 'Weekly Net P&L (Rs)',
                    data: weekPnls,
                    backgroundColor: weekColors,
                    borderRadius: 4
                }]
            },
            options: {
                responsive: true,
                plugins: {
                    legend: { display: false },
                    tooltip: {
                        callbacks: {
                            label: function(ctx) { return 'Net P&L: Rs ' + ctx.raw.toLocaleString(); }
                        }
                    }
                },
                scales: {
                    x: { ticks: { color: '#6b7280', maxTicksLimit: 20 }, grid: { display: false } },
                    y: { ticks: { color: '#6b7280' }, grid: { color: '#1f2937' } }
                }
            }
        });

        // Day of Week Chart
        new Chart(document.getElementById('dowChart'), {
            type: 'bar',
            data: {
                labels: __DOW_LABELS__,
                datasets: [{
                    label: 'Net P&L (Rs)',
                    data: __DOW_PNLS__,
                    backgroundColor: ['#3b82f6', '#10b981', '#f59e0b', '#8b5cf6', '#ec4899'],
                    borderRadius: 6
                }]
            },
            options: {
                responsive: true,
                plugins: { legend: { display: false } },
                scales: {
                    x: { ticks: { color: '#9ca3af' }, grid: { display: false } },
                    y: { ticks: { color: '#9ca3af' }, grid: { color: '#1f2937' } }
                }
            }
        });

        // Equity Curve Chart
        new Chart(document.getElementById('equityChart'), {
            type: 'line',
            data: {
                labels: weekLabels,
                datasets: [{
                    label: 'Cumulative Capital (Rs)',
                    data: __WEEK_CAPS__,
                    borderColor: '#00f2fe',
                    backgroundColor: 'rgba(0, 242, 254, 0.1)',
                    fill: true,
                    tension: 0.2,
                    pointRadius: 2
                }]
            },
            options: {
                responsive: true,
                plugins: {
                    legend: { display: false },
                    tooltip: {
                        callbacks: {
                            label: function(ctx) { return 'Capital: Rs ' + ctx.raw.toLocaleString(); }
                        }
                    }
                },
                scales: {
                    x: { ticks: { color: '#6b7280', maxTicksLimit: 20 }, grid: { display: false } },
                    y: { ticks: { color: '#6b7280' }, grid: { color: '#1f2937' } }
                }
            }
        });
    </script>
</body>
</html>
"""

    replacements = {
        "__SOURCE__": source,
        "__DATETIME__": datetime.now().strftime("%d-%b-%Y %H:%M:%S IST"),
        "__TOTAL_NET__": f"{total_net:+,.2f}",
        "__ROI__": f"{roi:+.2f}",
        "__WEEKLY_WR__": f"{weekly_wr:.1f}",
        "__WIN_WEEKS__": str(win_weeks),
        "__LOSS_WEEKS__": str(loss_weeks),
        "__DAILY_WR__": f"{daily_wr:.1f}",
        "__WIN_DAYS__": str(win_days),
        "__LOSS_DAYS__": str(tot_days - win_days),
        "__AVG_WEEK__": f"{avg_week:+,.2f}",
        "__TOT_WEEKS__": str(tot_weeks),
        "__BEST_WEEK__": f"{best_week:+,.2f}",
        "__WORST_WEEK__": f"{worst_week:+,.2f}",
        "__FINAL_CAP__": f"{final_cap:,.2f}",
        "__INITIAL_CAPITAL__": f"{INITIAL_CAPITAL:,.2f}",
        "__WEEKLY_ROWS__": weekly_rows_html,
        "__DAILY_ROWS__": daily_rows_html,
        "__WEEK_LABELS__": str(week_labels),
        "__WEEK_PNLS__": str(week_pnls),
        "__WEEK_CAPS__": str(week_caps),
        "__DOW_LABELS__": str(dow_labels),
        "__DOW_PNLS__": str(dow_pnls),
        "__TOT_DAYS__": str(tot_days)
    }

    html = template
    for k, v in replacements.items():
        html = html.replace(k, v)

    return html

def push_telegram_report(daily_df: pd.DataFrame, weekly_df: pd.DataFrame):
    recent_day = daily_df.iloc[-1]
    recent_week = weekly_df.iloc[-1]
    final_cap = weekly_df["Capital"].iloc[-1]
    tot_net = weekly_df["Net_PnL"].sum()
    roi = ((final_cap - INITIAL_CAPITAL) / INITIAL_CAPITAL) * 100

    d_sign = "🟢" if recent_day["Net_PnL"] >= 0 else "🔴"
    w_sign = "🟢" if recent_week["Net_PnL"] >= 0 else "🔴"

    msg = (
        f"📊 <b>DAILY & WEEKLY P&L STATUS REPORT</b>\n"
        f"📅 Date: <b>{recent_day['Date']} ({recent_day['Day']})</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"📊 <b>TODAY'S P&L:</b>\n"
        f"  • Net Daily: <b>{d_sign} Rs {recent_day['Net_PnL']:+,.2f}</b>\n"
        f"  • Trades: {recent_day['Trades']} ({recent_day['Wins']}W / {recent_day['Losses']}L)\n"
        f"  • Win Rate: {recent_day['Win_Rate']:.1f}%\n"
        f"  • Points: {recent_day['Points']:+.1f} pts\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"📅 <b>CURRENT WEEK P&L ({recent_week['Year_Week']}):</b>\n"
        f"  • Net Weekly: <b>{w_sign} Rs {recent_week['Net_PnL']:+,.2f}</b>\n"
        f"  • Weekly Trades: {recent_week['Trades']} ({recent_week['Wins']}W / {recent_week['Losses']}L)\n"
        f"  • Weekly Win Rate: {recent_week['Win_Rate']:.1f}%\n"
        f"  • Span: {recent_week['Week_Span']}\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"💰 <b>CAPITAL & PERFORMANCE:</b>\n"
        f"  • Current Balance: <b>Rs {final_cap:,.2f}</b>\n"
        f"  • Total Net P&L: <b>Rs {tot_net:+,.2f}</b>\n"
        f"  • Total ROI: <b>{roi:+.2f}%</b> (from Rs 50k)\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"🤖 <i>Status: Monitoring Active</i>"
    )
    ok = send_telegram_alert(msg)
    if ok:
        print(" Successfully sent Daily & Weekly P&L alert to Telegram group 🥇GOLD Zone!")
    else:
        print("❌ Failed to send Telegram alert.")

def main():
    parser = argparse.ArgumentParser(description="Track Daily and Weekly P&L for NIFTY Options Algo")
    parser.add_argument("--file", type=str, default=None, help="Path to trades CSV file")
    parser.add_argument("--notify", action="store_true", help="Send P&L summary to Telegram")
    parser.add_argument("--today", action="store_true", help="Show only today and current week summary")
    args = parser.parse_args()

    df, source = load_trades_data(args.file)
    daily_df = compute_daily_ledger(df)
    weekly_df = compute_weekly_ledger(df)
    dow_df = compute_day_of_week_stats(daily_df)
    monthly_df = compute_monthly_stats(df)

    if args.today:
        recent_d = daily_df.iloc[-1]
        recent_w = weekly_df.iloc[-1]
        print(f"\n📊 Today ({recent_d['Date']}): Rs {recent_d['Net_PnL']:+,.2f} ({recent_d['Trades']} trades, {recent_d['Win_Rate']}%)")
        print(f"📅 This Week ({recent_w['Year_Week']}): Rs {recent_w['Net_PnL']:+,.2f} ({recent_w['Trades']} trades, {recent_w['Win_Rate']}%)")
        print(f"💰 Account Capital: Rs {recent_w['Capital']:,.2f}\n")
        return

    print_console_summary(source, daily_df, weekly_df, dow_df)

    html_content = generate_interactive_html(source, daily_df, weekly_df, dow_df, monthly_df)
    output_html = "report_daily_weekly_pnl.html"
    with open(output_html, "w", encoding="utf-8") as f:
        f.write(html_content)
    print(f" Interactive HTML Dashboard generated: {output_html}")

    if args.notify:
        push_telegram_report(daily_df, weekly_df)

if __name__ == "__main__":
    main()
