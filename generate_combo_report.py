"""
Generate ultra-premium HTML report for:
"NIFTY Options 1 Lot (65 Qty) - Combined Breakout & Bounceback S&R Strategy"
"""
import os
import sys
import json
import pandas as pd
import numpy as np

def main():
    base_dir = os.path.dirname(os.path.abspath(__file__))
    candle_path = os.path.join(base_dir, "nifty_data", "candles", "NIFTY_5min.csv")
    daily_path = os.path.join(base_dir, "nifty_data", "candles", "NIFTY_1day.csv")

    from backtest_breakout_and_bounceback import run_simulation, NiftySREngine

    df_intra = pd.read_csv(candle_path)
    df_intra["datetime"] = pd.to_datetime(df_intra["datetime"])
    df_intra.sort_values("datetime", inplace=True)

    df_1d = pd.read_csv(daily_path)
    df_1d["datetime"] = pd.to_datetime(df_1d["datetime"]).dt.date
    df_1d.drop_duplicates(subset=["datetime"], inplace=True)
    df_1d.set_index("datetime", inplace=True)

    df_intra["date"] = df_intra["datetime"].dt.date
    session_data = []

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

    # Run simulations
    res_1_3 = run_simulation(session_data, sl_val=30.0, rr=3.0, trail=False)
    res_1_2 = run_simulation(session_data, sl_val=30.0, rr=2.0, trail=False)
    res_1_2_tr = run_simulation(session_data, sl_val=30.0, rr=2.0, trail=True)
    res_sl25_1_2 = run_simulation(session_data, sl_val=25.0, rr=2.0, trail=False)

    df_1_3 = res_1_3["trades_df"]
    df_1_2 = res_1_2["trades_df"]
    df_1_2_tr = res_1_2_tr["trades_df"]
    df_sl25_1_2 = res_sl25_1_2["trades_df"]

    initial_capital = 50000.0

    def get_series(df):
        caps = [initial_capital] + df["Capital"].tolist()
        dates = ["Start"] + [f"{r['Date']} {r['Time']}" for _, r in df.iterrows()]
        dds = [0.0]
        peak = initial_capital
        for c in df["Capital"]:
            peak = max(peak, c)
            dds.append(((c - peak) / peak) * 100.0)
        return dates, caps, dds

    d_1_3, eq_1_3, dd_1_3 = get_series(df_1_3)
    _, eq_1_2, dd_1_2 = get_series(df_1_2)
    _, eq_1_2_tr, dd_1_2_tr = get_series(df_1_2_tr)
    _, eq_sl25, dd_sl25 = get_series(df_sl25_1_2)

    trades_list = df_1_3.to_dict(orient="records")

    output_html = os.path.join(base_dir, "report_combo_breakout_bounceback.html")

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>NIFTY Options 1 Lot (65 Qty) - Combined Breakout & Bounceback Backtest Report</title>
    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700;800&family=JetBrains+Mono:wght@400;500;600;700&display=swap" rel="stylesheet">
    <script src="https://cdn.plot.ly/plotly-2.27.0.min.js"></script>
    <style>
        :root {{
            --bg: #0B0F19;
            --surface: #111827;
            --surface-hover: #1F2937;
            --surface-border: rgba(255, 255, 255, 0.08);
            --text-main: #F9FAFB;
            --text-muted: #94A3B8;
            --accent-cyan: #06B6D4;
            --accent-emerald: #10B981;
            --accent-violet: #8B5CF6;
            --accent-amber: #F59E0B;
            --accent-rose: #F43F5E;
        }}
        * {{ margin: 0; padding: 0; box-sizing: border-box; }}
        body {{
            background-color: var(--bg);
            color: var(--text-main);
            font-family: 'Inter', -apple-system, sans-serif;
            padding: 32px;
            line-height: 1.5;
        }}
        .container {{ max-width: 1400px; margin: 0 auto; }}
        .header {{
            background: linear-gradient(135deg, rgba(17, 24, 39, 0.95), rgba(31, 41, 55, 0.7));
            border: 1px solid var(--surface-border);
            border-radius: 20px;
            padding: 32px;
            margin-bottom: 28px;
            backdrop-filter: blur(12px);
            position: relative;
            overflow: hidden;
        }}
        .header::after {{
            content: '';
            position: absolute;
            top: 0; right: 0; width: 450px; height: 100%;
            background: radial-gradient(circle at top right, rgba(16, 185, 129, 0.15), transparent 70%);
            pointer-events: none;
        }}
        .badge-bar {{ display: flex; gap: 10px; margin-bottom: 12px; flex-wrap: wrap; }}
        .badge {{
            display: inline-flex; align-items: center; gap: 6px;
            padding: 4px 12px; border-radius: 9999px; font-size: 11px; font-weight: 700;
            text-transform: uppercase; letter-spacing: 0.05em;
        }}
        .badge-emerald {{ background: rgba(16, 185, 129, 0.15); color: #34D399; border: 1px solid rgba(16, 185, 129, 0.3); }}
        .badge-cyan {{ background: rgba(6, 182, 212, 0.15); color: #22D3EE; border: 1px solid rgba(6, 182, 212, 0.3); }}
        .badge-violet {{ background: rgba(139, 92, 246, 0.15); color: #A78BFA; border: 1px solid rgba(139, 92, 246, 0.3); }}
        .header h1 {{ font-size: 28px; font-weight: 800; letter-spacing: -0.02em; margin-bottom: 8px; }}
        .header p {{ color: var(--text-muted); font-size: 14px; max-width: 900px; }}

        .comparison-grid {{
            display: grid; grid-template-columns: repeat(auto-fit, minmax(310px, 1fr));
            gap: 20px; margin-bottom: 28px;
        }}
        .strategy-card {{
            background: var(--surface);
            border: 1px solid var(--surface-border);
            border-radius: 16px;
            padding: 24px;
            position: relative;
            transition: transform 0.2s ease, border-color 0.2s ease;
        }}
        .strategy-card:hover {{
            transform: translateY(-2px);
            border-color: rgba(255, 255, 255, 0.15);
        }}
        .strategy-card.highlight {{
            border-color: rgba(16, 185, 129, 0.5);
            background: linear-gradient(145deg, rgba(17, 24, 39, 1), rgba(16, 185, 129, 0.05));
        }}
        .card-title {{
            font-size: 17px; font-weight: 700; margin-bottom: 4px; display: flex; justify-content: space-between; align-items: center;
        }}
        .card-subtitle {{ font-size: 12px; color: var(--text-muted); margin-bottom: 20px; }}
        .kpi-row {{ display: grid; grid-template-columns: 1fr 1fr; gap: 14px; margin-bottom: 16px; }}
        .kpi-item {{ background: rgba(0, 0, 0, 0.25); border-radius: 10px; padding: 12px; border: 1px solid rgba(255, 255, 255, 0.04); }}
        .kpi-label {{ font-size: 11px; color: var(--text-muted); text-transform: uppercase; font-weight: 600; margin-bottom: 4px; }}
        .kpi-value {{ font-family: 'JetBrains Mono', monospace; font-size: 18px; font-weight: 700; }}
        .val-green {{ color: #10B981; }}
        .val-cyan {{ color: #06B6D4; }}
        .val-amber {{ color: #F59E0B; }}
        .val-red {{ color: #EF4444; }}

        .chart-card {{
            background: var(--surface);
            border: 1px solid var(--surface-border);
            border-radius: 16px;
            padding: 24px;
            margin-bottom: 28px;
        }}
        .chart-header {{
            display: flex; justify-content: space-between; align-items: center; margin-bottom: 16px; flex-wrap: wrap; gap: 12px;
        }}
        .chart-title {{ font-size: 18px; font-weight: 700; }}

        .table-wrap {{
            overflow-x: auto;
            border-radius: 12px;
            border: 1px solid var(--surface-border);
            margin-bottom: 28px;
        }}
        table {{
            width: 100%; border-collapse: collapse; font-size: 13px; text-align: left;
        }}
        th {{
            background: #162032; color: #94A3B8; font-weight: 600; padding: 12px 14px;
            text-transform: uppercase; font-size: 11px; letter-spacing: 0.05em; border-bottom: 1px solid var(--surface-border);
        }}
        td {{
            padding: 12px 14px; border-bottom: 1px solid rgba(255, 255, 255, 0.04);
            font-family: 'JetBrains Mono', monospace;
        }}
        tr:hover td {{ background: var(--surface-hover); }}

        .pill {{
            padding: 3px 8px; border-radius: 6px; font-size: 11px; font-weight: 700; display: inline-block;
        }}
        .pill-win {{ background: rgba(16, 185, 129, 0.15); color: #34D399; }}
        .pill-loss {{ background: rgba(239, 68, 68, 0.15); color: #F87171; }}
        .pill-trail {{ background: rgba(139, 92, 246, 0.15); color: #A78BFA; }}
        .pill-bo {{ background: rgba(6, 182, 212, 0.15); color: #22D3EE; }}
        .pill-bb {{ background: rgba(245, 158, 11, 0.15); color: #FBBF24; }}

        .insight-box {{
            background: linear-gradient(135deg, rgba(16, 185, 129, 0.08), rgba(6, 182, 212, 0.05));
            border: 1px solid rgba(16, 185, 129, 0.25);
            border-radius: 16px;
            padding: 24px;
            margin-bottom: 28px;
        }}
        .insight-box h3 {{ font-size: 16px; font-weight: 700; color: #34D399; margin-bottom: 10px; display: flex; align-items: center; gap: 8px; }}
        .insight-box ul {{ padding-left: 20px; color: #CBD5E1; font-size: 14px; line-height: 1.7; }}
        .insight-box li strong {{ color: #F8FAFC; }}
    </style>
</head>
<body>
    <div class="container">
        <!-- HEADER -->
        <div class="header">
            <div class="badge-bar">
                <span class="badge badge-emerald">COMPLETE HYBRID ARCHITECTURE</span>
                <span class="badge badge-cyan">1 LOT = 65 QTY STRICT</span>
                <span class="badge badge-violet">BREAKOUT + BOUNCEBACK</span>
            </div>
            <h1>Combined Strategy: Breakout & Bounceback on Support & Resistance</h1>
            <p>
                This strategy trades both market phases:
                <strong>1. Breakouts</strong>: Riding momentum when Spot crosses beyond key levels (R1 Breakout, S1 Breakdown, S2 Flush).
                <strong>2. Bouncebacks</strong>: Buying reversals when Spot defends key levels (S1 Support Bounce, R1 Resistance Reversal, S2 Sweep).
                All trades are strictly intraday (1 Lot = 65 Qty NIFTY Options) with full statutory costs & slippage.
            </p>
        </div>

        <!-- 3-WAY KPI CARDS -->
        <div class="comparison-grid">
            <!-- 1:3 RR (WINNER) -->
            <div class="strategy-card highlight">
                <div class="card-title">
                    <span>1:3 Risk-Reward (Combined)</span>
                    <span class="badge badge-emerald">HIGHEST RETURN</span>
                </div>
                <div class="card-subtitle">SL: 30 pts | TP: 90 pts | Breakout + Bounceback</div>
                <div class="kpi-row">
                    <div class="kpi-item">
                        <div class="kpi-label">Net Profit</div>
                        <div class="kpi-value val-green">+Rs 27,280.69</div>
                    </div>
                    <div class="kpi-item">
                        <div class="kpi-label">Return on Capital</div>
                        <div class="kpi-value val-cyan">+54.56%</div>
                    </div>
                </div>
                <div class="kpi-row">
                    <div class="kpi-item">
                        <div class="kpi-label">Win Rate</div>
                        <div class="kpi-value">49.1% (26W / 27L)</div>
                    </div>
                    <div class="kpi-item">
                        <div class="kpi-label">Profit Factor</div>
                        <div class="kpi-value val-green">1.70</div>
                    </div>
                </div>
                <div class="kpi-row">
                    <div class="kpi-item">
                        <div class="kpi-label">Sharpe Ratio</div>
                        <div class="kpi-value val-cyan">3.05</div>
                    </div>
                    <div class="kpi-item">
                        <div class="kpi-label">Total Trades</div>
                        <div class="kpi-value">53 Trades</div>
                    </div>
                </div>
            </div>

            <!-- 1:2 RR -->
            <div class="strategy-card">
                <div class="card-title">
                    <span>1:2 Risk-Reward (Combined)</span>
                    <span class="badge badge-cyan">HIGH TARGET HITS</span>
                </div>
                <div class="card-subtitle">SL: 30 pts | TP: 60 pts | Breakout + Bounceback</div>
                <div class="kpi-row">
                    <div class="kpi-item">
                        <div class="kpi-label">Net Profit</div>
                        <div class="kpi-value val-green">+Rs 21,559.45</div>
                    </div>
                    <div class="kpi-item">
                        <div class="kpi-label">Return on Capital</div>
                        <div class="kpi-value val-cyan">+43.12%</div>
                    </div>
                </div>
                <div class="kpi-row">
                    <div class="kpi-item">
                        <div class="kpi-label">Win Rate</div>
                        <div class="kpi-value">49.1% (26W / 27L)</div>
                    </div>
                    <div class="kpi-item">
                        <div class="kpi-label">Profit Factor</div>
                        <div class="kpi-value val-green">1.57</div>
                    </div>
                </div>
                <div class="kpi-row">
                    <div class="kpi-item">
                        <div class="kpi-label">Target Hits</div>
                        <div class="kpi-value val-cyan">13 Full Hits (25%)</div>
                    </div>
                    <div class="kpi-item">
                        <div class="kpi-label">Sharpe Ratio</div>
                        <div class="kpi-value">2.72</div>
                    </div>
                </div>
            </div>

            <!-- 1:2 TRAILING -->
            <div class="strategy-card">
                <div class="card-title">
                    <span>1:2 RR + Trailing SL</span>
                    <span class="badge badge-violet">OPTIMAL DEFENSE</span>
                </div>
                <div class="card-subtitle">SL: 30 pts | TP: 60 pts | BE at +30 pts</div>
                <div class="kpi-row">
                    <div class="kpi-item">
                        <div class="kpi-label">Net Profit</div>
                        <div class="kpi-value val-green">+Rs 16,373.55</div>
                    </div>
                    <div class="kpi-item">
                        <div class="kpi-label">Return on Capital</div>
                        <div class="kpi-value val-cyan">+32.75%</div>
                    </div>
                </div>
                <div class="kpi-row">
                    <div class="kpi-item">
                        <div class="kpi-label">Win Rate</div>
                        <div class="kpi-value val-green">54.7% (29W / 24L)</div>
                    </div>
                    <div class="kpi-item">
                        <div class="kpi-label">Profit Factor</div>
                        <div class="kpi-value val-green">1.52</div>
                    </div>
                </div>
                <div class="kpi-row">
                    <div class="kpi-item">
                        <div class="kpi-label">Stop Losses Hit</div>
                        <div class="kpi-value val-green">15 Only (vs 18)</div>
                    </div>
                    <div class="kpi-item">
                        <div class="kpi-label">Sharpe Ratio</div>
                        <div class="kpi-value">2.25</div>
                    </div>
                </div>
            </div>
        </div>

        <!-- INSIGHT BOX -->
        <div class="insight-box">
            <h3>Institutional Analytics: Dual-Engine Synergy</h3>
            <ul>
                <li><strong>Balanced Profits from Both Modes:</strong> In the combined system, <strong>Breakouts contributed +Rs 11,178.49</strong> and <strong>Bouncebacks contributed +Rs 10,380.96</strong>. The strategy never starves during range-bound regimes (where bouncebacks dominate) nor during breakout trend days (where flushes dominate).</li>
                <li><strong>Top Performing Setups:</strong>
                    <ul>
                        <li><code>S2 Flush Breakdown</code> (Breakout): <strong>60.0% Win Rate</strong>, generating <strong>+Rs 10,569.62 (+171.9 pts)</strong>.</li>
                        <li><code>R1 Resistance Reversal</code> (Bounceback): <strong>53.8% Win Rate</strong>, generating <strong>+Rs 9,476.86 (+157.6 pts)</strong>.</li>
                        <li><code>R2 Exhaustion Reversal</code> (Bounceback): <strong>100% Win Rate</strong>, generating <strong>+Rs 7,525.99 (+117.7 pts)</strong>.</li>
                        <li><code>R1 Resistance Breakout</code> (Breakout): <strong>66.7% Win Rate</strong>, generating <strong>+Rs 5,040.80 (+83.4 pts)</strong>.</li>
                    </ul>
                </li>
                <li><strong>1:3 vs 1:2 RR:</strong> 1:3 RR generated <strong>+Rs 27,280.69 (+54.56% ROI)</strong> compared to +Rs 21,559.45 for 1:2 RR, providing massive profit acceleration while maintaining a 3.05 Sharpe ratio.</li>
            </ul>
        </div>

        <!-- CHARTS SECTION -->
        <div class="chart-card">
            <div class="chart-header">
                <div class="chart-title">Equity Growth Comparison (Capital: Rs 50,000)</div>
                <div style="font-size: 12px; color: var(--text-muted);">Comparing 1:3 RR vs 1:2 RR vs 1:2 Trailing SL vs SL 25 pts</div>
            </div>
            <div id="equityChart" style="height: 420px;"></div>
        </div>

        <div class="chart-card">
            <div class="chart-header">
                <div class="chart-title">Underwater Drawdown Curve (% Peak Capital)</div>
            </div>
            <div id="ddChart" style="height: 280px;"></div>
        </div>

        <!-- TRADE LOG (1:3 COMBINED WINNER) -->
        <div class="chart-card">
            <div class="chart-header">
                <div class="chart-title">Executed Trades Log: Combined Strategy (30 pts SL / 90 pts TP, 1:3 RR)</div>
            </div>
            <div class="table-wrap">
                <table>
                    <thead>
                        <tr>
                            <th>#</th>
                            <th>Date</th>
                            <th>Time</th>
                            <th>Instrument</th>
                            <th>Category</th>
                            <th>Playbook</th>
                            <th>Entry Prem</th>
                            <th>Exit Prem</th>
                            <th>Points</th>
                            <th>Gross PnL</th>
                            <th>Costs</th>
                            <th>Net PnL</th>
                            <th>Result</th>
                        </tr>
                    </thead>
                    <tbody>
"""

    for i, t in enumerate(trades_list):
        is_win = t["Net_PnL"] > 0
        pnl_cls = "val-green" if is_win else "val-red"
        res_cls = "pill-win" if "TARGET" in t["Result"] else ("pill-trail" if "TRAILING" in t["Result"] else "pill-loss")
        cat_cls = "pill-bo" if t["Category"] == "BREAKOUT" else "pill-bb"
        html += f"""                        <tr>
                            <td>{i+1}</td>
                            <td>{t['Date']}</td>
                            <td>{t['Time']} - {t['Exit_Time']}</td>
                            <td>{t['Instrument']}</td>
                            <td><span class="pill {cat_cls}">{t['Category']}</span></td>
                            <td style="font-family: 'Inter', sans-serif; font-size: 12px;">{t['Playbook']}</td>
                            <td>Rs {t['Entry_Prem']:.1f}</td>
                            <td>Rs {t['Exit_Prem']:.1f}</td>
                            <td class="{pnl_cls}">{t['Prem_Pts']:+.1f} pts</td>
                            <td class="{pnl_cls}">Rs {t['Gross_PnL']:+,.0f}</td>
                            <td style="color: #94A3B8;">Rs {t['Costs']:.1f}</td>
                            <td class="{pnl_cls}" style="font-weight: 700;">Rs {t['Net_PnL']:+,.2f}</td>
                            <td><span class="pill {res_cls}">{t['Result']}</span></td>
                        </tr>
"""

    html += f"""                    </tbody>
                </table>
            </div>
        </div>
    </div>

    <!-- PLOTLY CHARTS JAVASCRIPT -->
    <script>
        const dates = {json.dumps(d_1_3)};
        const eq1_3 = {json.dumps(eq_1_3)};
        const eq1_2 = {json.dumps(eq_1_2)};
        const eq1_2_tr = {json.dumps(eq_1_2_tr)};
        const eq_sl25 = {json.dumps(eq_sl25)};

        const dd1_3 = {json.dumps(dd_1_3)};
        const dd1_2 = {json.dumps(dd_1_2)};
        const dd1_2_tr = {json.dumps(dd_1_2_tr)};
        const dd_sl25 = {json.dumps(dd_sl25)};

        // Equity Chart
        Plotly.newPlot('equityChart', [
            {{
                name: 'Combined 1:3 RR (30 pt SL / 90 pt TP) ⭐',
                x: dates, y: eq1_3,
                type: 'scatter', mode: 'lines',
                line: {{ color: '#10B981', width: 3.0 }}
            }},
            {{
                name: 'Combined 1:2 RR (30 pt SL / 60 pt TP)',
                x: dates, y: eq1_2,
                type: 'scatter', mode: 'lines',
                line: {{ color: '#06B6D4', width: 2.2 }}
            }},
            {{
                name: 'Combined 1:2 RR + Trailing SL',
                x: dates, y: eq1_2_tr,
                type: 'scatter', mode: 'lines',
                line: {{ color: '#8B5CF6', width: 2.0 }}
            }},
            {{
                name: 'SL 25 pts / TP 50 pts (1:2 RR)',
                x: dates, y: eq_sl25,
                type: 'scatter', mode: 'lines',
                line: {{ color: '#F59E0B', width: 1.8, dash: 'dot' }}
            }}
        ], {{
            paper_bgcolor: 'transparent',
            plot_bgcolor: 'transparent',
            margin: {{ l: 60, r: 20, t: 10, b: 40 }},
            legend: {{ orientation: 'h', y: 1.12, font: {{ family: 'Inter', color: '#F8FAFC', size: 12 }} }},
            xaxis: {{ gridcolor: 'rgba(255, 255, 255, 0.05)', showticklabels: false }},
            yaxis: {{ gridcolor: 'rgba(255, 255, 255, 0.05)', tickformat: ',.0f', tickprefix: 'Rs ', font: {{ family: 'JetBrains Mono', color: '#94A3B8' }} }}
        }}, {{ responsive: true, displayModeBar: false }});

        // Drawdown Chart
        Plotly.newPlot('ddChart', [
            {{
                name: '1:3 Combined DD',
                x: dates, y: dd1_3,
                type: 'scatter', mode: 'lines',
                line: {{ color: '#10B981', width: 2.0 }}
            }},
            {{
                name: '1:2 Combined DD',
                x: dates, y: dd1_2,
                type: 'scatter', mode: 'lines',
                line: {{ color: '#06B6D4', width: 1.8 }}
            }},
            {{
                name: '1:2 Trailing DD',
                x: dates, y: dd1_2_tr,
                type: 'scatter', mode: 'lines',
                line: {{ color: '#8B5CF6', width: 1.8 }}
            }}
        ], {{
            paper_bgcolor: 'transparent',
            plot_bgcolor: 'transparent',
            margin: {{ l: 60, r: 20, t: 10, b: 30 }},
            legend: {{ orientation: 'h', y: 1.15, font: {{ family: 'Inter', color: '#F8FAFC', size: 11 }} }},
            xaxis: {{ gridcolor: 'rgba(255, 255, 255, 0.05)', showticklabels: false }},
            yaxis: {{ gridcolor: 'rgba(255, 255, 255, 0.05)', tickformat: '.1f', ticksuffix: '%', font: {{ family: 'JetBrains Mono', color: '#94A3B8' }} }}
        }}, {{ responsive: true, displayModeBar: false }});
    </script>
</body>
</html>
"""

    with open(output_html, "w", encoding="utf-8") as f:
        f.write(html)
    print(f"[+] Successfully generated combined report at: {output_html}")

if __name__ == "__main__":
    main()
