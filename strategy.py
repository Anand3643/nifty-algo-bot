"""
Strategy module: Directional Option Buying
Features:
- Opening Range Breakout (ORB 15-min / 30-min)
- Supertrend Trend Filter
- EMA Momentum Filter (9 / 21 EMA)
- Intraday Session Management
"""
import pandas as pd
import numpy as np
from datetime import time
from typing import Dict, Any, List, Optional
from config import BacktestConfig
from options_pricing import BlackScholesEngine
from oi_engine import OpenInterestEngine

class DirectionalOptionStrategy:
    def __init__(self, config: Optional[BacktestConfig] = None):
        self.config = config or BacktestConfig()
        self.bs_engine = BlackScholesEngine(risk_free_rate=self.config.risk_free_rate)
        self.oi_engine = OpenInterestEngine(config=self.config)

    def compute_indicators(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Computes EMA and Supertrend indicators on the underlying 5m dataframe.
        """
        data = df.copy()

        # 1. Exponential Moving Averages
        data["EMA_fast"] = data["Close"].ewm(span=self.config.ema_fast, adjust=False).mean()
        data["EMA_slow"] = data["Close"].ewm(span=self.config.ema_slow, adjust=False).mean()

        # 2. Supertrend Calculation
        period = self.config.supertrend_period
        multiplier = self.config.supertrend_multiplier

        # True Range
        hl = data["High"] - data["Low"]
        h_prevc = (data["High"] - data["Close"].shift(1)).abs()
        l_prevc = (data["Low"] - data["Close"].shift(1)).abs()
        tr = pd.concat([hl, h_prevc, l_prevc], axis=1).max(axis=1)
        atr = tr.rolling(period).mean().bfill()

        hl2 = (data["High"] + data["Low"]) / 2.0
        upper_basic = hl2 + (multiplier * atr)
        lower_basic = hl2 - (multiplier * atr)

        upper_band = upper_basic.copy()
        lower_band = lower_basic.copy()
        direction = np.zeros(len(data), dtype=int)
        supertrend = np.zeros(len(data), dtype=float)

        close_vals = data["Close"].values
        ub_vals = upper_basic.values
        lb_vals = lower_basic.values

        # Iterative update for continuous Supertrend bands
        curr_dir = 1
        curr_ub = ub_vals[0]
        curr_lb = lb_vals[0]

        for i in range(1, len(data)):
            c = close_vals[i]
            c_prev = close_vals[i - 1]

            # Update lower band
            if lb_vals[i] > curr_lb or c_prev < curr_lb:
                curr_lb = lb_vals[i]

            # Update upper band
            if ub_vals[i] < curr_ub or c_prev > curr_ub:
                curr_ub = ub_vals[i]

            # Direction switch
            if curr_dir == 1:
                if c < curr_lb:
                    curr_dir = -1
                    curr_ub = ub_vals[i]
            else:
                if c > curr_ub:
                    curr_dir = 1
                    curr_lb = lb_vals[i]

            direction[i] = curr_dir
            supertrend[i] = curr_lb if curr_dir == 1 else curr_ub

        data["Supertrend"] = supertrend
        data["ST_Direction"] = direction  # 1 for Bullish, -1 for Bearish
        return data

    def extract_orb_levels(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Calculates the Opening Range High and Low for each trading session.
        By default, the first 15 minutes (09:15 - 09:30, i.e., first 3 bars of 5m).
        """
        data = df.copy()
        data["Date"] = data.index.date
        data["Time"] = data.index.time

        orb_bars_count = max(1, self.config.orb_period_minutes // 5)
        
        # Group by Date and compute ORB High & Low
        orb_highs = {}
        orb_lows = {}

        for date_val, group in data.groupby("Date"):
            first_bars = group.iloc[:orb_bars_count]
            orb_highs[date_val] = first_bars["High"].max()
            orb_lows[date_val] = first_bars["Low"].min()

        data["ORB_High"] = data["Date"].map(orb_highs)
        data["ORB_Low"] = data["Date"].map(orb_lows)
        data.drop(columns=["Date", "Time"], inplace=True)
        return data

    def generate_signals(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Generates trade entry triggers based on ORB + filters.
        Signals:
          1  = BUY ATM CE
         -1  = BUY ATM PE
          0  = NO SIGNAL
        """
        data = self.compute_indicators(df)
        data = self.extract_orb_levels(data)
        if "PCR" not in data.columns:
            data = self.oi_engine.attach_oi_analytics(data)

        data["Signal"] = 0
        data["Strike"] = 0
        data["Option_Type"] = ""

        entry_start = pd.to_datetime(self.config.entry_start_time).time()
        entry_end = pd.to_datetime(self.config.entry_end_time).time()

        dates = data.index.date
        unique_dates = np.unique(dates)

        signals = np.zeros(len(data), dtype=int)
        strikes = np.zeros(len(data), dtype=int)
        opt_types = [""] * len(data)

        for d in unique_dates:
            day_mask = (dates == d)
            day_indices = np.where(day_mask)[0]
            if len(day_indices) == 0:
                continue

            trades_today = 0
            orb_broken_up = False
            orb_broken_down = False

            for idx in day_indices:
                bar_time = data.index[idx].time()
                if bar_time < entry_start or bar_time > entry_end:
                    continue

                if trades_today >= self.config.max_trades_per_day:
                    break

                close_price = data["Close"].iloc[idx]
                orb_high = data["ORB_High"].iloc[idx]
                orb_low = data["ORB_Low"].iloc[idx]

                st_dir = data["ST_Direction"].iloc[idx]
                ema_fast = data["EMA_fast"].iloc[idx]
                ema_slow = data["EMA_slow"].iloc[idx]
                pcr_val = data["PCR"].iloc[idx]
                pcr_roc = data["PCR_ROC"].iloc[idx]
                oi_quad = data["OI_Quadrant"].iloc[idx]

                # CE Buy Conditions (Bullish ORB Breakout + OI Confirmation)
                ce_valid = not orb_broken_up and (close_price > orb_high)
                if self.config.use_supertrend_filter:
                    ce_valid = ce_valid and (st_dir == 1)
                if self.config.use_ema_filter:
                    ce_valid = ce_valid and (ema_fast > ema_slow)
                if self.config.use_oi_filter:
                    # Put writing must be dominant or expanding
                    ce_valid = ce_valid and ((pcr_val >= self.config.pcr_bullish_threshold) or (pcr_roc > 0.0))
                    if self.config.use_oi_buildup_filter:
                        ce_valid = ce_valid and (oi_quad in ["Long Buildup", "Short Covering"])

                if ce_valid:
                    signals[idx] = 1
                    strikes[idx] = self.bs_engine.get_atm_strike(close_price, self.config.strike_step)
                    opt_types[idx] = "CE"
                    orb_broken_up = True
                    trades_today += 1
                    continue

                # PE Buy Conditions (Bearish ORB Breakdown + OI Confirmation)
                pe_valid = not orb_broken_down and (close_price < orb_low)
                if self.config.use_supertrend_filter:
                    pe_valid = pe_valid and (st_dir == -1)
                if self.config.use_ema_filter:
                    pe_valid = pe_valid and (ema_fast < ema_slow)
                if self.config.use_oi_filter:
                    # Call writing must be dominant or expanding
                    pe_valid = pe_valid and ((pcr_val <= self.config.pcr_bearish_threshold) or (pcr_roc < 0.0))
                    if self.config.use_oi_buildup_filter:
                        pe_valid = pe_valid and (oi_quad in ["Short Buildup", "Long Unwinding"])

                if pe_valid:
                    signals[idx] = -1
                    strikes[idx] = self.bs_engine.get_atm_strike(close_price, self.config.strike_step)
                    opt_types[idx] = "PE"
                    orb_broken_down = True
                    trades_today += 1

        data["Signal"] = signals
        data["Strike"] = strikes
        data["Option_Type"] = opt_types
        return data
