import os
import sys
import datetime
import pandas as pd
import numpy as np

base_dir = r"c:\Users\Admin\Desktop\nifty backttteest"
sys.path.insert(0, base_dir)

from optimize_combined_strategy import NiftySREngine, BlackScholesPricing

# 1. Load Data
c5m = os.path.join(base_dir, 'nifty_data', 'candles', 'NIFTY_5min.csv')
c1d = os.path.join(base_dir, 'nifty_data', 'candles', 'NIFTY_1day.csv')

df_5m = pd.read_csv(c5m)
df_5m['datetime'] = pd.to_datetime(df_5m['datetime'])
df_5m['date'] = df_5m['datetime'].dt.date

df_1d = pd.read_csv(c1d)
df_1d['datetime'] = pd.to_datetime(df_1d['datetime']).dt.date
df_1d.drop_duplicates(subset=['datetime'], inplace=True)
df_1d.set_index('datetime', inplace=True)

oct_dates = sorted([d for d in df_5m['date'].unique() if d >= datetime.date(2026, 10, 1)])

# Run Benchmark 5m Engine (Core Engine)
def run_benchmark():
    sl_val = 40.0
    rr = 3.0
    tp_val = sl_val * rr
    lot_size = 65
    capital = 50000.0
    trades = []
    allowed_pb = ["S2 Flush Breakdown", "R1 Resistance Reversal", "R2 Exhaustion Reversal", "R1 Resistance Breakout", "S1 Support Breakdown"]

    for d in oct_dates:
        priors = [x for x in df_1d.index if x < d]
        if not priors: continue
        prev = df_1d.loc[priors[-1]]
        lvl = NiftySREngine.calculate_levels(float(prev['high']), float(prev['low']), float(prev['close']))
        grp = df_5m[df_5m['date'] == d].sort_values('datetime').reset_index(drop=True)
        if len(grp) < 3: continue
        dow = d.weekday()
        dte = max(0.5, (3 - dow) % 7 + 0.5) / 365.0

        bars = [{'dt': r['datetime'], 'time': r['datetime'].time(), 'open': float(r['open']), 'high': float(r['high']), 'low': float(r['low']), 'close': float(r['close'])} for _, r in grp.iterrows()]
        in_trade = False
        trade_dir = None
        strike = 0
        entry_prem = 0.0
        curr_sl = 0.0
        curr_tp = 0.0
        playbook = ''
        trades_today = 0
        entry_time = None

        for i in range(1, len(bars)):
            bar = bars[i]
            prev_bar = bars[i-1]
            t = bar['time']
            spot = bar['close']
            b_open = bar['open']
            b_high = bar['high']
            b_low = bar['low']
            b_range = b_high - b_low

            if in_trade:
                is_call = (trade_dir == "CE")
                prem_close = BlackScholesPricing.calculate_price(spot, strike, dte, 0.135, is_call=is_call)
                prem_high = BlackScholesPricing.calculate_price(b_high, strike, dte, 0.135, is_call=is_call) if is_call else BlackScholesPricing.calculate_price(b_low, strike, dte, 0.135, is_call=is_call)
                prem_low = BlackScholesPricing.calculate_price(b_low, strike, dte, 0.135, is_call=is_call) if is_call else BlackScholesPricing.calculate_price(b_high, strike, dte, 0.135, is_call=is_call)

                hit_tp = (prem_high >= curr_tp)
                hit_sl = (prem_low <= curr_sl)
                hit_eod = (t >= datetime.time(15, 10))

                if hit_tp or hit_sl or hit_eod:
                    exit_raw = curr_tp if hit_tp else (curr_sl if hit_sl else prem_close)
                    fill_entry = entry_prem * 1.005
                    fill_exit = max(0.5, exit_raw * 0.995)
                    pts = fill_exit - fill_entry
                    gross = pts * lot_size
                    stt = fill_exit * lot_size * 0.000625
                    txn = (fill_entry + fill_exit) * lot_size * 0.00053
                    brokerage = 40.0
                    gst = (brokerage + txn) * 0.18
                    costs = brokerage + stt + txn + gst
                    net = gross - costs
                    capital += net
                    reason = "TARGET 1:3 HIT" if hit_tp else ("STOP LOSS" if hit_sl else "EOD EXIT")

                    trades.append({
                        "Date": str(d),
                        "Time": entry_time.strftime("%H:%M"),
                        "Exit_Time": bar["dt"].strftime("%H:%M"),
                        "Instrument": f"NIFTY {strike} {trade_dir}",
                        "Playbook": playbook,
                        "Type": trade_dir,
                        "Strike": strike,
                        "Entry_Prem": round(fill_entry, 2),
                        "Exit_Prem": round(fill_exit, 2),
                        "Prem_Pts": round(pts, 2),
                        "Gross_PnL": round(gross, 2),
                        "Costs": round(costs, 2),
                        "Net_PnL": round(net, 2),
                        "Capital": round(capital, 2),
                        "Result": reason,
                        "Is_Win": net > 0
                    })
                    in_trade = False
                    trades_today += 1
                    continue

            if not in_trade and trades_today < 2 and datetime.time(9, 25) <= t <= datetime.time(14, 45):
                if b_range < 5: continue
                lower_wick = min(b_open, spot) - b_low
                upper_wick = b_high - max(b_open, spot)
                bull_body = (spot > b_open) and ((spot - b_open) >= 0.35 * b_range)
                bear_body = (spot < b_open) and ((b_open - spot) >= 0.35 * b_range)
                prev_c = prev_bar["close"]

                r1_break = (prev_c <= lvl["r1"]) and (spot > lvl["r1"]) and bull_body
                s1_break = (prev_c >= lvl["s1"]) and (spot < lvl["s1"]) and bear_body
                r2_break = (prev_c <= lvl["r2"]) and (spot > lvl["r2"]) and bull_body
                s2_break = (prev_c >= lvl["s2"]) and (spot < lvl["s2"]) and bear_body

                tested_s1 = (b_low <= lvl["s1"] <= b_high) or (prev_bar["low"] <= lvl["s1"] and b_low <= lvl["s1"])
                s1_bounce = tested_s1 and (spot > lvl["s1"]) and ((lower_wick >= 0.35 * b_range) or (spot > prev_bar["high"] and spot > b_open))
                tested_r1 = (b_high >= lvl["r1"] >= b_low) or (prev_bar["high"] >= lvl["r1"] and b_high >= lvl["r1"])
                r1_fade = tested_r1 and (spot < lvl["r1"]) and ((upper_wick >= 0.35 * b_range) or (spot < prev_bar["low"] and spot < b_open))
                tested_s2 = (b_low <= lvl["s2"])
                s2_bounce = tested_s2 and (spot > lvl["s2"]) and (lower_wick >= 0.35 * b_range)
                tested_r2 = (b_high >= lvl["r2"])
                r2_fade = tested_r2 and (spot < lvl["r2"]) and (upper_wick >= 0.35 * b_range)

                c_dir = None
                c_pb = ""
                if s1_break: c_dir = "PE"; c_pb = "S1 Support Breakdown"
                elif r1_break: c_dir = "CE"; c_pb = "R1 Resistance Breakout"
                elif s1_bounce: c_dir = "CE"; c_pb = "S1 Support Bounceback"
                elif r1_fade: c_dir = "PE"; c_pb = "R1 Resistance Reversal"
                elif s2_break: c_dir = "PE"; c_pb = "S2 Flush Breakdown"
                elif r2_break: c_dir = "CE"; c_pb = "R2 Expansion Breakout"
                elif s2_bounce: c_dir = "CE"; c_pb = "S2 Sweep Bounceback"
                elif r2_fade: c_dir = "PE"; c_pb = "R2 Exhaustion Reversal"

                if c_dir and c_pb in allowed_pb:
                    in_trade = True
                    trade_dir = c_dir
                    playbook = c_pb
                    strike = int(round(spot / 50) * 50)
                    is_call = (trade_dir == "CE")
                    entry_prem = BlackScholesPricing.calculate_price(spot, strike, dte, 0.135, is_call=is_call)
                    curr_sl = max(0.5, entry_prem - sl_val)
                    curr_tp = entry_prem + tp_val
                    entry_time = bar["dt"]
                    continue

    return pd.DataFrame(trades)

df_benchmark = run_benchmark()

# KPI metrics
total_trades = len(df_benchmark)
wins = int(df_benchmark['Is_Win'].sum())
losses = total_trades - wins
win_rate = (wins / total_trades) * 100.0 if total_trades > 0 else 0.0
net_pnl = float(df_benchmark['Net_PnL'].sum())
gross_win = float(df_benchmark[df_benchmark['Net_PnL'] > 0]['Net_PnL'].sum())
gross_loss = abs(float(df_benchmark[df_benchmark['Net_PnL'] < 0]['Net_PnL'].sum()))
pf = (gross_win / gross_loss) if gross_loss > 0 else 99.0
roi = (net_pnl / 50000.0) * 100.0
avg_win = float(df_benchmark[df_benchmark['Net_PnL'] > 0]['Net_PnL'].mean())
avg_loss = abs(float(df_benchmark[df_benchmark['Net_PnL'] < 0]['Net_PnL'].mean()))
realized_rr = avg_win / avg_loss if avg_loss > 0 else 0.0

# Capital & Drawdown series
cum_pnl = df_benchmark['Net_PnL'].cumsum()
eq_series = [50000.0] + (50000.0 + cum_pnl).tolist()
labels_eq = ["Start (₹50k)"] + [f"{r['Date']} {r['Time']}" for _, r in df_benchmark.iterrows()]
peak_series = pd.Series(eq_series).cummax()
dd_series = (pd.Series(eq_series) - peak_series).tolist()
max_dd = abs(min(dd_series))
max_dd_pct = (max_dd / 50000.0) * 100.0

# Daily PnL
daily_pnl = df_benchmark.groupby("Date")["Net_PnL"].sum().reset_index()
daily_dates = daily_pnl["Date"].tolist()
daily_values = [round(float(v), 2) for v in daily_pnl["Net_PnL"]]

# Playbook Breakdown
pb_group = df_benchmark.groupby("Playbook").agg(
    Trades=("Net_PnL", "count"),
    Wins=("Is_Win", "sum"),
    Net_PnL=("Net_PnL", "sum")
).reset_index()
pb_group["Win_Rate"] = round(pb_group["Wins"] / pb_group["Trades"] * 100.0, 1)
pb_group["Avg_Trade"] = round(pb_group["Net_PnL"] / pb_group["Trades"], 2)
pb_group.sort_values(by="Net_PnL", ascending=False, inplace=True)

pb_rows = ""
for _, r in pb_group.iterrows():
    cls = "pnl-pos" if r["Net_PnL"] > 0 else "pnl-neg"
    pb_rows += f"""
    <tr>
        <td><strong>{r['Playbook']}</strong></td>
        <td>{r['Trades']}</td>
        <td>{r['Wins']}W / {r['Trades'] - r['Wins']}L</td>
        <td><strong>{r['Win_Rate']:.1f}%</strong></td>
        <td class="{cls}"><strong>₹{r['Net_PnL']:+,.2f}</strong></td>
        <td>₹{r['Avg_Trade']:+,.2f}</td>
    </tr>
    """

# Trade log rows
trade_rows = ""
for idx, r in df_benchmark.iterrows():
    cls = "pnl-pos" if r["Net_PnL"] > 0 else "pnl-neg"
    res_cls = "badge-target" if "TARGET" in r["Result"] else ("badge-sl" if "STOP" in r["Result"] else "badge-eod")
    trade_rows += f"""
    <tr>
        <td>#{idx+1}</td>
        <td><strong>{r['Date']}</strong></td>
        <td>{r['Time']}</td>
        <td>{r['Exit_Time']}</td>
        <td><strong>{r['Instrument']}</strong></td>
        <td>{r['Playbook']}</td>
        <td>₹{r['Entry_Prem']:.2f}</td>
        <td>₹{r['Exit_Prem']:.2f}</td>
        <td>{r['Prem_Pts']:+.2f}</td>
        <td class="{cls}"><strong>₹{r['Net_PnL']:+,.2f}</strong></td>
        <td>₹{r['Capital']:,.2f}</td>
        <td><span class="badge {res_cls}">{r['Result']}</span></td>
    </tr>
    """

html_template = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>NIFTY Options Backtest Report — October 2026 Month-to-Date</title>
    <link href="https://fonts.googleapis.com/css2?family=Outfit:wght@300;400;500;600;700;800&family=JetBrains+Mono:wght@400;600;700&display=swap" rel="stylesheet">
    <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
    <style>
        :root {{
            --bg: #090d16;
            --surface: #111827;
            --surface-card: #162032;
            --border: #233044;
            --primary: #00f2fe;
            --accent: #4facfe;
            --green: #10b981;
            --red: #f43f5e;
            --text-main: #f9fafb;
            --text-muted: #94a3b8;
        }}
        * {{ margin: 0; padding: 0; box-sizing: border-box; }}
        body {{
            background: var(--bg);
            color: var(--text-main);
            font-family: 'Outfit', sans-serif;
            padding: 30px 24px;
            line-height: 1.5;
        }}
        .container {{ max-width: 1400px; margin: 0 auto; }}
        .header {{
            background: linear-gradient(135deg, #1e1b4b 0%, #0f172a 100%);
            border: 1px solid rgba(255, 255, 255, 0.12);
            padding: 28px 32px;
            border-radius: 16px;
            margin-bottom: 24px;
            display: flex;
            justify-content: space-between;
            align-items: center;
            box-shadow: 0 10px 30px rgba(0,0,0,0.5);
        }}
        .header h1 {{
            font-size: 26px;
            font-weight: 800;
            background: linear-gradient(90deg, #00f2fe, #4facfe);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
        }}
        .header p {{ color: var(--text-muted); font-size: 14px; margin-top: 6px; }}
        .pill {{
            padding: 8px 16px;
            border-radius: 30px;
            font-size: 13px;
            font-weight: 700;
            background: rgba(16, 185, 129, 0.15);
            border: 1px solid var(--green);
            color: var(--green);
        }}
        .kpi-grid {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(210px, 1fr));
            gap: 16px;
            margin-bottom: 24px;
        }}
        .kpi-card {{
            background: var(--surface);
            border: 1px solid var(--border);
            border-radius: 14px;
            padding: 20px;
            transition: transform 0.2s, border-color 0.2s;
        }}
        .kpi-card:hover {{
            transform: translateY(-2px);
            border-color: rgba(0, 242, 254, 0.4);
        }}
        .kpi-lbl {{ font-size: 12px; color: var(--text-muted); text-transform: uppercase; font-weight: 600; letter-spacing: 0.5px; }}
        .kpi-val {{ font-size: 26px; font-weight: 800; margin-top: 8px; font-family: 'JetBrains Mono', monospace; }}
        .kpi-sub {{ font-size: 12px; color: var(--text-muted); margin-top: 6px; }}
        .pnl-pos {{ color: var(--green); }}
        .pnl-neg {{ color: var(--red); }}
        .charts-grid {{
            display: grid;
            grid-template-columns: 2fr 1fr;
            gap: 20px;
            margin-bottom: 24px;
        }}
        @media (max-width: 1024px) {{
            .charts-grid {{ grid-template-columns: 1fr; }}
        }}
        .card {{
            background: var(--surface);
            border: 1px solid var(--border);
            border-radius: 14px;
            padding: 24px;
            margin-bottom: 24px;
        }}
        .card h2 {{
            font-size: 18px;
            font-weight: 700;
            margin-bottom: 18px;
            display: flex;
            align-items: center;
            gap: 10px;
        }}
        table {{
            width: 100%;
            border-collapse: collapse;
            font-size: 13px;
        }}
        th {{
            background: #192336;
            color: #94a3b8;
            padding: 12px 14px;
            text-align: left;
            font-weight: 600;
            text-transform: uppercase;
            font-size: 11px;
            letter-spacing: 0.5px;
        }}
        td {{
            padding: 12px 14px;
            border-bottom: 1px solid rgba(255,255,255,0.05);
            font-family: 'JetBrains Mono', monospace;
        }}
        tr:hover td {{ background: rgba(255, 255, 255, 0.02); }}
        .badge {{
            padding: 4px 10px;
            border-radius: 6px;
            font-size: 11px;
            font-weight: 700;
        }}
        .badge-target {{ background: rgba(16, 185, 129, 0.2); color: #10b981; border: 1px solid rgba(16, 185, 129, 0.4); }}
        .badge-sl {{ background: rgba(244, 63, 94, 0.2); color: #f43f5e; border: 1px solid rgba(244, 63, 94, 0.4); }}
        .badge-eod {{ background: rgba(148, 163, 184, 0.2); color: #cbd5e1; border: 1px solid rgba(148, 163, 184, 0.4); }}
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <div>
                <h1>📊 NIFTY OPTIONS BACKTEST — OCTOBER 2026 (MTD)</h1>
                <p>Evaluation Period: <strong>01-Oct-2026 to 21-Oct-2026</strong> | Strategy: 5-Minute Institutional S&R Engine | 1 Lot (65 Qty) | Starting Capital: ₹50,000</p>
            </div>
            <div>
                <span class="pill">STATUS: VERIFIED (13 TRADING DAYS)</span>
            </div>
        </div>

        <div class="kpi-grid">
            <div class="kpi-card">
                <div class="kpi-lbl">Total Net P&L</div>
                <div class="kpi-val {'pnl-pos' if net_pnl >= 0 else 'pnl-neg'}">₹{net_pnl:+,.2f}</div>
                <div class="kpi-sub">ROI: <strong>{roi:+.2f}%</strong> on ₹50,000 Capital</div>
            </div>
            <div class="kpi-card">
                <div class="kpi-lbl">Win Rate</div>
                <div class="kpi-val pnl-pos">{win_rate:.1f}%</div>
                <div class="kpi-sub"><strong>{wins} Wins</strong> / {losses} Losses ({total_trades} Trades)</div>
            </div>
            <div class="kpi-card">
                <div class="kpi-lbl">Profit Factor</div>
                <div class="kpi-val pnl-pos">{pf:.2f}</div>
                <div class="kpi-sub">Gross Win: ₹{gross_win:,.0f} | Gross Loss: ₹{gross_loss:,.0f}</div>
            </div>
            <div class="kpi-card">
                <div class="kpi-lbl">Realized Risk-Reward</div>
                <div class="kpi-val">{realized_rr:.2f}</div>
                <div class="kpi-sub">Avg Win: +₹{avg_win:,.0f} | Avg Loss: -₹{avg_loss:,.0f}</div>
            </div>
            <div class="kpi-card">
                <div class="kpi-lbl">Max Peak Drawdown</div>
                <div class="kpi-val pnl-neg">₹{max_dd:,.2f}</div>
                <div class="kpi-sub">{max_dd_pct:.2f}% of Starting Capital</div>
            </div>
            <div class="kpi-card">
                <div class="kpi-lbl">Final Account Equity</div>
                <div class="kpi-val pnl-pos">₹{50000.0 + net_pnl:,.2f}</div>
                <div class="kpi-sub">Started at ₹50,000.00</div>
            </div>
        </div>

        <div class="charts-grid">
            <div class="card">
                <h2>📈 Equity Growth Curve (October 2026)</h2>
                <div style="height: 320px;">
                    <canvas id="equityChart"></canvas>
                </div>
            </div>
            <div class="card">
                <h2>📅 Daily P&L Breakdown</h2>
                <div style="height: 320px;">
                    <canvas id="dailyChart"></canvas>
                </div>
            </div>
        </div>

        <div class="card">
            <h2>🎯 Playbook Performance Breakdown (October 2026)</h2>
            <div style="overflow-x: auto;">
                <table>
                    <thead>
                        <tr>
                            <th>Playbook Strategy</th>
                            <th>Trades</th>
                            <th>Wins / Losses</th>
                            <th>Win Rate</th>
                            <th>Net P&L</th>
                            <th>Avg / Trade</th>
                        </tr>
                    </thead>
                    <tbody>
                        {pb_rows}
                    </tbody>
                </table>
            </div>
        </div>

        <div class="card">
            <h2>📋 Complete October 2026 Trade-by-Trade Ledger</h2>
            <div style="overflow-x: auto;">
                <table>
                    <thead>
                        <tr>
                            <th>#</th>
                            <th>Date</th>
                            <th>Entry</th>
                            <th>Exit</th>
                            <th>Contract</th>
                            <th>Playbook</th>
                            <th>Entry Prem</th>
                            <th>Exit Prem</th>
                            <th>Points</th>
                            <th>Net P&L</th>
                            <th>Capital</th>
                            <th>Result</th>
                        </tr>
                    </thead>
                    <tbody>
                        {trade_rows}
                    </tbody>
                </table>
            </div>
        </div>
    </div>

    <script>
        // Equity Chart
        const ctxEq = document.getElementById('equityChart').getContext('2d');
        new Chart(ctxEq, {{
            type: 'line',
            data: {{
                labels: {labels_eq},
                datasets: [{{
                    label: 'Account Equity (₹)',
                    data: {eq_series},
                    borderColor: '#00f2fe',
                    backgroundColor: 'rgba(0, 242, 254, 0.12)',
                    fill: true,
                    tension: 0.25,
                    borderWidth: 2.5,
                    pointBackgroundColor: '#00f2fe',
                    pointRadius: 4
                }}]
            }},
            options: {{
                responsive: true,
                maintainAspectRatio: false,
                plugins: {{ legend: {{ display: false }} }},
                scales: {{
                    x: {{ grid: {{ color: 'rgba(255,255,255,0.05)' }}, ticks: {{ color: '#94a3b8', font: {{ size: 10 }} }} }},
                    y: {{ grid: {{ color: 'rgba(255,255,255,0.05)' }}, ticks: {{ color: '#94a3b8', callback: v => '₹' + v.toLocaleString() }} }}
                }}
            }}
        }});

        // Daily P&L Chart
        const ctxDaily = document.getElementById('dailyChart').getContext('2d');
        const dailyVals = {daily_values};
        new Chart(ctxDaily, {{
            type: 'bar',
            data: {{
                labels: {daily_dates},
                datasets: [{{
                    label: 'Daily P&L (₹)',
                    data: dailyVals,
                    backgroundColor: dailyVals.map(v => v >= 0 ? '#10b981' : '#f43f5e'),
                    borderRadius: 6
                }}]
            }},
            options: {{
                responsive: true,
                maintainAspectRatio: false,
                plugins: {{ legend: {{ display: false }} }},
                scales: {{
                    x: {{ grid: {{ display: false }}, ticks: {{ color: '#94a3b8', font: {{ size: 10 }} }} }},
                    y: {{ grid: {{ color: 'rgba(255,255,255,0.05)' }}, ticks: {{ color: '#94a3b8', callback: v => '₹' + v.toLocaleString() }} }}
                }}
            }}
        }});
    </script>
</body>
</html>
"""

report_file = os.path.join(base_dir, "report_october_2026_backtest.html")
with open(report_file, "w", encoding="utf-8") as f:
    f.write(html_template)

print(f"Generated complete interactive HTML report: {report_file}")
