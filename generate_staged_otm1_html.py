import os
import sys
import json
import pandas as pd
import numpy as np

base_dir = r"c:\Users\Admin\Desktop\nifty backttteest"

# Read generated trade logs
df_otm1 = pd.read_csv(os.path.join(base_dir, "trades_3year_otm1_staged.csv"))
df_atm = pd.read_csv(os.path.join(base_dir, "trades_3year_atm_staged.csv"))
df_base = pd.read_csv(os.path.join(base_dir, "trades_3year_50_200_trailed.csv"))

# Prepare equity curves for Chart.js
df_otm1['cum_pnl'] = df_otm1['net_pnl'].cumsum()
df_atm['cum_pnl'] = df_atm['net_pnl'].cumsum()
df_base['cum_pnl'] = df_base['net_pnl'].cumsum()

# Sample 50 points evenly for smooth charting
step_otm1 = max(1, len(df_otm1) // 50)
curve_otm1 = df_otm1.iloc[::step_otm1][['date', 'cum_pnl']].to_dict(orient='records')
if df_otm1.iloc[-1]['date'] != curve_otm1[-1]['date']:
    curve_otm1.append({'date': df_otm1.iloc[-1]['date'], 'cum_pnl': df_otm1.iloc[-1]['cum_pnl']})

labels = [x['date'] for x in curve_otm1]
data_otm1 = [round(x['cum_pnl'], 2) for x in curve_otm1]

# Align ATM and Baseline to same dates
cum_atm_map = dict(zip(df_atm['date'], df_atm['cum_pnl']))
cum_base_map = dict(zip(df_base['date'], df_base['cum_pnl']))

data_atm = []
last_atm = 0
for d in labels:
    if d in cum_atm_map: last_atm = cum_atm_map[d]
    data_atm.append(round(last_atm, 2))

data_base = []
last_base = 0
for d in labels:
    if d in cum_base_map: last_base = cum_base_map[d]
    data_base.append(round(last_base, 2))

# October 2026 Table rows
oct_df = df_otm1[df_otm1['month'] == '2026-10'].copy()
oct_rows = ""
for _, r in oct_df.iterrows():
    is_win = r['is_win']
    badge = '<span class="badge badge-win">WIN</span>' if is_win else '<span class="badge badge-loss">LOSS</span>'
    pnl_class = "text-green" if r['net_pnl'] > 0 else "text-red"
    oct_rows += f"""
    <tr>
        <td><b>{r['date']}</b></td>
        <td>{r['entry_time']} &rarr; {r['exit_time']}</td>
        <td><span class="badge badge-inst">{r['instrument']}</span></td>
        <td>{r['playbook']}</td>
        <td>Rs {r['entry_prem']:.2f}</td>
        <td>Rs {r['exit_prem_1']:.2f}</td>
        <td>Rs {r['exit_prem_2']:.2f}</td>
        <td>{r['pts']:+.2f} pts</td>
        <td class="{pnl_class}"><b>Rs {r['net_pnl']:+,.2f}</b></td>
        <td><span class="badge badge-subtle">{r['result']}</span></td>
    </tr>
    """

html_content = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>NIFTY Options Backtest: OTM-1 & Staged Scale-Outs (3-Year Audit)</title>
    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700;800&family=JetBrains+Mono:wght@400;600&display=swap" rel="stylesheet">
    <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
    <style>
        :root {{
            --bg-primary: #0a0e17;
            --bg-secondary: #111827;
            --bg-card: #1a2234;
            --bg-card-hover: #222d44;
            --border: #26334d;
            --text-main: #f3f4f6;
            --text-muted: #9ca3af;
            --green: #10b981;
            --green-glow: rgba(16, 185, 129, 0.2);
            --red: #ef4444;
            --red-glow: rgba(239, 68, 68, 0.2);
            --blue: #3b82f6;
            --purple: #8b5cf6;
            --amber: #f59e0b;
            --cyan: #06b6d4;
        }}
        * {{ margin: 0; padding: 0; box-sizing: border-box; }}
        body {{
            background: var(--bg-primary);
            color: var(--text-main);
            font-family: 'Inter', -apple-system, sans-serif;
            padding: 30px 20px;
            line-height: 1.6;
        }}
        .container {{ max-width: 1380px; margin: 0 auto; }}
        .header {{
            background: linear-gradient(135deg, rgba(59, 130, 246, 0.15), rgba(139, 92, 246, 0.15));
            border: 1px solid var(--border);
            border-radius: 16px;
            padding: 32px;
            margin-bottom: 28px;
            position: relative;
            overflow: hidden;
        }}
        .header h1 {{
            font-size: 28px;
            font-weight: 800;
            background: linear-gradient(135deg, #60a5fa, #c084fc);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
            margin-bottom: 8px;
        }}
        .header p {{ color: var(--text-muted); font-size: 15px; }}
        .pill-row {{ display: flex; gap: 12px; margin-top: 18px; flex-wrap: wrap; }}
        .pill {{
            background: rgba(255, 255, 255, 0.05);
            border: 1px solid var(--border);
            padding: 6px 14px;
            border-radius: 20px;
            font-size: 13px;
            font-weight: 500;
            color: var(--text-main);
        }}
        .pill-gold {{ border-color: var(--amber); color: var(--amber); background: rgba(245, 158, 11, 0.1); }}
        .pill-green {{ border-color: var(--green); color: var(--green); background: var(--green-glow); }}

        .grid-3 {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(380px, 1fr)); gap: 20px; margin-bottom: 28px; }}
        .card {{
            background: var(--bg-card);
            border: 1px solid var(--border);
            border-radius: 14px;
            padding: 24px;
            transition: all 0.2s ease;
        }}
        .card:hover {{ border-color: var(--blue); transform: translateY(-2px); }}
        .card-champion {{
            border-color: var(--green);
            box-shadow: 0 0 25px var(--green-glow);
            position: relative;
        }}
        .champ-badge {{
            position: absolute;
            top: -12px;
            right: 20px;
            background: var(--green);
            color: #000;
            font-size: 11px;
            font-weight: 800;
            padding: 4px 12px;
            border-radius: 12px;
            letter-spacing: 0.5px;
            text-transform: uppercase;
        }}
        .card h3 {{ font-size: 18px; margin-bottom: 16px; font-weight: 700; color: #fff; }}
        .metric-row {{
            display: flex;
            justify-content: space-between;
            align-items: center;
            padding: 10px 0;
            border-bottom: 1px solid rgba(255, 255, 255, 0.05);
            font-size: 14px;
        }}
        .metric-row:last-child {{ border-bottom: none; }}
        .metric-label {{ color: var(--text-muted); }}
        .metric-val {{ font-family: 'JetBrains Mono', monospace; font-weight: 600; }}
        .text-green {{ color: var(--green); }}
        .text-red {{ color: var(--red); }}
        .text-cyan {{ color: var(--cyan); }}
        .text-amber {{ color: var(--amber); }}

        .chart-box {{
            background: var(--bg-card);
            border: 1px solid var(--border);
            border-radius: 14px;
            padding: 24px;
            margin-bottom: 28px;
        }}
        .chart-box h3 {{ font-size: 18px; margin-bottom: 16px; font-weight: 700; }}

        .table-box {{
            background: var(--bg-card);
            border: 1px solid var(--border);
            border-radius: 14px;
            padding: 24px;
            margin-bottom: 28px;
            overflow-x: auto;
        }}
        .table-box h3 {{ font-size: 18px; margin-bottom: 16px; font-weight: 700; }}
        table {{
            width: 100%;
            border-collapse: collapse;
            font-size: 13.5px;
        }}
        th {{
            background: var(--bg-secondary);
            color: var(--text-muted);
            text-align: left;
            padding: 12px 14px;
            font-weight: 600;
            border-bottom: 1px solid var(--border);
        }}
        td {{
            padding: 12px 14px;
            border-bottom: 1px solid rgba(255, 255, 255, 0.04);
            font-family: 'JetBrains Mono', monospace;
        }}
        tr:hover td {{ background: var(--bg-card-hover); }}
        .badge {{
            padding: 3px 8px;
            border-radius: 6px;
            font-size: 11px;
            font-weight: 700;
            display: inline-block;
        }}
        .badge-win {{ background: var(--green-glow); color: var(--green); border: 1px solid var(--green); }}
        .badge-loss {{ background: var(--red-glow); color: var(--red); border: 1px solid var(--red); }}
        .badge-inst {{ background: rgba(59, 130, 246, 0.15); color: #93c5fd; border: 1px solid var(--blue); }}
        .badge-subtle {{ background: rgba(255, 255, 255, 0.05); color: #d1d5db; }}

        .summary-banner {{
            background: linear-gradient(135deg, rgba(16, 185, 129, 0.1), rgba(6, 182, 212, 0.1));
            border: 1px solid rgba(16, 185, 129, 0.3);
            border-radius: 12px;
            padding: 20px;
            margin-bottom: 28px;
        }}
        .summary-banner h4 {{ color: var(--green); margin-bottom: 6px; font-size: 16px; font-weight: 700; }}
        .summary-banner p {{ color: #d1d5db; font-size: 14px; }}
    </style>
</head>
<body>
<div class="container">
    <div class="header">
        <h1>Institutional Options Backtest: OTM-1 & Staged Scale-Outs</h1>
        <p>Comprehensive 3-Year & October 2026 MTD Backtest Audit (31-Oct-2023 to 21-Oct-2026 | 733 Sessions)</p>
        <div class="pill-row">
            <div class="pill pill-gold">Fixed 1 Lot (65 Qty)</div>
            <div class="pill">Strike: OTM-1 (+50 CE / -50 PE)</div>
            <div class="pill pill-green">Staged Exit: 50% @ +100 pts (1:2 RR) | 50% Runner @ +200 pts (1:4 RR)</div>
            <div class="pill">Breakeven Lock: Entry + 4 pts buffer</div>
            <div class="pill">Realistic Costs (STT, GST, ₹40 Bkrg, 0.5% Slippage)</div>
        </div>
    </div>

    <div class="summary-banner">
        <h4>Key Takeaways & Core Breakthroughs</h4>
        <p>
            <b>1. Profit Factor Surges to 2.52:</b> OTM-1 Staged Scale-out delivers the cleanest risk-adjusted metrics across 3 years. <br>
            <b>2. Max Drawdown Slashed by 28%:</b> Drawdown drops from <b>Rs 19,504.79</b> down to <b>Rs 14,058.29</b> because OTM-1 options carry lower entry premium and bleed less on choppy reversal attempts.<br>
            <b>3. October 2026 MTD Surges 4.4x:</b> Month-to-date October net profit jumped to <b>+Rs 14,475.19</b> compared to the ATM Baseline Trailed setup of <b>+Rs 3,245.70</b>, turning Monday's false breakdown into a green session (+Rs 2,809 net).
        </p>
    </div>

    <div class="grid-3">
        <!-- OTM-1 Staged Card -->
        <div class="card card-champion">
            <div class="champ-badge">MAX RISK-ADJUSTED</div>
            <h3>OTM-1 Staged Scale-Out</h3>
            <div style="font-size: 13px; color: var(--text-muted); margin-bottom: 12px;">50% @ +100 pts | SL to BE+4 | 50% @ +200 pts</div>
            <div class="metric-row"><span class="metric-label">3-Year Net P&L</span><span class="metric-val text-green">+Rs 387,888.26</span></div>
            <div class="metric-row"><span class="metric-label">Return on Capital (ROI)</span><span class="metric-val text-green">+775.8%</span></div>
            <div class="metric-row"><span class="metric-label">Profit Factor (PF)</span><span class="metric-val text-cyan">2.52</span></div>
            <div class="metric-row"><span class="metric-label">Max Drawdown</span><span class="metric-val text-red">Rs 14,058.29 (-28.1%)</span></div>
            <div class="metric-row"><span class="metric-label">Calmar Ratio</span><span class="metric-val text-cyan">27.59x</span></div>
            <div class="metric-row"><span class="metric-label">Win Rate</span><span class="metric-val">54.3% (204W / 172L)</span></div>
            <div class="metric-row"><span class="metric-label">Avg Loss per Losing Trade</span><span class="metric-val text-red">-Rs 1,479.77 (Lowest)</span></div>
            <div class="metric-row" style="background: rgba(16, 185, 129, 0.08); padding: 10px 8px; border-radius: 8px;">
                <span class="metric-label" style="color: #fff; font-weight: 600;">October 2026 MTD P&L</span>
                <span class="metric-val text-green" style="font-size: 16px;">+Rs 14,475.19</span>
            </div>
        </div>

        <!-- ATM Staged Card -->
        <div class="card">
            <h3>ATM Staged Scale-Out</h3>
            <div style="font-size: 13px; color: var(--text-muted); margin-bottom: 12px;">50% @ +100 pts | SL to BE+4 | 50% @ +200 pts (ATM Strike)</div>
            <div class="metric-row"><span class="metric-label">3-Year Net P&L</span><span class="metric-val text-green">+Rs 416,273.42</span></div>
            <div class="metric-row"><span class="metric-label">Return on Capital (ROI)</span><span class="metric-val text-green">+832.5%</span></div>
            <div class="metric-row"><span class="metric-label">Profit Factor (PF)</span><span class="metric-val">2.29</span></div>
            <div class="metric-row"><span class="metric-label">Max Drawdown</span><span class="metric-val text-red">Rs 16,147.26</span></div>
            <div class="metric-row"><span class="metric-label">Calmar Ratio</span><span class="metric-val">25.78x</span></div>
            <div class="metric-row"><span class="metric-label">Win Rate</span><span class="metric-val">53.8% (204W / 175L)</span></div>
            <div class="metric-row"><span class="metric-label">Avg Loss per Losing Trade</span><span class="metric-val text-red">-Rs 1,843.30</span></div>
            <div class="metric-row" style="background: rgba(255, 255, 255, 0.03); padding: 10px 8px; border-radius: 8px;">
                <span class="metric-label" style="color: #fff; font-weight: 600;">October 2026 MTD P&L</span>
                <span class="metric-val text-green" style="font-size: 16px;">+Rs 11,549.61</span>
            </div>
        </div>

        <!-- ATM Baseline Trailed Card -->
        <div class="card">
            <h3>ATM Baseline (Trailed 50:200)</h3>
            <div style="font-size: 13px; color: var(--text-muted); margin-bottom: 12px;">SL: 50 | TP: 200 | Dynamic 15 pt Trail (Live Bot Default)</div>
            <div class="metric-row"><span class="metric-label">3-Year Net P&L</span><span class="metric-val text-green">+Rs 463,526.83</span></div>
            <div class="metric-row"><span class="metric-label">Return on Capital (ROI)</span><span class="metric-val text-green">+927.1%</span></div>
            <div class="metric-row"><span class="metric-label">Profit Factor (PF)</span><span class="metric-val">2.44</span></div>
            <div class="metric-row"><span class="metric-label">Max Drawdown</span><span class="metric-val text-red">Rs 19,504.79 (Highest)</span></div>
            <div class="metric-row"><span class="metric-label">Calmar Ratio</span><span class="metric-val">23.76x</span></div>
            <div class="metric-row"><span class="metric-label">Win Rate</span><span class="metric-val">55.8% (216W / 171L)</span></div>
            <div class="metric-row"><span class="metric-label">Avg Loss per Losing Trade</span><span class="metric-val text-red">-Rs 1,878.87</span></div>
            <div class="metric-row" style="background: rgba(255, 255, 255, 0.03); padding: 10px 8px; border-radius: 8px;">
                <span class="metric-label" style="color: #fff; font-weight: 600;">October 2026 MTD P&L</span>
                <span class="metric-val text-amber" style="font-size: 16px;">+Rs 3,245.70</span>
            </div>
        </div>
    </div>

    <!-- Chart -->
    <div class="chart-box">
        <h3>3-Year Cumulative Equity Curve (31-Oct-2023 to 21-Oct-2026)</h3>
        <canvas id="equityChart" height="95"></canvas>
    </div>

    <!-- October Trades Ledger -->
    <div class="table-box">
        <h3>October 2026 Month-to-Date (MTD) Trade Ledger (OTM-1 Staged Scale-Out)</h3>
        <table>
            <thead>
                <tr>
                    <th>Date</th>
                    <th>Time</th>
                    <th>Contract</th>
                    <th>Playbook</th>
                    <th>Entry</th>
                    <th>Exit 1 (50%)</th>
                    <th>Exit 2 (50%)</th>
                    <th>Avg Pts</th>
                    <th>Net P&L</th>
                    <th>Exit Outcome</th>
                </tr>
            </thead>
            <tbody>
                {oct_rows}
            </tbody>
        </table>
    </div>
</div>

<script>
    const ctx = document.getElementById('equityChart').getContext('2d');
    const chart = new Chart(ctx, {{
        type: 'line',
        data: {{
            labels: {json.dumps(labels)},
            datasets: [
                {{
                    label: 'OTM-1 Staged Scale-Out (50% @ 100, 50% @ 200) - Min Drawdown',
                    data: {json.dumps(data_otm1)},
                    borderColor: '#10b981',
                    backgroundColor: 'rgba(16, 185, 129, 0.05)',
                    borderWidth: 2.5,
                    pointRadius: 0,
                    tension: 0.1
                }},
                {{
                    label: 'ATM Baseline (Trailed 50:200)',
                    data: {json.dumps(data_base)},
                    borderColor: '#3b82f6',
                    borderWidth: 1.8,
                    borderDash: [4, 4],
                    pointRadius: 0,
                    tension: 0.1
                }},
                {{
                    label: 'ATM Staged Scale-Out',
                    data: {json.dumps(data_atm)},
                    borderColor: '#a855f7',
                    borderWidth: 1.8,
                    pointRadius: 0,
                    tension: 0.1
                }}
            ]
        }},
        options: {{
            responsive: true,
            plugins: {{
                legend: {{
                    labels: {{ color: '#d1d5db', font: {{ family: 'Inter', size: 12 }} }}
                }},
                tooltip: {{
                    mode: 'index',
                    intersect: false,
                    callbacks: {{
                        label: function(c) {{ return c.dataset.label + ': Rs ' + c.raw.toLocaleString(); }}
                    }}
                }}
            }},
            scales: {{
                x: {{
                    grid: {{ color: 'rgba(255, 255, 255, 0.05)' }},
                    ticks: {{ color: '#9ca3af', maxTicksLimit: 12 }}
                }},
                y: {{
                    grid: {{ color: 'rgba(255, 255, 255, 0.05)' }},
                    ticks: {{
                        color: '#9ca3af',
                        callback: function(v) {{ return 'Rs ' + (v/1000).toFixed(0) + 'k'; }}
                    }}
                }}
            }}
        }}
    }});
</script>
</body>
</html>
"""

report_path = os.path.join(base_dir, "report_staged_otm1.html")
with open(report_path, "w", encoding="utf-8") as f:
    f.write(html_content)

print(f"Report generated successfully: {report_path}")
