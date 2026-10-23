"""
NIFTY Options (1 Lot = 65 Qty) Support & Resistance Institutional Backtesting Engine
Executes intraday ATM Call (CE) & Put (PE) Options Trading using:
1. Verified Step Delta & Locked SPR Support & Resistance Levels
2. Fixed Stop Loss (SL) and Take Profit (TP) Execution:
   - Mode 1: Fixed Premium Points (e.g. 25 pts SL / 30 pts TP, 30 pts SL / 30 pts TP)
   - Mode 2: Fixed Percentage of Entry Premium (e.g. 30% SL / 60% TP, 25% SL / 50% TP)
3. Black-Scholes Dynamic Pricing with Time Decay (Theta), Implied Volatility & DTE
4. Realistic Indian Options Cost Model (Flat Rs 20/order Brokerage, STT on sell, Txn Charges, GST)
5. Standalone Interactive Visual HTML Dashboard Generator
"""
import os
import sys
import json
import argparse
from datetime import datetime, time
import math
import numpy as np
import pandas as pd
SQRT2 = math.sqrt(2.0)

def std_norm_cdf(x: float) -> float:
    return 0.5 * (1.0 + math.erf(x / SQRT2))

class BlackScholesPricing:
    @staticmethod
    def calculate_price(spot: float, strike: float, tte: float, vol: float, r: float = 0.065, is_call: bool = True) -> float:
        if tte <= 0.0001:
            return max(0.5, (spot - strike) if is_call else (strike - spot))
        denom = vol * math.sqrt(tte)
        d1 = (math.log(spot / strike) + (r + 0.5 * vol**2) * tte) / denom
        d2 = d1 - denom
        if is_call:
            p = spot * std_norm_cdf(d1) - strike * math.exp(-r * tte) * std_norm_cdf(d2)
        else:
            p = strike * math.exp(-r * tte) * std_norm_cdf(-d2) - spot * std_norm_cdf(-d1)
        return max(0.5, p)

class NiftySREngine:
    @staticmethod
    def calculate_levels(high: float, low: float, close: float, model: str = "formula") -> dict:
        r = high - low
        c = close
        p = round(((high + low + close) / 3.0) / 5) * 5
        bc = round(((high + low) / 2.0) / 5) * 5
        tc = round(((2.0 * p) - bc) / 5) * 5

        if model == "step":
            r1 = round((c + 50) / 5) * 5
            r2 = round((c + 115) / 5) * 5
            r3 = round((c + 180) / 5) * 5
            r4 = round((c + 260) / 5) * 5

            s1 = round((c - 50) / 5) * 5
            s2 = round((c - 100) / 5) * 5
            s3 = round((c - 170) / 5) * 5
            s4 = round((c - 260) / 5) * 5
        else:
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

        return {
            "pivot": p, "bc": bc, "tc": tc,
            "cpr_top": cpr_top, "cpr_bot": cpr_bot,
            "r1": r1, "r2": r2, "r3": r3, "r4": r4,
            "s1": s1, "s2": s2, "s3": s3, "s4": s4,
            "range": r, "prev_close": c
        }

def run_options_backtest(
    sl_mode: str = "points",
    sl_val: float = 25.0,
    tp_val: float = None,
    rr: float = 2.0,
    trail: bool = False,
    strategy_mode: str = "breakout", # "breakout" (default) or "reversal"
    break_levels: str = "r1_s1",    # "r1_s1" or "all"
    model: str = "formula",
    lot_size: int = 65,
    initial_capital: float = 50000.0,
    timeframe: str = "5m",
    max_trades_per_day: int = 1,
    slippage: float = 0.005,
    vol: float = 0.135
):
    if tp_val is None:
        tp_val = sl_val * rr
    base_dir = os.path.dirname(os.path.abspath(__file__))
    nifty_dir = os.path.join(base_dir, "nifty_data")

    candle_file = "NIFTY_5min.csv" if timeframe == "5m" else "NIFTY_15min.csv"
    candle_path = os.path.join(nifty_dir, "candles", candle_file)
    daily_path = os.path.join(nifty_dir, "candles", "NIFTY_1day.csv")

    if not os.path.exists(candle_path):
        raise FileNotFoundError(f"Data not found: {candle_path}")

    df_intra = pd.read_csv(candle_path)
    df_intra["datetime"] = pd.to_datetime(df_intra["datetime"])
    df_intra.sort_values("datetime", inplace=True)
    df_intra.set_index("datetime", inplace=True)

    df_1d = pd.read_csv(daily_path)
    df_1d["datetime"] = pd.to_datetime(df_1d["datetime"]).dt.date
    df_1d.drop_duplicates(subset=["datetime"], inplace=True)
    df_1d.set_index("datetime", inplace=True)

    unique_dates = sorted(list(set(df_intra.index.date)))

    sl_label = f"{sl_val:.0f} pts" if sl_mode == "points" else f"{int(sl_val*100)}%"
    tp_label = f"{tp_val:.0f} pts" if sl_mode == "points" else f"{int(tp_val*100)}%"

    print("=" * 85)
    print("   NIFTY OPTIONS 1 LOT (65 QTY) INTRADAY S&R BREAKOUT/BREAKDOWN BACKTEST")
    print(f"   Strategy: {strategy_mode.upper()} ON {break_levels.upper()} LEVELS | Risk-to-Reward: 1:{rr:g}")
    print(f"   Fixed SL: {sl_label} | Fixed TP: {tp_label} | Trailing: {'YES' if trail else 'NO'}")
    print(f"   Position: 1 Lot = {lot_size} Qty | Capital: Rs {initial_capital:,.2f} | Timeframe: {timeframe.upper()}")
    print(f"   Sessions: {len(unique_dates)} from {unique_dates[0]} to {unique_dates[-1]}")
    print("=" * 85)

    # Cost parameters
    BROKERAGE_ORDER = 20.0  # Rs 20/order
    STT_RATE = 0.000625     # 0.0625% on sell side option turnover
    EXCHANGE_TXN_RATE = 0.00053 # 0.053% NSE options turnover
    GST_RATE = 0.18         # 18% on (Brokerage + Txn charges)

    trades = []
    equity = initial_capital

    for current_date in unique_dates:
        priors = [d for d in df_1d.index if d < current_date]
        if not priors:
            continue
        prev_row = df_1d.loc[priors[-1]]

        lvl = NiftySREngine.calculate_levels(
            float(prev_row["high"]), float(prev_row["low"]), float(prev_row["close"]), model=model
        )

        day_bars = df_intra[df_intra.index.date == current_date]
        if len(day_bars) < 12:
            continue

        day_open = float(day_bars["open"].iloc[0])

        dow = current_date.weekday()
        dte = max(0.5, (3 - dow) % 7 + 0.5) / 365.0

        in_trade = False
        trade_dir = None
        strike = 0
        entry_spot = 0.0
        entry_prem = 0.0
        sl_prem = 0.0
        tp_prem = 0.0
        entry_time = None
        playbook = ""
        trades_today = 0
        max_fav_prem = 0.0

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
                is_call = (trade_dir == "CE")
                prem_close = BlackScholesPricing.calculate_price(spot, strike, dte, vol, is_call=is_call)
                prem_high = BlackScholesPricing.calculate_price(b_high, strike, dte, vol, is_call=is_call) if is_call else BlackScholesPricing.calculate_price(b_low, strike, dte, vol, is_call=is_call)
                prem_low = BlackScholesPricing.calculate_price(b_low, strike, dte, vol, is_call=is_call) if is_call else BlackScholesPricing.calculate_price(b_high, strike, dte, vol, is_call=is_call)

                max_fav_prem = max(max_fav_prem, prem_high)

                # Dynamic Trailing Stop Loss
                if trail:
                    if sl_mode == "points":
                        if max_fav_prem >= entry_prem + sl_val:
                            sl_prem = max(sl_prem, entry_prem + 4.0)
                        if max_fav_prem >= entry_prem + 2.0 * sl_val:
                            sl_prem = max(sl_prem, entry_prem + sl_val)
                    else:
                        if max_fav_prem >= entry_prem * (1.0 + sl_val):
                            sl_prem = max(sl_prem, entry_prem * 1.03)
                        if max_fav_prem >= entry_prem * (1.0 + 2.0 * sl_val):
                            sl_prem = max(sl_prem, entry_prem * (1.0 + sl_val))

                hit_tp = (prem_high >= tp_prem)
                hit_sl = (prem_low <= sl_prem)
                hit_eod = (t >= time(15, 10))

                if hit_tp or hit_sl or hit_eod:
                    if hit_tp:
                        exit_raw = tp_prem
                        reason = f"TARGET 1:{rr:g} HIT"
                    elif hit_sl:
                        exit_raw = sl_prem
                        initial_sl = (entry_prem - sl_val) if sl_mode == "points" else entry_prem * (1.0 - sl_val)
                        reason = "TRAILING SL" if (sl_prem > initial_sl) else "STOP LOSS"
                    else:
                        exit_raw = prem_close
                        reason = "EOD EXIT"

                    fill_entry = entry_prem * (1.0 + slippage)
                    fill_exit = max(0.5, exit_raw * (1.0 - slippage))

                    pts_diff = fill_exit - fill_entry
                    gross_pnl = pts_diff * lot_size

                    # Statutory options costs
                    sell_turnover = fill_exit * lot_size
                    buy_turnover = fill_entry * lot_size
                    stt = sell_turnover * STT_RATE
                    txn_charges = (buy_turnover + sell_turnover) * EXCHANGE_TXN_RATE
                    brokerage = 2 * BROKERAGE_ORDER
                    gst = (brokerage + txn_charges) * GST_RATE
                    total_costs = brokerage + stt + txn_charges + gst

                    net_pnl = gross_pnl - total_costs
                    equity += net_pnl
                    ret_pct = (pts_diff / fill_entry) * 100.0

                    trades.append({
                        "Date": current_date.strftime("%Y-%m-%d"),
                        "Time": entry_time.strftime("%H:%M"),
                        "Exit_Time": bar.name.strftime("%H:%M"),
                        "Instrument": f"NIFTY {strike} {trade_dir}",
                        "Type": trade_dir,
                        "Strike": strike,
                        "Playbook": playbook,
                        "Lots": 1,
                        "Qty": lot_size,
                        "Entry_Spot": round(entry_spot, 1),
                        "Exit_Spot": round(spot, 1),
                        "Entry_Prem": round(fill_entry, 2),
                        "Exit_Prem": round(fill_exit, 2),
                        "Prem_Pts": round(pts_diff, 2),
                        "Gross_PnL": round(gross_pnl, 2),
                        "Costs": round(total_costs, 2),
                        "Net_PnL": round(net_pnl, 2),
                        "Return_Pct": round(ret_pct, 2),
                        "Capital": round(equity, 2),
                        "Result": reason,
                        "Pivot": lvl["pivot"],
                        "R1": lvl["r1"], "R2": lvl["r2"],
                        "S1": lvl["s1"], "S2": lvl["s2"]
                    })

                    in_trade = False
                    trades_today += 1
                    continue

            # -------------------------------------------------------------
            # ENTRY CHECK (Break Support & Resistance Playbooks)
            # -------------------------------------------------------------
            if not in_trade and trades_today < max_trades_per_day:
                if t < time(9, 25) or t > time(14, 45):
                    continue
                if b_range < 5:
                    continue

                prev_c = float(prev_bar["close"])
                bull_bar = (spot > b_open) and ((spot - b_open) >= 0.35 * b_range)
                bear_bar = (spot < b_open) and ((b_open - spot) >= 0.35 * b_range)

                take_trade = False
                td = None
                pb = ""

                if strategy_mode == "breakout":
                    # 1. Break Resistance Triggers (Buy ATM CE)
                    r1_break = (prev_c <= lvl["r1"]) and (spot > lvl["r1"]) and bull_bar
                    r2_break = (prev_c <= lvl["r2"]) and (spot > lvl["r2"]) and bull_bar
                    cpr_up = (prev_c <= lvl["cpr_top"]) and (spot > lvl["cpr_top"]) and bull_bar and (day_open >= lvl["cpr_bot"])

                    # 2. Break Support Triggers (Buy ATM PE)
                    s1_break = (prev_c >= lvl["s1"]) and (spot < lvl["s1"]) and bear_bar
                    s2_break = (prev_c >= lvl["s2"]) and (spot < lvl["s2"]) and bear_bar
                    cpr_dn = (prev_c >= lvl["cpr_bot"]) and (spot < lvl["cpr_bot"]) and bear_bar and (day_open <= lvl["cpr_top"])

                    if break_levels == "r1_s1":
                        if r1_break:
                            td = "CE"; pb = "Break Resistance (R1 Breakout)"; take_trade = True
                        elif s1_break:
                            td = "PE"; pb = "Break Support (S1 Breakdown)"; take_trade = True
                    else:
                        if r1_break:
                            td = "CE"; pb = "Break Resistance (R1 Breakout)"; take_trade = True
                        elif s1_break:
                            td = "PE"; pb = "Break Support (S1 Breakdown)"; take_trade = True
                        elif r2_break:
                            td = "CE"; pb = "Break Resistance (R2 Expansion)"; take_trade = True
                        elif s2_break:
                            td = "PE"; pb = "Break Support (S2 Flush)"; take_trade = True
                        elif cpr_up:
                            td = "CE"; pb = "Break Resistance (CPR Top Breakout)"; take_trade = True
                        elif cpr_dn:
                            td = "PE"; pb = "Break Support (CPR Bot Breakdown)"; take_trade = True
                else:
                    # Reversal / Bounce Playbooks
                    tested_sup = (b_low <= lvl["cpr_top"] <= b_high) or (b_low <= lvl["s1"] <= b_high)
                    bull_rej = (spot > max(lvl["s1"], lvl["cpr_top"])) and ((min(b_open, spot) - b_low) >= 0.38 * b_range)
                    if tested_sup and bull_rej and (day_open >= lvl["cpr_bot"]):
                        td = "CE"; pb = "Bullish Support Bounce (CPR/S1)"; take_trade = True

                    tested_res = (b_high >= lvl["r2"])
                    bear_rej = (spot < lvl["r2"]) and ((b_high - max(b_open, spot)) >= 0.38 * b_range)
                    if not take_trade and tested_res and bear_rej:
                        td = "PE"; pb = "R2 Resistance Reversal"; take_trade = True

                    s1_break_rev = (prev_c >= lvl["s1"]) and (spot < lvl["s1"]) and ((b_open - spot) >= 0.45 * b_range)
                    if not take_trade and s1_break_rev and (day_open <= lvl["cpr_top"]):
                        td = "PE"; pb = "S1 Breakdown Flush"; take_trade = True

                    tested_s2 = (b_low <= lvl["s2"])
                    s2_bull = (spot > lvl["s2"]) and ((min(b_open, spot) - b_low) >= 0.38 * b_range)
                    if not take_trade and tested_s2 and s2_bull:
                        td = "CE"; pb = "S2 Sweep Reversal"; take_trade = True

                if take_trade:
                    in_trade = True
                    trade_dir = td
                    playbook = pb
                    strike = int(round(spot / 50) * 50)
                    entry_spot = spot
                    is_call = (trade_dir == "CE")
                    entry_prem = BlackScholesPricing.calculate_price(spot, strike, dte, vol, is_call=is_call)
                    if sl_mode == "points":
                        sl_prem = max(0.5, entry_prem - sl_val)
                        tp_prem = entry_prem + tp_val
                    else:
                        sl_prem = entry_prem * (1.0 - sl_val)
                        tp_prem = entry_prem * (1.0 + tp_val)
                    entry_time = bar.name
                    max_fav_prem = entry_prem
                    continue

    df_trades = pd.DataFrame(trades)
    output_csv = os.path.join(base_dir, "trades_nifty_options_1lot_65qty.csv")
    df_trades.to_csv(output_csv, index=False)

    total_trades = len(df_trades)
    if total_trades == 0:
        print("[!] No trades executed.")
        return

    wins = df_trades[df_trades["Net_PnL"] > 0]
    losses = df_trades[df_trades["Net_PnL"] <= 0]
    win_rate = (len(wins) / total_trades) * 100.0

    total_pts = df_trades["Prem_Pts"].sum()
    total_gross = df_trades["Gross_PnL"].sum()
    total_costs = df_trades["Costs"].sum()
    total_net = df_trades["Net_PnL"].sum()
    roi_pct = (total_net / initial_capital) * 100.0

    gross_profit = wins["Gross_PnL"].sum() if len(wins) else 0.0
    gross_loss = abs(losses["Gross_PnL"].sum()) if len(losses) else 0.0
    profit_factor = (gross_profit / gross_loss) if gross_loss > 0 else 99.0

    avg_win_pts = wins["Prem_Pts"].mean() if len(wins) else 0.0
    avg_loss_pts = abs(losses["Prem_Pts"].mean()) if len(losses) else 0.0
    rr_ratio = (avg_win_pts / avg_loss_pts) if avg_loss_pts > 0 else 0.0

    peak = df_trades["Capital"].cummax()
    drawdown = df_trades["Capital"] - peak
    max_dd_val = abs(drawdown.min())
    max_dd_pct = (max_dd_val / initial_capital) * 100.0

    daily_ret = df_trades.groupby("Date")["Net_PnL"].sum()
    sharpe = (daily_ret.mean() / daily_ret.std()) * np.sqrt(252) if daily_ret.std() > 0 else 0.0

    print("\n" + "=" * 60)
    print("      NIFTY OPTIONS (1 LOT = 65 QTY) BACKTEST RESULTS")
    print("=" * 60)
    print(f"Contract Traded        : NIFTY ATM Options (1 Lot = {lot_size} Qty)")
    print(f"Fixed SL / TP Rule     : SL: {sl_label} | TP: {tp_label}")
    print(f"Total Completed Trades : {total_trades}")
    print(f"Winning Trades         : {len(wins)} ({win_rate:.1f}%)")
    print(f"Losing Trades          : {len(losses)} ({100-win_rate:.1f}%)")
    print(f"Total Premium Points   : {total_pts:+.1f} pts (Avg {total_pts/total_trades:+.1f} pts/trade)")
    print(f"Gross P&L              : Rs {total_gross:+,.2f}")
    print(f"Total Costs & Taxes    : Rs {total_costs:,.2f} (Avg Rs {total_costs/total_trades:.1f}/trade)")
    print(f"Total Net PnL (Rs)     : Rs {total_net:+,.2f} ({roi_pct:+.2f}% on Rs {initial_capital:,.0f})")
    print(f"Profit Factor          : {profit_factor:.2f}")
    print(f"Average Win / Loss     : +{avg_win_pts:.1f} pts / -{avg_loss_pts:.1f} pts (RR: {rr_ratio:.2f}:1)")
    print(f"Max Peak Drawdown      : Rs {max_dd_val:,.2f} (-{max_dd_pct:.2f}%)")
    print(f"Sharpe Ratio (Ann.)    : {sharpe:.2f}")
    print("=" * 60)

    print("\n[+] Breakdown by Playbook:")
    for pb, g in df_trades.groupby("Playbook"):
        w = len(g[g["Net_PnL"] > 0])
        pnl = g["Net_PnL"].sum()
        pts = g["Prem_Pts"].sum()
        print(f"  - {pb:32s}: {len(g):2d} trades | Net PnL: Rs {pnl:+9,.2f} ({pts:+6.1f} pts) | Win: {w/len(g)*100:5.1f}%")

    output_html = os.path.join(base_dir, "report_nifty_options_1lot_65qty.html")
    generate_options_html_report(
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
            "sl_label": sl_label,
            "tp_label": tp_label,
            "timeframe": timeframe,
            "model": model
        },
        output_file=output_html
    )

def generate_options_html_report(df_trades: pd.DataFrame, summary: dict, output_file: str):
    cum_equity = [summary["initial_capital"]] + df_trades["Capital"].tolist()
    trade_labels = ["Start"] + [f"T{i+1}: {r['Date']}" for i, r in df_trades.iterrows()]

    # Drawdown Curve
    curr_peak = summary["initial_capital"]
    dd_pct = [0.0]
    for cap in df_trades["Capital"]:
        curr_peak = max(curr_peak, cap)
        dd_pct.append(((cap - curr_peak) / curr_peak) * 100.0)

    # Daily PnL
    daily_pnl = df_trades.groupby("Date")["Net_PnL"].sum()
    daily_dates = daily_pnl.index.tolist()
    daily_vals = daily_pnl.values.tolist()
    daily_colors = ["#10B981" if v > 0 else "#EF4444" for v in daily_vals]

    trades_list = df_trades.to_dict(orient="records")

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>NIFTY Options (1 Lot = 65 Qty) Fixed SL/TP Backtest Report</title>
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
            background: rgba(16, 185, 129, 0.15);
            color: #34D399;
            border: 1px solid rgba(16, 185, 129, 0.3);
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
        .pill-ce {{ background: rgba(16, 185, 129, 0.15); color: #34D399; padding: 2px 6px; border-radius: 4px; font-weight: bold; }}
        .pill-pe {{ background: rgba(239, 68, 68, 0.15); color: #F87171; padding: 2px 6px; border-radius: 4px; font-weight: bold; }}
    </style>
</head>
<body>
    <div class="header">
        <div>
            <h1>NIFTY Options (1 Lot = 65 Qty) Fixed SL/TP Backtest</h1>
            <div class="sub">Fixed SL: {summary['sl_label']} | Fixed TP: {summary['tp_label']} | 1 Lot = {summary['lot_size']} Qty | Model: {summary['model'].upper()}</div>
        </div>
        <div>
            <span class="badge">WIN RATE: {summary['win_rate']:.1f}%</span>
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
            <div class="kpi-label">Win Rate</div>
            <div class="kpi-val" style="color: #10B981;">{summary['win_rate']:.1f}%</div>
            <div style="font-size: 11px; color: var(--text-secondary); margin-top: 4px;">{summary['wins']} Wins / {summary['losses']} Losses</div>
        </div>
        <div class="kpi-card">
            <div class="kpi-label">Profit Factor</div>
            <div class="kpi-val" style="color: #A78BFA;">{summary['profit_factor']:.2f}</div>
            <div style="font-size: 11px; color: var(--text-secondary); margin-top: 4px;">RR: {summary['rr_ratio']:.2f} : 1</div>
        </div>
        <div class="kpi-card">
            <div class="kpi-label">Total Option Points</div>
            <div class="kpi-val" style="color: #60A5FA;">{summary['total_pts']:+.1f} pts</div>
            <div style="font-size: 11px; color: var(--text-secondary); margin-top: 4px;">Avg {summary['avg_trade_pts']:+.1f} pts/trade</div>
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
            <span>📈 Cumulative Equity Curve (Nifty Options 1 Lot = 65 Qty)</span>
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
            <span style="font-size: 12px; color: var(--text-secondary);">Exported to: trades_nifty_options_1lot_65qty.csv</span>
        </div>
        <div class="table-wrap">
            <table>
                <thead>
                    <tr>
                        <th>#</th>
                        <th>Date</th>
                        <th>Time</th>
                        <th>Exit Time</th>
                        <th>Instrument</th>
                        <th>Playbook</th>
                        <th>Entry Prem</th>
                        <th>Exit Prem</th>
                        <th>Prem Pts</th>
                        <th>Gross PnL</th>
                        <th>Costs</th>
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
                        <td><span class="{'pill-ce' if r['Type'] == 'CE' else 'pill-pe'}">{r['Instrument']}</span></td>
                        <td>{r['Playbook']}</td>
                        <td>Rs {r['Entry_Prem']}</td>
                        <td>Rs {r['Exit_Prem']}</td>
                        <td style="color: {'#34D399' if r['Prem_Pts'] > 0 else '#F87171'}; font-weight: bold;">{r['Prem_Pts']:+.1f}</td>
                        <td>Rs {r['Gross_PnL']:+,.0f}</td>
                        <td>Rs {r['Costs']:.0f}</td>
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

        // Equity Curve
        Plotly.newPlot('equityChart', [{{
            x: labels,
            y: eqData,
            type: 'scatter',
            mode: 'lines',
            line: {{ color: '#10B981', width: 2.5 }},
            fill: 'tozeroy',
            fillcolor: 'rgba(16, 185, 129, 0.08)'
        }}], {{
            paper_bgcolor: 'transparent',
            plot_bgcolor: 'transparent',
            margin: {{ l: 60, r: 30, t: 10, b: 30 }},
            xaxis: {{ gridcolor: 'rgba(255, 255, 255, 0.05)', showticklabels: false }},
            yaxis: {{ gridcolor: 'rgba(255, 255, 255, 0.05)', tickformat: ',.0f', tickprefix: 'Rs ', font: {{ family: 'JetBrains Mono', color: '#94A3B8' }} }}
        }}, {{ responsive: true, displayModeBar: false }});

        // Daily PnL
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

        // Drawdown Chart
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
    print(f"\n[+] Interactive Options Report generated at: {output_file}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="NIFTY Options 1 Lot 65 Qty Fixed SL/TP Backtest")
    parser.add_argument("--strategy-mode", type=str, default="breakout", choices=["breakout", "reversal"], help="Strategy mode (breakout or reversal)")
    parser.add_argument("--break-levels", type=str, default="r1_s1", choices=["r1_s1", "all"], help="Break levels to trade (r1_s1 or all)")
    parser.add_argument("--sl-mode", type=str, default="points", choices=["points", "pct"], help="SL/TP mode (points or pct)")
    parser.add_argument("--sl", type=float, default=25.0, help="SL value (points or decimal pct e.g. 0.25)")
    parser.add_argument("--tp", type=float, default=None, help="TP value (points or decimal pct e.g. 0.75). If omitted, calculated as sl * rr")
    parser.add_argument("--rr", type=float, default=2.0, help="Risk-to-Reward ratio (e.g. 2.0 for 1:2, 3.0 for 1:3)")
    parser.add_argument("--trail", action="store_true", help="Enable trailing stop loss to breakeven after 1:1 and lock 1:1 after 1:2")
    parser.add_argument("--model", type=str, default="formula", choices=["formula", "step"], help="S&R level model")
    parser.add_argument("--capital", type=float, default=50000.0, help="Initial capital in Rs")
    args = parser.parse_args()

    run_options_backtest(
        sl_mode=args.sl_mode,
        sl_val=args.sl,
        tp_val=args.tp,
        rr=args.rr,
        trail=args.trail,
        strategy_mode=args.strategy_mode,
        break_levels=args.break_levels,
        model=args.model,
        initial_capital=args.capital
    )
