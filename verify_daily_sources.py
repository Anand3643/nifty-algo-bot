"""
Cross-verification of NIFTY 50 Daily Candle (Previous Day: 14-Oct-2026)
Across 3 independent sources:
1. Yahoo Finance (^NSEI)
2. Angel One SmartAPI (Token 99926000)
3. NSE Official India Portal
"""
import json
import time
import requests
import pyotp
import pandas as pd
import yfinance as yf
from datetime import datetime, timedelta
from SmartApi import SmartConnect

def fetch_yahoo():
    print("--- 1. Fetching from Yahoo Finance (^NSEI) ---")
    try:
        df = yf.download("^NSEI", period="5d", interval="1d", progress=False)
        if hasattr(df.columns, "levels") and len(df.columns.levels) > 1:
            df.columns = [c[0].lower() for c in df.columns]
        else:
            df.columns = [str(c).lower() for c in df.columns]
        
        # Look for 2026-10-14
        row_14 = None
        for dt, row in df.iterrows():
            d_str = str(dt.date())
            if d_str == "2026-10-14":
                row_14 = row
                break
        if row_14 is None:
            # Take the second to last row if today is in df
            row_14 = df.iloc[-2] if len(df) >= 2 else df.iloc[-1]
            d_str = str(df.index[-2].date()) if len(df) >= 2 else str(df.index[-1].date())

        res = {
            "source": "Yahoo Finance (^NSEI)",
            "date": d_str,
            "open": round(float(row_14["open"]), 2),
            "high": round(float(row_14["high"]), 2),
            "low": round(float(row_14["low"]), 2),
            "close": round(float(row_14["close"]), 2)
        }
        print(f"Yahoo Finance: {res}")
        return res
    except Exception as e:
        print(f"Yahoo Finance Error: {e}")
        return None

def fetch_angel():
    print("\n--- 2. Fetching from Angel One SmartAPI ---")
    try:
        from nifty_algo_bot import BotConfig
        cfg = BotConfig()
        smart_api = SmartConnect(api_key=cfg.API_KEY)
        totp = pyotp.TOTP(cfg.TOTP_SECRET).now()
        session = smart_api.generateSession(cfg.CLIENT_ID, cfg.PASSWORD, totp)
        if not session.get("status"):
            print("Angel Login Failed:", session)
            return None
        
        time.sleep(1)
        params = {
            "exchange": "NSE",
            "symboltoken": "99926000",
            "interval": "ONE_DAY",
            "fromdate": "2026-10-10 09:15",
            "todate": "2026-10-15 15:30"
        }
        res = smart_api.getCandleData(params)
        data = res.get("data", [])
        print(f"Angel returned {len(data)} candles.")
        if data:
            # Find 2026-10-14
            for c in data:
                c_dt = str(c[0])[:10]
                if c_dt == "2026-10-14":
                    return {
                        "source": "Angel One SmartAPI",
                        "date": c_dt,
                        "open": round(float(c[1]), 2),
                        "high": round(float(c[2]), 2),
                        "low": round(float(c[3]), 2),
                        "close": round(float(c[4]), 2)
                    }
            # Fallback to last before today
            today_str = datetime.now().strftime("%Y-%m-%d")
            past = [c for c in data if str(c[0])[:10] < today_str]
            if past:
                c = past[-1]
                return {
                    "source": "Angel One SmartAPI",
                    "date": str(c[0])[:10],
                    "open": round(float(c[1]), 2),
                    "high": round(float(c[2]), 2),
                    "low": round(float(c[3]), 2),
                    "close": round(float(c[4]), 2)
                }
    except Exception as e:
        print(f"Angel SmartAPI Error: {e}")
        return None

def fetch_nse():
    print("\n--- 3. Fetching from Official NSE India Website ---")
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.5",
        "Referer": "https://www.nseindia.com/"
    }
    s = requests.Session()
    s.headers.update(headers)
    try:
        # First request home page to get session cookies
        r_home = s.get("https://www.nseindia.com", timeout=10)
        time.sleep(1)
        # Fetch indices API
        r_api = s.get("https://www.nseindia.com/api/allIndices", timeout=10)
        if r_api.status_code == 200:
            data = r_api.json().get("data", [])
            for item in data:
                if item.get("index") == "NIFTY 50" or item.get("indexSymbol") == "NIFTY 50":
                    print("Found NIFTY 50 in NSE API!")
                    # previousClose is yesterday's official close
                    prev_close = float(item.get("previousClose", 0))
                    # open of today
                    today_open = float(item.get("open", 0))
                    today_high = float(item.get("high", 0))
                    today_low = float(item.get("low", 0))
                    last = float(item.get("last", 0))
                    return {
                        "source": "NSE India Official API",
                        "index": "NIFTY 50",
                        "previous_day_close": prev_close,
                        "today_open": today_open,
                        "today_high": today_high,
                        "today_low": today_low,
                        "today_last": last
                    }
        else:
            print(f"NSE API returned status {r_api.status_code}")
    except Exception as e:
        print(f"NSE India fetch error: {e}")
    return None

if __name__ == "__main__":
    y_data = fetch_yahoo()
    a_data = fetch_angel()
    n_data = fetch_nse()
    
    print("\n" + "="*70)
    print("DATA CROSS-VERIFICATION SUMMARY:")
    print("="*70)
    if y_data:
        print(f"1. Yahoo Finance ({y_data['date']}): H={y_data['high']}, L={y_data['low']}, C={y_data['close']}")
    if a_data:
        print(f"2. Angel One ({a_data['date']}): H={a_data['high']}, L={a_data['low']}, C={a_data['close']}")
    if n_data:
        print(f"3. NSE India Official: Previous Day Close={n_data['previous_day_close']}, Today Open={n_data['today_open']}")
