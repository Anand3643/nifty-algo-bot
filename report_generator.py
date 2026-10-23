"""
Interactive HTML Backtest Report Generator
Builds a modern, glassmorphic, institutional-grade analytics dashboard with interactive charts,
KPI metrics, drawdown analysis, and trade log visualizer.
"""
import os
import json
import pandas as pd
import numpy as np
from typing import Dict, Any, List
from config import BacktestConfig

class ReportGenerator:
    def __init__(self, output_path: str = "backtest_report.html"):
        self.output_path = output_path

    def generate(
        self,
        trades_df: pd.DataFrame,
        metrics: Dict[str, Any],
        config: BacktestConfig,
        spot_df: pd.DataFrame
    ) -> str:
        """
        Generates a standalone, beautiful HTML dashboard report.
        """
        # Prepare Equity Curve Data
        df = trades_df.copy()
        if not df.empty:
            df["entry_dt"] = pd.to_datetime(df["entry_time"])
            df["cum_pnl"] = df["net_pnl"].cumsum()
            df["equity"] = config.initial_capital + df["cum_pnl"]
            df["peak"] = df["equity"].cummax()
            df["drawdown"] = df["equity"] - df["peak"]
            df["drawdown_pct"] = (df["drawdown"] / df["peak"]) * 100.0

            equity_dates = df["exit_time"].tolist()
            equity_values = df["equity"].tolist()
            peak_values = df["peak"].tolist()
            dd_pct_values = df["drawdown_pct"].tolist()

            # Daily PnL for Bar Chart
            df["date"] = df["entry_dt"].dt.strftime("%Y-%m-%d")
            daily_pnl = df.groupby("date")["net_pnl"].sum().reset_index()
            daily_dates = daily_pnl["date"].tolist()
            daily_pnls = daily_pnl["net_pnl"].tolist()
            daily_colors = ["#10b981" if p >= 0 else "#ef4444" for p in daily_pnls]

            # Drop temporary datetime objects before serialization
            df_clean = df.drop(columns=["entry_dt"])
            trades_json = df_clean.to_dict(orient="records")
        else:
            equity_dates, equity_values, peak_values, dd_pct_values = [], [], [], []
            daily_dates, daily_pnls, daily_colors = [], [], []
            trades_json = []

        trades_json_str = json.dumps(trades_json, default=str)
        equity_dates_str = json.dumps(equity_dates, default=str)
        equity_values_str = json.dumps(equity_values, default=str)
        peak_values_str = json.dumps(peak_values, default=str)
        dd_pct_str = json.dumps(dd_pct_values, default=str)
        daily_dates_str = json.dumps(daily_dates, default=str)
        daily_pnls_str = json.dumps(daily_pnls, default=str)
        daily_colors_str = json.dumps(daily_colors, default=str)

        # Color helpers
        net_pnl = metrics.get("net_pnl", 0.0)
        pnl_color = "#10b981" if net_pnl >= 0 else "#ef4444"
        pnl_sign = "+" if net_pnl >= 0 else ""

        html_content = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>NIFTY Options Directional Backtest | Quant Report</title>
    <link rel="preconnect" href="https://fonts.googleapis.com">
    <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700;800&family=JetBrains+Mono:wght@400;600&display=swap" rel="stylesheet">
    <script src="https://cdn.plot.ly/plotly-2.35.2.min.js"></script>
    <style>
        :root {{
            --bg-base: #0B0F19;
            --bg-card: #111827;
            --bg-card-hover: #1F2937;
            --border: rgba(255, 255, 255, 0.08);
            --border-highlight: rgba(99, 102, 241, 0.3);
            --text-primary: #F9FAFB;
            --text-secondary: #9CA3AF;
            --text-muted: #6B7280;
            --accent-primary: #6366F1;
            --accent-cyan: #06B6D4;
            --success: #10B981;
            --success-glow: rgba(16, 185, 129, 0.15);
            --danger: #EF4444;
            --danger-glow: rgba(239, 68, 68, 0.15);
            --warning: #F59E0B;
        }}

        * {{
            box-sizing: border-box;
            margin: 0;
            padding: 0;
        }}

        body {{
            background-color: var(--bg-base);
            color: var(--text-primary);
            font-family: 'Inter', -apple-system, BlinkMacSystemFont, sans-serif;
            min-height: 100vh;
            padding: 24px 32px 64px 32px;
            overflow-x: hidden;
        }}

        .container {{
            max-width: 1440px;
            margin: 0 auto;
        }}

        /* Header Bar */
        .header {{
            display: flex;
            justify-content: space-between;
            align-items: center;
            background: linear-gradient(135deg, rgba(31, 41, 55, 0.6) 0%, rgba(17, 24, 39, 0.8) 100%);
            backdrop-filter: blur(12px);
            border: 1px solid var(--border);
            border-radius: 16px;
            padding: 24px 32px;
            margin-bottom: 24px;
            box-shadow: 0 10px 30px rgba(0, 0, 0, 0.4);
        }}

        .header-title-box h1 {{
            font-size: 26px;
            font-weight: 800;
            letter-spacing: -0.5px;
            background: linear-gradient(90deg, #FFFFFF, #93C5FD, #818CF8);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
            margin-bottom: 6px;
        }}

        .header-subtitle {{
            color: var(--text-secondary);
            font-size: 14px;
            display: flex;
            align-items: center;
            gap: 12px;
        }}

        .badge {{
            display: inline-flex;
            align-items: center;
            padding: 4px 10px;
            border-radius: 9999px;
            font-size: 12px;
            font-weight: 600;
            text-transform: uppercase;
            letter-spacing: 0.5px;
        }}

        .badge-live {{
            background: rgba(16, 185, 129, 0.2);
            color: var(--success);
            border: 1px solid rgba(16, 185, 129, 0.3);
        }}

        .badge-nifty {{
            background: rgba(99, 102, 241, 0.2);
            color: #A5B4FC;
            border: 1px solid rgba(99, 102, 241, 0.3);
        }}

        /* KPI Grid */
        .kpi-grid {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(210px, 1fr));
            gap: 16px;
            margin-bottom: 24px;
        }}

        .kpi-card {{
            background: var(--bg-card);
            border: 1px solid var(--border);
            border-radius: 14px;
            padding: 20px;
            transition: all 0.25s ease;
            position: relative;
            overflow: hidden;
        }}

        .kpi-card:hover {{
            transform: translateY(-2px);
            border-color: var(--border-highlight);
            box-shadow: 0 8px 24px rgba(0, 0, 0, 0.3);
        }}

        .kpi-title {{
            font-size: 12px;
            font-weight: 600;
            color: var(--text-secondary);
            text-transform: uppercase;
            letter-spacing: 0.8px;
            margin-bottom: 8px;
            display: flex;
            justify-content: space-between;
        }}

        .kpi-value {{
            font-size: 26px;
            font-weight: 800;
            letter-spacing: -0.5px;
            font-family: 'JetBrains Mono', monospace;
        }}

        .kpi-subtext {{
            font-size: 12px;
            color: var(--text-muted);
            margin-top: 6px;
        }}

        /* Main Content Grid */
        .charts-grid {{
            display: grid;
            grid-template-columns: 2fr 1fr;
            gap: 20px;
            margin-bottom: 24px;
        }}

        @media (max-width: 1024px) {{
            .charts-grid {{
                grid-template-columns: 1fr;
            }}
        }}

        .card {{
            background: var(--bg-card);
            border: 1px solid var(--border);
            border-radius: 16px;
            padding: 24px;
            box-shadow: 0 4px 20px rgba(0, 0, 0, 0.25);
        }}

        .card-header {{
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 18px;
        }}

        .card-title {{
            font-size: 16px;
            font-weight: 700;
            color: var(--text-primary);
            display: flex;
            align-items: center;
            gap: 8px;
        }}

        /* Trade Log Table */
        .table-controls {{
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 16px;
            gap: 16px;
            flex-wrap: wrap;
        }}

        .search-input {{
            background: rgba(255, 255, 255, 0.05);
            border: 1px solid var(--border);
            border-radius: 8px;
            padding: 8px 14px;
            color: var(--text-primary);
            font-size: 13px;
            outline: none;
            width: 260px;
        }}

        .search-input:focus {{
            border-color: var(--accent-primary);
        }}

        .filter-buttons {{
            display: flex;
            gap: 8px;
        }}

        .btn-filter {{
            background: rgba(255, 255, 255, 0.05);
            border: 1px solid var(--border);
            color: var(--text-secondary);
            padding: 6px 12px;
            border-radius: 6px;
            font-size: 12px;
            cursor: pointer;
            transition: all 0.2s;
        }}

        .btn-filter.active, .btn-filter:hover {{
            background: var(--accent-primary);
            color: #FFFFFF;
            border-color: var(--accent-primary);
        }}

        .table-responsive {{
            overflow-x: auto;
            max-height: 480px;
            border-radius: 10px;
            border: 1px solid var(--border);
        }}

        table {{
            width: 100%;
            border-collapse: collapse;
            font-size: 13px;
            text-align: left;
        }}

        thead {{
            background: #1F2937;
            position: sticky;
            top: 0;
            z-index: 10;
        }}

        th {{
            padding: 12px 14px;
            font-size: 11px;
            font-weight: 700;
            color: var(--text-secondary);
            text-transform: uppercase;
            letter-spacing: 0.5px;
            border-bottom: 1px solid var(--border);
        }}

        td {{
            padding: 12px 14px;
            border-bottom: 1px solid rgba(255, 255, 255, 0.04);
            font-family: 'JetBrains Mono', monospace;
            font-size: 12px;
        }}

        tr:hover td {{
            background: rgba(255, 255, 255, 0.02);
        }}

        .badge-ce {{
            background: rgba(16, 185, 129, 0.15);
            color: #34D399;
            padding: 3px 8px;
            border-radius: 4px;
            font-weight: 600;
            font-size: 11px;
        }}

        .badge-pe {{
            background: rgba(239, 68, 68, 0.15);
            color: #F87171;
            padding: 3px 8px;
            border-radius: 4px;
            font-weight: 600;
            font-size: 11px;
        }}

        .status-target {{
            color: var(--success);
            font-weight: 600;
        }}

        .status-sl {{
            color: var(--danger);
            font-weight: 600;
        }}

        .status-trail {{
            color: var(--accent-cyan);
            font-weight: 600;
        }}

        .status-eod {{
            color: var(--warning);
            font-weight: 600;
        }}

        /* Breakdown Stats List */
        .stat-row {{
            display: flex;
            justify-content: space-between;
            padding: 10px 0;
            border-bottom: 1px solid rgba(255, 255, 255, 0.05);
            font-size: 13px;
        }}

        .stat-row:last-child {{
            border-bottom: none;
        }}

        .stat-label {{
            color: var(--text-secondary);
        }}

        .stat-value {{
            font-weight: 600;
            font-family: 'JetBrains Mono', monospace;
        }}
    </style>
</head>
<body>
    <div class="container">
        <!-- Header -->
        <header class="header">
            <div class="header-title-box">
                <h1>NIFTY Options Directional Buying Backtest</h1>
                <div class="header-subtitle">
                    <span class="badge badge-live">Verified Quant Engine</span>
                    <span class="badge badge-nifty">NIFTY 50 (ATM CE / PE)</span>
                    <span>15m ORB + Supertrend & EMA Momentum Filter</span>
                </div>
            </div>
            <div style="text-align: right;">
                <div style="font-size: 12px; color: var(--text-muted);">INITIAL CAPITAL</div>
                <div style="font-size: 22px; font-weight: 800; font-family: 'JetBrains Mono';">₹{config.initial_capital:,.2f}</div>
                <div style="font-size: 11px; color: var(--text-secondary); margin-top: 4px;">Lots: {config.num_lots} ({config.num_lots * config.lot_size} Qty)</div>
            </div>
        </header>

        <!-- KPI Grid -->
        <div class="kpi-grid">
            <div class="kpi-card" style="border-left: 4px solid {pnl_color};">
                <div class="kpi-title">Net Realized P&L</div>
                <div class="kpi-value" style="color: {pnl_color};">{pnl_sign}₹{net_pnl:,.2f}</div>
                <div class="kpi-subtext">ROI: {pnl_sign}{metrics.get('roi_pct', 0.0):.2f}%</div>
            </div>

            <div class="kpi-card">
                <div class="kpi-title">Win Rate</div>
                <div class="kpi-value" style="color: #60A5FA;">{metrics.get('win_rate', 0.0):.1f}%</div>
                <div class="kpi-subtext">{metrics.get('win_count', 0)} Wins / {metrics.get('loss_count', 0)} Losses</div>
            </div>

            <div class="kpi-card">
                <div class="kpi-title">Profit Factor</div>
                <div class="kpi-value" style="color: #FBBF24;">{metrics.get('profit_factor', 0.0):.2f}</div>
                <div class="kpi-subtext">Gross Win / Gross Loss</div>
            </div>

            <div class="kpi-card">
                <div class="kpi-title">Sharpe Ratio</div>
                <div class="kpi-value" style="color: #A78BFA;">{metrics.get('sharpe_ratio', 0.0):.2f}</div>
                <div class="kpi-subtext">Sortino: {metrics.get('sortino_ratio', 0.0):.2f}</div>
            </div>

            <div class="kpi-card">
                <div class="kpi-title">Max Drawdown</div>
                <div class="kpi-value" style="color: #F87171;">-{metrics.get('max_drawdown_pct', 0.0):.2f}%</div>
                <div class="kpi-subtext">-₹{metrics.get('max_drawdown_amount', 0.0):,.2f} Peak-to-Trough</div>
            </div>

            <div class="kpi-card">
                <div class="kpi-title">Avg Trade P&L</div>
                <div class="kpi-value" style="color: {pnl_color};">{pnl_sign}₹{metrics.get('avg_trade_pnl', 0.0):,.2f}</div>
                <div class="kpi-subtext">Avg Win: ₹{metrics.get('avg_win', 0.0):,.0f} | Avg Loss: ₹{metrics.get('avg_loss', 0.0):,.0f}</div>
            </div>

            <div class="kpi-card">
                <div class="kpi-title">Total Charges & STT</div>
                <div class="kpi-value" style="color: #9CA3AF;">₹{metrics.get('total_charges', 0.0):,.2f}</div>
                <div class="kpi-subtext">₹40 Brokerage + 0.0625% STT</div>
            </div>
        </div>

        <!-- Charts Row 1 -->
        <div class="charts-grid">
            <div class="card">
                <div class="card-header">
                    <div class="card-title">📈 Cumulative Equity Curve (with Peak High-Water Mark)</div>
                </div>
                <div id="equityChart" style="height: 380px;"></div>
            </div>

            <div class="card">
                <div class="card-header">
                    <div class="card-title">🎯 Strategy & Signal Analytics</div>
                </div>
                <div class="stat-row">
                    <span class="stat-label">Total Trades</span>
                    <span class="stat-value">{metrics.get('total_trades', 0)}</span>
                </div>
                <div class="stat-row">
                    <span class="stat-label">Call (CE) Trades</span>
                    <span class="stat-value">{metrics.get('ce_trade_count', 0)} (Win: {metrics.get('ce_win_rate', 0)}% | PnL: ₹{metrics.get('ce_net_pnl', 0):,.0f})</span>
                </div>
                <div class="stat-row">
                    <span class="stat-label">Put (PE) Trades</span>
                    <span class="stat-value">{metrics.get('pe_trade_count', 0)} (Win: {metrics.get('pe_win_rate', 0)}% | PnL: ₹{metrics.get('pe_net_pnl', 0):,.0f})</span>
                </div>
                <div class="stat-row">
                    <span class="stat-label">Realized Risk / Reward</span>
                    <span class="stat-value">1 : {metrics.get('risk_reward_ratio', 0.0):.2f}</span>
                </div>
                <div class="stat-row">
                    <span class="stat-label">Avg Holding Time</span>
                    <span class="stat-value">{metrics.get('avg_holding_mins', 0)} Mins</span>
                </div>
                <div class="stat-row">
                    <span class="stat-label">Max Consec. Wins / Losses</span>
                    <span class="stat-value">{metrics.get('max_consecutive_wins', 0)} / {metrics.get('max_consecutive_losses', 0)}</span>
                </div>
                <div class="stat-row">
                    <span class="stat-label">Opening Range (ORB)</span>
                    <span class="stat-value">{config.orb_period_minutes} Minutes</span>
                </div>
                <div class="stat-row">
                    <span class="stat-label">Stop Loss / Target</span>
                    <span class="stat-value">{int(config.sl_pct*100)}% SL / {int(config.target_pct*100)}% Target</span>
                </div>
                <div class="stat-row">
                    <span class="stat-label">Trailing SL</span>
                    <span class="stat-value">{f"Active (+{int(config.trail_trigger_pct*100)}% triggers)" if config.enable_trailing_sl else "Disabled"}</span>
                </div>
                <div class="stat-row">
                    <span class="stat-label">OI & PCR Filter</span>
                    <span class="stat-value" style="color: #67E8F9;">{"Active (Bullish > " + str(config.pcr_bullish_threshold) + " | Bearish < " + str(config.pcr_bearish_threshold) + ")" if config.use_oi_filter else "Disabled"}</span>
                </div>
                <div class="stat-row">
                    <span class="stat-label">OI Buildup Quadrant</span>
                    <span class="stat-value" style="color: #C4B5FD;">{"Active (Buildup & Covering)" if config.use_oi_buildup_filter else "Disabled"}</span>
                </div>
            </div>
        </div>

        <!-- Charts Row 2 -->
        <div class="charts-grid">
            <div class="card">
                <div class="card-header">
                    <div class="card-title">🌊 Underwater Drawdown (%)</div>
                </div>
                <div id="drawdownChart" style="height: 260px;"></div>
            </div>

            <div class="card">
                <div class="card-header">
                    <div class="card-title">📊 Daily Net P&L Distribution</div>
                </div>
                <div id="dailyPnlChart" style="height: 260px;"></div>
            </div>
        </div>

        <!-- Trade Log Section -->
        <div class="card">
            <div class="card-header">
                <div class="card-title">📜 Verified Trade Execution Book ({len(df)} Trades)</div>
            </div>
            
            <div class="table-controls">
                <input type="text" id="searchInput" class="search-input" placeholder="Search strike, CE/PE, reason...">
                <div class="filter-buttons">
                    <button class="btn-filter active" onclick="filterTrades('ALL')">All</button>
                    <button class="btn-filter" onclick="filterTrades('CE')">Calls (CE)</button>
                    <button class="btn-filter" onclick="filterTrades('PE')">Puts (PE)</button>
                    <button class="btn-filter" onclick="filterTrades('WIN')">Winning</button>
                    <button class="btn-filter" onclick="filterTrades('LOSS')">Losing</button>
                </div>
            </div>

            <div class="table-responsive">
                <table id="tradeTable">
                    <thead>
                        <tr>
                            <th>#</th>
                            <th>Entry Time</th>
                            <th>Exit Time</th>
                            <th>Instrument</th>
                            <th>Spot Entry</th>
                            <th>Fill Premium</th>
                            <th>Exit Premium</th>
                            <th>Net P&L (₹)</th>
                            <th>Return %</th>
                            <th>Exit Reason</th>
                            <th>PCR</th>
                            <th>OI Quadrant</th>
                            <th>Delta</th>
                            <th>Duration</th>
                        </tr>
                    </thead>
                    <tbody id="tradeTableBody">
                    </tbody>
                </table>
            </div>
        </div>
    </div>

    <script>
        const tradesData = {trades_json_str};

        // 1. Plotly Equity Chart
        const equityTrace = {{
            x: {equity_dates_str},
            y: {equity_values_str},
            type: 'scatter',
            mode: 'lines',
            name: 'Strategy Equity',
            line: {{ color: '#10B981', width: 2.5 }}
        }};

        const peakTrace = {{
            x: {equity_dates_str},
            y: {peak_values_str},
            type: 'scatter',
            mode: 'lines',
            name: 'Peak Watermark',
            line: {{ color: 'rgba(255, 255, 255, 0.25)', width: 1.5, dash: 'dot' }}
        }};

        const layoutDark = {{
            paper_bgcolor: 'transparent',
            plot_bgcolor: 'transparent',
            margin: {{ l: 50, r: 20, t: 20, b: 40 }},
            font: {{ family: 'Inter', color: '#9CA3AF' }},
            xaxis: {{ gridcolor: 'rgba(255, 255, 255, 0.05)', showgrid: true }},
            yaxis: {{ gridcolor: 'rgba(255, 255, 255, 0.05)', showgrid: true, tickformat: '₹,d' }},
            legend: {{ orientation: 'h', y: 1.15, x: 0 }}
        }};

        Plotly.newPlot('equityChart', [equityTrace, peakTrace], layoutDark, {{ responsive: true, displayModeBar: false }});

        // 2. Underwater Drawdown Chart
        const ddTrace = {{
            x: {equity_dates_str},
            y: {dd_pct_str},
            type: 'scatter',
            fill: 'tozeroy',
            mode: 'lines',
            name: 'Drawdown %',
            fillcolor: 'rgba(239, 68, 68, 0.2)',
            line: {{ color: '#EF4444', width: 1.5 }}
        }};

        const ddLayout = {{
            ...layoutDark,
            yaxis: {{ gridcolor: 'rgba(255, 255, 255, 0.05)', showgrid: true, ticksuffix: '%' }},
            showlegend: false
        }};

        Plotly.newPlot('drawdownChart', [ddTrace], ddLayout, {{ responsive: true, displayModeBar: false }});

        // 3. Daily P&L Chart
        const dailyTrace = {{
            x: {daily_dates_str},
            y: {daily_pnls_str},
            type: 'bar',
            marker: {{ color: {daily_colors_str} }},
            name: 'Daily PnL'
        }};

        Plotly.newPlot('dailyPnlChart', [dailyTrace], {{ ...layoutDark, showlegend: false }}, {{ responsive: true, displayModeBar: false }});

        // Render Trade Table
        function renderTable(trades) {{
            const tbody = document.getElementById('tradeTableBody');
            tbody.innerHTML = '';
            trades.forEach(t => {{
                const tr = document.createElement('tr');
                const pnlClass = t.net_pnl >= 0 ? '#10B981' : '#EF4444';
                const pnlSign = t.net_pnl >= 0 ? '+' : '';
                
                let reasonClass = 'status-eod';
                if (t.exit_reason === 'Target Hit') reasonClass = 'status-target';
                else if (t.exit_reason === 'Stop Loss') reasonClass = 'status-sl';
                else if (t.exit_reason.includes('Trailing')) reasonClass = 'status-trail';

                const optBadge = t.option_type === 'CE' ? '<span class="badge-ce">BUY CE</span>' : '<span class="badge-pe">BUY PE</span>';
                const quadBadge = `<span style="background: rgba(167, 139, 250, 0.15); color: #C4B5FD; padding: 2px 6px; border-radius: 4px; font-size: 11px;">${{t.oi_quadrant || 'N/A'}}</span>`;

                tr.innerHTML = `
                    <td>${{t.trade_id}}</td>
                    <td>${{t.entry_time}}</td>
                    <td>${{t.exit_time}}</td>
                    <td>${{optBadge}} <strong>${{t.instrument}}</strong></td>
                    <td>₹${{t.spot_entry.toFixed(1)}}</td>
                    <td>₹${{t.fill_price.toFixed(2)}}</td>
                    <td>₹${{t.exit_price.toFixed(2)}}</td>
                    <td style="color: ${{pnlClass}}; font-weight: 700;">${{pnlSign}}₹${{t.net_pnl.toLocaleString('en-IN', {{minimumFractionDigits: 2}})}}</td>
                    <td style="color: ${{pnlClass}};">${{pnlSign}}${{t.return_pct.toFixed(2)}}%</td>
                    <td class="${{reasonClass}}">${{t.exit_reason}}</td>
                    <td style="font-weight: 700; color: #67E8F9;">${{t.entry_pcr ? t.entry_pcr.toFixed(2) : '1.00'}}</td>
                    <td>${{quadBadge}}</td>
                    <td>${{t.entry_delta.toFixed(2)}}</td>
                    <td>${{t.holding_mins}}m</td>
                `;
                tbody.appendChild(tr);
            }});
        }}

        renderTable(tradesData);

        // Filter and Search
        let currentFilter = 'ALL';
        function filterTrades(type) {{
            currentFilter = type;
            document.querySelectorAll('.btn-filter').forEach(b => b.classList.remove('active'));
            event.target.classList.add('active');
            applyFilters();
        }}

        document.getElementById('searchInput').addEventListener('input', applyFilters);

        function applyFilters() {{
            const query = document.getElementById('searchInput').value.toLowerCase();
            let filtered = tradesData.filter(t => {{
                if (currentFilter === 'CE' && t.option_type !== 'CE') return false;
                if (currentFilter === 'PE' && t.option_type !== 'PE') return false;
                if (currentFilter === 'WIN' && t.net_pnl <= 0) return false;
                if (currentFilter === 'LOSS' && t.net_pnl > 0) return false;
                
                if (query) {{
                    const matchText = `${{t.instrument}} ${{t.exit_reason}} ${{t.entry_time}} ${{t.exit_time}}`.toLowerCase();
                    return matchText.includes(query);
                }}
                return true;
            }});
            renderTable(filtered);
        }}
    </script>
</body>
</html>
"""
        with open(self.output_path, "w", encoding="utf-8") as f:
            f.write(html_content)

        print(f"[ReportGenerator] Saved interactive report to: {self.output_path}")
        return self.output_path
