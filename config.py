"""
NIFTY Options Backtesting Configuration
"""
from dataclasses import dataclass, field
from typing import Optional

@dataclass
class BacktestConfig:
    # Underlying Asset
    symbol: str = "^NSEI"
    vix_symbol: str = "^INDIAVIX"
    data_period: str = "60d"      # Max intraday 5m period supported by Yahoo Finance
    bar_interval: str = "5m"
    
    # Contract Specifications
    lot_size: int = 25            # Current NIFTY lot size (25)
    num_lots: int = 2             # Default lots traded = 2 (50 qty)
    strike_step: int = 50         # Nifty strike intervals
    risk_free_rate: float = 0.065 # 6.5% RBI repo rate
    default_iv: float = 0.14      # 14% default IV fallback
    
    # Strategy Rules (ORB + Trend Filter Option Buying)
    orb_period_minutes: int = 15  # 15-minute Opening Range (09:15 - 09:30)
    use_supertrend_filter: bool = True
    supertrend_period: int = 10
    supertrend_multiplier: float = 3.0
    use_ema_filter: bool = True
    ema_fast: int = 9
    ema_slow: int = 21

    # Open Interest (OI) Trading Rules
    use_oi_filter: bool = True          # Enable OI & PCR confirmation
    pcr_bullish_threshold: float = 1.05 # PCR > 1.05 confirms Put writing / Bullish sentiment
    pcr_bearish_threshold: float = 0.95 # PCR < 0.95 confirms Call writing / Bearish sentiment
    pcr_roc_period: int = 3             # 3-bar (15m) PCR rate of change to confirm momentum
    use_oi_buildup_filter: bool = True  # Only take trades matching OI build-up quadrant
    
    # Trade Windows & Frequency
    entry_start_time: str = "09:30"  # Can enter after ORB forms
    entry_end_time: str = "14:30"    # No new entries after 14:30
    square_off_time: str = "15:15"   # Intraday square-off
    max_trades_per_day: int = 1      # 1 high-conviction trade per day to avoid churn
    
    # Risk Management
    sl_pct: float = 0.20             # 20% Stop Loss on Option Entry Premium
    target_pct: float = 0.60         # 60% Target / Take Profit (1:3 Risk-Reward)
    enable_trailing_sl: bool = False # Trailing SL toggle
    trail_trigger_pct: float = 0.20  # Start trailing after 20% gain
    trail_step_pct: float = 0.10     # Move SL up by 10% for every 10% further gain
    
    # Transaction Costs & Slippage
    slippage_pct: float = 0.005      # 0.5% slippage on entry & exit premium
    brokerage_per_order: float = 20.0# ₹20 flat discount broker fee per order (₹40 round trip)
    stt_rate: float = 0.000625       # 0.0625% STT on sell side for options
    exchange_charges_pct: float = 0.00053  # NSE txn charges (0.053%)
    gst_rate: float = 0.18           # 18% GST on brokerage + exchange charges
    sebi_stamp_pct: float = 0.00003  # Stamp duty + SEBI turnover charges
    
    # Initial Capital for Drawdown & Return metrics
    initial_capital: float = 150000.0  # ₹1.5 Lakhs starting capital
