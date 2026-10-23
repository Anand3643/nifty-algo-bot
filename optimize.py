"""
Parameter Optimization & Strategy Heatmap Engine for NIFTY Options
Tests combinations of:
- ORB Periods (15m, 30m, 45m)
- Stop Loss % (20%, 25%, 30%)
- Target % (40%, 60%, 80%, 100%)
- Trailing Stop Loss (True, False)
- Max Trades Per Day (1, 2)
"""
import sys
import os
import itertools
import pandas as pd
from config import BacktestConfig
from data_loader import DataLoader
from strategy import DirectionalOptionStrategy
from backtest_engine import BacktestEngine
from metrics import PerformanceAnalytics

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

def run_grid_search():
    print("=" * 75)
    print("      NIFTY OPTION BUYING STRATEGY PARAMETER OPTIMIZATION GRID")
    print("=" * 75)

    base_config = BacktestConfig()
    loader = DataLoader(base_config)
    df_spot = loader.load_data()

    # Parameter Grid
    orb_periods = [15, 30, 45]
    sl_pcts = [0.20, 0.25, 0.30]
    target_pcts = [0.40, 0.60, 0.80]
    trailing_options = [True, False]
    max_trades_options = [1, 2]

    combinations = list(itertools.product(orb_periods, sl_pcts, target_pcts, trailing_options, max_trades_options))
    print(f"[*] Testing {len(combinations)} parameter permutations across {len(df_spot)} 5m bars...\n")

    results = []

    for idx, (orb_p, sl_p, tgt_p, trail_opt, max_tr) in enumerate(combinations, 1):
        cfg = BacktestConfig(
            orb_period_minutes=orb_p,
            sl_pct=sl_p,
            target_pct=tgt_p,
            enable_trailing_sl=trail_opt,
            max_trades_per_day=max_tr
        )

        strat = DirectionalOptionStrategy(cfg)
        df_sig = strat.generate_signals(df_spot)
        eng = BacktestEngine(cfg)
        trades = eng.run(df_sig)
        tdf = eng.to_dataframe()

        if tdf.empty:
            continue

        m = PerformanceAnalytics.calculate_metrics(tdf, initial_capital=cfg.initial_capital)

        results.append({
            "ORB_Mins": orb_p,
            "SL_%": int(sl_p * 100),
            "Target_%": int(tgt_p * 100),
            "Trailing_SL": "Yes" if trail_opt else "No",
            "Max_Trades": max_tr,
            "Total_Trades": m["total_trades"],
            "Win_Rate_%": m["win_rate"],
            "Profit_Factor": m["profit_factor"],
            "Net_PnL": m["net_pnl"],
            "ROI_%": m["roi_pct"],
            "Max_DD_%": m["max_drawdown_pct"],
            "Sharpe": m["sharpe_ratio"]
        })

    results_df = pd.DataFrame(results)
    results_df.sort_values(by="Net_PnL", ascending=False, inplace=True)

    csv_out = os.path.join(os.path.dirname(__file__), "optimization_results.csv")
    results_df.to_csv(csv_out, index=False)

    print("\n" + "=" * 85)
    print("               TOP 10 BEST PERFORMING PARAMETER CONFIGURATIONS")
    print("=" * 85)
    header = f"{'Rank':<5}{'ORB':<8}{'SL%':<6}{'Tgt%':<6}{'TSL':<6}{'Trades':<8}{'Win%':<8}{'PF':<6}{'MaxDD%':<8}{'Net PnL (Rs.)':<16}{'Sharpe':<8}"
    print(header)
    print("-" * 85)

    for i, (_, row) in enumerate(results_df.head(10).iterrows(), 1):
        line = (
            f"{i:<5}"
            f"{row['ORB_Mins']}m{'':<5}"
            f"{row['SL_%']}%{'':<3}"
            f"{row['Target_%']}%{'':<3}"
            f"{row['Trailing_SL']:<6}"
            f"{int(row['Total_Trades']):<8}"
            f"{row['Win_Rate_%']:.1f}%{'':<3}"
            f"{row['Profit_Factor']:.2f}{'':<2}"
            f"{row['Max_DD_%']:.1f}%{'':<3}"
            f"Rs. {row['Net_PnL']:>10,.2f}  "
            f"{row['Sharpe']:.2f}"
        )
        print(line)

    print("=" * 85)
    print(f"\n[+] Full grid results exported to: {csv_out}")
    return results_df

if __name__ == "__main__":
    run_grid_search()
