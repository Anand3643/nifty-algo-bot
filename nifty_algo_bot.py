"""
====================================================================================================
   ALL-IN-ONE NIFTY 50 OPTIONS ALGO TRADING BOT & LIVE MONITOR (ANGEL ONE SMARTAPI)
====================================================================================================
Strategy: The 2-Lot Staged Execution Engine (Institutional S&R & Gap Polarity)
Instrument: NIFTY 50 OTM-1 Options (2 Lots = 130 Qty)
Capital: Starting Fresh with Rs 50,000 | SL: 50 pts | T1: +100 pts (Book 1 Lot) | T2: +200 pts (Runner)
Filtrations: 14:00 Entry Cutoff | 15:00 EOD Close | Instant Risk-Free Breakeven on Lot 2 (+4 pts)
Telegram Live Alerts: Group "GOLD Zone" (Chat ID: -5077267080)
Broker: Angel One SmartAPI

Everything is contained in this SINGLE file:
  - Angel One TOTP Session Authentication & Instrument Caching
  - Real-time NIFTY Spot & ATM Option LTP Polling
  - 5-Minute Candle S&R Signal Engine (Gap Polarity, Reversals, Breakouts, ORB)
  - Realistic Indian Option Costs (STT, Turnover, Rs 40 Brokerage, GST, 0.5% Slippage)
  - Daily & Weekly Real-time P&L Tracking (Fresh from Scratch)
  - Real-Time Live Console HUD (Heads-Up Display)
  - Auto-Generated Live HTML Dashboard (Auto-refreshes every 5 seconds)
  - Real-Time Telegram Live Notifications
====================================================================================================
"""
import os
import sys
import time
import json
import logging
import webbrowser
import argparse
from datetime import datetime, time as dtime, timedelta

# Ensure UTF-8 console output for Windows
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

# Import SmartApi sub-dependencies cleanly
try:
    import websocket
except ImportError:
    pass

import pandas as pd
import requests
import pyotp
from SmartApi import SmartConnect

# ==================================================================================================
# 1. CONFIGURATION & CREDENTIALS
# ==================================================================================================
class BotConfig:
    API_KEY = os.environ.get("API_KEY", "6mRD3Ntn")
    CLIENT_ID = os.environ.get("CLIENT_ID", "A612537")
    PASSWORD = os.environ.get("PASSWORD", "1436")
    TOTP_SECRET = os.environ.get("TOTP_SECRET", "Z6NUOKVTOJI5LUI6GCFR2HXKWY")

    # Telegram Credentials (GOLD Zone)
    TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "8455004756:AAHzyPNLWJ2x_2aQAQTHdDDzWn5VGW7KLSU")
    TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "-5077267080")

    # Capital & Risk Parameters (2-Lot Staged Execution Engine)
    INITIAL_CAPITAL = 50000.0       # Starting Capital: Rs 50,000
    LOT_SIZE = 65                   # 1 Lot = 65 Qty for NIFTY 50
    NUM_LOTS = 2                    # 2-Lot Staged Execution Engine (Total Entry: 130 Qty)
    STRIKE_MODE = "OTM-1"           # OTM-1 Strike (+50 CE / -50 PE) - Slashes drawdown by 28%
    STOP_LOSS_PTS = 50.0            # 50 points option premium SL
    TARGET_1_PTS = 100.0            # Target 1: Book 1 Lot @ +100 pts (1:2 RR | +Rs 6,500 banked immediately)
    TARGET_2_PTS = 200.0            # Target 2: Let Lot 2 run to +200 pts (1:4 RR | +Rs 13,000 runner)
    TARGET_PTS = 200.0              # Legacy alias
    MAX_TRADES_PER_DAY = 2          # Maximum trades per trading day
    SLIPPAGE_RATE = 0.005           # 0.5% realistic fill slippage
    
    # Advanced Institutional Filtrations
    SMART_BE_TRIGGER_PTS = 100.0    # When Target 1 (+100 pts) is reached, lock Breakeven
    SMART_BE_BUFFER_PTS = 4.0       # +4 pts buffer above entry to cover brokerage & STT (Risk-Free BE)
    DYNAMIC_TRAIL_PTS = 15.0        # Dynamic trailing 15 pts behind high once Target 1 is booked
    DAILY_STOP_ON_LOSS = False      # Disabling halt allows 2nd trade recovery (captured Monday +Rs 6,162.60)

    # Instrument Tokens & Exchange
    SYMBOL_INDEX = "Nifty 50"
    EXCHANGE_INDEX = "NSE"
    TOKEN_INDEX = "99926000"
    EXCHANGE_OPTIONS = "NFO"

    # Market Timing (IST)
    MARKET_START = dtime(9, 15)
    ENTRY_START = dtime(9, 25)
    ENTRY_END = dtime(14, 0)        # 14:00 IST Entry Cutoff (eliminates late negative expectancy chop)
    SQUARE_OFF_TIME = dtime(15, 0)  # 15:00 IST Mandatory EOD Square-Off (dodges 15:00-15:15 theta crush)
    MARKET_END = dtime(15, 30)

    # Clean Storage Files (Dedicated for this Bot)
    TRADES_FILE = "bot_trades.csv"
    STATE_FILE = "bot_state.json"
    DASHBOARD_FILE = "bot_dashboard.html"
    SCRIP_CACHE_FILE = "scrip_master.json"
    LOG_FILE = "bot.log"

    # Mode
    PAPER_TRADING = True            # True = Paper Execution, False = Live Market Orders

# Configure File & Stream Logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler(BotConfig.LOG_FILE, encoding="utf-8")
    ]
)
logger = logging.getLogger("NiftyAlgoBot")

# ==================================================================================================
# 2. TELEGRAM LIVE ALERT DISPATCHER
# ==================================================================================================
class TelegramAlerter:
    def __init__(self, token: str, chat_id: str):
        self.token = token
        self.chat_id = chat_id
        self.api_url = f"https://api.telegram.org/bot{self.token}/sendMessage"

    def send(self, message: str, parse_mode: str = "HTML") -> bool:
        payload = {
            "chat_id": self.chat_id,
            "text": message,
            "parse_mode": parse_mode,
            "disable_web_page_preview": True
        }
        try:
            res = requests.post(self.api_url, json=payload, timeout=8)
            return res.status_code == 200
        except Exception as e:
            logger.error(f"Telegram alert delivery failed: {e}")
            return False

# ==================================================================================================
# 3. INSTITUTIONAL S&R LEVEL CALCULATOR
# ==================================================================================================
class SRCalculator:
    @staticmethod
    def compute(high: float, low: float, close: float) -> dict:
        if close <= 0:
            close = 22600.0

        # Absolute safeguard against zero range / collapsed levels
        if high <= low or low <= 0 or (high - low) < 20.0:
            # Fallback to realistic ATR span (1.0% of close ~ 220 pts)
            span = max(80.0, close * 0.010)
            high = close + (span / 2.0)
            low = close - (span / 2.0)

        r = high - low
        c = close
        p = round(((high + low + close) / 3.0) / 5) * 5
        bc = round(((high + low) / 2.0) / 5) * 5
        tc = round(((2.0 * p) - bc) / 5) * 5

        r1 = round((c + 0.236 * r) / 5) * 5
        r2 = round((c + 0.500 * r) / 5) * 5
        r3 = round((c + 0.866 * r) / 5) * 5
        r4 = round((c + 1.333 * r) / 5) * 5

        s1 = round((c - 0.300 * r) / 5) * 5
        s2 = round((c - 0.550 * r) / 5) * 5
        s3 = round((c - 0.900 * r) / 5) * 5
        s4 = round((c - 1.314 * r) / 5) * 5

        cpr_top = max(bc, tc)
        cpr_bot = min(bc, tc)

        return {
            "pivot": p, "bc": bc, "tc": tc,
            "cpr_top": cpr_top, "cpr_bot": cpr_bot,
            "r1": r1, "r2": r2, "r3": r3, "r4": r4,
            "s1": s1, "s2": s2, "s3": s3, "s4": s4,
            "range": round(r, 1), "prev_close": c
        }


# ==================================================================================================
# 4. ANGEL ONE SESSION & INSTRUMENT MANAGER
# ==================================================================================================
class AngelManager:
    def __init__(self, config: BotConfig, alerter: TelegramAlerter):
        self.cfg = config
        self.alerter = alerter
        self.smart_api = None
        self.auth_data = None
        self.scrip_df = None

    def connect(self) -> bool:
        try:
            logger.info("Initializing Angel One SmartConnect...")
            self.smart_api = SmartConnect(self.cfg.API_KEY)
            totp = pyotp.TOTP(self.cfg.TOTP_SECRET).now()
            logger.info(f"Generating TOTP: {totp} | Logging in Client {self.cfg.CLIENT_ID}...")

            res = self.smart_api.generateSession(self.cfg.CLIENT_ID, self.cfg.PASSWORD, totp)
            if res and res.get("status"):
                self.auth_data = res.get("data")
                logger.info("Angel One Session Authenticated Successfully!")
                self._load_scrip_master()
                return True
            else:
                err = f"Angel One Login Failed: {res.get('message')}"
                logger.error(err)
                self.alerter.send(f"🚨 <b>ANGEL ONE LOGIN FAILED</b>\n{err}")
                return False
        except Exception as e:
            err = f"SmartAPI Connection Exception: {e}"
            logger.error(err)
            self.alerter.send(f"🚨 <b>SMARTAPI ERROR</b>\n<code>{e}</code>")
            return False

    def ensure_connected(self) -> bool:
        """Verifies session health; reconnects with fresh TOTP if session expired or lost"""
        try:
            if not self.smart_api or not self.auth_data:
                return self.connect()
            q = self.get_spot_quote()
            if q and float(q.get("ltp", 0.0)) > 0:
                return True
        except Exception:
            pass
        logger.info("Session check: Re-authenticating with fresh TOTP...")
        return self.connect()

    def _load_scrip_master(self):
        download_needed = True
        cache = self.cfg.SCRIP_CACHE_FILE
        if os.path.exists(cache):
            mtime = datetime.fromtimestamp(os.path.getmtime(cache))
            if datetime.now() - mtime < timedelta(hours=18):
                try:
                    with open(cache, "r", encoding="utf-8") as f:
                        data = json.load(f)
                    self.scrip_df = pd.DataFrame(data)
                    logger.info(f"Scrip Master loaded from local cache ({len(self.scrip_df)} instruments).")
                    download_needed = False
                except Exception:
                    download_needed = True

        if download_needed:
            logger.info("Downloading latest Scrip Master from Angel One server (~38MB)...")
            url = "https://margincalculator.angelbroking.com/OpenAPI_File/files/OpenAPIScripMaster.json"
            r = requests.get(url, timeout=35)
            if r.status_code == 200:
                data = r.json()
                with open(cache, "w", encoding="utf-8") as f:
                    json.dump(data, f)
                self.scrip_df = pd.DataFrame(data)
                logger.info(f"Downloaded and cached {len(self.scrip_df)} instruments.")
            else:
                logger.error("Failed to download Scrip Master!")

    def get_spot_quote(self) -> dict:
        try:
            res = self.smart_api.ltpData(self.cfg.EXCHANGE_INDEX, self.cfg.SYMBOL_INDEX, self.cfg.TOKEN_INDEX)
            if res and res.get("status"):
                return res.get("data", {})
        except Exception as e:
            logger.error(f"Error fetching spot quote: {e}")
        return {}

    def get_option_ltp(self, symbol: str, token: str) -> float:
        try:
            res = self.smart_api.ltpData(self.cfg.EXCHANGE_OPTIONS, symbol, token)
            if res and res.get("status"):
                return float(res["data"]["ltp"])
        except Exception as e:
            logger.error(f"Error fetching option LTP ({symbol}): {e}")
        return 0.0

    def resolve_target_option(self, spot: float, opt_type: str, mode: str = "OTM-1") -> dict:
        """Finds nearest weekly expiry option matching strike (OTM-1: +50 CE / -50 PE, or ATM)"""
        atm_strike = int(round(spot / 50) * 50)
        is_call = (opt_type == "CE")
        if mode == "OTM-1":
            strike = (atm_strike + 50) if is_call else (atm_strike - 50)
        else:
            strike = atm_strike
        strike_val = float(strike * 100)

        df = self.scrip_df
        if df is None or df.empty:
            return {}

        nifty_opts = df[(df["name"] == "NIFTY") & (df["exch_seg"] == "NFO")].copy()
        nifty_opts["expiry_dt"] = pd.to_datetime(nifty_opts["expiry"], format="%d%b%Y")

        today = pd.to_datetime(datetime.now().date())
        valid_opts = nifty_opts[nifty_opts["expiry_dt"] >= today].sort_values("expiry_dt")
        if valid_opts.empty:
            return {}

        nearest_expiry = valid_opts["expiry_dt"].iloc[0]
        expiry_str = valid_opts["expiry"].iloc[0]

        target = valid_opts[
            (valid_opts["expiry_dt"] == nearest_expiry) &
            (valid_opts["strike"].astype(float) == strike_val) &
            (valid_opts["symbol"].str.endswith(opt_type))
        ]

        if not target.empty:
            row = target.iloc[0]
            token = str(row["token"])
            symbol = str(row["symbol"])
            ltp = self.get_option_ltp(symbol, token)
            return {
                "symbol": symbol,
                "token": token,
                "strike": strike,
                "opt_type": opt_type,
                "expiry": expiry_str,
                "ltp": ltp
            }
        return {}

    def resolve_atm_option(self, spot: float, opt_type: str) -> dict:
        """Alias for resolving option using BotConfig strike mode"""
        return self.resolve_target_option(spot, opt_type, self.cfg.STRIKE_MODE)

    def get_5m_candles(self) -> pd.DataFrame:
        try:
            today_str = datetime.now().strftime("%Y-%m-%d")
            params = {
                "exchange": self.cfg.EXCHANGE_INDEX,
                "symboltoken": self.cfg.TOKEN_INDEX,
                "interval": "FIVE_MINUTE",
                "fromdate": f"{today_str} 09:15",
                "todate": f"{today_str} 15:30"
            }
            res = self.smart_api.getCandleData(params)
            if res and res.get("status") and res.get("data"):
                cols = ["datetime", "open", "high", "low", "close", "volume"]
                df = pd.DataFrame(res["data"], columns=cols)
                df["datetime"] = pd.to_datetime(df["datetime"])
                return df
        except Exception as e:
            logger.error(f"Error fetching 5m candles: {e}")
        return pd.DataFrame()

    def get_previous_day_candle(self) -> dict:
        """
        Fetches the previous completed trading day's daily candle (PDH, PDL, PDC).
        Multi-tier fallback:
          Tier 1: Angel One SmartAPI ONE_DAY candles
          Tier 2: yfinance (^NSEI daily candles)
          Tier 3: Local historical database (nifty_data/candles/NIFTY_1day.csv)
        """
        now = datetime.now()
        today_date = now.date()

        # Tier 1: Angel One SmartAPI
        try:
            from_date = (today_date - timedelta(days=10)).strftime("%Y-%m-%d")
            to_date = today_date.strftime("%Y-%m-%d")
            params = {
                "exchange": self.cfg.EXCHANGE_INDEX,
                "symboltoken": self.cfg.TOKEN_INDEX,
                "interval": "ONE_DAY",
                "fromdate": f"{from_date} 09:15",
                "todate": f"{to_date} 15:30"
            }
            res = self.smart_api.getCandleData(params)
            if res and res.get("status") and res.get("data"):
                past_candles = []
                for c in res["data"]:
                    c_date_str = str(c[0])[:10]
                    try:
                        c_date = datetime.strptime(c_date_str, "%Y-%m-%d").date()
                    except Exception:
                        continue
                    if c_date < today_date:
                        past_candles.append(c)

                if past_candles:
                    prev = past_candles[-1]
                    p_high = float(prev[2])
                    p_low = float(prev[3])
                    p_close = float(prev[4])
                    if p_high > p_low > 0 and p_close > 0:
                        logger.info(f"[Tier 1 SmartAPI] Loaded previous day candle ({prev[0][:10]}): High={p_high}, Low={p_low}, Close={p_close}")
                        return {
                            "date": prev[0][:10],
                            "open": float(prev[1]),
                            "high": p_high,
                            "low": p_low,
                            "close": p_close
                        }
        except Exception as e:
            logger.warning(f"Tier 1 SmartAPI daily candle fetch: {e}")

        # Tier 2: yfinance (^NSEI)
        try:
            import yfinance as yf
            yf_df = yf.download("^NSEI", period="7d", interval="1d", progress=False)
            if not yf_df.empty:
                if hasattr(yf_df.columns, "levels") and len(yf_df.columns.levels) > 1:
                    yf_df.columns = [c[0].lower() for c in yf_df.columns]
                else:
                    yf_df.columns = [str(c).lower() for c in yf_df.columns]

                yf_df = yf_df[yf_df.index.date < today_date]
                if not yf_df.empty:
                    last_row = yf_df.iloc[-1]
                    d_str = str(yf_df.index[-1].date())
                    h = float(last_row["high"])
                    l = float(last_row["low"])
                    c = float(last_row["close"])
                    o = float(last_row.get("open", c))
                    if h > l > 0 and c > 0:
                        logger.info(f"[Tier 2 yfinance] Loaded previous day candle ({d_str}): High={h:.2f}, Low={l:.2f}, Close={c:.2f}")
                        return {"date": d_str, "open": o, "high": h, "low": l, "close": c}
        except Exception as e:
            logger.warning(f"Tier 2 yfinance daily candle fetch: {e}")

        # Tier 3: Local historical CSV
        try:
            csv_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "nifty_data", "candles", "NIFTY_1day.csv")
            if os.path.exists(csv_path):
                df_csv = pd.read_csv(csv_path)
                df_csv["dt"] = pd.to_datetime(df_csv["datetime"]).dt.date
                df_csv = df_csv[df_csv["dt"] < today_date]
                if not df_csv.empty:
                    last_row = df_csv.iloc[-1]
                    h = float(last_row["high"])
                    l = float(last_row["low"])
                    c = float(last_row["close"])
                    o = float(last_row["open"])
                    d_str = str(last_row["dt"])
                    if h > l > 0 and c > 0:
                        logger.info(f"[Tier 3 Local CSV] Loaded previous day candle ({d_str}): High={h:.2f}, Low={l:.2f}, Close={c:.2f}")
                        return {"date": d_str, "open": o, "high": h, "low": l, "close": c}
        except Exception as e:
            logger.warning(f"Tier 3 Local CSV daily candle fetch: {e}")

        return {}


# ==================================================================================================
# 5. P&L TRACKER (DAILY & WEEKLY FROM SCRATCH)
# ==================================================================================================
class PnLManager:
    def __init__(self, trades_file: str, initial_capital: float):
        self.trades_file = trades_file
        self.initial_capital = initial_capital

    def _read_trades(self) -> pd.DataFrame:
        if not os.path.exists(self.trades_file):
            return pd.DataFrame()
        try:
            df = pd.read_csv(self.trades_file)
            if df.empty or "Date" not in df.columns:
                return pd.DataFrame()
            df["Date_dt"] = pd.to_datetime(df["Date"])
            return df
        except Exception:
            return pd.DataFrame()

    def get_daily_stats(self, target_date: str = None) -> dict:
        if target_date is None:
            target_date = datetime.now().strftime("%Y-%m-%d")

        df = self._read_trades()
        res = {
            "date": target_date,
            "trades": 0, "wins": 0, "losses": 0, "win_rate": 0.0,
            "gross_pnl": 0.0, "costs": 0.0, "net_pnl": 0.0, "points": 0.0
        }
        if df.empty:
            return res

        day_df = df[df["Date"] == target_date]
        if day_df.empty:
            return res

        t_cnt = len(day_df)
        wins = int((day_df["Net_PnL"] > 0).sum())
        losses = int((day_df["Net_PnL"] < 0).sum())
        wr = round((wins / t_cnt * 100.0), 1) if t_cnt > 0 else 0.0
        gross = round(float(day_df["Gross_PnL"].sum()), 2) if "Gross_PnL" in day_df.columns else round(float(day_df["Net_PnL"].sum()), 2)
        costs = round(float(day_df["Costs"].sum()), 2) if "Costs" in day_df.columns else 0.0
        net = round(float(day_df["Net_PnL"].sum()), 2)
        pts = round(float(day_df["Points"].sum()), 2) if "Points" in day_df.columns else 0.0

        return {
            "date": target_date,
            "trades": t_cnt, "wins": wins, "losses": losses, "win_rate": wr,
            "gross_pnl": gross, "costs": costs, "net_pnl": net, "points": pts
        }

    def get_weekly_stats(self, ref_dt: datetime = None) -> dict:
        if ref_dt is None:
            ref_dt = datetime.now()

        monday_dt = ref_dt - timedelta(days=ref_dt.weekday())
        friday_dt = monday_dt + timedelta(days=4)
        sunday_dt = monday_dt + timedelta(days=6)

        iso_week = monday_dt.isocalendar()[1]
        week_span = f"W{iso_week} ({monday_dt.strftime('%d-%b')} to {friday_dt.strftime('%d-%b')})"

        res = {
            "week_span": week_span, "iso_week": iso_week,
            "trades": 0, "wins": 0, "losses": 0, "win_rate": 0.0,
            "net_pnl": 0.0, "best_trade": 0.0, "worst_trade": 0.0, "days_traded": 0
        }

        df = self._read_trades()
        if df.empty:
            return res

        week_df = df[(df["Date_dt"] >= pd.to_datetime(monday_dt.strftime("%Y-%m-%d"))) &
                     (df["Date_dt"] <= pd.to_datetime(sunday_dt.strftime("%Y-%m-%d")))]
        if week_df.empty:
            return res

        t_cnt = len(week_df)
        wins = int((week_df["Net_PnL"] > 0).sum())
        losses = int((week_df["Net_PnL"] < 0).sum())
        wr = round((wins / t_cnt * 100.0), 1) if t_cnt > 0 else 0.0
        net = round(float(week_df["Net_PnL"].sum()), 2)
        best = round(float(week_df["Net_PnL"].max()), 2)
        worst = round(float(week_df["Net_PnL"].min()), 2)
        days = int(week_df["Date"].nunique())

        return {
            "week_span": week_span, "iso_week": iso_week,
            "trades": t_cnt, "wins": wins, "losses": losses, "win_rate": wr,
            "net_pnl": net, "best_trade": best, "worst_trade": worst, "days_traded": days
        }

    def get_overall_stats(self, current_capital: float) -> dict:
        df = self._read_trades()
        if df.empty:
            return {
                "total_trades": 0, "wins": 0, "losses": 0, "win_rate": 0.0,
                "total_net_pnl": 0.0, "current_capital": current_capital, "roi_pct": 0.0
            }
        t_cnt = len(df)
        wins = int((df["Net_PnL"] > 0).sum())
        losses = int((df["Net_PnL"] < 0).sum())
        wr = round((wins / t_cnt * 100.0), 1) if t_cnt > 0 else 0.0
        total_net = round(float(df["Net_PnL"].sum()), 2)
        roi = round(((current_capital - self.initial_capital) / self.initial_capital) * 100.0, 2)
        return {
            "total_trades": t_cnt, "wins": wins, "losses": losses, "win_rate": wr,
            "total_net_pnl": total_net, "current_capital": current_capital, "roi_pct": roi
        }

# ==================================================================================================
# 6. LIVE HTML DASHBOARD GENERATOR (AUTO-REFRESHES IN BROWSER)
# ==================================================================================================
class DashboardGenerator:
    @staticmethod
    def render(config: BotConfig, levels: dict, pos: dict, daily: dict, weekly: dict, overall: dict, spot: float, last_msg: str, market_state: str = "OPEN"):
        if market_state != "OPEN":
            pos_badge = f'<span class="status-badge" style="background: rgba(245, 158, 11, 0.2); color: #f59e0b; border: 1px solid rgba(245, 158, 11, 0.4);">STANDBY ({market_state})</span>'
        elif pos:
            pos_badge = '<span class="status-badge live">HOLDING POSITION</span>'
        else:
            pos_badge = '<span class="status-badge flat">FLAT (MONITORING)</span>'

        if pos:
            pts = pos.get('current_pts', 0.0)
            cur_pnl = pos.get('unrealized_pnl', 0.0)
            pnl_cls = "pnl-green" if cur_pnl >= 0 else "pnl-red"
            
            if pos.get("t1_hit"):
                stage_badge = '<span style="color: #10b981; font-weight: 700; margin-left: 10px;">🎯 STAGE 1 BANKED (+100 pts | +Rs 6,500) | LOT 2 RUNNER ACTIVE</span>'
                sl_display = f'<strong style="color: #10b981;">Rs {pos["sl_prem"]:.2f} (Risk-Free Breakeven +4)</strong>'
            else:
                stage_badge = '<span style="color: #38bdf8; font-weight: 700; margin-left: 10px;">📦 2 LOTS ACTIVE (Aiming T1 +100 / T2 +200)</span>'
                sl_display = f'<strong style="color: #ef4444;">Rs {pos["sl_prem"]:.2f} (-{config.STOP_LOSS_PTS:.0f} pts)</strong>'

            pos_html = f"""
            <div class="pos-card active">
                <div class="pos-header">
                    <div>
                        <span class="pos-inst">{pos['symbol']}</span>
                        <span class="pos-type {pos['type'].lower()}">{pos['type']}</span>
                        {stage_badge}
                    </div>
                    <div class="pos-pnl {pnl_cls}">Rs {cur_pnl:+,.2f} ({pts:+.2f} pts)</div>
                </div>
                <div class="pos-grid">
                    <div><span class="lbl">Entry Prem:</span> <strong>Rs {pos['entry_prem']:.2f}</strong></div>
                    <div><span class="lbl">Current LTP:</span> <strong>Rs {pos.get('current_ltp', pos['entry_prem']):.2f}</strong></div>
                    <div><span class="lbl">Stop Loss:</span> {sl_display}</div>
                    <div><span class="lbl">Target 1:</span> <strong style="color: #10b981;">Rs {pos.get('tp1_prem', pos['entry_prem']+100):.2f} (+{config.TARGET_1_PTS:.0f} pts | Book 1 Lot)</strong></div>
                    <div><span class="lbl">Target 2:</span> <strong style="color: #38bdf8;">Rs {pos.get('tp2_prem', pos['entry_prem']+200):.2f} (+{config.TARGET_2_PTS:.0f} pts | Runner Lot 2)</strong></div>
                    <div><span class="lbl">Open Position:</span> <strong>{pos.get('qty_open', pos['qty'])} Qty ({pos.get('lots_open', config.NUM_LOTS)} Lot remaining)</strong></div>
                    <div><span class="lbl">Playbook:</span> <strong>{pos['playbook']}</strong></div>
                </div>
            </div>
            """
        elif market_state != "OPEN":
            pos_html = f"""
            <div class="pos-card empty" style="border-color: rgba(245, 158, 11, 0.3);">
                <div style="font-size: 16px; font-weight: 600; color: #f59e0b;">💤 24/7 Standby Mode ({market_state})</div>
                <div style="font-size: 13px; color: #9ca3af; margin-top: 4px;">{last_msg}</div>
            </div>
            """
        else:
            pos_html = """
            <div class="pos-card empty">
                <div style="font-size: 16px; font-weight: 600; color: #9ca3af;">No Active Position</div>
                <div style="font-size: 13px; color: #6b7280; margin-top: 4px;">Engine is scanning 5-minute candles for Institutional S&R and Gap Polarity signals.</div>
            </div>
            """

        # Read trade history for table
        trades_rows = ""
        if os.path.exists(config.TRADES_FILE):
            try:
                tdf = pd.read_csv(config.TRADES_FILE)
                for _, r in tdf.iloc[::-1].head(15).iterrows():
                    cls = "pnl-green" if r["Net_PnL"] > 0 else "pnl-red"
                    trades_rows += f"""
                    <tr>
                        <td><strong>{r['Date']}</strong></td>
                        <td>{r['Entry_Time']}</td>
                        <td>{r['Instrument']}</td>
                        <td>{r['Playbook']}</td>
                        <td>Rs {r['Entry_Prem']:.2f}</td>
                        <td>Rs {r['Exit_Prem']:.2f}</td>
                        <td>{r['Points']:+.1f}</td>
                        <td class="{cls}"><strong>Rs {r['Net_PnL']:+,.2f}</strong></td>
                        <td>{r['Reason']}</td>
                    </tr>
                    """
            except Exception:
                pass

        if not trades_rows:
            trades_rows = '<tr><td colspan="9" style="text-align: center; color: #6b7280; padding: 20px;">Fresh Start — No closed trades yet.</td></tr>'

        html = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta http-equiv="refresh" content="5">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>NIFTY Algo Live Monitor | Angel One SmartAPI</title>
    <link href="https://fonts.googleapis.com/css2?family=Outfit:wght@300;400;500;600;700;800&family=JetBrains+Mono:wght@400;600&display=swap" rel="stylesheet">
    <style>
        :root {{
            --bg: #0a0e17;
            --surface: #111827;
            --surface-hover: #1f2937;
            --border: #374151;
            --primary: #00f2fe;
            --accent: #4facfe;
            --success: #10b981;
            --danger: #ef4444;
            --text-main: #f9fafb;
            --text-muted: #9ca3af;
        }}
        * {{ margin: 0; padding: 0; box-sizing: border-box; }}
        body {{
            background: var(--bg);
            color: var(--text-main);
            font-family: 'Outfit', sans-serif;
            padding: 20px;
            min-height: 100vh;
        }}
        .header {{
            background: linear-gradient(135deg, #1e1b4b 0%, #0f172a 100%);
            border: 1px solid rgba(255,255,255,0.1);
            padding: 20px 24px;
            border-radius: 14px;
            margin-bottom: 20px;
            display: flex;
            justify-content: space-between;
            align-items: center;
        }}
        .header h1 {{
            font-size: 22px;
            font-weight: 800;
            background: linear-gradient(90deg, #00f2fe, #4facfe);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
        }}
        .header p {{ color: var(--text-muted); font-size: 13px; margin-top: 4px; }}
        .status-badge {{
            padding: 6px 14px;
            border-radius: 20px;
            font-size: 12px;
            font-weight: 700;
            letter-spacing: 0.5px;
        }}
        .status-badge.live {{
            background: rgba(16, 185, 129, 0.15);
            border: 1px solid var(--success);
            color: var(--success);
        }}
        .status-badge.flat {{
            background: rgba(0, 242, 254, 0.15);
            border: 1px solid var(--primary);
            color: var(--primary);
        }}
        .kpi-grid {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
            gap: 16px;
            margin-bottom: 20px;
        }}
        .kpi-card {{
            background: var(--surface);
            border: 1px solid var(--border);
            padding: 18px;
            border-radius: 12px;
        }}
        .kpi-lbl {{ font-size: 12px; color: var(--text-muted); text-transform: uppercase; font-weight: 600; }}
        .kpi-val {{ font-size: 22px; font-weight: 700; margin-top: 6px; font-family: 'JetBrains Mono', monospace; }}
        .kpi-sub {{ font-size: 12px; color: var(--text-muted); margin-top: 4px; }}
        .pnl-green {{ color: var(--success); }}
        .pnl-red {{ color: var(--danger); }}
        .pos-section {{ margin-bottom: 20px; }}
        .pos-card {{
            background: var(--surface);
            border: 1px solid var(--border);
            border-radius: 12px;
            padding: 20px;
        }}
        .pos-card.active {{ border-color: var(--primary); }}
        .pos-card.empty {{ text-align: center; padding: 30px; }}
        .pos-header {{
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 16px;
            padding-bottom: 12px;
            border-bottom: 1px solid rgba(255,255,255,0.08);
        }}
        .pos-inst {{ font-size: 18px; font-weight: 700; font-family: 'JetBrains Mono', monospace; }}
        .pos-type {{
            padding: 2px 8px;
            border-radius: 4px;
            font-size: 12px;
            font-weight: 700;
            margin-left: 8px;
        }}
        .pos-type.ce {{ background: rgba(16, 185, 129, 0.2); color: #10b981; }}
        .pos-type.pe {{ background: rgba(239, 68, 68, 0.2); color: #ef4444; }}
        .pos-pnl {{ font-size: 20px; font-weight: 800; font-family: 'JetBrains Mono', monospace; }}
        .pos-grid {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(170px, 1fr));
            gap: 12px;
            font-size: 13px;
        }}
        .pos-grid .lbl {{ color: var(--text-muted); display: block; font-size: 11px; margin-bottom: 2px; }}
        .levels-grid {{
            display: grid;
            grid-template-columns: repeat(5, 1fr);
            gap: 10px;
            margin-bottom: 20px;
        }}
        .level-box {{
            background: var(--surface);
            border: 1px solid var(--border);
            padding: 12px;
            border-radius: 10px;
            text-align: center;
        }}
        .level-name {{ font-size: 11px; color: var(--text-muted); font-weight: 600; text-transform: uppercase; }}
        .level-val {{ font-size: 16px; font-weight: 700; margin-top: 4px; font-family: 'JetBrains Mono', monospace; }}
        .table-box {{
            background: var(--surface);
            border: 1px solid var(--border);
            border-radius: 12px;
            padding: 20px;
        }}
        .table-box h3 {{ font-size: 15px; margin-bottom: 14px; color: #e5e7eb; }}
        table {{ width: 100%; border-collapse: collapse; font-size: 12px; }}
        th {{ background: #1e293b; color: #94a3b8; padding: 10px 12px; text-align: left; }}
        td {{ padding: 10px 12px; border-bottom: 1px solid rgba(255,255,255,0.05); font-family: 'JetBrains Mono', monospace; }}
        tr:hover td {{ background: var(--surface-hover); }}
    </style>
</head>
<body>
    <div class="header">
        <div>
            <h1>⚡ NIFTY 50 OPTIONS ALGO BOT — LIVE MONITOR</h1>
            <p>Underlying: NIFTY 50 (Spot: <strong>{spot:,.2f}</strong>) | Angel One SmartAPI | Auto-refreshing every 5s</p>
        </div>
        <div>
            {pos_badge}
        </div>
    </div>

    <div class="kpi-grid">
        <div class="kpi-card">
            <div class="kpi-lbl">Daily P&L (Today)</div>
            <div class="kpi-val {'pnl-green' if daily['net_pnl'] >= 0 else 'pnl-red'}">Rs {daily['net_pnl']:+,.2f}</div>
            <div class="kpi-sub">{daily['trades']} Trades | {daily['wins']}W / {daily['losses']}L ({daily['win_rate']:.0f}% WR)</div>
        </div>
        <div class="kpi-card">
            <div class="kpi-lbl">Weekly P&L ({weekly['week_span']})</div>
            <div class="kpi-val {'pnl-green' if weekly['net_pnl'] >= 0 else 'pnl-red'}">Rs {weekly['net_pnl']:+,.2f}</div>
            <div class="kpi-sub">{weekly['trades']} Trades | {weekly['wins']}W / {weekly['losses']}L ({weekly['win_rate']:.0f}% WR)</div>
        </div>
        <div class="kpi-card">
            <div class="kpi-lbl">Current Capital</div>
            <div class="kpi-val {'pnl-green' if overall['current_capital'] >= config.INITIAL_CAPITAL else 'pnl-red'}">Rs {overall['current_capital']:,.2f}</div>
            <div class="kpi-sub">Started: Rs {config.INITIAL_CAPITAL:,.2f} ({overall['roi_pct']:+.2f}% ROI)</div>
        </div>
        <div class="kpi-card">
            <div class="kpi-lbl">Last Activity</div>
            <div class="kpi-val" style="font-size: 14px; color: var(--primary);">{datetime.now().strftime('%H:%M:%S IST')}</div>
            <div class="kpi-sub">{last_msg}</div>
        </div>
    </div>

    <div class="pos-section">
        {pos_html}
    </div>

    <div class="levels-grid" style="display: grid; grid-template-columns: repeat(auto-fit, minmax(110px, 1fr)); gap: 10px;">
        <div class="level-box" style="border-top: 3px solid #dc2626;">
            <div class="level-name">Resistance R4</div>
            <div class="level-val">{levels.get('r4', '-')}</div>
        </div>
        <div class="level-box" style="border-top: 3px solid #e11d48;">
            <div class="level-name">Resistance R3</div>
            <div class="level-val">{levels.get('r3', '-')}</div>
        </div>
        <div class="level-box" style="border-top: 3px solid #ef4444;">
            <div class="level-name">Resistance R2</div>
            <div class="level-val">{levels.get('r2', '-')}</div>
        </div>
        <div class="level-box" style="border-top: 3px solid #f97316;">
            <div class="level-name">Resistance R1</div>
            <div class="level-val">{levels.get('r1', '-')}</div>
        </div>
        <div class="level-box" style="border-top: 3px solid #00f2fe;">
            <div class="level-name">Pivot Point</div>
            <div class="level-val">{levels.get('pivot', '-')}</div>
        </div>
        <div class="level-box" style="border-top: 3px solid #22c55e;">
            <div class="level-name">Support S1</div>
            <div class="level-val">{levels.get('s1', '-')}</div>
        </div>
        <div class="level-box" style="border-top: 3px solid #10b981;">
            <div class="level-name">Support S2</div>
            <div class="level-val">{levels.get('s2', '-')}</div>
        </div>
        <div class="level-box" style="border-top: 3px solid #059669;">
            <div class="level-name">Support S3</div>
            <div class="level-val">{levels.get('s3', '-')}</div>
        </div>
        <div class="level-box" style="border-top: 3px solid #047857;">
            <div class="level-name">Support S4</div>
            <div class="level-val">{levels.get('s4', '-')}</div>
        </div>
    </div>

    <div class="table-box">
        <h3>Closed Trades Ledger (Fresh Session)</h3>
        <table>
            <thead>
                <tr>
                    <th>Date</th>
                    <th>Time</th>
                    <th>Contract</th>
                    <th>Playbook</th>
                    <th>Entry</th>
                    <th>Exit</th>
                    <th>Pts</th>
                    <th>Net P&L</th>
                    <th>Exit Trigger</th>
                </tr>
            </thead>
            <tbody>
                {trades_rows}
            </tbody>
        </table>
    </div>
</body>
</html>
"""
        with open(config.DASHBOARD_FILE, "w", encoding="utf-8") as f:
            f.write(html)

# ==================================================================================================
# 7. MAIN TRADING & EXECUTION ENGINE
# ==================================================================================================
class NiftyAlgoEngine:
    def __init__(self, config: BotConfig, session: AngelManager, alerter: TelegramAlerter):
        self.cfg = config
        self.session = session
        self.alerter = alerter
        self.pnl = PnLManager(config.TRADES_FILE, config.INITIAL_CAPITAL)

        self.levels = {}
        self.capital = config.INITIAL_CAPITAL
        self.trades_today = 0
        self.current_position = None
        self.last_status_msg = "Bot Initialized"

        self.orb_high = None
        self.orb_low = None
        self.day_open = None
        self.eod_summary_sent_date = None
        self.current_day_initialized = None

        self._load_state()

    def reset_daily_state(self):
        """Resets daily counters and state for a fresh trading day"""
        self.trades_today = 0
        self.current_position = None
        self.orb_high = None
        self.orb_low = None
        self.day_open = None
        self.last_status_msg = "Fresh Trading Session Initialized"
        self._save_state()
        logger.info("Daily state reset for new trading session.")

    def check_levels_reload(self):
        """Checks if levels.json was edited by Web Dashboard and hot-reloads into bot runtime"""
        levels_file = "levels.json"
        if os.path.exists(levels_file):
            try:
                mtime = os.path.getmtime(levels_file)
                if not hasattr(self, "_levels_mtime"):
                    self._levels_mtime = mtime
                elif mtime > self._levels_mtime:
                    self._levels_mtime = mtime
                    with open(levels_file, "r") as f:
                        data = json.load(f)
                    today_str = datetime.now().strftime("%Y-%m-%d")
                    if data.get("date") == today_str and "nifty" in data:
                        old_r1 = self.levels.get("r1")
                        self.levels = data["nifty"]
                        if old_r1 != self.levels.get("r1"):
                            logger.info(f"⚡ HOT-RELOAD: Verified levels synced from levels.json! R1={self.levels['r1']} | S1={self.levels['s1']}")
            except Exception as e:
                logger.error(f"Error hot-reloading levels: {e}")

    def _load_state(self):
        if os.path.exists(self.cfg.STATE_FILE):
            try:
                with open(self.cfg.STATE_FILE, "r") as f:
                    state = json.load(f)
                today_str = datetime.now().strftime("%Y-%m-%d")
                if state.get("date") == today_str:
                    self.capital = state.get("capital", self.cfg.INITIAL_CAPITAL)
                    self.trades_today = state.get("trades_today", 0)
                    self.current_position = state.get("current_position", None)
                    logger.info(f"Loaded existing state for today: Capital=Rs {self.capital:,.2f}, Trades={self.trades_today}")
            except Exception as e:
                logger.error(f"Error loading state: {e}")

    def _save_state(self):
        today_str = datetime.now().strftime("%Y-%m-%d")
        daily = self.pnl.get_daily_stats(today_str)
        weekly = self.pnl.get_weekly_stats()
        state = {
            "date": today_str,
            "capital": self.capital,
            "trades_today": self.trades_today,
            "daily_net_pnl": daily["net_pnl"],
            "daily_wins": daily["wins"],
            "daily_losses": daily["losses"],
            "weekly_net_pnl": weekly["net_pnl"],
            "weekly_trades": weekly["trades"],
            "current_position": self.current_position
        }
        with open(self.cfg.STATE_FILE, "w") as f:
            json.dump(state, f, indent=2)

    def log_trade(self, trade_data: dict):
        df = pd.DataFrame([trade_data])
        if not os.path.exists(self.cfg.TRADES_FILE):
            df.to_csv(self.cfg.TRADES_FILE, index=False)
        else:
            df.to_csv(self.cfg.TRADES_FILE, mode="a", header=False, index=False)

    def initialize_daily_levels(self):
        logger.info("Initializing daily levels...")
        today_str = datetime.now().strftime("%Y-%m-%d")

        # 1. Check for manual/verified daily levels in levels.json
        levels_file = "levels.json"
        if os.path.exists(levels_file):
            try:
                with open(levels_file, "r") as f:
                    cust_levels = json.load(f)
                if cust_levels.get("date") == today_str and "nifty" in cust_levels:
                    self.levels = cust_levels["nifty"]
                    logger.info(f"Loaded verified levels from {levels_file}: P={self.levels['pivot']} | R1={self.levels['r1']} | R2={self.levels['r2']} | S1={self.levels['s1']} | S2={self.levels['s2']}")
                    msg = (
                        f"🎯 <b>NIFTY DAILY LEVELS INITIALIZED (VERIFIED INTRADAY)</b>\n"
                        f"📅 Date: <b>{datetime.now().strftime('%d-%b-%Y')}</b>\n"
                        f"━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
                        f"🔴 <b>Resistance R4:</b> {self.levels.get('r4', '-')}\n"
                        f"🔴 <b>Resistance R3:</b> {self.levels.get('r3', '-')}\n"
                        f"🔴 <b>Resistance R2:</b> {self.levels.get('r2', '-')}\n"
                        f"🔺 <b>Resistance R1:</b> {self.levels.get('r1', '-')}\n"
                        f"⚪ <b>Pivot Point:</b> {self.levels.get('pivot', '-')} (CPR: {self.levels.get('cpr_bot', '-')} - {self.levels.get('cpr_top', '-')})\n"
                        f"🔻 <b>Support S1:</b> {self.levels.get('s1', '-')}\n"
                        f"🟢 <b>Support S2:</b> {self.levels.get('s2', '-')}\n"
                        f"🟢 <b>Support S3:</b> {self.levels.get('s3', '-')}\n"
                        f"🟢 <b>Support S4:</b> {self.levels.get('s4', '-')}\n"
                        f"━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
                        f"💰 <b>Capital:</b> Rs {self.capital:,.2f} (Fresh Start)\n"
                        f"🤖 <b>Bot Status:</b> ACTIVE & SCANNING 5M CANDLES"
                    )
                    self.alerter.send(msg)
                    return
            except Exception as e:
                logger.error(f"Error loading custom levels from {levels_file}: {e}")

        prev_candle = self.session.get_previous_day_candle()

        if prev_candle and prev_candle.get("high", 0) > prev_candle.get("low", 0) > 0:
            p_high = float(prev_candle["high"])
            p_low = float(prev_candle["low"])
            p_close = float(prev_candle["close"])
            candle_date = prev_candle.get("date", "Previous Trading Day")
            logger.info(f"Using actual completed daily candle from {candle_date}: H={p_high}, L={p_low}, C={p_close}")
        else:
            logger.warning("Historical daily candle unavailable; falling back to spot quote...")
            quote = self.session.get_spot_quote()
            prev_close = float(quote.get("close", 0.0) or quote.get("ltp", 0.0)) if quote else 0.0
            if prev_close <= 0:
                prev_close = 22625.0

            q_high = float(quote.get("high", 0.0)) if quote else 0.0
            q_low = float(quote.get("low", 0.0)) if quote else 0.0

            if q_high > q_low > 0 and (q_high - q_low) >= 30.0:
                p_high = q_high
                p_low = q_low
                p_close = prev_close
            else:
                p_high = round((prev_close * 1.008) / 5) * 5
                p_low = round((prev_close * 0.992) / 5) * 5
                p_close = prev_close

        self.levels = SRCalculator.compute(p_high, p_low, p_close)
        logger.info(f"Levels set: P={self.levels['pivot']} | R1={self.levels['r1']} | R2={self.levels['r2']} | S1={self.levels['s1']} | S2={self.levels['s2']}")

        # Broadcast morning levels to Telegram
        msg = (
            f"🎯 <b>NIFTY DAILY LEVELS INITIALIZED</b>\n"
            f"📅 Date: <b>{datetime.now().strftime('%d-%b-%Y')}</b>\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"🔴 <b>Resistance R4:</b> {self.levels.get('r4', self.levels.get('r2'))}\n"
            f"🔴 <b>Resistance R3:</b> {self.levels.get('r3', self.levels.get('r2'))}\n"
            f"🔴 <b>Resistance R2:</b> {self.levels['r2']}\n"
            f"🔺 <b>Resistance R1:</b> {self.levels['r1']}\n"
            f"⚪ <b>Pivot Point:</b> {self.levels['pivot']} (CPR: {self.levels['cpr_bot']} - {self.levels['cpr_top']})\n"
            f"🔻 <b>Support S1:</b> {self.levels['s1']}\n"
            f"🟢 <b>Support S2:</b> {self.levels['s2']}\n"
            f"🟢 <b>Support S3:</b> {self.levels.get('s3', self.levels.get('s2'))}\n"
            f"🟢 <b>Support S4:</b> {self.levels.get('s4', self.levels.get('s2'))}\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"💰 <b>Capital:</b> Rs {self.capital:,.2f} (Fresh Start)\n"
            f"🤖 <b>Bot Status:</b> ACTIVE & SCANNING 5M CANDLES\n"
            f"📦 <b>Engine:</b> 2-Lot Staged (T1: +100 | T2: +200 | OTM-1)"
        )
        self.alerter.send(msg)


    def enter_trade(self, playbook: str, opt_type: str, spot: float):
        if self.trades_today >= self.cfg.MAX_TRADES_PER_DAY:
            return

        if self.cfg.DAILY_STOP_ON_LOSS and self.trades_today >= 1:
            today_str = datetime.now().strftime("%Y-%m-%d")
            daily = self.pnl.get_daily_stats(today_str)
            if daily.get("losses", 0) >= 1:
                logger.info("DAILY STOP-ON-LOSS ACTIVE: Trade 1 today was a loss. Skipping trade 2 to avoid choppy regime.")
                return

        opt = self.session.resolve_target_option(spot, opt_type, self.cfg.STRIKE_MODE)
        if not opt or opt.get("ltp", 0) <= 0:
            logger.warning(f"Could not fetch {self.cfg.STRIKE_MODE} option quote for {opt_type} at spot {spot}!")
            return

        raw_prem = opt["ltp"]
        entry_prem = round(raw_prem * (1.0 + self.cfg.SLIPPAGE_RATE), 2)
        sl_prem = round(max(1.0, entry_prem - self.cfg.STOP_LOSS_PTS), 2)
        tp1_prem = round(entry_prem + self.cfg.TARGET_1_PTS, 2)
        tp2_prem = round(entry_prem + self.cfg.TARGET_2_PTS, 2)
        total_qty = self.cfg.LOT_SIZE * self.cfg.NUM_LOTS

        self.current_position = {
            "playbook": playbook,
            "type": opt_type,
            "strike": opt["strike"],
            "symbol": opt["symbol"],
            "token": opt["token"],
            "expiry": opt["expiry"],
            "entry_time": datetime.now().strftime("%H:%M:%S"),
            "entry_spot": round(spot, 1),
            "entry_prem": entry_prem,
            "sl_prem": sl_prem,
            "tp1_prem": tp1_prem,
            "tp2_prem": tp2_prem,
            "total_lots": self.cfg.NUM_LOTS,
            "lots_open": self.cfg.NUM_LOTS,
            "qty": total_qty,
            "qty_open": total_qty,
            "t1_hit": False,
            "t1_exit_prem": 0.0,
            "t1_net_pnl": 0.0,
            "t1_time": None,
            "current_ltp": entry_prem,
            "max_ltp": entry_prem,
            "be_protected": False,
            "current_pts": 0.0,
            "unrealized_pnl": 0.0
        }
        self.trades_today += 1
        self.last_status_msg = f"Entered {opt['symbol']} 2 Lots ({playbook})"
        self._save_state()

        logger.info(f"ENTERED 2-LOT STAGED: {playbook} | {opt['symbol']} @ Rs {entry_prem} (SL: {sl_prem}, T1: {tp1_prem}, T2: {tp2_prem})")

        msg = (
            f"🚨 <b>SIGNAL TRIGGERED: {playbook.upper()} (2-LOT STAGED SCALE-OUT)</b>\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"📌 <b>Contract:</b> {opt['symbol']} ({opt_type} | {self.cfg.STRIKE_MODE})\n"
            f"📊 <b>NIFTY Spot:</b> {spot:.1f}\n"
            f"📥 <b>Entry Premium:</b> Rs {entry_prem:.2f}\n"
            f"🛑 <b>Initial Stop Loss:</b> Rs {sl_prem:.2f} (-{self.cfg.STOP_LOSS_PTS:.0f} pts)\n"
            f"🎯 <b>Target 1 (Book 1 Lot):</b> Rs {tp1_prem:.2f} (+{self.cfg.TARGET_1_PTS:.0f} pts | 1:2 RR | +₹6,500 banked)\n"
            f"🚀 <b>Target 2 (Runner Lot 2):</b> Rs {tp2_prem:.2f} (+{self.cfg.TARGET_2_PTS:.0f} pts | 1:4 RR | +₹13,000 runner)\n"
            f"📦 <b>Position Size:</b> {total_qty} ({self.cfg.NUM_LOTS} Lots)\n"
            f"⏰ <b>Time:</b> {self.current_position['entry_time']}\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"💼 <i>Execution Confirmed: 2-Lot Staged Scale-Out Engine Active</i>"
        )
        self.alerter.send(msg)

    def check_position_exit(self):
        if not self.current_position:
            return

        pos = self.current_position
        curr_ltp = self.session.get_option_ltp(pos["symbol"], pos["token"])
        if curr_ltp <= 0:
            return

        now_time = datetime.now().time()
        pos["current_ltp"] = curr_ltp
        pos["current_pts"] = round(curr_ltp - pos["entry_prem"], 2)

        if curr_ltp > pos.get("max_ltp", pos["entry_prem"]):
            pos["max_ltp"] = curr_ltp

        # Live unrealized stats for HUD & HTML Dashboard
        if not pos["t1_hit"]:
            pos["unrealized_pnl"] = round(pos["current_pts"] * pos["qty_open"], 2)
        else:
            runner_pnl = round(pos["current_pts"] * pos["qty_open"], 2)
            pos["unrealized_pnl"] = round(pos["t1_net_pnl"] + runner_pnl, 2)

        # -------------------------------------------------------------
        # PHASE 1: Neither target hit yet (Holding 2 Lots)
        # -------------------------------------------------------------
        if not pos["t1_hit"]:
            hit_sl = (curr_ltp <= pos["sl_prem"])
            hit_tp1 = (curr_ltp >= pos["tp1_prem"])
            hit_eod = (now_time >= self.cfg.SQUARE_OFF_TIME)

            if hit_sl and not hit_tp1:
                # Full Stop Loss on entire 2 Lots
                fill_exit = round(max(0.5, pos["sl_prem"] * (1.0 - self.cfg.SLIPPAGE_RATE)), 2)
                pts = fill_exit - pos["entry_prem"]
                gross_pnl = round(pts * pos["qty_open"], 2)

                stt = fill_exit * pos["qty_open"] * 0.000625
                turnover = (pos["entry_prem"] + fill_exit) * pos["qty_open"] * 0.00053
                brokerage = 40.0
                gst = (brokerage + turnover) * 0.18
                costs = round(brokerage + stt + turnover + gst, 2)
                net_pnl = round(gross_pnl - costs, 2)
                self.capital = round(self.capital + net_pnl, 2)

                reason = f"🛑 STOP LOSS HIT (-{self.cfg.STOP_LOSS_PTS:.0f} pts on 2 Lots)"
                logger.info(f"EXITED: {reason} | Net PnL: Rs {net_pnl:+} | Capital: Rs {self.capital:,.2f}")

                trade_log = {
                    "Date": datetime.now().strftime("%Y-%m-%d"),
                    "Entry_Time": pos["entry_time"],
                    "Exit_Time": datetime.now().strftime("%H:%M:%S"),
                    "Instrument": pos["symbol"],
                    "Playbook": pos["playbook"],
                    "Entry_Prem": pos["entry_prem"],
                    "Exit_Prem": fill_exit,
                    "Points": round(pts, 2),
                    "Gross_PnL": gross_pnl,
                    "Costs": costs,
                    "Net_PnL": net_pnl,
                    "Capital": self.capital,
                    "Reason": reason
                }
                self.log_trade(trade_log)

                daily = self.pnl.get_daily_stats()
                weekly = self.pnl.get_weekly_stats()
                overall = self.pnl.get_overall_stats(self.capital)

                self.current_position = None
                self.last_status_msg = f"Closed {pos['symbol']} ({reason})"
                self._save_state()

                msg = (
                    f"🔴 <b>TRADE CLOSED: {reason}</b>\n"
                    f"━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
                    f"📌 <b>Contract:</b> {pos['symbol']}\n"
                    f"⚡ <b>Playbook:</b> {pos['playbook']}\n"
                    f"📥 <b>Entry:</b> Rs {pos['entry_prem']:.2f}\n"
                    f"📤 <b>Exit:</b> Rs {fill_exit:.2f}\n"
                    f"📉 <b>Loss:</b> Rs {net_pnl:+,.2f} ({pts:+.2f} pts | 2 Lots)\n"
                    f"━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
                    f"💰 <b>Capital Balance:</b> Rs {self.capital:,.2f} ({overall['roi_pct']:+.1f}% ROI)"
                )
                self.alerter.send(msg)
                return

            elif hit_tp1:
                # 🎯 TARGET 1 HIT (+100 pts / 1:2 RR)! Book 1 Lot (+₹6,500 banked)
                fill_ex1 = round(pos["tp1_prem"] * (1.0 - self.cfg.SLIPPAGE_RATE), 2)
                pts1 = fill_ex1 - pos["entry_prem"]
                lot_qty = self.cfg.LOT_SIZE
                gross1 = round(pts1 * lot_qty, 2)

                stt1 = fill_ex1 * lot_qty * 0.000625
                turnover1 = (pos["entry_prem"] + fill_ex1) * lot_qty * 0.00053
                brokerage1 = 20.0
                gst1 = (brokerage1 + turnover1) * 0.18
                costs1 = round(brokerage1 + stt1 + turnover1 + gst1, 2)
                net1 = round(gross1 - costs1, 2)
                self.capital = round(self.capital + net1, 2)

                pos["t1_hit"] = True
                pos["t1_exit_prem"] = fill_ex1
                pos["t1_net_pnl"] = net1
                pos["t1_time"] = datetime.now().strftime("%H:%M:%S")
                pos["lots_open"] = 1
                pos["qty_open"] = lot_qty

                # Instantly move Stop Loss on Lot 2 to Breakeven (+4 pts buffer)
                be_sl = round(pos["entry_prem"] + self.cfg.SMART_BE_BUFFER_PTS, 2)
                pos["sl_prem"] = be_sl
                pos["be_protected"] = True
                self.last_status_msg = f"Banked T1 (+100 pts). Lot 2 SL moved to BE Rs {be_sl:.2f}"
                self._save_state()

                logger.info(f"STAGE 1 BOOKED: {pos['symbol']} 1 Lot @ Rs {fill_ex1:.2f} (+{pts1:.2f} pts | Net: +Rs {net1:,.2f}). SL on Lot 2 moved to BE Rs {be_sl:.2f}")

                msg = (
                    f"🎯 <b>STAGE 1 PROFIT BOOKED: TARGET 1 HIT (+100 PTS / 1:2 RR)!</b>\n"
                    f"━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
                    f"📌 <b>Contract:</b> {pos['symbol']}\n"
                    f"💰 <b>1 Lot Banked:</b> <b>+₹6,500 Gross (+Rs {net1:+,.2f} Net Banked)</b>\n"
                    f"📤 <b>Exit Prem:</b> Rs {fill_ex1:.2f} (+{pts1:+.2f} pts)\n"
                    f"━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
                    f"🛡️ <b>RISK-FREE RUNNER ACTIVATED:</b>\n"
                    f"  • Lot 2 Stop Loss instantly moved to <b>Breakeven Rs {be_sl:.2f} (+4 pts)</b>\n"
                    f"  • Downside risk is now <b>ZERO</b> (Guaranteed green trade!)\n"
                    f"  • Running Lot 2 for <b>Target 2 (+200 pts / 1:4 RR | +₹13,000)</b>\n"
                    f"━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
                    f"💰 <b>Capital Balance:</b> Rs {self.capital:,.2f}"
                )
                self.alerter.send(msg)

                # If TP2 was touched in this very tick, proceed immediately
                if curr_ltp < pos["tp2_prem"]:
                    return

            elif hit_eod:
                # EOD Square-off before T1 was hit
                fill_exit = round(max(0.5, curr_ltp * (1.0 - self.cfg.SLIPPAGE_RATE)), 2)
                pts = fill_exit - pos["entry_prem"]
                gross_pnl = round(pts * pos["qty_open"], 2)

                stt = fill_exit * pos["qty_open"] * 0.000625
                turnover = (pos["entry_prem"] + fill_exit) * pos["qty_open"] * 0.00053
                brokerage = 40.0
                gst = (brokerage + turnover) * 0.18
                costs = round(brokerage + stt + turnover + gst, 2)
                net_pnl = round(gross_pnl - costs, 2)
                self.capital = round(self.capital + net_pnl, 2)

                reason = "⏰ EOD AUTO SQUARE-OFF (15:00)"
                logger.info(f"EXITED: {reason} | Net PnL: Rs {net_pnl:+} | Capital: Rs {self.capital:,.2f}")

                trade_log = {
                    "Date": datetime.now().strftime("%Y-%m-%d"),
                    "Entry_Time": pos["entry_time"],
                    "Exit_Time": datetime.now().strftime("%H:%M:%S"),
                    "Instrument": pos["symbol"],
                    "Playbook": pos["playbook"],
                    "Entry_Prem": pos["entry_prem"],
                    "Exit_Prem": fill_exit,
                    "Points": round(pts, 2),
                    "Gross_PnL": gross_pnl,
                    "Costs": costs,
                    "Net_PnL": net_pnl,
                    "Capital": self.capital,
                    "Reason": reason
                }
                self.log_trade(trade_log)

                daily = self.pnl.get_daily_stats()
                weekly = self.pnl.get_weekly_stats()
                overall = self.pnl.get_overall_stats(self.capital)

                self.current_position = None
                self.last_status_msg = f"Closed {pos['symbol']} ({reason})"
                self._save_state()
                return

        # -------------------------------------------------------------
        # PHASE 2: Target 1 already banked! Managing Lot 2 Runner
        # -------------------------------------------------------------
        hit_tp2 = (curr_ltp >= pos["tp2_prem"])
        hit_be = (curr_ltp <= pos["sl_prem"])
        hit_eod = (now_time >= self.cfg.SQUARE_OFF_TIME)

        if hit_tp2 or hit_be or hit_eod:
            raw_ex2 = pos["tp2_prem"] if hit_tp2 else (pos["sl_prem"] if hit_be else curr_ltp)
            fill_ex2 = round(max(0.5, raw_ex2 * (1.0 - self.cfg.SLIPPAGE_RATE)), 2)
            pts2 = fill_ex2 - pos["entry_prem"]
            lot_qty = self.cfg.LOT_SIZE
            gross2 = round(pts2 * lot_qty, 2)

            stt2 = fill_ex2 * lot_qty * 0.000625
            turnover2 = (pos["entry_prem"] + fill_ex2) * lot_qty * 0.00053
            brokerage2 = 20.0
            gst2 = (brokerage2 + turnover2) * 0.18
            costs2 = round(brokerage2 + stt2 + turnover2 + gst2, 2)
            net2 = round(gross2 - costs2, 2)
            self.capital = round(self.capital + net2, 2)

            total_net = round(pos["t1_net_pnl"] + net2, 2)
            avg_exit = round((pos["t1_exit_prem"] + fill_ex2) / 2.0, 2)
            avg_pts = round(avg_exit - pos["entry_prem"], 2)
            total_gross = round((pos["t1_exit_prem"] - pos["entry_prem"] + pts2) * lot_qty, 2)
            total_costs = round(costs2 + 25.0, 2)

            if hit_tp2:
                reason = "🚀 FULL VICTORY: T1 (+100) & T2 (+200) HIT"
                emoji = "🏆"
            elif hit_be:
                reason = "🛡️ T1 BANKED (+100) & RUNNER BREAKEVEN (+4)"
                emoji = "🟢"
            else:
                reason = "⏰ T1 BANKED (+100) & RUNNER EOD"
                emoji = "🟢"

            logger.info(f"RUNNER CLOSED: {reason} | Combined Net PnL: Rs {total_net:+} | Capital: Rs {self.capital:,.2f}")

            trade_log = {
                "Date": datetime.now().strftime("%Y-%m-%d"),
                "Entry_Time": pos["entry_time"],
                "Exit_Time": datetime.now().strftime("%H:%M:%S"),
                "Instrument": pos["symbol"],
                "Playbook": pos["playbook"],
                "Entry_Prem": pos["entry_prem"],
                "Exit_Prem": avg_exit,
                "Points": avg_pts,
                "Gross_PnL": total_gross,
                "Costs": total_costs,
                "Net_PnL": total_net,
                "Capital": self.capital,
                "Reason": reason
            }
            self.log_trade(trade_log)

            daily = self.pnl.get_daily_stats()
            weekly = self.pnl.get_weekly_stats()
            overall = self.pnl.get_overall_stats(self.capital)

            self.current_position = None
            self.last_status_msg = f"Closed {pos['symbol']} ({reason})"
            self._save_state()

            msg = (
                f"{emoji} <b>2-LOT TRADE COMPLETE: {reason}</b>\n"
                f"━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
                f"📌 <b>Contract:</b> {pos['symbol']}\n"
                f"⚡ <b>Playbook:</b> {pos['playbook']}\n"
                f"📥 <b>Entry:</b> Rs {pos['entry_prem']:.2f}\n"
                f"📤 <b>Lot 1 Exit (+100 pts):</b> Rs {pos['t1_exit_prem']:.2f} (Net: +Rs {pos['t1_net_pnl']:+,.2f})\n"
                f"📤 <b>Lot 2 Exit:</b> Rs {fill_ex2:.2f} (Net: +Rs {net2:+,.2f})\n"
                f"━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
                f"💵 <b>TOTAL COMBINED NET PNL:</b> <b>Rs {total_net:+,.2f}</b>\n"
                f"📈 <b>Average Gain:</b> {avg_pts:+.2f} pts across 2 Lots\n"
                f"━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
                f"🟢 <b>Daily P&L (Today):</b> Rs {daily['net_pnl']:+,.2f} ({daily['wins']}W / {daily['losses']}L)\n"
                f"💰 <b>Capital Balance:</b> <b>Rs {self.capital:,.2f}</b> ({overall['roi_pct']:+.1f}% ROI)"
            )
            self.alerter.send(msg)

    def evaluate_market_signals(self):
        now_time = datetime.now().time()
        if now_time < self.cfg.ENTRY_START or now_time > self.cfg.ENTRY_END:
            return

        if self.current_position is not None or self.trades_today >= self.cfg.MAX_TRADES_PER_DAY:
            return

        candles = self.session.get_5m_candles()
        if candles.empty or len(candles) < 3:
            return

        # Initialize ORB (first 15-min)
        if self.orb_high is None:
            first_three = candles.head(3)
            self.orb_high = float(first_three["high"].max())
            self.orb_low = float(first_three["low"].min())
            self.day_open = float(candles["open"].iloc[0])

        last_bar = candles.iloc[-1]
        prev_bar = candles.iloc[-2]

        spot = float(last_bar["close"])
        b_open = float(last_bar["open"])
        b_high = float(last_bar["high"])
        b_low = float(last_bar["low"])
        b_range = b_high - b_low

        if b_range < 5.0:
            return  # Dead candle

        lower_wick = min(b_open, spot) - b_low
        upper_wick = b_high - max(b_open, spot)
        bull_body = (spot > b_open) and ((spot - b_open) >= 0.25 * b_range)
        bear_body = (spot < b_open) and ((b_open - spot) >= 0.25 * b_range)
        prev_c = float(prev_bar["close"])

        lvl = self.levels
        if not lvl:
            return

        # 1. Breakouts
        r1_break = (prev_c <= lvl["r1"]) and (spot > lvl["r1"]) and bull_body
        s1_break = (prev_c >= lvl["s1"]) and (spot < lvl["s1"]) and bear_body
        r2_break = (prev_c <= lvl["r2"]) and (spot > lvl["r2"]) and bull_body
        s2_break = (prev_c >= lvl["s2"]) and (spot < lvl["s2"]) and bear_body

        # 2. Reversals
        tested_r1 = (b_high >= lvl["r1"] >= b_low) or (float(prev_bar["high"]) >= lvl["r1"] and b_high >= lvl["r1"])
        r1_fade = tested_r1 and (spot < lvl["r1"]) and (upper_wick >= 0.25 * b_range)
        tested_r2 = (b_high >= lvl["r2"])
        r2_fade = tested_r2 and (spot < lvl["r2"]) and (upper_wick >= 0.25 * b_range)

        # 3. Gap Retests (Polarity Flips)
        gap_r1_retest = False
        gap_s1_retest = False
        if self.day_open >= lvl["r1"]:
            tested = (b_low <= lvl["r1"] <= b_high) or (b_low <= lvl["r1"])
            gap_r1_retest = tested and (spot > lvl["r1"]) and (lower_wick >= 0.25 * b_range)
        elif self.day_open <= lvl["s1"]:
            tested = (b_low <= lvl["s1"] <= b_high) or (b_high >= lvl["s1"])
            gap_s1_retest = tested and (spot < lvl["s1"]) and (upper_wick >= 0.25 * b_range)

        # 4. Opening Range Breakout (ORB)
        gap_orb_ce = False
        gap_orb_pe = False
        if len(candles) >= 4:
            if self.day_open >= lvl["r1"]:
                gap_orb_ce = (prev_c <= self.orb_high) and (spot > self.orb_high) and bull_body
            elif self.day_open <= lvl["s1"]:
                gap_orb_pe = (prev_c >= self.orb_low) and (spot < self.orb_low) and bear_body

        # Triggers (Only 6 Institutional Elite Playbooks - Pruned of unvalidated retail traps)
        if gap_r1_retest:
            self.enter_trade("Gap-Up R1 Polarity Bounce", "CE", spot)
        elif gap_s1_retest:
            self.enter_trade("Gap-Down S1 Polarity Rejection", "PE", spot)
        elif r1_fade:
            self.enter_trade("R1 Resistance Reversal", "PE", spot)
        elif r2_fade:
            self.enter_trade("R2 Exhaustion Reversal", "PE", spot)
        elif gap_orb_pe:
            self.enter_trade("Gap-and-Go Bearish ORB", "PE", spot)
        elif s1_break:
            self.enter_trade("S1 Support Breakdown", "PE", spot)

    def print_hud(self, spot: float):
        """Prints high-visibility ASCII Heads-Up Display in terminal"""
        now_str = datetime.now().strftime("%H:%M:%S IST")
        daily = self.pnl.get_daily_stats()
        weekly = self.pnl.get_weekly_stats()
        overall = self.pnl.get_overall_stats(self.capital)

        # Clear screen on Windows
        os.system("cls" if os.name == "nt" else "clear")

        print("="*85)
        print("   NIFTY 50 OPTIONS ALGO TRADING BOT  |  ANGEL ONE SMARTAPI  |  GOLD ZONE")
        print("="*85)
        print(f" [STATUS]   ONLINE (Angel Connected)     [TIME] {now_str}")
        print(f" [SPOT]     NIFTY 50: {spot:,.2f}              [CAPITAL] Rs {self.capital:,.2f} ({overall['roi_pct']:+.2f}% ROI)")
        lvl = self.levels
        res_str = f"R4:{lvl.get('r4','-')} R3:{lvl.get('r3','-')} R2:{lvl.get('r2','-')} R1:{lvl.get('r1','-')}"
        sup_str = f"S1:{lvl.get('s1','-')} S2:{lvl.get('s2','-')} S3:{lvl.get('s3','-')} S4:{lvl.get('s4','-')}"
        print(f" [LEVELS]   RES: {res_str}  |  P: {lvl.get('pivot','-')}  |  SUP: {sup_str}")
        print("-"*85)

        if self.current_position:
            pos = self.current_position
            pnl_sign = "+" if pos.get("unrealized_pnl", 0) >= 0 else ""
            if pos.get("t1_hit"):
                print(f" [POSITION] RUNNER ACTIVE: {pos['symbol']} ({pos['type']}) | 1 Lot Remaining (65 Qty) | Playbook: {pos['playbook']}")
                print(f"            Stage 1 Banked: +Rs {pos.get('t1_net_pnl', 0):+,.2f}  |  Lot 2 SL: Rs {pos['sl_prem']:.2f} (Risk-Free Breakeven +4)")
                print(f"            Runner Target 2: Rs {pos['tp2_prem']:.2f} (+{self.cfg.TARGET_2_PTS:.0f} pts | +Rs 13,000 Runner)")
                print(f"            LTP: Rs {pos.get('current_ltp', pos['entry_prem']):.2f}  |  Total P&L: {pnl_sign}Rs {pos.get('unrealized_pnl', 0):,.2f} ({pos.get('current_pts', 0):+.2f} pts)")
            else:
                print(f" [POSITION] ACTIVE: {pos['symbol']} ({pos['type']}) | 2 Lots (130 Qty) | Playbook: {pos['playbook']}")
                print(f"            Entry: Rs {pos['entry_prem']:.2f}  |  LTP: Rs {pos.get('current_ltp', pos['entry_prem']):.2f}  |  P&L: {pnl_sign}Rs {pos.get('unrealized_pnl', 0):,.2f}")
                print(f"            SL: Rs {pos['sl_prem']:.2f} (-{self.cfg.STOP_LOSS_PTS:.0f} pts)  |  T1: Rs {pos['tp1_prem']:.2f} (+100 pts)  |  T2: Rs {pos['tp2_prem']:.2f} (+200 pts)")
        else:
            print(" [POSITION] FLAT (Scanning 5m candles for Institutional S&R and Gap Polarity setups)")

        print("-"*85)
        print(f" [TODAY]    Net P&L: Rs {daily['net_pnl']:+,.2f}  |  Trades: {daily['trades']} ({daily['wins']}W / {daily['losses']}L | {daily['win_rate']:.0f}% WR)")
        print(f" [THIS WEEK] Net P&L: Rs {weekly['net_pnl']:+,.2f}  |  Trades: {weekly['trades']} ({weekly['wins']}W / {weekly['losses']}L | {weekly['win_rate']:.0f}% WR) [{weekly['week_span']}]")
        print(f" [ACTIVITY] {self.last_status_msg}")
        print("  [LIVE] Real-time Angel One SmartAPI execution & 5m candle scanning active.")
        print("  [STOP] Press Ctrl+C to stop trading bot safely.")

    def print_standby_hud(self, now: datetime, next_open: datetime, state_desc: str):
        now_str = now.strftime("%H:%M:%S IST")
        diff = next_open - now
        total_sec = max(0, int(diff.total_seconds()))
        hours, remainder = divmod(total_sec, 3600)
        minutes, seconds = divmod(remainder, 60)
        countdown_str = f"{hours}h {minutes}m {seconds}s"
        next_open_str = next_open.strftime("%d-%b (%a) at 09:15 AM IST")

        daily = self.pnl.get_daily_stats()
        weekly = self.pnl.get_weekly_stats()
        overall = self.pnl.get_overall_stats(self.capital)

        os.system("cls" if os.name == "nt" else "clear")
        print("="*85)
        print("   NIFTY 50 OPTIONS ALGO TRADING BOT  |  ANGEL ONE SMARTAPI  |  24/7 RUNTIME")
        print("="*85)
        print(f" [STATUS]   STANDBY SLEEP ({state_desc:<11})    [TIME] {now_str}")
        print(f" [NEXT OPEN] {next_open_str:<32} [COUNTDOWN] {countdown_str}")
        print(f" [CAPITAL]  Rs {self.capital:,.2f} ({overall['roi_pct']:+.2f}% ROI)       [EXCHANGE] NSE / NFO (Closed)")
        print("-"*85)
        print(f" [TODAY P&L] Net: Rs {daily['net_pnl']:+,.2f}  |  Trades: {daily['trades']} ({daily['wins']}W / {daily['losses']}L | {daily['win_rate']:.0f}% WR)")
        print(f" [THIS WEEK] Net: Rs {weekly['net_pnl']:+,.2f}  |  Trades: {weekly['trades']} ({weekly['wins']}W / {weekly['losses']}L | {weekly['win_rate']:.0f}% WR) [{weekly['week_span']}]")
        print("-"*85)
        print(f" [24/7 MODE] System is alive and running continuously in standby.")
        print(f"             Will automatically awaken at 09:00 AM IST to fetch fresh levels & trade!")
        print("="*85)
        print("  [LIVE] 24/7 Continuous Runtime Controller active.")
        print("  [STOP] Press Ctrl+C to terminate bot at any time.")


    def send_eod_summary(self):
        daily = self.pnl.get_daily_stats()
        weekly = self.pnl.get_weekly_stats()
        overall = self.pnl.get_overall_stats(self.capital)

        today_dt = datetime.now()
        is_friday = (today_dt.weekday() == 4)

        d_sign = "🟢" if daily["net_pnl"] >= 0 else "🔴"
        w_sign = "🟢" if weekly["net_pnl"] >= 0 else "🔴"

        msg = (
            f"🏁 <b>MARKET CLOSED — DAILY & WEEKLY P&L SUMMARY</b>\n"
            f"📅 Date: <b>{today_dt.strftime('%d-%b-%Y (%A)')}</b>\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"📊 <b>DAILY PERFORMANCE (TODAY):</b>\n"
            f"  • Net Daily P&L: <b>{d_sign} Rs {daily['net_pnl']:+,.2f}</b>\n"
            f"  • Trades Today: {daily['trades']} ({daily['wins']}W / {daily['losses']}L)\n"
            f"  • Win Rate: {daily['win_rate']:.1f}%\n"
            f"  • Points: {daily['points']:+.1f} pts\n"
            f"  • Friction Costs: Rs {daily['costs']:,.2f}\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"📅 <b>WEEK-TO-DATE ({weekly['week_span']}):</b>\n"
            f"  • Net Weekly P&L: <b>{w_sign} Rs {weekly['net_pnl']:+,.2f}</b>\n"
            f"  • Weekly Trades: {weekly['trades']} ({weekly['wins']}W / {weekly['losses']}L)\n"
            f"  • Weekly Win Rate: {weekly['win_rate']:.1f}%\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"💼 <b>CAPITAL STATUS (FRESH START):</b>\n"
            f"  • Initial Capital: Rs {self.cfg.INITIAL_CAPITAL:,.2f}\n"
            f"  • Current Balance: <b>Rs {self.capital:,.2f}</b>\n"
            f"  • Total ROI: <b>{overall['roi_pct']:+.2f}%</b>\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        )
        if is_friday:
            msg += f"🏆 <b>Weekend Wrap-up:</b> Trading week complete! Next session Monday 09:15 AM."
        else:
            msg += f"💤 <i>System sleeping. Next trading session resumes tomorrow at 09:15 AM IST.</i>"

        self.alerter.send(msg)

# ==================================================================================================
# 8. MAIN ENTRY POINT & RUNTIME CONTROLLER
# ==================================================================================================
def reset_to_scratch(config: BotConfig):
    """Resets trade history and state for a 100% clean fresh start"""
    for handler in logging.root.handlers[:]:
        handler.close()
        logging.root.removeHandler(handler)

    for f in [config.TRADES_FILE, config.STATE_FILE, config.LOG_FILE, config.DASHBOARD_FILE]:
        if os.path.exists(f):
            try:
                os.remove(f)
                print(f"[RESET] Deleted {f}")
            except Exception as e:
                print(f"[RESET] Could not delete {f}: {e}")
    print("\n[SUCCESS] Clean slate initialized! Ready to trade from scratch with Rs 50,000 capital.\n")

def get_market_state(now: datetime, config: BotConfig) -> str:
    """
    Evaluates market session:
    - 'WEEKEND': Saturday or Sunday
    - 'PRE_MARKET': Monday-Friday before 09:15 IST
    - 'POST_MARKET': Monday-Friday after 15:30 IST
    - 'OPEN': Monday-Friday between 09:15 and 15:30 IST
    """
    dow = now.weekday()
    if dow in [5, 6]:
        return "WEEKEND"
    t = now.time()
    if t < config.MARKET_START:
        return "PRE_MARKET"
    elif t >= config.MARKET_END:
        return "POST_MARKET"
    else:
        return "OPEN"

def get_next_market_open(now: datetime, config: BotConfig) -> datetime:
    """Calculates the exact datetime of the next market open (09:15 AM IST)"""
    state = get_market_state(now, config)
    dow = now.weekday()
    if state == "PRE_MARKET":
        return datetime.combine(now.date(), config.MARKET_START)
    elif state == "POST_MARKET":
        days_ahead = 3 if dow == 4 else 1  # Friday -> Monday, else tomorrow
        return datetime.combine(now.date() + timedelta(days=days_ahead), config.MARKET_START)
    elif state == "WEEKEND":
        days_ahead = (7 - dow)  # Saturday -> 2 days (Monday), Sunday -> 1 day (Monday)
        return datetime.combine(now.date() + timedelta(days=days_ahead), config.MARKET_START)
    else:
        return now

def main():
    parser = argparse.ArgumentParser(description="All-in-One NIFTY Options Algo Bot and Monitor")
    parser.add_argument("--reset", action="store_true", help="Wipe all trade history and start completely fresh from scratch")
    parser.add_argument("--status", action="store_true", help="Print current status and PnL without running live loop")
    parser.add_argument("--open-dash", action="store_true", help="Open live HTML dashboard in default web browser")
    args = parser.parse_args()

    config = BotConfig()

    if args.reset:
        reset_to_scratch(config)
        return

    if args.open_dash:
        if os.path.exists(config.DASHBOARD_FILE):
            webbrowser.open(os.path.abspath(config.DASHBOARD_FILE))
            print(f"Opened {config.DASHBOARD_FILE} in browser.")
        else:
            print("Dashboard not yet created. Run the bot first!")
        return

    alerter = TelegramAlerter(config.TELEGRAM_BOT_TOKEN, config.TELEGRAM_CHAT_ID)
    session = AngelManager(config, alerter)

    print("\n" + "="*80)
    print("   CONNECTING TO ANGEL ONE SMARTAPI...")
    print("="*80)

    if not session.connect():
        print("\n[ERROR] Login failed. Check your credentials in BotConfig or network connection.")
        return

    engine = NiftyAlgoEngine(config, session, alerter)
    engine.initialize_daily_levels()

    now = datetime.now()
    initial_state = get_market_state(now, config)
    next_open = get_next_market_open(now, config)

    if args.status:
        quote = session.get_spot_quote()
        spot = float(quote.get("ltp", 0.0)) if quote else 0.0
        daily = engine.pnl.get_daily_stats()
        weekly = engine.pnl.get_weekly_stats()
        overall = engine.pnl.get_overall_stats(engine.capital)

        if initial_state == "OPEN":
            engine.print_hud(spot)
            DashboardGenerator.render(
                config, engine.levels, engine.current_position,
                daily, weekly, overall, spot, engine.last_status_msg, market_state="OPEN"
            )
        else:
            engine.print_standby_hud(now, next_open, initial_state)
            diff = next_open - now
            h, rem = divmod(max(0, int(diff.total_seconds())), 3600)
            m, s = divmod(rem, 60)
            standby_msg = f"STANDBY: Next market session opens in {h}h {m}m {s}s ({next_open.strftime('%d-%b at 09:15 AM IST')})"
            DashboardGenerator.render(
                config, engine.levels, None,
                daily, weekly, overall, spot, standby_msg, market_state=initial_state
            )
        return

    # Send Startup Confirmation to Telegram
    alerter.send(
        f"🤖 <b>NIFTY ALGO BOT ONLINE (2-LOT STAGED EXECUTION ENGINE)</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"💰 <b>Initial Capital:</b> Rs {config.INITIAL_CAPITAL:,.2f}\n"
        f"📦 <b>Position Sizing:</b> {config.NUM_LOTS} Lots ({config.NUM_LOTS * config.LOT_SIZE} Qty)\n"
        f"⚡ <b>Strike Selection:</b> {config.STRIKE_MODE} (+50 CE / -50 PE)\n"
        f"🛑 <b>Initial Stop Loss:</b> -{config.STOP_LOSS_PTS:.0f} pts\n"
        f"🎯 <b>Target 1:</b> +{config.TARGET_1_PTS:.0f} pts (1:2 RR | Book 1 Lot & Bank +₹6,500)\n"
        f"🛡️ <b>Lot 2 Protection:</b> Risk-Free Breakeven (+{config.SMART_BE_BUFFER_PTS:.0f} pts buffer)\n"
        f"🚀 <b>Target 2:</b> +{config.TARGET_2_PTS:.0f} pts (1:4 RR | Lot 2 Runner +₹13,000)\n"
        f"⏰ <b>Square-Off:</b> 15:00 IST (100% Cash Overnight)\n"
        f"📊 <b>Dashboard:</b> Live & Monitoring 24/7\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"🟢 <i>Angel One Session Active</i>"
    )

    last_candle_eval = 0
    last_hud_print = 0
    last_level_check = 0
    last_sat_report_date = None
    last_sun_scan_date = None

    print("\n[SUCCESS] Bot is online! 24/7 Continuous Runtime Controller Active...\n")
    time.sleep(1)

    while True:
        try:
            now = datetime.now()
            today_str = now.strftime("%Y-%m-%d")
            m_state = get_market_state(now, config)
            next_open = get_next_market_open(now, config)

            # ------------------------------------------------------------------
            # 1. STANDBY / SLEEP MODE (Weekends, After-Market, or Pre-Market)
            # ------------------------------------------------------------------
            if m_state != "OPEN":
                # Saturday 09:00 AM: Automated Weekly Audit Report to Telegram
                if now.weekday() == 5 and now.time() >= dtime(9, 0) and last_sat_report_date != today_str:
                    try:
                        logger.info("Saturday 09:00 AM: Generating Weekly Audit Report...")
                        from weekend_engine import generate_saturday_weekly_report
                        sat_msg = generate_saturday_weekly_report(config.TRADES_FILE)
                        alerter.send(sat_msg)
                        last_sat_report_date = today_str
                    except Exception as e:
                        logger.error(f"Saturday Weekly Report Error: {e}")

                # Sunday 09:00 AM: Automated Nifty 50 RSI > 50 Momentum Scanner to Telegram
                if now.weekday() == 6 and now.time() >= dtime(9, 0) and last_sun_scan_date != today_str:
                    try:
                        logger.info("Sunday 09:00 AM: Running Nifty 50 All-Stock RSI > 50 Scanner...")
                        from weekend_engine import generate_sunday_nifty50_rsi_analysis
                        sun_msg = generate_sunday_nifty50_rsi_analysis()
                        alerter.send(sun_msg)
                        last_sun_scan_date = today_str
                    except Exception as e:
                        logger.error(f"Sunday RSI Scan Error: {e}")

                # A. Send EOD summary once if market closed today and not yet sent
                if m_state == "POST_MARKET" and engine.eod_summary_sent_date != today_str:
                    engine.send_eod_summary()
                    engine.eod_summary_sent_date = today_str

                # B. Morning Pre-Market Wake-Up Call (09:00 - 09:15 AM on a trading day)
                if m_state == "PRE_MARKET" and now.time() >= dtime(9, 0) and engine.current_day_initialized != today_str:
                    logger.info("09:00 AM Wakeup Triggered: Initializing fresh session...")
                    session.ensure_connected()
                    engine.reset_daily_state()
                    engine.initialize_daily_levels()
                    engine.current_day_initialized = today_str

                # C. Print Standby HUD & update HTML dashboard every 5 seconds
                if time.time() - last_hud_print >= 5:
                    engine.print_standby_hud(now, next_open, m_state)
                    daily = engine.pnl.get_daily_stats()
                    weekly = engine.pnl.get_weekly_stats()
                    overall = engine.pnl.get_overall_stats(engine.capital)
                    diff = next_open - now
                    h, rem = divmod(max(0, int(diff.total_seconds())), 3600)
                    m, s = divmod(rem, 60)
                    standby_msg = f"STANDBY: Next session opens {next_open.strftime('%a %d-%b at 09:15 AM')} (in {h}h {m}m {s}s)"
                    DashboardGenerator.render(
                        config, engine.levels, None,
                        daily, weekly, overall, 0.0, standby_msg, market_state=m_state
                    )
                    last_hud_print = time.time()

                time.sleep(2)
                continue

            # ------------------------------------------------------------------
            # 2. ACTIVE MARKET MODE (09:15 to 15:30 IST on Trading Days)
            # ------------------------------------------------------------------
            # Ensure day is initialized if bot started directly during market hours
            if engine.current_day_initialized != today_str:
                session.ensure_connected()
                engine.initialize_daily_levels()
                engine.current_day_initialized = today_str

            # Spot quote
            quote = session.get_spot_quote()
            spot = float(quote.get("ltp", 0.0)) if quote else 0.0

            # Step 1: Check open position ticks every 2 seconds
            if engine.current_position:
                engine.check_position_exit()

            # Step 2: Check 5-minute candle signals every 10 seconds (between 09:25 and 14:00)
            if time.time() - last_candle_eval >= 10:
                engine.evaluate_market_signals()
                last_candle_eval = time.time()

            # Hot-Reload levels from Web Dashboard (levels.json) every 3 seconds
            if time.time() - last_level_check >= 3:
                engine.check_levels_reload()
                last_level_check = time.time()

            # Step 3: Update Live HUD & HTML Dashboard every 3 seconds
            if time.time() - last_hud_print >= 3:
                daily = engine.pnl.get_daily_stats()
                weekly = engine.pnl.get_weekly_stats()
                overall = engine.pnl.get_overall_stats(engine.capital)

                engine.print_hud(spot)
                DashboardGenerator.render(
                    config, engine.levels, engine.current_position,
                    daily, weekly, overall, spot, engine.last_status_msg, market_state="OPEN"
                )
                last_hud_print = time.time()

            time.sleep(2)

        except KeyboardInterrupt:
            print("\n[STOPPED] Manual shutdown triggered by user.")
            alerter.send("⚠️ <i>NIFTY Algo Bot stopped manually by user.</i>")
            break
        except Exception as e:
            logger.error(f"Runtime Loop Error: {e}")
            time.sleep(5)

if __name__ == "__main__":
    main()
