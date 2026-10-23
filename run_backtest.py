import sys
import argparse
import os
import pandas as pd

# Fix Windows console UTF-8 encoding for currency symbols and emojis
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

from config import BacktestConfig
from data_loader import DataLoader
from strategy import DirectionalOptionStrategy
from backtest_engine import BacktestEngine
from metrics import PerformanceAnalytics
from report_generator import ReportGenerator

def parse_args():
    parser = argparse.ArgumentParser(description="NIFTY Directional Option Buying Backtesting Engine")
    parser.add_argument("--lots", type=int, default=2, help="Number of Nifty lots traded per signal (default: 2)")
    parser.add_argument("--sl", type=float, default=0.20, help="Stop loss %% on option premium (default: 0.20 = 20%%)")
    parser.add_argument("--target", type=float, default=0.60, help="Target %% on option premium (default: 0.60 = 60%%)")
    parser.add_argument("--orb", type=int, default=15, help="Opening Range duration in minutes (default: 15)")
    parser.add_argument("--max-trades", type=int, default=1, help="Maximum trades allowed per day (default: 1)")
    parser.add_argument("--trailing", action="store_true", help="Enable Trailing Stop Loss (default: False)")
    parser.add_argument("--no-oi", action="store_true", help="Disable Open Interest & PCR confirmation filters")
    parser.add_argument("--pcr-bullish", type=float, default=1.05, help="Bullish Put-Call Ratio threshold (default: 1.05)")
    parser.add_argument("--pcr-bearish", type=float, default=0.95, help="Bearish Put-Call Ratio threshold (default: 0.95)")
    parser.add_argument("--custom-oi", type=str, default=None, help="Path to custom intraday Open Interest CSV data")
    parser.add_argument("--refresh", action="store_true", help="Force refresh cached market data from Yahoo Finance")
    parser.add_argument("--custom-csv", type=str, default=None, help="Path to custom 5m Nifty CSV data")
    return parser.parse_args()

def main():
    args = parse_args()

    print("=" * 70)
    print("     NIFTY 50 OPEN INTEREST & MOMENTUM OPTION BACKTESTING")
    print("=" * 70)

    # 1. Initialize Configuration
    config = BacktestConfig(
        num_lots=args.lots,
        sl_pct=args.sl,
        target_pct=args.target,
        orb_period_minutes=args.orb,
        max_trades_per_day=args.max_trades,
        enable_trailing_sl=args.trailing,
        use_oi_filter=not args.no_oi,
        pcr_bullish_threshold=args.pcr_bullish,
        pcr_bearish_threshold=args.pcr_bearish
    )

    print(f"[*] Configuration Loaded:")
    print(f"    - Lots: {config.num_lots} ({config.num_lots * config.lot_size} Qty per trade)")
    print(f"    - ORB Window: {config.orb_period_minutes} Mins (09:15 - 09:{15 + config.orb_period_minutes:02d})")
    print(f"    - Open Interest (OI) Filter: {'Active (PCR + 4-Quadrant Buildup)' if config.use_oi_filter else 'Disabled'}")
    if config.use_oi_filter:
        print(f"      * Bullish PCR Threshold: >= {config.pcr_bullish_threshold} (Put Writing dominance)")
        print(f"      * Bearish PCR Threshold: <= {config.pcr_bearish_threshold} (Call Writing dominance)")
    print(f"    - Stop Loss: {config.sl_pct * 100:.1f}% | Target: {config.target_pct * 100:.1f}%")
    print(f"    - Trailing SL: {'Enabled (+20% trigger)' if config.enable_trailing_sl else 'Disabled'}")
    print(f"    - Transaction Cost Model: Flat Rs. 40 + STT 0.0625% + GST 18% + 0.5% Slippage")
    print("-" * 70)

    # 2. Load Market Data
    loader = DataLoader(config)
    df_spot = loader.load_data(custom_csv=args.custom_csv, force_refresh=args.refresh)
    print(f"[*] Loaded {len(df_spot)} 5-minute bars from {df_spot.index[0].strftime('%Y-%m-%d')} to {df_spot.index[-1].strftime('%Y-%m-%d')}")

    # 3. Generate Strategy Signals
    print("[*] Computing Technical Indicators & ORB Breakout Signals...")
    strategy = DirectionalOptionStrategy(config)
    df_signals = strategy.generate_signals(df_spot)
    total_signals = (df_signals["Signal"] != 0).sum()
    print(f"[*] Total Valid Breakout Signals Generated: {total_signals}")

    # 4. Run Backtest Simulation
    print("[*] Simulating Black-Scholes Synthetic Option Contracts & Intraday Exits...")
    engine = BacktestEngine(config)
    trades = engine.run(df_signals)
    trades_df = engine.to_dataframe()

    if trades_df.empty:
        print("[!] No trades were executed. Check strategy filters or date range.")
        return

    # Save Trade Log CSV
    csv_path = os.path.join(os.path.dirname(__file__), "trades_log.csv")
    trades_df.to_csv(csv_path, index=False)
    print(f"[*] Saved verified trade log to: {csv_path}")

    # 5. Compute Quantitative Analytics
    metrics = PerformanceAnalytics.calculate_metrics(trades_df, initial_capital=config.initial_capital)

    # 6. Generate Interactive HTML Report
    report_gen = ReportGenerator(output_path=os.path.join(os.path.dirname(__file__), "backtest_report.html"))
    report_path = report_gen.generate(trades_df, metrics, config, df_spot)

    # 7. Print Terminal Performance Summary
    print("\n" + "=" * 70)
    print("                    PERFORMANCE TEARSHEET")
    print("=" * 70)
    print(f"  Initial Capital        : Rs. {metrics['initial_capital']:,.2f}")
    print(f"  Final Equity           : Rs. {metrics['final_equity']:,.2f}")
    print(f"  Net Realized P&L       : Rs. {metrics['net_pnl']:,.2f} ({metrics['roi_pct']:+.2f}%)")
    print(f"  Total Trades Executed  : {metrics['total_trades']} ({metrics['trading_days']} Trading Days)")
    print(f"  Win / Loss Record      : {metrics['win_count']} Wins / {metrics['loss_count']} Losses")
    print(f"  Win Rate               : {metrics['win_rate']:.2f}%")
    print(f"  Profit Factor          : {metrics['profit_factor']:.2f}")
    print(f"  Average Trade P&L      : Rs. {metrics['avg_trade_pnl']:,.2f}")
    print(f"  Average Win / Loss     : Rs. {metrics['avg_win']:,.2f} / Rs. {metrics['avg_loss']:,.2f}")
    print(f"  Realized Risk/Reward   : 1 : {metrics['risk_reward_ratio']:.2f}")
    print(f"  Max Drawdown           : -Rs. {metrics['max_drawdown_amount']:,.2f} (-{metrics['max_drawdown_pct']:.2f}%)")
    print(f"  Annualized Sharpe      : {metrics['sharpe_ratio']:.2f}")
    print(f"  Sortino Ratio          : {metrics['sortino_ratio']:.2f}")
    print(f"  Calmar Ratio           : {metrics['calmar_ratio']:.2f}")
    print(f"  Max Win / Loss Streak  : {metrics['max_consecutive_wins']} Wins / {metrics['max_consecutive_losses']} Losses")
    print(f"  Total Brokerage & STT  : Rs. {metrics['total_charges']:,.2f}")
    print("-" * 70)
    print(f"  Call (CE) Performance  : {metrics['ce_trade_count']} trades | Win: {metrics['ce_win_rate']:.1f}% | Net: Rs. {metrics['ce_net_pnl']:,.2f}")
    print(f"  Put (PE) Performance   : {metrics['pe_trade_count']} trades | Win: {metrics['pe_win_rate']:.1f}% | Net: Rs. {metrics['pe_net_pnl']:,.2f}")
    print("=" * 70)
    print(f"\n[+] Interactive Visual Report Ready: {report_path}")
    print("[+] Open the HTML report in your browser to view interactive equity charts and full trade logs!\n")

if __name__ == "__main__":
    main()
