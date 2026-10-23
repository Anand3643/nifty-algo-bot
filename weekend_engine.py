import os
import sys

if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

import datetime
from datetime import datetime as dt, time as dtime, timedelta
import pandas as pd
import numpy as np

# Ensure yfinance is available
try:
    import yfinance as yf
except ImportError:
    import subprocess
    subprocess.check_call([sys.executable, "-m", "pip", "install", "yfinance"])
    import yfinance as yf

NIFTY_50_TICKERS = [
    'ADANIENT.NS', 'ADANIPORTS.NS', 'APOLLOHOSP.NS', 'ASIANPAINT.NS', 'AXISBANK.NS',
    'BAJAJ-AUTO.NS', 'BAJFINANCE.NS', 'BAJAJFINSV.NS', 'BEL.NS', 'BPCL.NS',
    'BHARTIARTL.NS', 'BRITANNIA.NS', 'CIPLA.NS', 'COALINDIA.NS', 'DRREDDY.NS',
    'EICHERMOT.NS', 'GRASIM.NS', 'HCLTECH.NS', 'HDFCBANK.NS', 'HDFCLIFE.NS',
    'HEROMOTOCO.NS', 'HINDALCO.NS', 'HINDUNILVR.NS', 'ICICIBANK.NS', 'ITC.NS',
    'INDUSINDBK.NS', 'INFY.NS', 'JSWSTEEL.NS', 'KOTAKBANK.NS', 'LT.NS',
    'M&M.NS', 'MARUTI.NS', 'NTPC.NS', 'NESTLEIND.NS', 'ONGC.NS',
    'POWERGRID.NS', 'RELIANCE.NS', 'SBILIFE.NS', 'SHRIRAMFIN.NS', 'SBIN.NS',
    'SUNPHARMA.NS', 'TCS.NS', 'TATACONSUM.NS', 'TATAMOTORS.NS', 'TATASTEEL.NS',
    'TECHM.NS', 'TITAN.NS', 'TRENT.NS', 'ULTRACEMCO.NS', 'WIPRO.NS'
]

def calculate_rsi(series, period=14):
    delta = series.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.rolling(window=period).mean()
    avg_loss = loss.rolling(window=period).mean()
    rs = avg_gain / avg_loss
    return 100.0 - (100.0 / (1.0 + rs))

def generate_saturday_weekly_report(trades_file="bot_trades.csv"):
    """Compiles the Monday-Friday weekly trading performance and returns Telegram text"""
    now = dt.now()
    # Monday of the current/just concluded week
    monday = (now - timedelta(days=now.weekday())).replace(hour=0, minute=0, second=0)
    
    if not os.path.exists(trades_file):
        return (
            "📊 <b>NIFTY 50 ALGO — WEEKLY AUDIT REPORT</b>\n"
            f"<i>Week of {monday.strftime('%d-%b-%Y')}</i>\n\n"
            "⚠️ No trade activity recorded yet in <code>bot_trades.csv</code>."
        )

    try:
        df = pd.read_csv(trades_file)
        if df.empty or 'date' not in df.columns:
            return (
                "📊 <b>NIFTY 50 ALGO — WEEKLY AUDIT REPORT</b>\n"
                f"<i>Week of {monday.strftime('%d-%b-%Y')}</i>\n\n"
                "ℹ️ Bot initialized. Zero trades executed during this trading week."
            )
        
        df['dt'] = pd.to_datetime(df['date'])
        week_df = df[df['dt'] >= monday]

        if week_df.empty:
            return (
                "📊 <b>NIFTY 50 ALGO — WEEKLY AUDIT REPORT</b>\n"
                f"<i>Week of {monday.strftime('%d-%b-%Y')}</i>\n\n"
                "ℹ️ Zero trades executed during this trading week. Capital preserved."
            )

        n_trades = len(week_df)
        pnl_col = 'net_pnl' if 'net_pnl' in week_df.columns else ('pnl' if 'pnl' in week_df.columns else None)
        net_pnl = week_df[pnl_col].sum() if pnl_col else 0.0
        wins = len(week_df[week_df[pnl_col] > 0]) if pnl_col else 0
        losses = n_trades - wins
        wr = (wins / n_trades * 100.0) if n_trades > 0 else 0.0

        pnl_emoji = "🟢" if net_pnl >= 0 else "🔴"
        pnl_sign = "+" if net_pnl >= 0 else ""

        msg = (
            "📊 <b>NIFTY 50 ALGO — WEEKLY AUDIT REPORT</b>\n"
            f"<i>Trading Week: {monday.strftime('%d-%b')} to {now.strftime('%d-%b-%Y')}</i>\n\n"
            f"{pnl_emoji} <b>Net Weekly P&L:</b> <code>{pnl_sign}Rs {net_pnl:,.2f}</code>\n"
            f"📈 <b>Win Rate:</b> <code>{wr:.1f}%</code> ({wins}W / {losses}L)\n"
            f"🔢 <b>Total Trades:</b> <code>{n_trades}</code>\n"
            f"🛡️ <b>Strategy:</b> 2-Lot Staged OTM-1 (S&R + Gap Polarity)\n\n"
            "<b>Week Trades Breakdown:</b>\n"
        )

        for _, r in week_df.tail(5).iterrows():
            trade_pnl = r.get(pnl_col, 0.0)
            t_sign = "+" if trade_pnl >= 0 else ""
            t_icon = "✅" if trade_pnl >= 0 else "❌"
            inst = r.get('instrument', 'NIFTY')
            pb = r.get('playbook', 'S&R')
            msg += f"{t_icon} {r.get('date', '')} | {inst} | <b>{t_sign}Rs {trade_pnl:,.2f}</b> ({pb})\n"

        msg += "\n<i>Weekend auto-briefing generated automatically. Monday market prep in progress.</i>"
        return msg

    except Exception as e:
        return f"⚠️ <b>Weekly Report Error:</b> {e}"

def generate_sunday_nifty50_rsi_analysis():
    """Scans all Nifty 50 stocks for RSI > 50 and ranks the top bullish setups"""
    try:
        now_str = dt.now().strftime("%d-%b-%Y")
        # Download 2 months of daily closes
        data = yf.download(NIFTY_50_TICKERS, period="2mo", interval="1d", progress=False)
        if data.empty or 'Close' not in data:
            return "⚠️ Unable to fetch Nifty 50 weekend data from market feeds."

        closes = data['Close']
        results = []
        total_scanned = 0

        for ticker in NIFTY_50_TICKERS:
            if ticker in closes.columns:
                s = closes[ticker].dropna()
                if len(s) >= 15:
                    total_scanned += 1
                    rsi_series = calculate_rsi(s)
                    cur_rsi = rsi_series.iloc[-1]
                    cur_price = s.iloc[-1]
                    
                    if cur_rsi > 50.0:
                        sym = ticker.replace('.NS', '')
                        results.append({
                            "symbol": sym,
                            "rsi": round(cur_rsi, 1),
                            "price": round(cur_price, 2)
                        })

        results.sort(key=lambda x: x["rsi"], reverse=True)
        bullish_count = len(results)
        bullish_pct = (bullish_count / total_scanned * 100.0) if total_scanned > 0 else 0.0

        # Market breadth sentiment
        if bullish_pct >= 60:
            breadth_state = "🔥 BULLISH MOMENTUM (Broad Market Strength)"
        elif bullish_pct >= 40:
            breadth_state = "⚖️ BALANCED / SELECTIVE STOCK-PICKING"
        else:
            breadth_state = "❄️ DEFENSIVE / WEAK BREADTH"

        msg = (
            "🎯 <b>SUNDAY NIFTY 50 MOMENTUM RADAR (RSI > 50)</b>\n"
            f"<i>Analysis Date: {now_str} | Setup: Daily RSI Filter</i>\n\n"
            f"📊 <b>Nifty 50 Market Breadth:</b>\n"
            f"• Stocks with RSI > 50: <b>{bullish_count} / {total_scanned} ({bullish_pct:.0f}%)</b>\n"
            f"• Regime: <b>{breadth_state}</b>\n\n"
            "🏆 <b>TOP BULLISH SETUPS FOR MONDAY WATCHLIST:</b>\n"
        )

        for i, item in enumerate(results[:10], 1):
            star = "🔥" if item["rsi"] >= 70 else "⚡"
            msg += f"<b>{i}. {item['symbol']}</b>: RSI <code>{item['rsi']}</code> | Rs {item['price']:,.2f} {star}\n"

        if len(results) > 10:
            other_syms = ", ".join([r['symbol'] for r in results[10:20]])
            msg += f"\n<i>Also Bullish (RSI 50-60):</i> {other_syms}\n"

        msg += "\n💡 <i>Stocks with Daily RSI > 50 indicate institutional accumulation and high probability trend continuation.</i>"
        return msg

    except Exception as e:
        return f"⚠️ <b>Sunday Scanner Error:</b> {e}"

if __name__ == "__main__":
    print("Testing Saturday Report:")
    print(generate_saturday_weekly_report())
    print("\nTesting Sunday Analysis:")
    print(generate_sunday_nifty50_rsi_analysis())
