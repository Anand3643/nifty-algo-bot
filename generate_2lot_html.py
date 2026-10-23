import os
import sys
import json
import pandas as pd
import numpy as np

base_dir = r"c:\Users\Admin\Desktop\nifty backttteest"

df_2lot_otm1 = pd.read_csv(os.path.join(base_dir, "trades_3year_2lot_staged_otm1.csv"))
df_2lot_atm = pd.read_csv(os.path.join(base_dir, "trades_3year_2lot_staged_atm.csv"))
df_1lot_base = pd.read_csv(os.path.join(base_dir, "trades_3year_50_200_trailed.csv"))

df_2lot_otm1['cum_pnl'] = df_2lot_otm1['net_pnl'].cumsum()
df_2lot_atm['cum_pnl'] = df_2lot_atm['net_pnl'].cumsum()
df_1lot_base['cum_pnl'] = df_1lot_base['net_pnl'].cumsum()

# Sample for Chart.js
step = max(1, len(df_2lot_otm1) // 50)
curve_sample = df_2lot_otm1.iloc[::step][['date', 'cum_pnl']].to_dict(orient='records')
if df_2lot_otm1.iloc[-1]['date'] != curve_sample[-1]['date']:
    curve_sample.append({'date': df_2lot_otm1.iloc[-1]['date'], 'cum_pnl': df_2lot_otm1.iloc[-1]['cum_pnl']})

labels = [x['date'] for x in curve_sample]
data_2lot_otm1 = [round(x['cum_pnl'], 2) for x in curve_sample]

atm_map = dict(zip(df_2lot_atm['date'], df_2lot_atm['cum_pnl']))
base_map = dict(zip(df_1lot_base['date'], df_1lot_base['cum_pnl']))

data_2lot_atm = []
last_atm = 0
for d in labels:
    if d in atm_map: last_atm = atm_map[d]
    data_2lot_atm.append(round(last_atm, 2))

data_1lot_base = []
last_base = 0
for d in labels:
    if d in base_map: last_base = base_map[d]
    data_1lot_base.append(round(last_base, 2))

# October trades
oct_df = df_2lot_otm1[df_2lot_otm1['month'] == '2026-10'].copy()
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
        <td>Rs {r['exit_prem_1']:.2f} ({r['pts_lot1']:+.1f} pts)</td>
        <td>Rs {r['exit_prem_2']:.2f} ({r['pts_lot2']:+.1f} pts)</td>
        <td class="{pnl_class}"><b>Rs {r['net_pnl']:+,.2f}</b></td>
        <td><span class="badge badge-subtle">{r['result']}</span></td>
    </tr>
    """

html = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>The 2-Lot Staged Execution Engine: Backtest Audit</title>
    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700;800&family=JetBrains+Mono:wght@400;600&display=swap" rel="stylesheet">
    <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
    <style>
        :root {{
            --bg-primary: #0a0e17;
            --bg-secondary: #111827;
            --bg-card: #1a2234;
            --border: #26334d;
            --text-main: #f3f4f6;
            --text-muted: #9ca3af;
            --green: #10b981;
            --green-glow: rgba(16, 185, 129, 0.2);
            --red: #ef4444;
            --red-glow: rgba(239, 68, 68, 0.2);
            --blue: #3b82f6;
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
        .container {{ max-width: 1400px; margin: 0 auto; }}
        .header {{
            background: linear-gradient(135deg, rgba(16, 185, 129, 0.15), rgba(59, 130, 246, 0.15));
            border: 1px solid var(--border);
            border-radius: 16px;
            padding: 32px;
            margin-bottom: 28px;
        }}
        .header h1 {{
            font-size: 28px;
            font-weight: 800;
            background: linear-gradient(135deg, #34d399, #60a5fa);
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
        }}
        .pill-green {{ border-color: var(--green); color: var(--green); background: var(--green-glow); }}
        .pill-gold {{ border-color: var(--amber); color: var(--amber); background: rgba(245, 158, 11, 0.1); }}

        .grid-3 {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(380px, 1fr)); gap: 20px; margin-bottom: 28px; }}
        .card {{
            background: var(--bg-card);
            border: 1px solid var(--border);
            border-radius: 14px;
            padding: 24px;
            position: relative;
        }}
        .card-champion {{
            border-color: var(--green);
            box-shadow: 0 0 25px var(--green-glow);
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
            text-transform: uppercase;
        }}
        .card h3 {{ font-size: 18px; margin-bottom: 16px; font-weight: 700; }}
        .metric-row {{
            display: flex;
            justify-content: space-between;
            align-items: center;
            padding: 9px 0;
            border-bottom: 1px solid rgba(255, 255, 255, 0.05);
            font-size: 14px;
        }}
        .metric-row:last-child {{ border-bottom: none; }}
        .metric-label {{ color: var(--text-muted); }}
        .metric-val {{ font-family: 'JetBrains Mono', monospace; font-weight: 600; }}
        .text-green {{ color: var(--green); }}
        .text-red {{ color: var(--red); }}
        .text-cyan {{ color: var(--cyan); }}

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
    </style>
</head>
<body>
<div class="container">
    <div class="header">
        <h1>The 2-Lot Staged Execution Engine</h1>
        <p>Comprehensive 3-Year & October 2026 MTD Backtest Audit (31-Oct-2023 to 21-Oct-2026 | 733 Sessions)</p>
        <div class="pill-row">
            <div class="pill pill-gold">2 Lots (130 Qty) Clean Execution</div>
            <div class="pill pill-green">Target 1 (+100 pts / 1:2 RR): Book 1 Lot (+Rs 6,500 Banked)</div>
            <div class="pill">SL on Lot 2: Risk-Free Breakeven (Entry + Rs 4.00)</div>
            <div class="pill pill-green">Target 2 (+200 pts / 1:4 RR): Runner Lot 2 (+Rs 13,000 Runner)</div>
            <div class="pill">OTM-1 Strikes (+50 CE / -50 PE)</div>
        </div>
    </div>

    <div class="grid-3">
        <!-- 2-Lot OTM-1 Staged Card -->
        <div class="card card-champion">
            <div class="champ-badge">MAX PROFIT FACTOR</div>
            <h3>2-Lot OTM-1 Staged Engine</h3>
            <div style="font-size: 13px; color: var(--text-muted); margin-bottom: 12px;">OTM-1 Strikes | T1: +100 | BE Lock: +4 | T2: +200</div>
            <div class="metric-row"><span class="metric-label">3-Year Net P&L</span><span class="metric-val text-green">+Rs 793,523.92</span></div>
            <div class="metric-row"><span class="metric-label">Return on Capital (ROI)</span><span class="metric-val text-green">+1,587.0%</span></div>
            <div class="metric-row"><span class="metric-label">Profit Factor (PF)</span><span class="metric-val text-cyan">2.58 (Highest)</span></div>
            <div class="metric-row"><span class="metric-label">Max Peak Drawdown</span><span class="metric-val text-red">Rs 27,691.79</span></div>
            <div class="metric-row"><span class="metric-label">Calmar Ratio</span><span class="metric-val text-cyan">28.66x (Top Tier)</span></div>
            <div class="metric-row"><span class="metric-label">Win Rate</span><span class="metric-val">54.8% (206W / 170L)</span></div>
            <div class="metric-row"><span class="metric-label">Avg Win / Avg Loss</span><span class="metric-val">Rs 6,283.76 / -Rs 2,946.65</span></div>
            <div class="metric-row" style="background: rgba(16, 185, 129, 0.08); padding: 10px 8px; border-radius: 8px;">
                <span class="metric-label" style="color: #fff; font-weight: 600;">October 2026 MTD P&L</span>
                <span class="metric-val text-green" style="font-size: 16px;">+Rs 29,375.21</span>
            </div>
        </div>

        <!-- 2-Lot ATM Staged Card -->
        <div class="card">
            <h3>2-Lot ATM Staged Engine</h3>
            <div style="font-size: 13px; color: var(--text-muted); margin-bottom: 12px;">ATM Strikes | T1: +100 | BE Lock: +4 | T2: +200</div>
            <div class="metric-row"><span class="metric-label">3-Year Net P&L</span><span class="metric-val text-green">+Rs 850,435.49</span></div>
            <div class="metric-row"><span class="metric-label">Return on Capital (ROI)</span><span class="metric-val text-green">+1,700.9%</span></div>
            <div class="metric-row"><span class="metric-label">Profit Factor (PF)</span><span class="metric-val">2.34</span></div>
            <div class="metric-row"><span class="metric-label">Max Peak Drawdown</span><span class="metric-val text-red">Rs 31,869.70</span></div>
            <div class="metric-row"><span class="metric-label">Calmar Ratio</span><span class="metric-val">26.68x</span></div>
            <div class="metric-row"><span class="metric-label">Win Rate</span><span class="metric-val">54.4% (206W / 173L)</span></div>
            <div class="metric-row"><span class="metric-label">Avg Win / Avg Loss</span><span class="metric-val">Rs 7,220.08 / -Rs 3,681.51</span></div>
            <div class="metric-row" style="background: rgba(255, 255, 255, 0.03); padding: 10px 8px; border-radius: 8px;">
                <span class="metric-label" style="color: #fff; font-weight: 600;">October 2026 MTD P&L</span>
                <span class="metric-val text-green" style="font-size: 16px;">+Rs 23,349.22</span>
            </div>
        </div>

        <!-- 1-Lot Baseline Card -->
        <div class="card">
            <h3>1-Lot Baseline (Trailed 50:200)</h3>
            <div style="font-size: 13px; color: var(--text-muted); margin-bottom: 12px;">1 Lot (65 Qty) | SL: 50 | TP: 200 | Dynamic 15 pt Trail</div>
            <div class="metric-row"><span class="metric-label">3-Year Net P&L</span><span class="metric-val text-green">+Rs 463,526.83</span></div>
            <div class="metric-row"><span class="metric-label">Return on Capital (ROI)</span><span class="metric-val text-green">+927.1%</span></div>
            <div class="metric-row"><span class="metric-label">Profit Factor (PF)</span><span class="metric-val">2.44</span></div>
            <div class="metric-row"><span class="metric-label">Max Peak Drawdown</span><span class="metric-val text-red">Rs 19,504.79</span></div>
            <div class="metric-row"><span class="metric-label">Calmar Ratio</span><span class="metric-val">23.76x</span></div>
            <div class="metric-row"><span class="metric-label">Win Rate</span><span class="metric-val">55.8% (216W / 171L)</span></div>
            <div class="metric-row"><span class="metric-label">Avg Win / Avg Loss</span><span class="metric-val">Rs 3,633.40 / -Rs 1,878.87</span></div>
            <div class="metric-row" style="background: rgba(255, 255, 255, 0.03); padding: 10px 8px; border-radius: 8px;">
                <span class="metric-label" style="color: #fff; font-weight: 600;">October 2026 MTD P&L</span>
                <span class="metric-val text-amber" style="font-size: 16px;">+Rs 3,245.70</span>
            </div>
        </div>
    </div>

    <!-- Chart -->
    <div class="chart-box">
        <h3>3-Year Cumulative Equity Curve Comparison</h3>
        <canvas id="equityChart" height="90"></canvas>
    </div>

    <!-- October Trades -->
    <div class="table-box">
        <h3>October 2026 Month-to-Date (MTD) Trade Ledger: 2-Lot OTM-1 Staged Engine</h3>
        <table>
            <thead>
                <tr>
                    <th>Date</th>
                    <th>Time</th>
                    <th>Contract</th>
                    <th>Playbook</th>
                    <th>Entry</th>
                    <th>Lot 1 (+100 Target)</th>
                    <th>Lot 2 (Runner Target)</th>
                    <th>Net P&L</th>
                    <th>Outcome</th>
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
    new Chart(ctx, {{
        type: 'line',
        data: {{
            labels: {json.dumps(labels)},
            datasets: [
                {{
                    label: '2-Lot OTM-1 Staged Scale-Out (Champion: PF 2.58 | Net +Rs 793.5k)',
                    data: {json.dumps(data_2lot_otm1)},
                    borderColor: '#10b981',
                    backgroundColor: 'rgba(16, 185, 129, 0.05)',
                    borderWidth: 2.8,
                    pointRadius: 0,
                    tension: 0.1
                }},
                {{
                    label: '2-Lot ATM Staged Scale-Out (Net +Rs 850.4k)',
                    data: {json.dumps(data_2lot_atm)},
                    borderColor: '#a855f7',
                    borderWidth: 2,
                    pointRadius: 0,
                    tension: 0.1
                }},
                {{
                    label: '1-Lot Baseline Trailed (Net +Rs 463.5k)',
                    data: {json.dumps(data_1lot_base)},
                    borderColor: '#3b82f6',
                    borderWidth: 1.5,
                    borderDash: [4, 4],
                    pointRadius: 0,
                    tension: 0.1
                }}
            ]
        }},
        options: {{
            responsive: true,
            plugins: {{
                legend: {{ labels: {{ color: '#d1d5db', font: {{ family: 'Inter', size: 12 }} }} }},
                tooltip: {{ mode: 'index', intersect: false }}
            }},
            scales: {{
                x: {{ grid: {{ color: 'rgba(255, 255, 255, 0.05)' }}, ticks: {{ color: '#9ca3af', maxTicksLimit: 12 }} }},
                y: {{
                    grid: {{ color: 'rgba(255, 255, 255, 0.05)' }},
                    ticks: {{ color: '#9ca3af', callback: v => 'Rs ' + (v/1000).toFixed(0) + 'k' }}
                }}
            }}
        }}
    }});
</script>
</body>
</html>
"""

report_file = os.path.join(base_dir, "report_2lot_staged_engine.html")
with open(report_file, "w", encoding="utf-8") as f:
    f.write(html)
print(f"Generated: {report_file}")
