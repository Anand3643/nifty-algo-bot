"""
========================================================================================
   ANGEL ONE ALGORITHMIC PAPER TRADING SYSTEM — NIFTY OPTIONS S&R CHAMPION STRATEGY
========================================================================================
Broker: Angel One SmartAPI
Strategy: Intraday S&R Breakout, Reversal & Gap Polarity Engine
Timeframe: 5-Minute Candles
Instrument: NIFTY 50 ATM Options (CE / PE) | 1 Lot = 65 Qty
Capital: Rs 50,000 | SL: 40 pts | TP: 120 pts (1:3 Risk-to-Reward)
Max Trades / Day: 2 | Daily Auto Square-off: 15:10 IST
Telegram Live Alerts: Enabled to Chat ID -5073639718
========================================================================================
"""
import os
import sys
import time
import json
import logging
from datetime import datetime, time as dtime, timedelta
# Auto-heal missing SmartApi sub-dependencies (e.g. logzero, six, websocket-client)
for _pkg in ["logzero", "six", "websocket-client"]:
    try:
        if _pkg == "websocket-client":
            import websocket
        else:
            __import__(_pkg)
    except ImportError:
        import subprocess
        subprocess.check_call([sys.executable, "-m", "pip", "install", _pkg])

import pandas as pd
import numpy as np
import requests
import pyotp
from SmartApi import SmartConnect

# Setup Logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler("algo_trader.log", encoding="utf-8")
    ]
)
logger = logging.getLogger("AngelAlgo")

# ==========================================
# CONFIGURATION & CREDENTIALS
# ==========================================
class AlgoConfig:
    # Angel One SmartAPI Credentials
    API_KEY = "6mRD3Ntn"
    CLIENT_ID = "A612537"
    PASSWORD = "1436"
    TOTP_SECRET = "Z6NUOKVTOJI5LUI6GCFR2HXKWY"

    # Telegram Alert Configuration (GOLD Zone)
    TELEGRAM_BOT_TOKEN = "8455004756:AAHzyPNLWJ2x_2aQAQTHdDDzWn5VGW7KLSU"
    TELEGRAM_CHAT_ID = "-5077267080"

    # Strategy Parameters
    SYMBOL = "Nifty 50"
    EXCHANGE_INDEX = "NSE"
    TOKEN_INDEX = "99926000"
    EXCHANGE_OPTIONS = "NFO"

    INITIAL_CAPITAL = 50000.0
    LOT_SIZE = 65
    NUM_LOTS = 1
    STOP_LOSS_PTS = 40.0         # 40 points option premium SL
    TARGET_PTS = 120.0           # 120 points option premium TP (1:3 RR)
    MAX_TRADES_PER_DAY = 2
    SLIPPAGE_RATE = 0.005        # 0.5% realistic fill slippage

    # Timing
    MARKET_START = dtime(9, 15)
    ENTRY_START = dtime(9, 25)
    ENTRY_END = dtime(14, 45)
    SQUARE_OFF_TIME = dtime(15, 10)
    MARKET_END = dtime(15, 30)

    # Execution Mode
    PAPER_TRADING = True         # True = Paper Execution, False = Live Market Orders

# ==========================================
# TELEGRAM NOTIFIER
# ==========================================
class TelegramNotifier:
    def __init__(self, bot_token: str, chat_id: str):
        self.bot_token = bot_token
        self.chat_id = chat_id
        self.api_url = f"https://api.telegram.org/bot{self.bot_token}/sendMessage"

    def send_message(self, text: str, parse_mode: str = "HTML") -> bool:
        payload = {
            "chat_id": self.chat_id,
            "text": text,
            "parse_mode": parse_mode,
            "disable_web_page_preview": True
        }
        try:
            r = requests.post(self.api_url, json=payload, timeout=8)
            if r.status_code == 200:
                return True
            else:
                logger.warning(f"Telegram alert failed: {r.status_code} {r.text}")
                return False
        except Exception as e:
            logger.error(f"Telegram network error: {e}")
            return False

# ==========================================
# S&R INSTITUTIONAL ENGINE
# ==========================================
class NiftySREngine:
    @staticmethod
    def calculate_levels(high: float, low: float, close: float) -> dict:
        if close <= 0:
            close = 22600.0

        # Absolute safeguard against zero range / collapsed levels
        if high <= low or low <= 0 or (high - low) < 20.0:
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


# ==========================================
# ANGEL ONE SMARTAPI SESSION & INSTRUMENT MANAGER
# ==========================================
class AngelSessionManager:
    def __init__(self, config: AlgoConfig, notifier: TelegramNotifier):
        self.cfg = config
        self.notifier = notifier
        self.smart_api = None
        self.auth_data = None
        self.scrip_df = None
        self.cache_file = "scrip_master.json"

    def connect(self) -> bool:
        try:
            logger.info("Initializing Angel One SmartConnect...")
            self.smart_api = SmartConnect(self.cfg.API_KEY)
            totp = pyotp.TOTP(self.cfg.TOTP_SECRET).now()
            logger.info(f"Generated TOTP: {totp}. Logging in client {self.cfg.CLIENT_ID}...")

            login_res = self.smart_api.generateSession(self.cfg.CLIENT_ID, self.cfg.PASSWORD, totp)
            if login_res and login_res.get("status"):
                self.auth_data = login_res.get("data")
                logger.info(" Angel One Session Authenticated Successfully!")
                self._load_scrip_master()
                return True
            else:
                msg = f"❌ Angel One Login Failed: {login_res.get('message')}"
                logger.error(msg)
                self.notifier.send_message(f"🚨 <b>ANGEL ONE LOGIN FAILED</b>\n{msg}")
                return False
        except Exception as e:
            err = f"❌ Connection Exception: {e}"
            logger.error(err)
            self.notifier.send_message(f"🚨 <b>SMARTAPI CRITICAL ERROR</b>\n<code>{e}</code>")
            return False

    def _load_scrip_master(self):
        download_needed = True
        if os.path.exists(self.cache_file):
            mtime = datetime.fromtimestamp(os.path.getmtime(self.cache_file))
            if datetime.now() - mtime < timedelta(hours=12):
                logger.info(f"Loading cached scrip master from {self.cache_file}...")
                try:
                    with open(self.cache_file, "r", encoding="utf-8") as f:
                        data = json.load(f)
                    self.scrip_df = pd.DataFrame(data)
                    download_needed = False
                except Exception:
                    download_needed = True

        if download_needed:
            logger.info("Downloading fresh Scrip Master from Angel One server (~40MB)...")
            url = "https://margincalculator.angelbroking.com/OpenAPI_File/files/OpenAPIScripMaster.json"
            r = requests.get(url, timeout=30)
            if r.status_code == 200:
                data = r.json()
                with open(self.cache_file, "w", encoding="utf-8") as f:
                    json.dump(data, f)
                self.scrip_df = pd.DataFrame(data)
                logger.info(f"Scrip master loaded with {len(self.scrip_df)} instruments.")
            else:
                logger.error("Failed to download scrip master!")

    def get_spot_quote(self) -> dict:
        try:
            res = self.smart_api.ltpData(self.cfg.EXCHANGE_INDEX, self.cfg.SYMBOL, self.cfg.TOKEN_INDEX)
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

    def resolve_atm_option(self, spot: float, opt_type: str) -> dict:
        """
        Calculates ATM strike and finds nearest weekly expiry contract
        """
        strike = int(round(spot / 50) * 50)
        strike_val = float(strike * 100)  # Angel scrip strike is multiplied by 100

        df = self.scrip_df
        nifty_opts = df[(df["name"] == "NIFTY") & (df["exch_seg"] == "NFO")].copy()
        nifty_opts["expiry_dt"] = pd.to_datetime(nifty_opts["expiry"], format="%d%b%Y")

        today = pd.to_datetime(datetime.now().date())
        valid_opts = nifty_opts[nifty_opts["expiry_dt"] >= today].sort_values("expiry_dt")

        if valid_opts.empty:
            logger.error("No valid NIFTY options found in master!")
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
        logger.warning(f"Could not find {opt_type} contract for strike {strike} expiry {expiry_str}")
        return {}

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
                # Candle format: [timestamp, open, high, low, close, volume]
                cols = ["datetime", "open", "high", "low", "close", "volume"]
                df = pd.DataFrame(res["data"], columns=cols)
                df["datetime"] = pd.to_datetime(df["datetime"])
                return df
        except Exception as e:
            logger.error(f"Error fetching 5m candles: {e}")
        return pd.DataFrame()

# ==========================================
# DAILY & WEEKLY P&L TRACKER
# ==========================================
class PnLTracker:
    def __init__(self, log_file: str = "algo_paper_trades.csv", initial_capital: float = 50000.0):
        self.log_file = log_file
        self.initial_capital = initial_capital

    def _read_trades(self) -> pd.DataFrame:
        if not os.path.exists(self.log_file):
            return pd.DataFrame()
        try:
            df = pd.read_csv(self.log_file)
            if df.empty or "Date" not in df.columns:
                return pd.DataFrame()
            df["Date_dt"] = pd.to_datetime(df["Date"])
            return df
        except Exception as e:
            logger.error(f"Error reading trade log for PnL: {e}")
            return pd.DataFrame()

    def get_daily_stats(self, target_date: str = None) -> dict:
        if target_date is None:
            target_date = datetime.now().strftime("%Y-%m-%d")

        df = self._read_trades()
        default_res = {
            "date": target_date,
            "trade_count": 0,
            "wins": 0,
            "losses": 0,
            "win_rate": 0.0,
            "gross_pnl": 0.0,
            "costs": 0.0,
            "net_pnl": 0.0,
            "points": 0.0,
            "roi_pct": 0.0
        }

        if df.empty:
            return default_res

        day_df = df[df["Date"] == target_date]
        if day_df.empty:
            return default_res

        trade_count = len(day_df)
        wins = int((day_df["Net_PnL"] > 0).sum())
        losses = int((day_df["Net_PnL"] < 0).sum())
        win_rate = round((wins / trade_count * 100.0), 1) if trade_count > 0 else 0.0
        gross_pnl = round(float(day_df["Gross_PnL"].sum()), 2) if "Gross_PnL" in day_df.columns else round(float(day_df["Net_PnL"].sum()), 2)
        costs = round(float(day_df["Costs"].sum()), 2) if "Costs" in day_df.columns else 0.0
        net_pnl = round(float(day_df["Net_PnL"].sum()), 2)
        points = round(float(day_df["Points"].sum()), 2) if "Points" in day_df.columns else 0.0
        roi_pct = round((net_pnl / self.initial_capital) * 100.0, 2)

        return {
            "date": target_date,
            "trade_count": trade_count,
            "wins": wins,
            "losses": losses,
            "win_rate": win_rate,
            "gross_pnl": gross_pnl,
            "costs": costs,
            "net_pnl": net_pnl,
            "points": points,
            "roi_pct": roi_pct
        }

    def get_weekly_stats(self, ref_dt: datetime = None) -> dict:
        if ref_dt is None:
            ref_dt = datetime.now()

        monday_dt = ref_dt - timedelta(days=ref_dt.weekday())
        sunday_dt = monday_dt + timedelta(days=6)
        friday_dt = monday_dt + timedelta(days=4)

        monday_str = monday_dt.strftime("%Y-%m-%d")
        sunday_str = sunday_dt.strftime("%Y-%m-%d")
        iso_week = monday_dt.isocalendar()[1]
        week_label = f"W{iso_week} ({monday_dt.strftime('%d-%b')} to {friday_dt.strftime('%d-%b')})"

        default_res = {
            "week_label": week_label,
            "iso_week": iso_week,
            "trade_count": 0,
            "wins": 0,
            "losses": 0,
            "win_rate": 0.0,
            "gross_pnl": 0.0,
            "costs": 0.0,
            "net_pnl": 0.0,
            "best_trade": 0.0,
            "worst_trade": 0.0,
            "days_traded": 0,
            "roi_pct": 0.0
        }

        df = self._read_trades()
        if df.empty:
            return default_res

        week_df = df[(df["Date_dt"] >= pd.to_datetime(monday_str)) & (df["Date_dt"] <= pd.to_datetime(sunday_str))]
        if week_df.empty:
            return default_res

        trade_count = len(week_df)
        wins = int((week_df["Net_PnL"] > 0).sum())
        losses = int((week_df["Net_PnL"] < 0).sum())
        win_rate = round((wins / trade_count * 100.0), 1) if trade_count > 0 else 0.0
        gross_pnl = round(float(week_df["Gross_PnL"].sum()), 2) if "Gross_PnL" in week_df.columns else round(float(week_df["Net_PnL"].sum()), 2)
        costs = round(float(week_df["Costs"].sum()), 2) if "Costs" in week_df.columns else 0.0
        net_pnl = round(float(week_df["Net_PnL"].sum()), 2)
        best_trade = round(float(week_df["Net_PnL"].max()), 2)
        worst_trade = round(float(week_df["Net_PnL"].min()), 2)
        days_traded = int(week_df["Date"].nunique())
        roi_pct = round((net_pnl / self.initial_capital) * 100.0, 2)

        return {
            "week_label": week_label,
            "iso_week": iso_week,
            "trade_count": trade_count,
            "wins": wins,
            "losses": losses,
            "win_rate": win_rate,
            "gross_pnl": gross_pnl,
            "costs": costs,
            "net_pnl": net_pnl,
            "best_trade": best_trade,
            "worst_trade": worst_trade,
            "days_traded": days_traded,
            "roi_pct": roi_pct
        }

    def get_overall_stats(self, current_capital: float = None) -> dict:
        df = self._read_trades()
        if current_capital is None:
            current_capital = self.initial_capital

        default_res = {
            "total_trades": 0,
            "wins": 0,
            "losses": 0,
            "win_rate": 0.0,
            "total_net_pnl": round(current_capital - self.initial_capital, 2),
            "current_capital": round(current_capital, 2),
            "roi_pct": round(((current_capital - self.initial_capital) / self.initial_capital) * 100.0, 2)
        }

        if df.empty:
            return default_res

        total_trades = len(df)
        wins = int((df["Net_PnL"] > 0).sum())
        losses = int((df["Net_PnL"] < 0).sum())
        win_rate = round((wins / total_trades * 100.0), 1) if total_trades > 0 else 0.0
        total_net_pnl = round(float(df["Net_PnL"].sum()), 2)
        current_cap = round(self.initial_capital + total_net_pnl, 2)
        roi_pct = round((total_net_pnl / self.initial_capital) * 100.0, 2)

        return {
            "total_trades": total_trades,
            "wins": wins,
            "losses": losses,
            "win_rate": win_rate,
            "total_net_pnl": total_net_pnl,
            "current_capital": current_cap,
            "roi_pct": roi_pct
        }

# ==========================================
# POSITION & ALGO EXECUTION ENGINE
# ==========================================
class PaperTradeExecutor:
    def __init__(self, config: AlgoConfig, session: AngelSessionManager, notifier: TelegramNotifier):
        self.cfg = config
        self.session = session
        self.notifier = notifier
        self.levels = {}
        self.capital = config.INITIAL_CAPITAL
        self.trades_today = 0
        self.current_position = None
        self.state_file = "algo_state.json"
        self.log_file = "algo_paper_trades.csv"
        self.pnl_tracker = PnLTracker(self.log_file, self.cfg.INITIAL_CAPITAL)
        self.orb_high = None
        self.orb_low = None
        self.day_open = None
        self._load_state()

    def _load_state(self):
        if os.path.exists(self.state_file):
            try:
                with open(self.state_file, "r") as f:
                    state = json.load(f)
                today_str = datetime.now().strftime("%Y-%m-%d")
                if state.get("date") == today_str:
                    self.capital = state.get("capital", self.cfg.INITIAL_CAPITAL)
                    self.trades_today = state.get("trades_today", 0)
                    self.current_position = state.get("current_position", None)
                    logger.info(f"Loaded existing state for today: Capital=Rs {self.capital:,.2f}, Trades={self.trades_today}")
            except Exception as e:
                logger.error(f"Failed to load state: {e}")

    def _save_state(self):
        today_str = datetime.now().strftime("%Y-%m-%d")
        daily_stats = self.pnl_tracker.get_daily_stats(today_str)
        weekly_stats = self.pnl_tracker.get_weekly_stats()
        state = {
            "date": today_str,
            "capital": self.capital,
            "trades_today": self.trades_today,
            "daily_net_pnl": daily_stats["net_pnl"],
            "daily_wins": daily_stats["wins"],
            "daily_losses": daily_stats["losses"],
            "weekly_net_pnl": weekly_stats["net_pnl"],
            "weekly_trades": weekly_stats["trade_count"],
            "weekly_wins": weekly_stats["wins"],
            "weekly_losses": weekly_stats["losses"],
            "current_position": self.current_position
        }
        with open(self.state_file, "w") as f:
            json.dump(state, f, indent=2)

    def log_trade(self, trade_data: dict):
        df = pd.DataFrame([trade_data])
        if not os.path.exists(self.log_file):
            df.to_csv(self.log_file, index=False)
        else:
            df.to_csv(self.log_file, mode="a", header=False, index=False)

    def initialize_day(self):
        logger.info("Initializing daily levels...")
        today_date = datetime.now().date()
        today_str = today_date.strftime("%Y-%m-%d")

        # 1. Check for manual/verified daily levels in levels.json
        levels_file = "levels.json"
        if os.path.exists(levels_file):
            try:
                with open(levels_file, "r") as f:
                    cust_levels = json.load(f)
                if cust_levels.get("date") == today_str and "nifty" in cust_levels:
                    self.levels = cust_levels["nifty"]
                    logger.info(f"Loaded verified levels from {levels_file}: P={self.levels['pivot']} | R1={self.levels['r1']} | S1={self.levels['s1']}")
                    msg = (
                        f"🎯 <b>NIFTY DAILY LEVELS INITIALIZED (VERIFIED INTRADAY)</b>\n"
                        f"📅 Date: <b>{datetime.now().strftime('%d-%b-%Y')}</b>\n"
                        f"━━━━━━━━━━━━━━━━━━━\n"
                        f"🔴 <b>Resistance R4:</b> {self.levels.get('r4', self.levels.get('r2'))}\n"
                        f"🔴 <b>Resistance R3:</b> {self.levels.get('r3', self.levels.get('r2'))}\n"
                        f"🔴 <b>Resistance R2:</b> {self.levels['r2']}\n"
                        f"🔺 <b>Resistance R1:</b> {self.levels['r1']}\n"
                        f"⚪ <b>Pivot Point:</b> {self.levels['pivot']} (CPR: {self.levels.get('cpr_bot', '-')} - {self.levels.get('cpr_top', '-')})\n"
                        f"🔻 <b>Support S1:</b> {self.levels['s1']}\n"
                        f"🟢 <b>Support S2:</b> {self.levels['s2']}\n"
                        f"🟢 <b>Support S3:</b> {self.levels.get('s3', self.levels.get('s2'))}\n"
                        f"🟢 <b>Support S4:</b> {self.levels.get('s4', self.levels.get('s2'))}\n"
                        f"━━━━━━━━━━━━━━━━━━━\n"
                        f"💰 <b>Capital:</b> Rs {self.capital:,.2f}\n"
                        f"🤖 <b>Paper Bot:</b> ACTIVE & MONITORING"
                    )
                    self.notifier.send_message(msg)
                    return
            except Exception as e:
                logger.error(f"Error loading custom levels from {levels_file}: {e}")

        # 2. Multi-tier previous day candle fetch
        p_high, p_low, p_close = 0.0, 0.0, 0.0

        # Tier 1: SmartAPI
        try:
            from_str = (today_date - timedelta(days=10)).strftime("%Y-%m-%d")
            to_str = today_date.strftime("%Y-%m-%d")
            params = {
                "exchange": self.cfg.EXCHANGE_INDEX,
                "symboltoken": self.cfg.TOKEN_INDEX,
                "interval": "ONE_DAY",
                "fromdate": f"{from_str} 09:15",
                "todate": f"{to_str} 15:30"
            }
            res = self.session.smart_api.getCandleData(params)
            if res and res.get("status") and res.get("data"):
                past_candles = [c for c in res["data"] if datetime.strptime(str(c[0])[:10], "%Y-%m-%d").date() < today_date]
                if past_candles:
                    prev_c = past_candles[-1]
                    if float(prev_c[2]) > float(prev_c[3]) > 0:
                        p_high = float(prev_c[2])
                        p_low = float(prev_c[3])
                        p_close = float(prev_c[4])
                        logger.info(f"[Tier 1 SmartAPI] Loaded candle ({prev_c[0][:10]}): H={p_high}, L={p_low}, C={p_close}")
        except Exception as e:
            logger.warning(f"Tier 1 SmartAPI fetch: {e}")

        # Tier 2: yfinance (^NSEI)
        if p_high <= p_low or p_low <= 0:
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
                        h = float(last_row["high"])
                        l = float(last_row["low"])
                        c = float(last_row["close"])
                        if h > l > 0 and c > 0:
                            p_high, p_low, p_close = h, l, c
                            logger.info(f"[Tier 2 yfinance] Loaded candle ({yf_df.index[-1].date()}): H={h:.2f}, L={l:.2f}, C={c:.2f}")
            except Exception as e:
                logger.warning(f"Tier 2 yfinance fetch: {e}")

        # Tier 3: Local CSV
        if p_high <= p_low or p_low <= 0:
            try:
                csv_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "nifty_data", "candles", "NIFTY_1day.csv")
                if os.path.exists(csv_path):
                    df_csv = pd.read_csv(csv_path)
                    df_csv["dt"] = pd.to_datetime(df_csv["datetime"]).dt.date
                    df_csv = df_csv[df_csv["dt"] < today_date]
                    if not df_csv.empty:
                        last_row = df_csv.iloc[-1]
                        p_high = float(last_row["high"])
                        p_low = float(last_row["low"])
                        p_close = float(last_row["close"])
                        logger.info(f"[Tier 3 Local CSV] Loaded candle ({last_row['dt']}): H={p_high}, L={p_low}, C={p_close}")
            except Exception as e:
                logger.warning(f"Tier 3 Local CSV fetch: {e}")

        # Tier 4: Spot quote with safe ATR spread
        if p_high <= p_low or p_low <= 0:
            quote = self.session.get_spot_quote()
            p_close = float(quote.get("close", 0.0) or quote.get("ltp", 0.0)) if quote else 22625.0
            span = max(80.0, p_close * 0.010)
            p_high = round((p_close + span / 2.0) / 5) * 5
            p_low = round((p_close - span / 2.0) / 5) * 5

        self.levels = NiftySREngine.calculate_levels(p_high, p_low, p_close)
        logger.info(f"Levels Calculated: Pivot={self.levels['pivot']}, R1={self.levels['r1']}, R2={self.levels['r2']}, S1={self.levels['s1']}, S2={self.levels['s2']}")

        # Send Telegram Level Alert
        msg = (
            f"🎯 <b>NIFTY DAILY LEVELS INITIALIZED</b>\n"
            f"📅 Date: <b>{datetime.now().strftime('%d-%b-%Y')}</b>\n"
            f"━━━━━━━━━━━━━━━━━━━\n"
            f"🔴 <b>Resistance R4:</b> {self.levels.get('r4', self.levels.get('r2'))}\n"
            f"🔴 <b>Resistance R3:</b> {self.levels.get('r3', self.levels.get('r2'))}\n"
            f"🔴 <b>Resistance R2:</b> {self.levels['r2']}\n"
            f"🔺 <b>Resistance R1:</b> {self.levels['r1']}\n"
            f"⚪ <b>Pivot Point:</b> {self.levels['pivot']} (CPR: {self.levels['cpr_bot']} - {self.levels['cpr_top']})\n"
            f"🔻 <b>Support S1:</b> {self.levels['s1']}\n"
            f"🟢 <b>Support S2:</b> {self.levels['s2']}\n"
            f"🟢 <b>Support S3:</b> {self.levels.get('s3', self.levels.get('s2'))}\n"
            f"🟢 <b>Support S4:</b> {self.levels.get('s4', self.levels.get('s2'))}\n"
            f"━━━━━━━━━━━━━━━━━━━\n"
            f"💰 <b>Capital:</b> Rs {self.capital:,.2f}\n"
            f"🤖 <b>Paper Bot:</b> ACTIVE & MONITORING"
        )
        self.notifier.send_message(msg)


    def enter_trade(self, playbook: str, opt_type: str, spot: float):
        if self.trades_today >= self.cfg.MAX_TRADES_PER_DAY:
            logger.info("Daily trade limit reached.")
            return

        opt_info = self.session.resolve_atm_option(spot, opt_type)
        if not opt_info or opt_info.get("ltp", 0) <= 0:
            logger.error("Failed to resolve option quote for entry!")
            return

        raw_prem = opt_info["ltp"]
        # Apply 0.5% fill slippage
        entry_prem = round(raw_prem * (1.0 + self.cfg.SLIPPAGE_RATE), 2)
        sl_prem = round(max(1.0, entry_prem - self.cfg.STOP_LOSS_PTS), 2)
        tp_prem = round(entry_prem + self.cfg.TARGET_PTS, 2)

        self.current_position = {
            "playbook": playbook,
            "type": opt_type,
            "strike": opt_info["strike"],
            "symbol": opt_info["symbol"],
            "token": opt_info["token"],
            "expiry": opt_info["expiry"],
            "entry_time": datetime.now().strftime("%H:%M:%S"),
            "entry_spot": round(spot, 1),
            "entry_prem": entry_prem,
            "sl_prem": sl_prem,
            "tp_prem": tp_prem,
            "qty": self.cfg.LOT_SIZE * self.cfg.NUM_LOTS
        }
        self.trades_today += 1
        self._save_state()

        logger.info(f" ENTERED TRADE: {playbook} | {opt_info['symbol']} @ Rs {entry_prem} (SL: {sl_prem}, TP: {tp_prem})")

        # Telegram Alert
        msg = (
            f"🚨 <b>SIGNAL TRIGGERED: {playbook.upper()}</b>\n"
            f"━━━━━━━━━━━━━━━━━━━\n"
            f"📌 <b>Instrument:</b> {opt_info['symbol']} ({opt_type})\n"
            f"📊 <b>NIFTY Spot:</b> {spot:.1f}\n"
            f"💵 <b>Entry Premium:</b> Rs {entry_prem:.2f}\n"
            f"🛑 <b>Stop Loss:</b> Rs {sl_prem:.2f} (-{self.cfg.STOP_LOSS_PTS} pts)\n"
            f"🎯 <b>Target:</b> Rs {tp_prem:.2f} (+{self.cfg.TARGET_PTS} pts | 1:3 RR)\n"
            f"📦 <b>Quantity:</b> {self.current_position['qty']} (1 Lot)\n"
            f"⏰ <b>Time:</b> {self.current_position['entry_time']}\n"
            f"━━━━━━━━━━━━━━━━━━━\n"
            f"💼 <i>Paper Execution Confirmed</i>"
        )
        self.notifier.send_message(msg)

    def check_position_exit(self):
        if not self.current_position:
            return

        pos = self.current_position
        curr_ltp = self.session.get_option_ltp(pos["symbol"], pos["token"])
        if curr_ltp <= 0:
            return

        now_time = datetime.now().time()
        hit_tp = (curr_ltp >= pos["tp_prem"])
        hit_sl = (curr_ltp <= pos["sl_prem"])
        hit_eod = (now_time >= self.cfg.SQUARE_OFF_TIME)

        if hit_tp or hit_sl or hit_eod:
            raw_exit = pos["tp_prem"] if hit_tp else (pos["sl_prem"] if hit_sl else curr_ltp)
            # Deduct 0.5% slippage on exit
            fill_exit = round(max(0.5, raw_exit * (1.0 - self.cfg.SLIPPAGE_RATE)), 2)
            pts = fill_exit - pos["entry_prem"]
            gross_pnl = round(pts * pos["qty"], 2)

            # Indian options friction
            stt = fill_exit * pos["qty"] * 0.000625
            turnover_charges = (pos["entry_prem"] + fill_exit) * pos["qty"] * 0.00053
            brokerage = 40.0
            gst = (brokerage + turnover_charges) * 0.18
            total_costs = round(brokerage + stt + turnover_charges + gst, 2)
            net_pnl = round(gross_pnl - total_costs, 2)
            self.capital = round(self.capital + net_pnl, 2)

            reason = "🎯 TARGET 1:3 HIT" if hit_tp else ("🛑 STOP LOSS HIT" if hit_sl else "⏰ EOD AUTO SQUARE-OFF")
            logger.info(f" EXITED TRADE: {reason} | Exit Prem: Rs {fill_exit} | Net PnL: Rs {net_pnl:+} | Capital: Rs {self.capital:,.2f}")

            # Log trade record
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
                "Costs": total_costs,
                "Net_PnL": net_pnl,
                "Capital": self.capital,
                "Reason": reason
            }
            self.log_trade(trade_log)

            # Fetch fresh Daily, Weekly & Overall Stats
            daily = self.pnl_tracker.get_daily_stats()
            weekly = self.pnl_tracker.get_weekly_stats()
            overall = self.pnl_tracker.get_overall_stats(self.capital)

            self.current_position = None
            self._save_state()

            # Telegram Exit Alert
            pnl_emoji = "🟢" if net_pnl > 0 else "🔴"
            daily_emoji = "🟢" if daily["net_pnl"] >= 0 else "🔴"
            weekly_emoji = "🟢" if weekly["net_pnl"] >= 0 else "🔴"

            msg = (
                f"{pnl_emoji} <b>TRADE CLOSED: {reason}</b>\n"
                f"━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
                f"📌 <b>Instrument:</b> {pos['symbol']}\n"
                f"⚡ <b>Playbook:</b> {pos['playbook']}\n"
                f"📥 <b>Entry:</b> Rs {pos['entry_prem']:.2f}\n"
                f"📤 <b>Exit:</b> Rs {fill_exit:.2f}\n"
                f"📈 <b>Points:</b> {pts:+.2f} pts\n"
                f"💵 <b>Trade Net PnL:</b> <b>Rs {net_pnl:+,.2f}</b> (charges: Rs {total_costs:.2f})\n"
                f"━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
                f"{daily_emoji} <b>Daily P&L (Today):</b> <b>Rs {daily['net_pnl']:+,.2f}</b> "
                f"({daily['wins']}W / {daily['losses']}L | {daily['win_rate']:.0f}% WR)\n"
                f"{weekly_emoji} <b>Weekly P&L ({weekly['week_label']}):</b> <b>Rs {weekly['net_pnl']:+,.2f}</b> "
                f"({weekly['wins']}W / {weekly['losses']}L | {weekly['win_rate']:.0f}% WR)\n"
                f"💰 <b>Total Capital:</b> <b>Rs {self.capital:,.2f}</b> ({overall['roi_pct']:+.1f}% ROI)\n"
                f"━━━━━━━━━━━━━━━━━━━━━━━━━━"
            )
            self.notifier.send_message(msg)

    def send_eod_summary(self):
        daily = self.pnl_tracker.get_daily_stats()
        weekly = self.pnl_tracker.get_weekly_stats()
        overall = self.pnl_tracker.get_overall_stats(self.capital)

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
            f"  • Trades Today: {daily['trade_count']} ({daily['wins']} Wins / {daily['losses']} Losses)\n"
            f"  • Win Rate: {daily['win_rate']:.1f}%\n"
            f"  • Points Captured: {daily['points']:+.1f} pts\n"
            f"  • Total Frictional Costs: Rs {daily['costs']:,.2f}\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"📅 <b>WEEK-TO-DATE ({weekly['week_label']}):</b>\n"
            f"  • Net Weekly P&L: <b>{w_sign} Rs {weekly['net_pnl']:+,.2f}</b>\n"
            f"  • Weekly Trades: {weekly['trade_count']} ({weekly['wins']} Wins / {weekly['losses']} Losses)\n"
            f"  • Weekly Win Rate: {weekly['win_rate']:.1f}%\n"
            f"  • Days Traded: {weekly['days_traded']} day(s)\n"
            f"  • Best Trade: Rs {weekly['best_trade']:+,.2f} | Worst: Rs {weekly['worst_trade']:+,.2f}\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"💼 <b>ACCOUNT CAPITAL & ROI:</b>\n"
            f"  • Starting Capital: Rs {self.cfg.INITIAL_CAPITAL:,.2f}\n"
            f"  • Current Balance: <b>Rs {self.capital:,.2f}</b>\n"
            f"  • All-Time Net P&L: <b>Rs {overall['total_net_pnl']:+,.2f}</b>\n"
            f"  • Cumulative Return: <b>{overall['roi_pct']:+.2f}%</b>\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        )
        if is_friday:
            msg += (
                f"🏆 <b>WEEKEND WRAP-UP:</b>\n"
                f"Weekly Trading Complete! Net Week P&L: <b>{w_sign} Rs {weekly['net_pnl']:+,.2f}</b>.\n"
                f"Next trading session resumes Monday at 09:15 AM IST."
            )
        else:
            msg += f"💤 <i>System sleeping. Next trading session resumes tomorrow at 09:15 AM IST.</i>"

        logger.info(f"Sending EOD Summary: Daily Net=Rs {daily['net_pnl']}, Weekly Net=Rs {weekly['net_pnl']}")
        self.notifier.send_message(msg)

    def evaluate_market(self):
        now_time = datetime.now().time()
        if now_time < self.cfg.ENTRY_START or now_time > self.cfg.ENTRY_END:
            return

        if self.current_position is not None:
            return  # Already holding a trade

        if self.trades_today >= self.cfg.MAX_TRADES_PER_DAY:
            return

        candles = self.session.get_5m_candles()
        if candles.empty or len(candles) < 3:
            return

        # Setup Opening Range if not yet set
        if self.orb_high is None:
            first_three = candles.head(3)
            self.orb_high = float(first_three["high"].max())
            self.orb_low = float(first_three["low"].min())
            self.day_open = float(candles["open"].iloc[0])
            logger.info(f"15-min ORB Set: High={self.orb_high}, Low={self.orb_low}, DayOpen={self.day_open}")

        last_bar = candles.iloc[-1]
        prev_bar = candles.iloc[-2]

        spot = float(last_bar["close"])
        b_open = float(last_bar["open"])
        b_high = float(last_bar["high"])
        b_low = float(last_bar["low"])
        b_range = b_high - b_low

        if b_range < 5.0:
            return  # Dead bar

        lower_wick = min(b_open, spot) - b_low
        upper_wick = b_high - max(b_open, spot)
        bull_body = (spot > b_open) and ((spot - b_open) >= 0.25 * b_range)
        bear_body = (spot < b_open) and ((b_open - spot) >= 0.25 * b_range)
        prev_c = float(prev_bar["close"])

        lvl = self.levels
        if not lvl:
            return

        # Playbook Signal Evaluation
        # 1. Crossovers
        r1_break = (prev_c <= lvl["r1"]) and (spot > lvl["r1"]) and bull_body
        s1_break = (prev_c >= lvl["s1"]) and (spot < lvl["s1"]) and bear_body
        r2_break = (prev_c <= lvl["r2"]) and (spot > lvl["r2"]) and bull_body
        s2_break = (prev_c >= lvl["s2"]) and (spot < lvl["s2"]) and bear_body

        # 2. Reversals
        tested_r1 = (b_high >= lvl["r1"] >= b_low) or (float(prev_bar["high"]) >= lvl["r1"] and b_high >= lvl["r1"])
        r1_fade = tested_r1 and (spot < lvl["r1"]) and (upper_wick >= 0.25 * b_range)
        tested_r2 = (b_high >= lvl["r2"])
        r2_fade = tested_r2 and (spot < lvl["r2"]) and (upper_wick >= 0.25 * b_range)

        # 3. Gap Retest & Polarity Flip
        gap_r1_retest = False
        gap_s1_retest = False
        if self.day_open >= lvl["r1"]:
            tested = (b_low <= lvl["r1"] <= b_high) or (b_low <= lvl["r1"])
            gap_r1_retest = tested and (spot > lvl["r1"]) and (lower_wick >= 0.25 * b_range)
        elif self.day_open <= lvl["s1"]:
            tested = (b_low <= lvl["s1"] <= b_high) or (b_high >= lvl["s1"])
            gap_s1_retest = tested and (spot < lvl["s1"]) and (upper_wick >= 0.25 * b_range)

        # 4. Gap-and-Go ORB
        gap_orb_ce = False
        gap_orb_pe = False
        if len(candles) >= 4:
            if self.day_open >= lvl["r1"]:
                gap_orb_ce = (prev_c <= self.orb_high) and (spot > self.orb_high) and bull_body
            elif self.day_open <= lvl["s1"]:
                gap_orb_pe = (prev_c >= self.orb_low) and (spot < self.orb_low) and bear_body

        # Candidate Trigger Selection
        if gap_r1_retest:
            self.enter_trade("Gap-Up R1 Polarity Bounce", "CE", spot)
        elif gap_s1_retest:
            self.enter_trade("Gap-Down S1 Polarity Rejection", "PE", spot)
        elif r1_fade:
            self.enter_trade("R1 Resistance Reversal", "PE", spot)
        elif r2_fade:
            self.enter_trade("R2 Exhaustion Reversal", "PE", spot)
        elif gap_orb_ce:
            self.enter_trade("Gap-and-Go Bullish ORB", "CE", spot)
        elif gap_orb_pe:
            self.enter_trade("Gap-and-Go Bearish ORB", "PE", spot)
        elif s1_break:
            self.enter_trade("S1 Support Breakdown", "PE", spot)
        elif s2_break:
            self.enter_trade("S2 Flush Breakdown", "PE", spot)
        elif r1_break:
            self.enter_trade("R1 Resistance Breakout", "CE", spot)

# ==========================================
# MAIN TRADING ENGINE LOOP
# ==========================================
def main():
    print("""
    ========================================================================
       NIFTY ALGORITHMIC PAPER TRADING SYSTEM (ANGEL ONE SMARTAPI)
    ========================================================================
    """)
    config = AlgoConfig()
    notifier = TelegramNotifier(config.TELEGRAM_BOT_TOKEN, config.TELEGRAM_CHAT_ID)

    # Initial Connection
    session_mgr = AngelSessionManager(config, notifier)
    if not session_mgr.connect():
        logger.error("Failed to connect to Angel One. Terminating.")
        return

    executor = PaperTradeExecutor(config, session_mgr, notifier)
    executor.initialize_day()

    logger.info("Algo Paper Trading Loop Running. Monitoring market...")

    last_candle_check = 0
    while True:
        try:
            now = datetime.now()
            now_time = now.time()

            # Check open position ticks every 2 seconds
            if executor.current_position:
                executor.check_position_exit()

            # Check 5-minute candle signals every 10 seconds
            if time.time() - last_candle_check >= 10:
                executor.evaluate_market()
                last_candle_check = time.time()

            # Auto shutdown after market close
            if now_time >= config.MARKET_END:
                logger.info("Market Closed. Ending Session.")
                executor.send_eod_summary()
                break

            time.sleep(2)
        except KeyboardInterrupt:
            logger.info("Manual shutdown triggered.")
            notifier.send_message("⚠️ <i>Algo Paper Trader Manually Stopped.</i>")
            break
        except Exception as e:
            logger.error(f"Unexpected Loop Error: {e}")
            notifier.send_message(f"⚠️ <b>ALGO RUNTIME WARNING:</b> {e}")
            time.sleep(5)

if __name__ == "__main__":
    main()
