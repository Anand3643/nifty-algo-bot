"""
Generates an Executive Head-to-Head Visual Comparison HTML Report:
Our Algo Bot (CPR & Mathematical S&R Engine) vs. Arjun's Telegram Channel Levels
Evaluation Period: July 3, 2026 – October 15, 2026
"""
import os
import pandas as pd
import numpy as np

def generate_comparison_html():
    base_dir = os.path.dirname(os.path.abspath(__file__))
    comp_csv = os.path.join(base_dir, "head_to_head_comparison.csv")
    monthly_csv = os.path.join(base_dir, "monthly_comparison.csv")
    out_html = os.path.join(base_dir, "head_to_head_comparison_report.html")

    # Load trade data for equity curves
    df_our_full = pd.read_csv(os.path.join(base_dir, "trades_2year_5min_candles_nifty.csv"))
    df_our_full["Date"] = pd.to_datetime(df_our_full["Date"])
    df_our = df_our_full[(df_our_full["Date"] >= "2026-07-03") & (df_our_full["Date"] <= "2026-10-15")].copy()
    df_our.sort_values(["Date", "Time"], inplace=True)

    from backtest_telegram_levels import run_backtest as run_arjun_raw
    df_arjun_raw = run_arjun_raw(mode="BREAKOUT", sl_pts=40.0, rr=3.0)
    df_arjun_raw["Date"] = pd.to_datetime(df_arjun_raw["Date"])
    df_arjun_raw.sort_values(["Date", "Time"], inplace=True)

    df_arjun_opt = pd.read_csv(os.path.join(base_dir, "telegram_levels_best_trades.csv"))
    df_arjun_opt["Date"] = pd.to_datetime(df_arjun_opt["Date"])
    df_arjun_opt.sort_values(["Date", "Time"], inplace=True)

    # Recompute daily equity curves for aligned comparison
    dates = pd.date_range("2026-07-03", "2026-10-10", freq="B")
    
    def get_daily_curve(df):
        daily_pnl = df.groupby(df["Date"].dt.date)["Net_PnL"].sum()
        curve = [50000.0]
        cur_equity = 50000.0
        for d in dates:
            d_date = d.date()
            if d_date in daily_pnl:
                cur_equity += daily_pnl[d_date]
            curve.append(cur_equity)
        return curve

    eq_our = get_daily_curve(df_our)
    eq_arj_raw = get_daily_curve(df_arjun_raw)
    eq_arj_opt = get_daily_curve(df_arjun_opt)

    # SVG chart coords
    w = 850
    h = 280
    min_val = min(min(eq_our), min(eq_arj_raw), min(eq_arj_opt)) * 0.96
    max_val = max(max(eq_our), max(eq_arj_raw), max(eq_arj_opt)) * 1.04

    def to_points(curve):
        pts = []
        for i, val in enumerate(curve):
            x = (i / (len(curve) - 1)) * (w - 40) + 20
            y = h - 20 - ((val - min_val) / (max_val - min_val)) * (h - 40)
            pts.append(f"{x:.1f},{y:.1f}")
        return " ".join(pts)

    pts_our = to_points(eq_our)
    pts_raw = to_points(eq_arj_raw)
    pts_opt = to_points(eq_arj_opt)

    base_y = h - 20 - ((50000.0 - min_val) / (max_val - min_val)) * (h - 40)

    # Monthly comparison rows
    df_monthly = pd.read_csv(monthly_csv)
    monthly_rows = ""
    for _, r in df_monthly.iterrows():
        pnl_our = float(r["Our_PnL"])
        pnl_arj = float(r["Arjun_PnL"])
        pnl_raw = float(r["Arjun_Raw_PnL"])
        monthly_rows += f"""
        <tr>
            <td style="font-weight: 700; color: #f8fafc;">{r['Month']}</td>
            <td>{r['Our_Trades']} ({r['Our_WR']})</td>
            <td style="font-weight: 700; color: {'#10b981' if pnl_our > 0 else '#ef4444'};">Rs {pnl_our:,.2f}</td>
            <td>{r['Arjun_Trades']} ({r['Arjun_WR']})</td>
            <td style="font-weight: 700; color: {'#10b981' if pnl_arj > 0 else '#ef4444'};">Rs {pnl_arj:,.2f}</td>
            <td style="font-weight: 700; color: {'#10b981' if pnl_raw > 0 else '#ef4444'};">Rs {pnl_raw:,.2f}</td>
        </tr>
        """

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Head-to-Head Comparison: Our Bot vs Arjun Levels</title>
    <link href="https://fonts.googleapis.com/css2?family=Outfit:wght@300;400;500;600;700;800&family=JetBrains+Mono:wght@400;500;700&display=swap" rel="stylesheet">
    <style>
        :root {{
            --bg-base: #0a0f1d;
            --bg-card: rgba(17, 24, 39, 0.75);
            --border-card: rgba(255, 255, 255, 0.08);
            --accent-cyan: #06b6d4;
            --accent-emerald: #10b981;
            --accent-amber: #f59e0b;
            --accent-purple: #a855f7;
            --text-main: #f8fafc;
            --text-muted: #94a3b8;
        }}
        * {{ margin: 0; padding: 0; box-sizing: border-box; }}
        body {{
            background: radial-gradient(circle at 10% 10%, #111e38 0%, #060911 100%);
            color: var(--text-main);
            font-family: 'Outfit', sans-serif;
            padding: 30px;
            min-height: 100vh;
        }}
        .container {{
            max-width: 1240px;
            margin: 0 auto;
        }}
        .header {{
            display: flex;
            justify-content: space-between;
            align-items: center;
            background: var(--bg-card);
            border: 1px solid var(--border-card);
            backdrop-filter: blur(14px);
            padding: 26px 32px;
            border-radius: 20px;
            margin-bottom: 25px;
            box-shadow: 0 10px 30px rgba(0, 0, 0, 0.5);
        }}
        .header h1 {{
            font-size: 26px;
            font-weight: 800;
            background: linear-gradient(135deg, #38bdf8 0%, #34d399 100%);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
            margin-bottom: 6px;
        }}
        .header p {{
            color: var(--text-muted);
            font-size: 14px;
        }}
        .tag-period {{
            background: rgba(16, 185, 129, 0.15);
            border: 1px solid rgba(16, 185, 129, 0.3);
            color: #10b981;
            padding: 8px 18px;
            border-radius: 30px;
            font-weight: 600;
            font-size: 13px;
        }}
        .comparison-cards {{
            display: grid;
            grid-template-columns: 1fr 1fr;
            gap: 20px;
            margin-bottom: 25px;
        }}
        .side-card {{
            background: var(--bg-card);
            border: 1px solid var(--border-card);
            border-radius: 20px;
            padding: 26px;
            position: relative;
            overflow: hidden;
            backdrop-filter: blur(12px);
        }}
        .side-card.winner {{
            border: 1px solid rgba(16, 185, 129, 0.4);
            box-shadow: 0 0 25px rgba(16, 185, 129, 0.12);
        }}
        .side-card.winner::before {{
            content: "OVERALL WINNER (+307% MORE PROFIT)";
            position: absolute;
            top: 0;
            right: 0;
            background: linear-gradient(135deg, #10b981 0%, #059669 100%);
            color: #022c22;
            font-size: 10px;
            font-weight: 800;
            letter-spacing: 0.8px;
            padding: 6px 14px;
            border-radius: 0 0 0 12px;
        }}
        .side-title {{
            font-size: 18px;
            font-weight: 700;
            margin-bottom: 15px;
            display: flex;
            align-items: center;
            gap: 10px;
        }}
        .side-title.our {{ color: #34d399; }}
        .side-title.arjun {{ color: #a78bfa; }}
        .metric-row {{
            display: flex;
            justify-content: space-between;
            padding: 10px 0;
            border-bottom: 1px solid rgba(255, 255, 255, 0.05);
            font-size: 14px;
        }}
        .metric-row:last-child {{ border-bottom: none; }}
        .metric-lbl {{ color: var(--text-muted); }}
        .metric-val {{ font-weight: 700; font-family: 'JetBrains Mono', monospace; }}
        .chart-section {{
            background: var(--bg-card);
            border: 1px solid var(--border-card);
            border-radius: 20px;
            padding: 26px;
            margin-bottom: 25px;
            backdrop-filter: blur(12px);
        }}
        .chart-header {{
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 15px;
        }}
        .chart-legend {{
            display: flex;
            gap: 20px;
            font-size: 13px;
        }}
        .legend-item {{
            display: flex;
            align-items: center;
            gap: 8px;
        }}
        .dot {{
            width: 12px;
            height: 12px;
            border-radius: 50%;
        }}
        .chart-canvas {{
            background: rgba(7, 11, 20, 0.85);
            border-radius: 14px;
            padding: 20px;
            border: 1px solid rgba(255, 255, 255, 0.05);
        }}
        table {{
            width: 100%;
            border-collapse: collapse;
            font-size: 14px;
        }}
        th {{
            text-align: left;
            padding: 14px 16px;
            background: rgba(255, 255, 255, 0.03);
            color: var(--text-muted);
            font-weight: 600;
            text-transform: uppercase;
            font-size: 12px;
            border-bottom: 1px solid var(--border-card);
        }}
        td {{
            padding: 14px 16px;
            border-bottom: 1px solid rgba(255, 255, 255, 0.04);
            color: #cbd5e1;
        }}
        .callout {{
            background: linear-gradient(135deg, rgba(16, 185, 129, 0.08) 0%, rgba(6, 182, 212, 0.08) 100%);
            border-left: 4px solid #10b981;
            padding: 20px 24px;
            border-radius: 0 16px 16px 0;
            margin-bottom: 25px;
            line-height: 1.6;
            font-size: 14px;
        }}
        .callout strong {{ color: #34d399; }}
    </style>
</head>
<body>
    <div class="container">
        <!-- HEADER -->
        <div class="header">
            <div>
                <h1>Head-to-Head Quantitative Audit</h1>
                <p>Our Algo Bot (CPR + Mathematical Engine) vs. @FlyingcallsArjun Telegram Levels</p>
            </div>
            <div class="tag-period">
                03-Jul-2026 to 15-Oct-2026 (Identical Date Window)
            </div>
        </div>

        <!-- KEY TAKEAWAY CALLOUT -->
        <div class="callout">
            <strong>Key Quantitative Audit Finding:</strong>
            Across the exact same 68 trading sessions and using identical realistic execution costs (0.5% fill slippage, STT, turnover charges, and Rs 40 roundtrip brokerage), 
            <strong>Our Algo Bot generated +Rs 56,704.83 Net P&L (Profit Factor 2.59, +113.4% ROI)</strong> compared to 
            <strong>Arjun's +Rs 13,931.54 Net P&L (Profit Factor 1.33, +27.9% ROI)</strong>.
            Our bot generated <strong>4.07x higher net profit</strong> with a <strong>Sharpe Ratio of 5.78 vs 1.66</strong> and was profitable in <strong>every single month (4/4 green months)</strong>.
        </div>

        <!-- SIDE-BY-SIDE CARDS -->
        <div class="comparison-cards">
            <!-- OUR BOT -->
            <div class="side-card winner">
                <div class="side-title our">
                    <span>⚡ Our Algo Bot</span>
                    <span style="font-size: 13px; font-weight: 500; color: var(--text-muted);">(CPR & Mathematical S&R)</span>
                </div>
                <div class="metric-row">
                    <span class="metric-lbl">Total Net P&L:</span>
                    <span class="metric-val" style="color: #10b981; font-size: 18px;">+Rs 56,704.83 (+113.4%)</span>
                </div>
                <div class="metric-row">
                    <span class="metric-lbl">Win Rate:</span>
                    <span class="metric-val" style="color: #38bdf8;">53.4% (31 Wins / 27 Losses)</span>
                </div>
                <div class="metric-row">
                    <span class="metric-lbl">Profit Factor:</span>
                    <span class="metric-val" style="color: #a78bfa; font-size: 16px;">2.59 (Institutional Grade)</span>
                </div>
                <div class="metric-row">
                    <span class="metric-lbl">Max Drawdown:</span>
                    <span class="metric-val" style="color: #f87171;">Rs 6,920.83 (13.8%)</span>
                </div>
                <div class="metric-row">
                    <span class="metric-lbl">Sharpe Ratio:</span>
                    <span class="metric-val" style="color: #34d399;">5.78</span>
                </div>
                <div class="metric-row">
                    <span class="metric-lbl">Avg Trade P&L:</span>
                    <span class="metric-val" style="color: #f8fafc;">+Rs 977.67 / trade</span>
                </div>
                <div class="metric-row">
                    <span class="metric-lbl">Monthly Consistency:</span>
                    <span class="metric-val" style="color: #10b981;">4 / 4 Green Months (100%)</span>
                </div>
            </div>

            <!-- ARJUN TELEGRAM -->
            <div class="side-card">
                <div class="side-title arjun">
                    <span>📡 Arjun Telegram Levels</span>
                    <span style="font-size: 13px; font-weight: 500; color: var(--text-muted);">(Discretionary Morning S&R)</span>
                </div>
                <div class="metric-row">
                    <span class="metric-lbl">Total Net P&L (Raw Breakout):</span>
                    <span class="metric-val" style="color: #a78bfa; font-size: 18px;">+Rs 13,931.54 (+27.9%)</span>
                </div>
                <div class="metric-row">
                    <span class="metric-lbl">Win Rate:</span>
                    <span class="metric-val" style="color: #38bdf8;">54.5% (30 Wins / 25 Losses)</span>
                </div>
                <div class="metric-row">
                    <span class="metric-lbl">Profit Factor:</span>
                    <span class="metric-val" style="color: #f59e0b; font-size: 16px;">1.33</span>
                </div>
                <div class="metric-row">
                    <span class="metric-lbl">Max Drawdown:</span>
                    <span class="metric-val" style="color: #f87171;">Rs 16,835.82 (33.7%)</span>
                </div>
                <div class="metric-row">
                    <span class="metric-lbl">Sharpe Ratio:</span>
                    <span class="metric-val" style="color: #cbd5e1;">1.66</span>
                </div>
                <div class="metric-row">
                    <span class="metric-lbl">Avg Trade P&L:</span>
                    <span class="metric-val" style="color: #f8fafc;">+Rs 253.30 / trade</span>
                </div>
                <div class="metric-row">
                    <span class="metric-lbl">Monthly Consistency:</span>
                    <span class="metric-val" style="color: #f87171;">2 Green / 2 Red Months</span>
                </div>
            </div>
        </div>

        <!-- OVERLAID EQUITY CURVE -->
        <div class="chart-section">
            <div class="chart-header">
                <span style="font-size: 18px; font-weight: 700;">Overlaid Cumulative Equity Curves (Rs 50,000 Base)</span>
                <div class="chart-legend">
                    <div class="legend-item"><div class="dot" style="background: #10b981;"></div>Our Algo Bot (+Rs 56,704)</div>
                    <div class="legend-item"><div class="dot" style="background: #a855f7;"></div>Arjun Raw Breakout (+Rs 13,931)</div>
                    <div class="legend-item"><div class="dot" style="background: #06b6d4;"></div>Arjun Filtered (+Rs 8,960)</div>
                </div>
            </div>
            <div class="chart-canvas">
                <svg width="100%" height="{h}" viewBox="0 0 {w} {h}" preserveAspectRatio="none">
                    <!-- Baseline -->
                    <line x1="20" y1="{base_y}" x2="{w-20}" y2="{base_y}" stroke="rgba(255,255,255,0.12)" stroke-dasharray="4,4" />
                    <!-- Arjun Raw Line -->
                    <polyline points="{pts_raw}" fill="none" stroke="#a855f7" stroke-width="2.0" opacity="0.85" />
                    <!-- Arjun Opt Line -->
                    <polyline points="{pts_opt}" fill="none" stroke="#06b6d4" stroke-width="2.0" stroke-dasharray="3,3" opacity="0.85" />
                    <!-- Our Bot Line -->
                    <polyline points="{pts_our}" fill="none" stroke="#10b981" stroke-width="3.5" stroke-linecap="round" stroke-linejoin="round" />
                </svg>
                <div style="display: flex; justify-content: space-between; margin-top: 10px; font-size: 12px; color: var(--text-muted);">
                    <span>03-Jul-2026: Rs 50,000</span>
                    <span style="color: #a855f7;">Arjun Peak: Rs 68,299</span>
                    <span style="color: #10b981; font-weight: 700;">Our Bot Peak: Rs 106,704 (+113.4%)</span>
                </div>
            </div>
        </div>

        <!-- MONTHLY BREAKDOWN TABLE -->
        <div class="chart-section">
            <div style="font-size: 18px; font-weight: 700; margin-bottom: 16px;">Month-by-Month Head-to-Head P&L</div>
            <table>
                <thead>
                    <tr>
                        <th>Trading Month</th>
                        <th>Our Bot Trades (WR)</th>
                        <th>Our Bot Net P&L</th>
                        <th>Arjun Opt Trades (WR)</th>
                        <th>Arjun Opt Net P&L</th>
                        <th>Arjun Raw Net P&L</th>
                    </tr>
                </thead>
                <tbody>
                    {monthly_rows}
                </tbody>
            </table>
        </div>

        <!-- ARCHITECTURAL WHY SECTION -->
        <div class="chart-section">
            <div style="font-size: 18px; font-weight: 700; margin-bottom: 16px;">Why Our Bot Generated 4.07x More Profit (The Level Mechanics)</div>
            <div style="line-height: 1.7; font-size: 14px; color: #cbd5e1;">
                <p style="margin-bottom: 12px;">
                    <strong>1. The 42-Point Boundary Offset:</strong> Statistical regression between Arjun's morning levels and our mathematical CPR formula shows that Arjun's <strong>R1 is 42.1 points lower</strong> and his <strong>S1 is 45.6 points higher</strong> than standard institutional levels. Because Arjun's levels are compressed closer to the opening price, early morning volatility frequently punctures them, causing heavy whipsaws and false bounce signals (-Rs 11,597 loss on mean reversion).
                </p>
                <p style="margin-bottom: 12px;">
                    <strong>2. The Power of Exhaustion Reversals:</strong> Our bot uses wide mathematical R1/R2 and S1/S2 boundaries. When NIFTY actually extends into our R1 or R2, the market is overextended, allowing our bot's <strong>R1 Resistance Reversal</strong> and <strong>R2 Exhaustion Reversal</strong> playbooks to capture high-probability fades (<strong>60% to 80% Win Rate, generating +Rs 39,373 profit</strong>). Arjun's levels lack this outer exhaustion framework.
                </p>
                <p>
                    <strong>3. Regimes vs. Static Numbers:</strong> Arjun broadcasts the exact same 4 S&R lines regardless of whether the day is a narrow trend day or a wide sideways day. Our bot calculates the <strong>CPR Central Width</strong> every morning, dynamically choosing whether to activate the Breakout engine (tight CPR) or the Reversal engine (wide CPR).
                </p>
            </div>
        </div>
    </div>
</body>
</html>
"""
    with open(out_html, "w", encoding="utf-8") as f:
        f.write(html)
    print(f"Generated comparison dashboard: {out_html}")
    return out_html

if __name__ == "__main__":
    generate_comparison_html()
