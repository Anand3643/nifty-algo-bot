"""
Pure Open Interest (OI) & PCR Intraday Trading Suite
Implements institutional strategies driven strictly by:
1. PCR Velocity & Momentum: Put-Call Ratio trend shifts (Put Writing vs Call Writing dominance)
2. Short Squeeze & Long Unwinding: Trapped option sellers forced to cover
3. Strike Wall Boundaries: Max Call OI Resistance and Max Put OI Support
"""
import sys
import os
import argparse
import numpy as np
import pandas as pd

from config import BacktestConfig
from data_loader import DataLoader
from oi_engine import OpenInterestEngine
from options_pricing import BlackScholesEngine
from backtest_engine import BacktestEngine
from metrics import PerformanceAnalytics
from report_generator import ReportGenerator

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

def parse_args():
    parser = argparse.ArgumentParser(description="Pure Open Interest (OI) Intraday Trading Suite")
    parser.add_argument("--mode", type=str, default="pcr_momentum",
                        choices=["pcr_momentum", "short_squeeze", "wall_reversal"],
                        help="OI Trading Strategy mode: pcr_momentum, short_squeeze, or wall_reversal")
    parser.add_argument("--lots", type=int, default=2, help="Number of lots traded (default: 2)")
    parser.add_argument("--sl", type=float, default=0.20, help="Stop loss %% (default: 0.20 = 20%%)")
    parser.add_argument("--target", type=float, default=0.60, help="Target %% (default: 0.60 = 60%%)")
    parser.add_argument("--trailing", action="store_true", help="Enable trailing stop loss")
    return parser.parse_args()

def generate_pure_oi_signals(df: pd.DataFrame, mode: str, config: BacktestConfig) -> pd.DataFrame:
    """
    Generates signals strictly based on Open Interest and Put-Call Ratio microstructure.
    """
    data = df.copy()
    oi_engine = OpenInterestEngine(config)
    data = oi_engine.attach_oi_analytics(data)
    bs_engine = BlackScholesEngine(risk_free_rate=config.risk_free_rate)

    data["Signal"] = 0
    data["Strike"] = 0
    data["Option_Type"] = ""

    signals = np.zeros(len(data), dtype=int)
    strikes = np.zeros(len(data), dtype=int)
    opt_types = [""] * len(data)

    entry_start = pd.to_datetime(config.entry_start_time).time()
    entry_end = pd.to_datetime(config.entry_end_time).time()

    dates = data.index.date
    unique_dates = np.unique(dates)

    for d in unique_dates:
        day_mask = (dates == d)
        day_indices = np.where(day_mask)[0]
        if len(day_indices) == 0:
            continue

        trades_today = 0

        for idx in day_indices:
            bar_time = data.index[idx].time()
            if bar_time < entry_start or bar_time > entry_end:
                continue

            if trades_today >= config.max_trades_per_day:
                break

            close = data["Close"].iloc[idx]
            pcr = data["PCR"].iloc[idx]
            pcr_roc = data["PCR_ROC"].iloc[idx]
            quad = data["OI_Quadrant"].iloc[idx]
            bias = data["OI_Bias_Score"].iloc[idx]
            call_wall = data["Max_Call_OI_Strike"].iloc[idx]
            put_wall = data["Max_Put_OI_Strike"].iloc[idx]

            sig = 0
            # -----------------------------------------------------------
            # Mode 1: PCR Momentum & Velocity
            # -----------------------------------------------------------
            if mode == "pcr_momentum":
                # Bullish Bias: Expanding Put Writing + Long Buildup / Short Covering
                if (bias >= 25.0) or (pcr_roc > 0.2 and quad in ["Long Buildup", "Short Covering"]):
                    sig = 1
                # Bearish Bias: Expanding Call Writing + Short Buildup / Long Unwinding
                elif (bias <= -25.0) or (pcr_roc < -0.2 and quad in ["Short Buildup", "Long Unwinding"]):
                    sig = -1

            # -----------------------------------------------------------
            # Mode 2: Short Squeeze & Panic Unwinding Breakout
            # -----------------------------------------------------------
            elif mode == "short_squeeze":
                # Call writers trapped in short covering
                if quad == "Short Covering" and pcr_roc > 0.1:
                    sig = 1
                # Put writers trapped in panic unwinding
                elif quad == "Long Unwinding" and pcr_roc < -0.1:
                    sig = -1

            # -----------------------------------------------------------
            # Mode 3: Strike Wall Boundaries Reversal (Mean Reversion)
            # -----------------------------------------------------------
            elif mode == "wall_reversal":
                if close >= (call_wall - 50) and quad in ["Short Buildup"] and pcr_roc < 0:
                    sig = -1
                elif close <= (put_wall + 50) and quad in ["Long Buildup"] and pcr_roc > 0:
                    sig = 1

            if sig != 0:
                signals[idx] = sig
                strikes[idx] = bs_engine.get_atm_strike(close, config.strike_step)
                opt_types[idx] = "CE" if sig == 1 else "PE"
                trades_today += 1

    data["Signal"] = signals
    data["Strike"] = strikes
    data["Option_Type"] = opt_types
    return data

def main():
    args = parse_args()

    print("=" * 70)
    print(f"   NIFTY OPEN INTEREST INTRADAY TRADING SUITE [MODE: {args.mode.upper()}]")
    print("=" * 70)

    config = BacktestConfig(
        num_lots=args.lots,
        sl_pct=args.sl,
        target_pct=args.target,
        enable_trailing_sl=args.trailing,
        max_trades_per_day=1
    )

    print(f"[*] Configuration:")
    print(f"    - Strategy Mode: {args.mode.upper()}")
    print(f"    - Lots: {config.num_lots} ({config.num_lots * config.lot_size} Qty)")
    print(f"    - Risk Model: {int(config.sl_pct*100)}% SL | {int(config.target_pct*100)}% Target")
    print(f"    - Trailing SL: {'Enabled' if config.enable_trailing_sl else 'Disabled'}")
    print("-" * 70)

    loader = DataLoader(config)
    df_spot = loader.load_data()
    print(f"[*] Loaded {len(df_spot)} bars from {df_spot.index[0].date()} to {df_spot.index[-1].date()}")

    print(f"[*] Simulating Intraday Open Interest & Generating Signals for mode '{args.mode}'...")
    df_signals = generate_pure_oi_signals(df_spot, mode=args.mode, config=config)
    total_signals = (df_signals["Signal"] != 0).sum()
    print(f"[*] Generated {total_signals} Open Interest Trading Signals.")

    engine = BacktestEngine(config)
    trades = engine.run(df_signals)
    trades_df = engine.to_dataframe()

    if trades_df.empty:
        print("[!] No trades executed for this mode. Try different parameters.")
        return

    csv_path = os.path.join(os.path.dirname(__file__), f"trades_oi_{args.mode}.csv")
    trades_df.to_csv(csv_path, index=False)
    print(f"[*] Trade book exported to: {csv_path}")

    metrics = PerformanceAnalytics.calculate_metrics(trades_df, initial_capital=config.initial_capital)

    html_file = os.path.join(os.path.dirname(__file__), f"report_oi_{args.mode}.html")
    report_gen = ReportGenerator(output_path=html_file)
    report_gen.generate(trades_df, metrics, config, df_spot)

    print("\n" + "=" * 70)
    print(f"             PERFORMANCE TEARSHEET ({args.mode.upper()})")
    print("=" * 70)
    print(f"  Initial Capital        : Rs. {metrics['initial_capital']:,.2f}")
    print(f"  Final Equity           : Rs. {metrics['final_equity']:,.2f}")
    print(f"  Net Realized P&L       : Rs. {metrics['net_pnl']:,.2f} ({metrics['roi_pct']:+.2f}%)")
    print(f"  Total Trades Executed  : {metrics['total_trades']} ({metrics['trading_days']} Trading Days)")
    print(f"  Win / Loss Record      : {metrics['win_count']} Wins / {metrics['loss_count']} Losses")
    print(f"  Win Rate               : {metrics['win_rate']:.2f}%")
    print(f"  Profit Factor          : {metrics['profit_factor']:.2f}")
    print(f"  Average Trade P&L      : Rs. {metrics['avg_trade_pnl']:,.2f}")
    print(f"  Realized Risk/Reward   : 1 : {metrics['risk_reward_ratio']:.2f}")
    print(f"  Max Drawdown           : -Rs. {metrics['max_drawdown_amount']:,.2f} (-{metrics['max_drawdown_pct']:.2f}%)")
    print(f"  Annualized Sharpe      : {metrics['sharpe_ratio']:.2f}")
    print(f"  Sortino Ratio          : {metrics['sortino_ratio']:.2f}")
    print(f"  Total Brokerage & STT  : Rs. {metrics['total_charges']:,.2f}")
    print("-" * 70)
    print(f"  Call (CE) Performance  : {metrics['ce_trade_count']} trades | Win: {metrics['ce_win_rate']:.1f}% | Net: Rs. {metrics['ce_net_pnl']:,.2f}")
    print(f"  Put (PE) Performance   : {metrics['pe_trade_count']} trades | Win: {metrics['pe_win_rate']:.1f}% | Net: Rs. {metrics['pe_net_pnl']:,.2f}")
    print("=" * 70)
    print(f"\n[+] Interactive Report Saved: {html_file}")
    print(f"[+] Run 'start {os.path.basename(html_file)}' to view in your browser!\n")

if __name__ == "__main__":
    main()
