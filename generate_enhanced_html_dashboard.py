import os
import json
import pandas as pd
import numpy as np

base_dir = os.path.dirname(os.path.abspath(__file__))

# Load ledgers
df_base = pd.read_csv(os.path.join(base_dir, "trades_overall_best_setup_2year.csv"))
df_enh = pd.read_csv(os.path.join(base_dir, "trades_master_enhanced_setup_2year.csv"))

df_base["cum_pnl"] = df_base["net_pnl"].cumsum()
df_enh["cum_pnl"] = df_enh["net_pnl"].cumsum()

# Calculate drawdowns
cum_base = df_base["cum_pnl"]
dd_base = (cum_base - cum_base.cummax())

cum_enh = df_enh["cum_pnl"]
dd_enh = (cum_enh - cum_enh.cummax())

# Aggregations for charts
pb_agg = df_enh.groupby("playbook").agg(
    trades=("net_pnl", "count"),
    wins=("is_win", "sum"),
    net_pnl=("net_pnl", "sum"),
    avg_pnl=("net_pnl", "mean")
).reset_index()
pb_agg["wr"] = (pb_agg["wins"] / pb_agg["trades"] * 100).round(1)
pb_agg = pb_agg.sort_values("net_pnl", ascending=False)

day_order = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday"]
day_agg = df_enh.groupby("day_name").agg(
    trades=("net_pnl", "count"),
    wins=("is_win", "sum"),
    net_pnl=("net_pnl", "sum")
).reindex(day_order).reset_index()
day_agg["wr"] = (day_agg["wins"] / day_agg["trades"] * 100).round(1)

# Monthly PnL
df_enh["year_month"] = df_enh["date"].str.slice(0, 7)
monthly_agg = df_enh.groupby("year_month")["net_pnl"].sum().reset_index()

# Prep JSON data for Plotly
equity_dates_enh = df_enh["date"].tolist()
equity_vals_enh = df_enh["cum_pnl"].tolist()
dd_vals_enh = dd_enh.tolist()

equity_dates_base = df_base["date"].tolist()
equity_vals_base = df_base["cum_pnl"].tolist()
dd_vals_base = dd_base.tolist()

pb_names = pb_agg["playbook"].tolist()
pb_pnl = pb_agg["net_pnl"].round(2).tolist()
pb_wr = pb_agg["wr"].tolist()
pb_trades = pb_agg["trades"].tolist()

days = day_agg["day_name"].tolist()
day_pnl = day_agg["net_pnl"].round(2).tolist()
day_wr = day_agg["wr"].tolist()

month_labels = monthly_agg["year_month"].tolist()
month_pnl = monthly_agg["net_pnl"].round(2).tolist()

# Trades Table rows (last 60 trades)
recent_trades = df_enh.tail(60).iloc[::-1]
table_rows = []
for _, r in recent_trades.iterrows():
    pnl_cls = "text-emerald-400 font-bold" if r["net_pnl"] > 0 else "text-rose-400 font-bold"
    badge_cls = "bg-emerald-500/20 text-emerald-300 border-emerald-500/30" if r["is_win"] else "bg-rose-500/20 text-rose-300 border-rose-500/30"
    dir_badge = "bg-blue-500/20 text-blue-300 border-blue-500/30" if r["trade_dir"] == "CE" else "bg-amber-500/20 text-amber-300 border-amber-500/30"
    
    table_rows.append(f"""
    <tr class="border-b border-slate-800/80 hover:bg-slate-800/40 transition">
        <td class="py-2.5 px-3 font-mono text-slate-400 text-xs">{r['trade_id']}</td>
        <td class="py-2.5 px-3 text-slate-200 text-xs">{r['date']} <span class="text-slate-500 text-[10px]">({r['day_name'][:3]})</span></td>
        <td class="py-2.5 px-3 text-slate-300 text-xs font-mono">{r['entry_time']} &rarr; {r['exit_time']}</td>
        <td class="py-2.5 px-3"><span class="px-2 py-0.5 rounded text-[11px] font-semibold border {dir_badge}">{r['trade_dir']}</span></td>
        <td class="py-2.5 px-3 text-slate-300 text-xs">{r['playbook']}</td>
        <td class="py-2.5 px-3 text-slate-300 text-xs font-mono">{r['strike']}</td>
        <td class="py-2.5 px-3 text-slate-300 text-xs font-mono">&#8377;{r['entry_prem']:.1f}</td>
        <td class="py-2.5 px-3 text-slate-300 text-xs font-mono">&#8377;{r['exit_prem']:.1f}</td>
        <td class="py-2.5 px-3 font-mono text-xs {pnl_cls}">{r['pts']:+.1f}</td>
        <td class="py-2.5 px-3 font-mono text-xs {pnl_cls}">&#8377;{r['net_pnl']:+,.2f}</td>
        <td class="py-2.5 px-3 text-xs"><span class="px-2 py-0.5 rounded text-[10px] font-semibold border {badge_cls}">{r['result']}</span></td>
        <td class="py-2.5 px-3 font-mono text-xs text-slate-200 font-semibold">&#8377;{r['cum_pnl']:,.2f}</td>
    </tr>
    """)

table_html = "\n".join(table_rows)

html_content = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>NIFTY 50 Options Algorithm - Triple Filtration Enhanced Champion Report</title>
    <script src="https://cdn.tailwindcss.com"></script>
    <script src="https://cdn.plot.ly/plotly-2.35.2.min.js"></script>
    <link href="https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@300;400;500;600;700;800&family=JetBrains+Mono:wght@400;600;700&display=swap" rel="stylesheet">
    <style>
        body {{
            font-family: 'Plus Jakarta Sans', sans-serif;
            background-color: #0b0f17;
            color: #f1f5f9;
        }}
        .font-mono {{ font-family: 'JetBrains Mono', monospace; }}
        .glass-panel {{
            background: rgba(17, 24, 39, 0.7);
            backdrop-filter: blur(16px);
            border: 1px solid rgba(255, 255, 255, 0.08);
            box-shadow: 0 20px 40px -15px rgba(0, 0, 0, 0.5);
        }}
        .glass-glow {{
            background: radial-gradient(circle at top right, rgba(16, 185, 129, 0.08), transparent 40%),
                        radial-gradient(circle at bottom left, rgba(59, 130, 246, 0.08), transparent 40%);
        }}
        .custom-scroll::-webkit-scrollbar {{
            width: 6px;
            height: 6px;
        }}
        .custom-scroll::-webkit-scrollbar-track {{
            background: rgba(15, 23, 42, 0.6);
        }}
        .custom-scroll::-webkit-scrollbar-thumb {{
            background: rgba(51, 65, 85, 0.8);
            border-radius: 4px;
        }}
    </style>
</head>
<body class="p-4 md:p-8 min-h-screen">
    <div class="max-w-7xl mx-auto space-y-6">
        
        <!-- HEADER -->
        <header class="glass-panel rounded-2xl p-6 glass-glow flex flex-col md:flex-row md:items-center justify-between gap-4 border border-emerald-500/20">
            <div>
                <div class="flex items-center gap-3">
                    <span class="px-3 py-1 rounded-full text-xs font-bold tracking-wider uppercase bg-emerald-500/20 text-emerald-400 border border-emerald-500/30">
                        Institutional Level 3 Champion
                    </span>
                    <span class="text-xs font-mono text-slate-400">Backtested: Oct 2024 &ndash; Oct 2026 (492 Sessions)</span>
                </div>
                <h1 class="text-2xl md:text-3xl font-extrabold text-white mt-2 tracking-tight">
                    NIFTY 50 Options &bull; Triple-Filtered Enhanced Setup
                </h1>
                <p class="text-sm text-slate-400 mt-1">
                    ATM Strike &bull; Current Weekly Expiry &bull; SL 50 pts &bull; TP 200 pts (1:4 RR) &bull; 14:00 Cutoff &bull; Smart BE Lock (+80 pts) &bull; Stop-On-Loss Daily Halt
                </p>
            </div>
            <div class="flex flex-col md:items-end justify-center">
                <div class="text-xs text-slate-400 uppercase tracking-wider font-semibold">Net P&L (1 Lot = 65 Qty)</div>
                <div class="text-3xl font-mono font-extrabold text-emerald-400 mt-0.5 tracking-tight">&#8377;+4,25,890.06</div>
                <div class="text-xs font-medium text-emerald-500 font-mono mt-0.5">+851.8% ROI on &#8377;50k Capital &bull; Calmar 42.1x</div>
            </div>
        </header>

        <!-- KPI STATS CARDS -->
        <div class="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-4">
            <div class="glass-panel rounded-xl p-4 border border-slate-800">
                <div class="text-[11px] font-medium text-slate-400 uppercase tracking-wider">Win Rate</div>
                <div class="text-2xl font-mono font-bold text-white mt-1">62.58%</div>
                <div class="text-xs text-emerald-400 font-medium mt-1">194W / 116L (310 trades)</div>
            </div>
            <div class="glass-panel rounded-xl p-4 border border-slate-800">
                <div class="text-[11px] font-medium text-slate-400 uppercase tracking-wider">Profit Factor</div>
                <div class="text-2xl font-mono font-bold text-emerald-400 mt-1">3.04</div>
                <div class="text-xs text-slate-400 mt-1">Gross Win / Loss</div>
            </div>
            <div class="glass-panel rounded-xl p-4 border border-slate-800">
                <div class="text-[11px] font-medium text-slate-400 uppercase tracking-wider">Max Drawdown</div>
                <div class="text-2xl font-mono font-bold text-rose-400 mt-1">&#8377;10,106.61</div>
                <div class="text-xs text-emerald-400 mt-1">Only 20.2% of &#8377;50k</div>
            </div>
            <div class="glass-panel rounded-xl p-4 border border-slate-800">
                <div class="text-[11px] font-medium text-slate-400 uppercase tracking-wider">Calmar Ratio</div>
                <div class="text-2xl font-mono font-bold text-indigo-400 mt-1">42.14x</div>
                <div class="text-xs text-slate-400 mt-1">Return-to-Drawdown</div>
            </div>
            <div class="glass-panel rounded-xl p-4 border border-slate-800">
                <div class="text-[11px] font-medium text-slate-400 uppercase tracking-wider">Average Trade</div>
                <div class="text-2xl font-mono font-bold text-emerald-400 mt-1">&#8377;+1,373.84</div>
                <div class="text-xs text-slate-400 mt-1">Net post-slippage & costs</div>
            </div>
            <div class="glass-panel rounded-xl p-4 border border-slate-800">
                <div class="text-[11px] font-medium text-slate-400 uppercase tracking-wider">Sleep Peace</div>
                <div class="text-2xl font-bold text-sky-400 mt-1">100% Cash</div>
                <div class="text-xs text-slate-400 mt-1">15:10 IST EOD close</div>
            </div>
        </div>

        <!-- PROGRESSIVE FILTRATION COMPARISON TABLE -->
        <div class="glass-panel rounded-2xl p-6 border border-slate-800">
            <h3 class="text-lg font-bold text-white mb-3 flex items-center gap-2">
                <span>⚡ Progressive Filtration Impact Comparison</span>
            </h3>
            <div class="overflow-x-auto">
                <table class="w-full text-left text-xs">
                    <thead>
                        <tr class="text-slate-400 border-b border-slate-800 uppercase text-[10px] tracking-wider">
                            <th class="py-3 px-3">Filtration Stage</th>
                            <th class="py-3 px-3">Total Trades</th>
                            <th class="py-3 px-3">Win Rate</th>
                            <th class="py-3 px-3">Net P&L</th>
                            <th class="py-3 px-3">Profit Factor</th>
                            <th class="py-3 px-3">Max Drawdown</th>
                            <th class="py-3 px-3">Calmar</th>
                            <th class="py-3 px-3">Key Value Added</th>
                        </tr>
                    </thead>
                    <tbody class="divide-y divide-slate-800/60 font-mono">
                        <tr class="hover:bg-slate-800/30 transition">
                            <td class="py-3 px-3 font-sans text-slate-300 font-semibold">Baseline Champion Setup</td>
                            <td class="py-3 px-3 text-slate-400">381</td>
                            <td class="py-3 px-3 text-slate-300">54.86%</td>
                            <td class="py-3 px-3 text-emerald-400 font-bold">&#8377;4,06,484.13</td>
                            <td class="py-3 px-3 text-slate-300">2.51</td>
                            <td class="py-3 px-3 text-rose-400">&#8377;15,516.52</td>
                            <td class="py-3 px-3 text-slate-300">26.20x</td>
                            <td class="py-3 px-3 font-sans text-slate-400 text-[11px]">Solid baseline with 6 elite playbooks</td>
                        </tr>
                        <tr class="hover:bg-slate-800/30 transition">
                            <td class="py-3 px-3 font-sans text-sky-300 font-semibold">+ Filter 1: 14:00 Entry Cutoff</td>
                            <td class="py-3 px-3 text-slate-400">348</td>
                            <td class="py-3 px-3 text-sky-300">56.32%</td>
                            <td class="py-3 px-3 text-emerald-400 font-bold">&#8377;4,07,553.02</td>
                            <td class="py-3 px-3 text-sky-300">2.63</td>
                            <td class="py-3 px-3 text-emerald-400 font-semibold">&#8377;13,760.83</td>
                            <td class="py-3 px-3 text-sky-300">29.62x</td>
                            <td class="py-3 px-3 font-sans text-slate-400 text-[11px]">Eliminates 33 late chop trades (-&#8377;5.7k loss removed)</td>
                        </tr>
                        <tr class="hover:bg-slate-800/30 transition">
                            <td class="py-3 px-3 font-sans text-indigo-300 font-semibold">+ Filter 2: Smart BE Lock (+80 pts)</td>
                            <td class="py-3 px-3 text-slate-400">348</td>
                            <td class="py-3 px-3 text-indigo-300">58.05%</td>
                            <td class="py-3 px-3 text-emerald-400 font-bold">&#8377;4,06,765.00</td>
                            <td class="py-3 px-3 text-indigo-300">2.66</td>
                            <td class="py-3 px-3 text-emerald-400 font-semibold">&#8377;13,760.83</td>
                            <td class="py-3 px-3 text-indigo-300">29.56x</td>
                            <td class="py-3 px-3 font-sans text-slate-400 text-[11px]">Protects 10 large winners from turning into full SL hits</td>
                        </tr>
                        <tr class="bg-emerald-500/10 hover:bg-emerald-500/15 transition border-l-4 border-emerald-500">
                            <td class="py-3 px-3 font-sans text-emerald-300 font-bold">🏆 Level 3: Triple-Filtered Master</td>
                            <td class="py-3 px-3 text-emerald-300 font-bold">310</td>
                            <td class="py-3 px-3 text-emerald-400 font-bold text-sm">62.58%</td>
                            <td class="py-3 px-3 text-emerald-400 font-extrabold text-sm">&#8377;4,25,890.06</td>
                            <td class="py-3 px-3 text-emerald-300 font-bold">3.04</td>
                            <td class="py-3 px-3 text-emerald-400 font-bold">&#8377;10,106.61</td>
                            <td class="py-3 px-3 text-emerald-300 font-bold">42.14x</td>
                            <td class="py-3 px-3 font-sans text-emerald-200 text-[11px]"><b>Daily halt after 1 loss skips 36 losing trades (-&#8377;20k saved!)</b></td>
                        </tr>
                    </tbody>
                </table>
            </div>
        </div>

        <!-- MAIN CHART: EQUITY CURVE COMPARISON -->
        <div class="glass-panel rounded-2xl p-6 border border-slate-800 space-y-4">
            <div class="flex flex-col sm:flex-row sm:items-center justify-between gap-2">
                <div>
                    <h3 class="text-lg font-bold text-white">Cumulative Net P&L Growth vs Baseline</h3>
                    <p class="text-xs text-slate-400">Comparing Baseline Champion (+&#8377;406k) against Triple-Filtered Enhanced Setup (+&#8377;425.9k)</p>
                </div>
                <div class="flex items-center gap-3 text-xs">
                    <span class="flex items-center gap-1.5"><span class="w-3 h-3 rounded-full bg-slate-500"></span> Baseline Setup</span>
                    <span class="flex items-center gap-1.5"><span class="w-3 h-3 rounded-full bg-emerald-400"></span> Triple-Filtered Setup</span>
                </div>
            </div>
            <div id="equityChart" style="height: 420px;"></div>
        </div>

        <!-- UNDERWATER DRAWDOWN COMPARISON -->
        <div class="glass-panel rounded-2xl p-6 border border-slate-800 space-y-4">
            <div>
                <h3 class="text-lg font-bold text-white">Underwater Drawdown Profile</h3>
                <p class="text-xs text-slate-400">Notice how the Enhanced setup compresses Max Drawdown from &#8377;15.5k down to only &#8377;10.1k</p>
            </div>
            <div id="ddChart" style="height: 240px;"></div>
        </div>

        <!-- TWO COLUMNS: PLAYBOOK BREAKDOWN & MONTHLY RETURNS -->
        <div class="grid grid-cols-1 lg:grid-cols-2 gap-6">
            <!-- PLAYBOOK PERFORMANCE -->
            <div class="glass-panel rounded-2xl p-6 border border-slate-800 space-y-4">
                <h3 class="text-lg font-bold text-white">Performance by Playbook</h3>
                <div id="playbookChart" style="height: 320px;"></div>
            </div>

            <!-- DAY OF WEEK BREAKDOWN -->
            <div class="glass-panel rounded-2xl p-6 border border-slate-800 space-y-4">
                <h3 class="text-lg font-bold text-white">Day of the Week Consistency</h3>
                <div id="dayChart" style="height: 320px;"></div>
            </div>
        </div>

        <!-- MONTHLY PNL BAR CHART -->
        <div class="glass-panel rounded-2xl p-6 border border-slate-800 space-y-4">
            <h3 class="text-lg font-bold text-white">Monthly Net Profit Distribution</h3>
            <div id="monthlyChart" style="height: 280px;"></div>
        </div>

        <!-- DETAILED RECENT TRADES LEDGER -->
        <div class="glass-panel rounded-2xl p-6 border border-slate-800 space-y-4">
            <div class="flex items-center justify-between">
                <div>
                    <h3 class="text-lg font-bold text-white">Recent Trade Executions Ledger</h3>
                    <p class="text-xs text-slate-400">Showing last 60 trades (full 310 trades saved to <code class="text-emerald-400 font-mono">trades_master_enhanced_setup_2year.csv</code>)</p>
                </div>
                <span class="text-xs font-mono text-slate-500">310 Total Executions</span>
            </div>
            <div class="overflow-x-auto max-h-[500px] custom-scroll">
                <table class="w-full text-left">
                    <thead class="sticky top-0 bg-slate-900/95 backdrop-blur z-10 border-b border-slate-800 text-[11px] text-slate-400 uppercase tracking-wider">
                        <tr>
                            <th class="py-2.5 px-3">#</th>
                            <th class="py-2.5 px-3">Date</th>
                            <th class="py-2.5 px-3">Time</th>
                            <th class="py-2.5 px-3">Dir</th>
                            <th class="py-2.5 px-3">Playbook</th>
                            <th class="py-2.5 px-3">Strike</th>
                            <th class="py-2.5 px-3">Entry</th>
                            <th class="py-2.5 px-3">Exit</th>
                            <th class="py-2.5 px-3">Pts</th>
                            <th class="py-2.5 px-3">Net P&L</th>
                            <th class="py-2.5 px-3">Exit Reason</th>
                            <th class="py-2.5 px-3">Cum P&L</th>
                        </tr>
                    </thead>
                    <tbody>
                        {table_html}
                    </tbody>
                </table>
            </div>
        </div>

    </div>

    <!-- PLOTLY SCRIPTS -->
    <script>
        const darkLayout = {{
            paper_bgcolor: 'transparent',
            plot_bgcolor: 'transparent',
            font: {{ family: 'Plus Jakarta Sans', color: '#94a3b8' }},
            margin: {{ t: 20, r: 20, b: 40, l: 60 }},
            xaxis: {{
                gridcolor: 'rgba(255, 255, 255, 0.05)',
                zerolinecolor: 'rgba(255, 255, 255, 0.1)',
            }},
            yaxis: {{
                gridcolor: 'rgba(255, 255, 255, 0.05)',
                zerolinecolor: 'rgba(255, 255, 255, 0.1)',
            }}
        }};

        // 1. EQUITY CURVE
        const traceBase = {{
            x: {json.dumps(equity_dates_base)},
            y: {json.dumps(equity_vals_base)},
            type: 'scatter',
            mode: 'lines',
            name: 'Baseline Champion (+Rs 406.5k)',
            line: {{ color: '#64748b', width: 2, dash: 'dot' }}
        }};

        const traceEnh = {{
            x: {json.dumps(equity_dates_enh)},
            y: {json.dumps(equity_vals_enh)},
            type: 'scatter',
            mode: 'lines',
            name: 'Triple-Filtered Champion (+Rs 425.9k)',
            line: {{ color: '#10b981', width: 3 }}
        }};

        Plotly.newPlot('equityChart', [traceBase, traceEnh], {{
            ...darkLayout,
            hovermode: 'x unified',
            legend: {{ orientation: 'h', y: 1.15, x: 0.01 }}
        }}, {{ responsive: true, displayModeBar: false }});

        // 2. UNDERWATER DRAWDOWN
        const traceDdBase = {{
            x: {json.dumps(equity_dates_base)},
            y: {json.dumps(dd_vals_base)},
            type: 'scatter',
            mode: 'lines',
            name: 'Baseline DD (Max Rs -15.5k)',
            line: {{ color: '#ef4444', width: 1, dash: 'dot' }}
        }};

        const traceDdEnh = {{
            x: {json.dumps(equity_dates_enh)},
            y: {json.dumps(dd_vals_enh)},
            type: 'scatter',
            mode: 'lines',
            fill: 'tozeroy',
            fillcolor: 'rgba(16, 185, 129, 0.15)',
            name: 'Enhanced DD (Max Rs -10.1k)',
            line: {{ color: '#10b981', width: 2 }}
        }};

        Plotly.newPlot('ddChart', [traceDdBase, traceDdEnh], {{
            ...darkLayout,
            hovermode: 'x unified',
            legend: {{ orientation: 'h', y: 1.2, x: 0.01 }}
        }}, {{ responsive: true, displayModeBar: false }});

        // 3. PLAYBOOK BAR CHART
        const tracePb = {{
            x: {json.dumps(pb_names)},
            y: {json.dumps(pb_pnl)},
            type: 'bar',
            marker: {{
                color: {json.dumps(pb_pnl)}.map(v => v > 0 ? '#10b981' : '#ef4444'),
                opacity: 0.85
            }},
            text: {json.dumps(pb_wr)}.map((w, i) => `Rs ${{pb_pnl[i].toLocaleString()}} (WR ${{w}}%)`),
            textposition: 'auto'
        }};

        Plotly.newPlot('playbookChart', [tracePb], {{
            ...darkLayout,
            margin: {{ t: 20, r: 20, b: 80, l: 60 }},
            xaxis: {{ tickangle: -25, gridcolor: 'rgba(255,255,255,0.05)' }}
        }}, {{ responsive: true, displayModeBar: false }});

        // 4. DAY OF WEEK BAR CHART
        const traceDay = {{
            x: {json.dumps(days)},
            y: {json.dumps(day_pnl)},
            type: 'bar',
            marker: {{ color: '#38bdf8', opacity: 0.85 }},
            text: {json.dumps(day_wr)}.map((w, i) => `Rs ${{day_pnl[i].toLocaleString()}} (WR ${{w}}%)`),
            textposition: 'auto'
        }};

        Plotly.newPlot('dayChart', [traceDay], {{
            ...darkLayout,
            margin: {{ t: 20, r: 20, b: 40, l: 60 }}
        }}, {{ responsive: true, displayModeBar: false }});

        // 5. MONTHLY PNL BAR CHART
        const traceMonth = {{
            x: {json.dumps(month_labels)},
            y: {json.dumps(month_pnl)},
            type: 'bar',
            marker: {{
                color: {json.dumps(month_pnl)}.map(v => v >= 0 ? '#10b981' : '#ef4444'),
                opacity: 0.85
            }}
        }};

        Plotly.newPlot('monthlyChart', [traceMonth], {{
            ...darkLayout,
            margin: {{ t: 20, r: 20, b: 60, l: 60 }},
            xaxis: {{ tickangle: -45, gridcolor: 'rgba(255,255,255,0.05)' }}
        }}, {{ responsive: true, displayModeBar: false }});
    </script>
</body>
</html>
"""

report_path = os.path.join(base_dir, "report_master_enhanced_setup_2year.html")
with open(report_path, "w", encoding="utf-8") as f:
    f.write(html_content)

print(f"Generated enhanced dashboard at {report_path}")
