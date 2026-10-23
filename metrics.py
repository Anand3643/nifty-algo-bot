"""
Quantitative Performance Analytics Engine
Calculates Sharpe, Sortino, Max Drawdown, Profit Factor, Expectancy, and Streak statistics.
"""
import numpy as np
import pandas as pd
from typing import Dict, Any

class PerformanceAnalytics:
    @staticmethod
    def calculate_metrics(trades_df: pd.DataFrame, initial_capital: float = 150000.0) -> Dict[str, Any]:
        """
        Computes institutional-grade backtest performance statistics.
        """
        if trades_df.empty:
            return {"total_trades": 0, "net_pnl": 0.0, "win_rate": 0.0}

        df = trades_df.copy()
        df["entry_dt"] = pd.to_datetime(df["entry_time"])
        df["exit_dt"] = pd.to_datetime(df["exit_time"])

        total_trades = len(df)
        wins = df[df["net_pnl"] > 0]
        losses = df[df["net_pnl"] <= 0]

        win_count = len(wins)
        loss_count = len(losses)
        win_rate = (win_count / total_trades) * 100.0 if total_trades > 0 else 0.0

        gross_profit = wins["gross_pnl"].sum() if not wins.empty else 0.0
        gross_loss = abs(losses["gross_pnl"].sum()) if not losses.empty else 0.0
        profit_factor = round(gross_profit / gross_loss, 2) if gross_loss > 0 else (999.0 if gross_profit > 0 else 0.0)

        total_charges = df["total_charges"].sum()
        total_gross_pnl = df["gross_pnl"].sum()
        net_pnl = df["net_pnl"].sum()
        roi_pct = (net_pnl / initial_capital) * 100.0

        avg_trade = df["net_pnl"].mean()
        avg_win = wins["net_pnl"].mean() if not wins.empty else 0.0
        avg_loss = losses["net_pnl"].mean() if not losses.empty else 0.0
        risk_reward_realized = abs(avg_win / avg_loss) if avg_loss != 0 else 0.0

        # Equity Curve and Drawdown calculation
        df["cum_pnl"] = df["net_pnl"].cumsum()
        df["equity"] = initial_capital + df["cum_pnl"]
        df["peak_equity"] = df["equity"].cummax()
        df["drawdown"] = df["equity"] - df["peak_equity"]
        df["drawdown_pct"] = (df["drawdown"] / df["peak_equity"]) * 100.0

        max_dd_amount = abs(df["drawdown"].min()) if not df.empty else 0.0
        max_dd_pct = abs(df["drawdown_pct"].min()) if not df.empty else 0.0

        # Daily P&L series for Sharpe & Sortino
        df["date"] = df["entry_dt"].dt.date
        daily_pnl = df.groupby("date")["net_pnl"].sum()
        daily_returns = daily_pnl / initial_capital

        trading_days = len(daily_pnl)
        annual_factor = 252

        mean_daily = daily_returns.mean()
        std_daily = daily_returns.std()
        downside_std = daily_returns[daily_returns < 0].std()

        sharpe_ratio = round((mean_daily / std_daily) * np.sqrt(annual_factor), 2) if std_daily > 0 else 0.0
        sortino_ratio = round((mean_daily / downside_std) * np.sqrt(annual_factor), 2) if downside_std > 0 else 0.0
        calmar_ratio = round((roi_pct / max_dd_pct), 2) if max_dd_pct > 0 else 0.0

        # Consecutive streaks
        is_win = (df["net_pnl"] > 0).astype(int).values
        max_consec_wins = 0
        max_consec_losses = 0
        cur_w = 0
        cur_l = 0
        for w in is_win:
            if w == 1:
                cur_w += 1
                cur_l = 0
                max_consec_wins = max(max_consec_wins, cur_w)
            else:
                cur_l += 1
                cur_w = 0
                max_consec_losses = max(max_consec_losses, cur_l)

        # CE vs PE Breakdown
        ce_trades = df[df["option_type"] == "CE"]
        pe_trades = df[df["option_type"] == "PE"]

        ce_pnl = ce_trades["net_pnl"].sum() if not ce_trades.empty else 0.0
        pe_pnl = pe_trades["net_pnl"].sum() if not pe_trades.empty else 0.0
        ce_win_rate = (len(ce_trades[ce_trades["net_pnl"] > 0]) / len(ce_trades) * 100) if not ce_trades.empty else 0.0
        pe_win_rate = (len(pe_trades[pe_trades["net_pnl"] > 0]) / len(pe_trades) * 100) if not pe_trades.empty else 0.0

        # Exit Reason Breakdown
        exit_reasons = df["exit_reason"].value_counts().to_dict()

        return {
            "initial_capital": initial_capital,
            "final_equity": round(initial_capital + net_pnl, 2),
            "total_trades": total_trades,
            "win_count": win_count,
            "loss_count": loss_count,
            "win_rate": round(win_rate, 2),
            "profit_factor": profit_factor,
            "gross_profit": round(gross_profit, 2),
            "gross_loss": round(gross_loss, 2),
            "net_pnl": round(net_pnl, 2),
            "roi_pct": round(roi_pct, 2),
            "total_charges": round(total_charges, 2),
            "avg_trade_pnl": round(avg_trade, 2),
            "avg_win": round(avg_win, 2),
            "avg_loss": round(avg_loss, 2),
            "risk_reward_ratio": round(risk_reward_realized, 2),
            "max_drawdown_amount": round(max_dd_amount, 2),
            "max_drawdown_pct": round(max_dd_pct, 2),
            "sharpe_ratio": sharpe_ratio,
            "sortino_ratio": sortino_ratio,
            "calmar_ratio": calmar_ratio,
            "max_consecutive_wins": max_consec_wins,
            "max_consecutive_losses": max_consec_losses,
            "avg_holding_mins": round(df["holding_mins"].mean(), 1) if not df.empty else 0.0,
            "ce_trade_count": len(ce_trades),
            "ce_net_pnl": round(ce_pnl, 2),
            "ce_win_rate": round(ce_win_rate, 2),
            "pe_trade_count": len(pe_trades),
            "pe_net_pnl": round(pe_pnl, 2),
            "pe_win_rate": round(pe_win_rate, 2),
            "exit_reasons": exit_reasons,
            "trading_days": trading_days
        }
