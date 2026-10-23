"""
Head-to-Head Comparative Backtest:
Our Algo Bot (Mathematical CPR & Multi-Playbook Engine)
VS.
Arjun's Telegram Channel Levels (@FlyingcallsArjun)

Evaluation Period: July 3, 2026 – October 15, 2026 (Exact Same Window)
Instrument: NIFTY ATM Options (1 Lot, 65 Qty)
Cost Model: Identical realistic slippage (0.5%), STT, turnover charges, and Rs 40 roundtrip brokerage.
"""
import os
import pandas as pd
import numpy as np

def run_comparison():
    base_dir = os.path.dirname(os.path.abspath(__file__))

    # 1. Load Our Bot Trades
    df_our_full = pd.read_csv(os.path.join(base_dir, "trades_2year_5min_candles_nifty.csv"))
    df_our_full["Date"] = pd.to_datetime(df_our_full["Date"])
    df_our = df_our_full[(df_our_full["Date"] >= "2026-07-03") & (df_our_full["Date"] <= "2026-10-15")].copy()
    df_our.sort_values(["Date", "Time"], inplace=True)
    df_our.reset_index(drop=True, inplace=True)

    # Recompute equity curve from Rs 50,000 base
    cap_our = 50000.0
    caps_our = []
    for pnl in df_our["Net_PnL"]:
        cap_our += pnl
        caps_our.append(cap_our)
    df_our["Capital"] = caps_our

    # 2. Load Arjun Best Breakout Trades
    df_arjun = pd.read_csv(os.path.join(base_dir, "telegram_levels_best_trades.csv"))
    df_arjun["Date"] = pd.to_datetime(df_arjun["Date"])
    df_arjun.sort_values(["Date", "Time"], inplace=True)
    df_arjun.reset_index(drop=True, inplace=True)

    # 3. Load Arjun Raw Breakout Trades (from summary run)
    from backtest_telegram_levels import run_backtest as run_arjun_raw
    df_arjun_raw = run_arjun_raw(mode="BREAKOUT", sl_pts=40.0, rr=3.0)
    df_arjun_raw["Date"] = pd.to_datetime(df_arjun_raw["Date"])

    # Helper function for comprehensive metrics
    def get_metrics(df, name):
        if df.empty:
            return {}
        total = len(df)
        wins = (df["Net_PnL"] > 0).sum()
        losses = (df["Net_PnL"] <= 0).sum()
        wr = (wins / total) * 100.0
        net = df["Net_PnL"].sum()
        g_win = df[df["Net_PnL"] > 0]["Net_PnL"].sum()
        g_loss = abs(df[df["Net_PnL"] <= 0]["Net_PnL"].sum())
        pf = g_win / g_loss if g_loss > 0 else 99.0
        peak = df["Capital"].cummax()
        max_dd = abs((df["Capital"] - peak).min())
        avg_trade = df["Net_PnL"].mean()
        avg_win = df[df["Net_PnL"] > 0]["Net_PnL"].mean() if wins > 0 else 0.0
        avg_loss = df[df["Net_PnL"] <= 0]["Net_PnL"].mean() if losses > 0 else 0.0
        daily_pnl = df.groupby(df["Date"].dt.date)["Net_PnL"].sum()
        sharpe = (daily_pnl.mean() / daily_pnl.std()) * np.sqrt(252) if daily_pnl.std() > 0 else 0.0
        roi = (net / 50000.0) * 100.0

        return {
            "Engine": name,
            "Trades": total,
            "Wins": wins,
            "Losses": losses,
            "Win_Rate": f"{wr:.1f}%",
            "Net_PnL": round(net, 2),
            "ROI": f"{roi:+.1f}%",
            "PF": round(pf, 2),
            "Max_DD": round(max_dd, 2),
            "Avg_Trade": round(avg_trade, 2),
            "Avg_Win": round(avg_win, 2),
            "Avg_Loss": round(avg_loss, 2),
            "Realized_RR": round(abs(avg_win / avg_loss), 2) if avg_loss != 0 else 0.0,
            "Sharpe": round(sharpe, 2)
        }

    met_our = get_metrics(df_our, "Our Bot (Mathematical CPR & Multi-Playbook)")
    met_arjun_opt = get_metrics(df_arjun, "Arjun Levels (Optimized Breakout + EMA + Trail)")
    met_arjun_raw = get_metrics(df_arjun_raw, "Arjun Levels (Raw Breakout 40pt SL 1:3 RR)")

    comp_df = pd.DataFrame([met_our, met_arjun_opt, met_arjun_raw])
    comp_df.to_csv("head_to_head_comparison.csv", index=False)

    # Monthly Breakdown
    df_our["Month"] = df_our["Date"].dt.strftime("%Y-%m")
    df_arjun["Month"] = df_arjun["Date"].dt.strftime("%Y-%m")
    df_arjun_raw["Month"] = df_arjun_raw["Date"].dt.strftime("%Y-%m")

    months = sorted(list(set(df_our["Month"]).union(set(df_arjun["Month"]))))
    monthly_records = []
    for m in months:
        pnl_our = df_our[df_our["Month"] == m]["Net_PnL"].sum()
        trades_our = len(df_our[df_our["Month"] == m])
        wr_our = (df_our[df_our["Month"] == m]["Net_PnL"] > 0).mean() * 100.0 if trades_our > 0 else 0.0

        pnl_arj_opt = df_arjun[df_arjun["Month"] == m]["Net_PnL"].sum()
        trades_arj_opt = len(df_arjun[df_arjun["Month"] == m])
        wr_arj_opt = (df_arjun[df_arjun["Month"] == m]["Net_PnL"] > 0).mean() * 100.0 if trades_arj_opt > 0 else 0.0

        pnl_arj_raw = df_arjun_raw[df_arjun_raw["Month"] == m]["Net_PnL"].sum()
        trades_arj_raw = len(df_arjun_raw[df_arjun_raw["Month"] == m])
        wr_arj_raw = (df_arjun_raw[df_arjun_raw["Month"] == m]["Net_PnL"] > 0).mean() * 100.0 if trades_arj_raw > 0 else 0.0

        monthly_records.append({
            "Month": m,
            "Our_Trades": trades_our,
            "Our_WR": f"{wr_our:.0f}%",
            "Our_PnL": round(pnl_our, 2),
            "Arjun_Trades": trades_arj_opt,
            "Arjun_WR": f"{wr_arj_opt:.0f}%",
            "Arjun_PnL": round(pnl_arj_opt, 2),
            "Arjun_Raw_PnL": round(pnl_arj_raw, 2),
        })

    df_monthly = pd.DataFrame(monthly_records)
    df_monthly.to_csv("monthly_comparison.csv", index=False)

    print("=========================================================================================")
    print("HEAD-TO-HEAD COMPARISON: OUR BOT VS. ARJUN TELEGRAM LEVELS (03-Jul-2026 to 15-Oct-2026)")
    print("=========================================================================================")
    print(comp_df[["Engine", "Trades", "Win_Rate", "Net_PnL", "ROI", "PF", "Max_DD", "Sharpe"]].to_string(index=False))
    print("\nMONTHLY BREAKDOWN:")
    print(df_monthly.to_string(index=False))

    return comp_df, df_monthly

if __name__ == "__main__":
    run_comparison()
