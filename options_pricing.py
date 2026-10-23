"""
Black-Scholes Options Pricing & Greeks Engine for NIFTY Index Options
"""
import numpy as np
import pandas as pd
from scipy.stats import norm
from datetime import datetime, time, timedelta
from typing import Tuple, Dict, Any

class BlackScholesEngine:
    def __init__(self, risk_free_rate: float = 0.065):
        """
        :param risk_free_rate: RBI repo rate or prevailing risk-free yield (default: 6.5%)
        """
        self.r = risk_free_rate

    @staticmethod
    def get_expiry_date(dt: datetime) -> datetime:
        """
        Calculates weekly NIFTY expiry date (Thursday).
        If current day is Thursday, expires today at 15:30.
        If Friday-Wednesday, expires on the coming Thursday.
        Preserves timezone if dt is timezone-aware.
        """
        days_ahead = (3 - dt.weekday()) % 7
        expiry_date = dt.date() + timedelta(days=days_ahead)
        combined = datetime.combine(expiry_date, time(15, 30))
        if hasattr(dt, "tzinfo") and dt.tzinfo is not None:
            combined = combined.replace(tzinfo=dt.tzinfo)
        return combined

    def time_to_expiry_years(self, current_dt: datetime, expiry_dt: datetime) -> float:
        """
        Calculates exact fractional time to expiry in years based on minutes remaining.
        Ensures a tiny positive epsilon near expiry to avoid division by zero.
        """
        if current_dt.tzinfo is not None and expiry_dt.tzinfo is None:
            expiry_dt = expiry_dt.replace(tzinfo=current_dt.tzinfo)
        elif current_dt.tzinfo is None and expiry_dt.tzinfo is not None:
            current_dt = current_dt.replace(tzinfo=expiry_dt.tzinfo)

        diff_seconds = (expiry_dt - current_dt).total_seconds()
        # Minimum time 10 minutes (0.000019 years)
        diff_seconds = max(diff_seconds, 600.0)
        return diff_seconds / (365.25 * 86400.0)

    def price(
        self,
        spot: float,
        strike: float,
        T: float,
        iv: float,
        option_type: str = "CE"
    ) -> float:
        """
        Standard Black-Scholes formula for European Call / Put option.
        :param spot: Current NIFTY Spot Price
        :param strike: Option Strike Price
        :param T: Time to Expiration in Years
        :param iv: Implied Volatility (annualized, e.g. 0.14 for 14%)
        :param option_type: 'CE' for Call or 'PE' for Put
        """
        if spot <= 0 or strike <= 0 or T <= 0 or iv <= 0:
            # Intrinsic value fallback
            if option_type == "CE":
                return max(0.05, spot - strike)
            else:
                return max(0.05, strike - spot)

        d1 = (np.log(spot / strike) + (self.r + 0.5 * iv ** 2) * T) / (iv * np.sqrt(T))
        d2 = d1 - iv * np.sqrt(T)

        if option_type == "CE":
            price = spot * norm.cdf(d1) - strike * np.exp(-self.r * T) * norm.cdf(d2)
        else:
            price = strike * np.exp(-self.r * T) * norm.cdf(-d2) - spot * norm.cdf(-d1)

        # Enforce minimum tick price (₹0.05 on NSE)
        return max(0.05, float(price))

    def greeks(
        self,
        spot: float,
        strike: float,
        T: float,
        iv: float,
        option_type: str = "CE"
    ) -> Dict[str, float]:
        """
        Calculates Delta, Gamma, Theta, Vega for the option contract.
        """
        if spot <= 0 or strike <= 0 or T <= 0 or iv <= 0:
            return {"delta": 0.5 if option_type == "CE" else -0.5, "gamma": 0.0, "theta": 0.0, "vega": 0.0}

        d1 = (np.log(spot / strike) + (self.r + 0.5 * iv ** 2) * T) / (iv * np.sqrt(T))
        d2 = d1 - iv * np.sqrt(T)

        pdf_d1 = norm.pdf(d1)
        gamma = pdf_d1 / (spot * iv * np.sqrt(T))
        vega = spot * norm.pdf(d1) * np.sqrt(T) / 100.0  # per 1% change in vol

        if option_type == "CE":
            delta = norm.cdf(d1)
            theta = (
                - (spot * pdf_d1 * iv) / (2 * np.sqrt(T))
                - self.r * strike * np.exp(-self.r * T) * norm.cdf(d2)
            ) / 365.0  # per calendar day
        else:
            delta = norm.cdf(d1) - 1.0
            theta = (
                - (spot * pdf_d1 * iv) / (2 * np.sqrt(T))
                + self.r * strike * np.exp(-self.r * T) * norm.cdf(-d2)
            ) / 365.0  # per calendar day

        return {
            "delta": round(float(delta), 4),
            "gamma": round(float(gamma), 6),
            "theta": round(float(theta), 2),
            "vega": round(float(vega), 2),
        }

    def simulate_option_candle(
        self,
        spot_open: float,
        spot_high: float,
        spot_low: float,
        spot_close: float,
        strike: float,
        current_dt: datetime,
        iv: float,
        option_type: str = "CE"
    ) -> Dict[str, float]:
        """
        Derives accurate option OHLC for the current 5-minute candle.
        For Call: High occurs when Spot is High, Low occurs when Spot is Low.
        For Put: High occurs when Spot is Low, Low occurs when Spot is High.
        """
        expiry_dt = self.get_expiry_date(current_dt)
        T = self.time_to_expiry_years(current_dt, expiry_dt)

        p_open = self.price(spot_open, strike, T, iv, option_type)
        p_close = self.price(spot_close, strike, T, iv, option_type)

        if option_type == "CE":
            p_high = self.price(spot_high, strike, T, iv, option_type)
            p_low = self.price(spot_low, strike, T, iv, option_type)
        else:
            p_high = self.price(spot_low, strike, T, iv, option_type)
            p_low = self.price(spot_high, strike, T, iv, option_type)

        # Enforce OHLC consistency
        c_high = max(p_open, p_high, p_close)
        c_low = min(p_open, p_low, p_close)

        greeks_dict = self.greeks(spot_close, strike, T, iv, option_type)

        return {
            "open": round(p_open, 2),
            "high": round(c_high, 2),
            "low": round(c_low, 2),
            "close": round(p_close, 2),
            "T_days": round(T * 365.25, 2),
            **greeks_dict
        }

    @staticmethod
    def get_atm_strike(spot: float, step: int = 50) -> int:
        """
        Rounds spot to nearest strike interval (default 50 for Nifty)
        """
        return int(round(spot / step) * step)
