"""
Data loader and preprocessor for NIFTY 50 and INDIA VIX
Supports automatic downloading from Yahoo Finance with local caching,
as well as importing custom user CSV datasets.
"""
import os
import yfinance as yf
import pandas as pd
import numpy as np
from datetime import datetime
from typing import Optional, Tuple
from config import BacktestConfig

class DataLoader:
    def __init__(self, config: Optional[BacktestConfig] = None):
        self.config = config or BacktestConfig()
        self.data_dir = os.path.join(os.path.dirname(__file__), "data")
        os.makedirs(self.data_dir, exist_ok=True)

    def load_data(self, custom_csv: Optional[str] = None, force_refresh: bool = False) -> pd.DataFrame:
        """
        Loads NIFTY 5m intraday data and merges matching INDIA VIX daily volatility.
        Returns a cleaned DataFrame indexed by Datetime (IST).
        """
        if custom_csv and os.path.exists(custom_csv):
            print(f"[DataLoader] Loading custom data from: {custom_csv}")
            df = self._load_custom_csv(custom_csv)
        else:
            cache_file = os.path.join(self.data_dir, "nifty_5m_cache.csv")
            if os.path.exists(cache_file) and not force_refresh:
                print(f"[DataLoader] Loading cached NIFTY 5m data from: {cache_file}")
                df = pd.read_csv(cache_file, index_col=0, parse_dates=True)
            else:
                print(f"[DataLoader] Downloading {self.config.data_period} of {self.config.bar_interval} NIFTY data...")
                raw_df = yf.download(
                    self.config.symbol,
                    period=self.config.data_period,
                    interval=self.config.bar_interval,
                    progress=False
                )
                df = self._clean_yf_dataframe(raw_df)
                df.to_csv(cache_file)
                print(f"[DataLoader] Successfully downloaded and cached {len(df)} bars.")

        # Ensure index is datetime with IST timezone
        df.index = pd.to_datetime(df.index)
        if df.index.tz is None:
            df.index = df.index.tz_localize("Asia/Kolkata")
        else:
            df.index = df.index.tz_convert("Asia/Kolkata")

        # Filter strictly for Indian Market Hours: 09:15 to 15:30
        df["time"] = df.index.time
        start_time = pd.to_datetime("09:15").time()
        end_time = pd.to_datetime("15:30").time()
        df = df[(df["time"] >= start_time) & (df["time"] <= end_time)].copy()

        # Load and merge INDIA VIX
        df = self._merge_vix(df, force_refresh=force_refresh)

        # Drop temporary time column
        df.drop(columns=["time"], inplace=True)
        return df

    def _merge_vix(self, df: pd.DataFrame, force_refresh: bool = False) -> pd.DataFrame:
        """
        Fetches India VIX and maps it to intraday bars by date.
        """
        vix_cache = os.path.join(self.data_dir, "india_vix_cache.csv")
        try:
            if os.path.exists(vix_cache) and not force_refresh:
                vix_df = pd.read_csv(vix_cache, index_col=0, parse_dates=True)
            else:
                print("[DataLoader] Downloading INDIA VIX data for volatility calibration...")
                raw_vix = yf.download(
                    self.config.vix_symbol,
                    period="90d",
                    interval="1d",
                    progress=False
                )
                vix_df = self._clean_yf_dataframe(raw_vix)
                vix_df.to_csv(vix_cache)

            # Map daily Close VIX to intraday dates
            vix_df["date_str"] = vix_df.index.strftime("%Y-%m-%d")
            vix_map = vix_df.set_index("date_str")["Close"].to_dict()

            df["date_str"] = df.index.strftime("%Y-%m-%d")
            df["VIX"] = df["date_str"].map(vix_map)
            # Fill missing with default IV (e.g. 14.0%)
            df["VIX"] = df["VIX"].bfill().ffill().fillna(self.config.default_iv * 100.0)
            df["IV"] = df["VIX"] / 100.0
            df.drop(columns=["date_str"], inplace=True)
        except Exception as e:
            print(f"[DataLoader] Warning: Could not merge VIX ({e}), using default IV = {self.config.default_iv}")
            df["VIX"] = self.config.default_iv * 100.0
            df["IV"] = self.config.default_iv

        return df

    def _clean_yf_dataframe(self, raw_df: pd.DataFrame) -> pd.DataFrame:
        """
        Flattens multi-index columns returned by yfinance v0.2.x+
        """
        df = raw_df.copy()
        if isinstance(df.columns, pd.MultiIndex):
            # Yahoo finance returns tuples like ('Close', '^NSEI')
            new_cols = []
            for col in df.columns:
                metric = col[0] if isinstance(col, tuple) else str(col)
                new_cols.append(metric)
            df.columns = new_cols

        # Ensure required columns exist
        req_cols = ["Open", "High", "Low", "Close"]
        for c in req_cols:
            if c not in df.columns:
                raise ValueError(f"Missing expected OHLC column '{c}' in downloaded data.")

        # Ensure numeric values and drop NaNs
        for c in req_cols:
            df[c] = pd.to_numeric(df[c], errors="coerce")
        df.dropna(subset=req_cols, inplace=True)
        return df

    def _load_custom_csv(self, filepath: str) -> pd.DataFrame:
        """
        Parses custom CSV with standard headers (Date/Datetime, Open, High, Low, Close, Volume).
        """
        df = pd.read_csv(filepath)
        dt_col = None
        for col in ["Datetime", "datetime", "Date", "date", "Timestamp", "timestamp"]:
            if col in df.columns:
                dt_col = col
                break
        if dt_col is None:
            dt_col = df.columns[0]

        df[dt_col] = pd.to_datetime(df[dt_col])
        df.set_index(dt_col, inplace=True)

        rename_dict = {}
        for c in df.columns:
            lower = c.strip().lower()
            if lower == "open": rename_dict[c] = "Open"
            elif lower == "high": rename_dict[c] = "High"
            elif lower == "low": rename_dict[c] = "Low"
            elif lower == "close": rename_dict[c] = "Close"
            elif lower == "volume": rename_dict[c] = "Volume"

        df.rename(columns=rename_dict, inplace=True)
        return df
