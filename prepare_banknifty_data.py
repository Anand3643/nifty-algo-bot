"""
Prepares Continuous 5-Minute and Daily Candles for BANKNIFTY
Merges:
1. Historical 5m candles from wasted/indian options/bank_nifty_5m.csv (May - Aug 2026)
2. Live high-resolution 5m candles from Yahoo Finance ^NSEBANK (Jul - Oct 2026)
3. 2-Year Daily Candles from Yahoo Finance ^NSEBANK
"""
import os
import pandas as pd
import yfinance as yf
from datetime import datetime

def prepare_banknifty_data():
    base_dir = os.path.dirname(os.path.abspath(__file__))
    out_dir = os.path.join(base_dir, "banknifty_data", "candles")
    os.makedirs(out_dir, exist_ok=True)

    print("--- 1. Downloading 2-Year Daily Candles for BANKNIFTY (^NSEBANK) ---")
    df_daily = yf.download("^NSEBANK", period="2y", interval="1d", progress=False)
    if hasattr(df_daily.columns, "levels") and len(df_daily.columns.levels) > 1:
        df_daily.columns = [c[0].lower() for c in df_daily.columns]
    else:
        df_daily.columns = [str(c).lower() for c in df_daily.columns]

    daily_records = []
    for dt, r in df_daily.iterrows():
        daily_records.append({
            "datetime": str(dt.date()),
            "open": round(float(r["open"]), 2),
            "high": round(float(r["high"]), 2),
            "low": round(float(r["low"]), 2),
            "close": round(float(r["close"]), 2),
            "volume": float(r.get("volume", 0))
        })
    df_d = pd.DataFrame(daily_records).drop_duplicates(subset=["datetime"]).sort_values("datetime")
    daily_path = os.path.join(out_dir, "BANKNIFTY_1day.csv")
    df_d.to_csv(daily_path, index=False)
    print(f"Saved {len(df_d)} daily candles to {daily_path} ({df_d['datetime'].min()} to {df_d['datetime'].max()})")

    print("\n--- 2. Building Continuous 5-Minute Intraday Candles ---")
    # A. Source 1: wasted/indian options
    p_src1 = r"C:\Users\Admin\Desktop\wasted\indian options\bank_nifty_5m.csv"
    dfs = []
    if os.path.exists(p_src1):
        df1 = pd.read_csv(p_src1)
        # Convert UTC to IST (+5:30)
        dt_col = "Datetime" if "Datetime" in df1.columns else "datetime"
        df1["datetime"] = pd.to_datetime(df1[dt_col]) + pd.Timedelta(hours=5, minutes=30)
        df1.rename(columns={"Open": "open", "High": "high", "Low": "low", "Close": "close", "Volume": "volume"}, inplace=True)
        dfs.append(df1[["datetime", "open", "high", "low", "close", "volume"]])
        print(f"Loaded {len(df1)} bars from {p_src1}")

    # B. Source 2: Yahoo Finance 60-day 5m candles
    df2 = yf.download("^NSEBANK", period="60d", interval="5m", progress=False)
    if not df2.empty:
        if hasattr(df2.columns, "levels") and len(df2.columns.levels) > 1:
            df2.columns = [c[0].lower() for c in df2.columns]
        else:
            df2.columns = [str(c).lower() for c in df2.columns]
        df2.reset_index(inplace=True)
        # Timezone convert to naive IST
        dt_col2 = "Datetime" if "Datetime" in df2.columns else "datetime"
        df2["datetime"] = pd.to_datetime(df2[dt_col2]).dt.tz_localize(None)
        dfs.append(df2[["datetime", "open", "high", "low", "close", "volume"]])
        print(f"Loaded {len(df2)} bars from Yahoo Finance ^NSEBANK")

    if dfs:
        df_5m = pd.concat(dfs).drop_duplicates(subset=["datetime"]).sort_values("datetime")
        # Round prices
        for col in ["open", "high", "low", "close"]:
            df_5m[col] = df_5m[col].round(2)
        out_5m_path = os.path.join(out_dir, "BANKNIFTY_5min.csv")
        df_5m.to_csv(out_5m_path, index=False)
        print(f"Saved {len(df_5m)} continuous 5-minute candles to {out_5m_path}")
        print(f"Intraday Range: {df_5m['datetime'].min()} to {df_5m['datetime'].max()}")
        return daily_path, out_5m_path

if __name__ == "__main__":
    prepare_banknifty_data()
