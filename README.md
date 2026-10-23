# NIFTY Options Backtesting Suite: Open Interest & Directional Momentum

An institutional-grade, event-driven backtesting engine and interactive analytics dashboard built specifically for **NIFTY 50 Intraday Options Trading (ATM CE & PE)** using **Open Interest (OI)**, **Put-Call Ratio (PCR)**, and **Price Momentum**.

---

## 🚀 Key Features

1. **Open Interest (OI) & PCR Analytics Engine** ([`oi_engine.py`](file:///C:/Users/Admin/Desktop/nifty%20backttteest/oi_engine.py)):
   - **Put-Call Ratio (PCR)** tracking and rate-of-change (velocity).
   - **4-Quadrant Institutional Buildup**:
     - 🟢 **Long Buildup**: Price ↑ + OI ↑ (Aggressive buying)
     - 🔴 **Short Buildup**: Price ↓ + OI ↑ (Aggressive Call writing / shorting)
     - ⚡ **Short Covering**: Price ↑ + OI ↓ (Call sellers trapped & covering → explosive spikes)
     - ⚠️ **Long Unwinding**: Price ↓ + OI ↓ (Put writers panic liquidating → rapid selloffs)
   - **Strike Boundary Walls**: Identifies Key Resistance (`Max Call OI Strike`) and Support (`Max Put OI Strike`).
   - Supports external custom intraday OI CSV files or institutional microstructure simulation.

2. **Synthetic Black-Scholes & Greeks Engine** ([`options_pricing.py`](file:///C:/Users/Admin/Desktop/nifty%20backttteest/options_pricing.py)):
   - Calculates exact option premiums, Delta, Gamma, Theta, and Vega for weekly Nifty contracts based on intraday spot movements.
   - Accurately models intraday **Theta time decay** toward weekly Thursday expiries.
   - Calibrates implied volatility (IV) dynamically using **INDIA VIX (`^INDIAVIX`)**.

3. **Realistic Execution & Cost Model**:
   - **Slippage**: 0.5% on entry & exit premiums.
   - **Brokerage & Taxes**: ₹40 flat round-trip brokerage + 0.0625% STT (Sell side) + NSE Txn charges + GST.
   - **Risk Management**: Configurable Stop Loss % (e.g. 20%), Target % (e.g. 60%), Trailing SL, and mandatory 15:15 IST intraday square-off.

4. **Institutional Analytics & Interactive Dashboard**:
   - Interactive Cumulative Equity Curve with Peak High-Water Mark.
   - Underwater Drawdown (%) chart.
   - Daily P&L distribution bar chart.
   - Full search & filter trade execution book with duration, Greeks, PCR, and OI quadrant badges.
   - Quant Tearsheet: Sharpe Ratio, Sortino Ratio, Calmar Ratio, Profit Factor, Win Rate, and Streaks.

---

## 📁 Project Structure

| File | Description |
| :--- | :--- |
| [`config.py`](file:///C:/Users/Admin/Desktop/nifty%20backttteest/config.py) | Strategy, capital, risk rules, and Open Interest parameters |
| [`oi_engine.py`](file:///C:/Users/Admin/Desktop/nifty%20backttteest/oi_engine.py) | Open Interest, PCR velocity, and 4-quadrant buildup analytics |
| [`options_pricing.py`](file:///C:/Users/Admin/Desktop/nifty%20backttteest/options_pricing.py) | Black-Scholes pricing formula, Greeks, and weekly expiry calendar |
| [`data_loader.py`](file:///C:/Users/Admin/Desktop/nifty%20backttteest/data_loader.py) | Automatic Yahoo Finance 5m spot & VIX fetcher with local CSV caching |
| [`strategy.py`](file:///C:/Users/Admin/Desktop/nifty%20backttteest/strategy.py) | ORB calculations with Supertrend, EMA, and Open Interest confirmation |
| [`backtest_engine.py`](file:///C:/Users/Admin/Desktop/nifty%20backttteest/backtest_engine.py) | Intraday bar-by-bar simulator with SL/Target fills, slippage, and costs |
| [`metrics.py`](file:///C:/Users/Admin/Desktop/nifty%20backttteest/metrics.py) | Performance analytics (Sharpe, Sortino, Drawdown, Profit Factor) |
| [`report_generator.py`](file:///C:/Users/Admin/Desktop/nifty%20backttteest/report_generator.py) | Standalone interactive HTML dashboard generator with Plotly charts |
| [`optimize.py`](file:///C:/Users/Admin/Desktop/nifty%20backttteest/optimize.py) | Parameter sweep & grid search optimizer across 108 strategy combinations |
| [`backtest_formula_levels.py`](file:///C:/Users/Admin/Desktop/nifty%20backttteest/backtest_formula_levels.py) | Institutional SPR formula levels backtesting engine (Options & Spot) |
| [`formula_levels_backtest_report.html`](file:///C:/Users/Admin/Desktop/nifty%20backttteest/formula_levels_backtest_report.html) | Interactive HTML visual report for formula SPR levels strategy |
| [`trades_formula_levels.csv`](file:///C:/Users/Admin/Desktop/nifty%20backttteest/trades_formula_levels.csv) | Formula levels trade execution log book |
| [`run_backtest.py`](file:///C:/Users/Admin/Desktop/nifty%20backttteest/run_backtest.py) | Hybrid strategy runner (ORB + Trend Filter + Open Interest) |
| [`run_oi_strategy.py`](file:///C:/Users/Admin/Desktop/nifty%20backttteest/run_oi_strategy.py) | Pure Open Interest intraday runner (PCR momentum, Short Squeeze, Wall Reversals) |
| [`backtest_report.html`](file:///C:/Users/Admin/Desktop/nifty%20backttteest/backtest_report.html) | Generated interactive HTML dashboard report |
| [`trades_log.csv`](file:///C:/Users/Admin/Desktop/nifty%20backttteest/trades_log.csv) | Verified trade log export with entry/exit fills, PCR, and PnL |

---

## ⚡ How to Run

### 1. Hybrid Setup: Technical Momentum + Open Interest Confirmation (Recommended)
```powershell
python run_backtest.py
```
Options:
```powershell
# Adjust PCR thresholds
python run_backtest.py --pcr-bullish 1.10 --pcr-bearish 0.90

# 30-minute ORB + OI Confirmation
python run_backtest.py --orb 30 --sl 0.20 --target 0.80

# Disable OI filter (run pure technical breakout)
python run_backtest.py --no-oi
```

### 2. Pure Open Interest Intraday Trading
```powershell
# Mode A: PCR Velocity & Momentum shifts
python run_oi_strategy.py --mode pcr_momentum

# Mode B: Short Squeeze & Panic Unwinding
python run_oi_strategy.py --mode short_squeeze

# Mode C: Fading Strike Walls (Max Call/Put OI Resistance & Support)
python run_oi_strategy.py --mode wall_reversal
```

### 3. Strategy Parameter Optimization Grid
```powershell
python optimize.py
```

### 4. View Interactive HTML Dashboard
Double-click [`backtest_report.html`](file:///C:/Users/Admin/Desktop/nifty backttteest/backtest_report.html) or run:
```powershell
start backtest_report.html
```

---

## 🔒 Locked SPR (Support, Pivot, Resistance) & CPR Formula Engine

The project includes the verified institutional **SPR & Central Pivot Range (CPR)** calculator ([`generate_next_day_levels.py`](file:///C:/Users/Admin/Desktop/nifty%20backttteest/generate_next_day_levels.py)).

### Locked Formula Architecture:
* **CPR Formulation**:
  * Central Pivot ($P$): $\frac{H + L + C}{3}$
  * Bottom Central ($BC$): $\frac{H + L}{2}$
  * Top Central ($TC$): $(2 \times P) - BC$
* **NIFTY SPOT Multipliers**:
  * $\text{RES}_4 = C + (1.333 \times R)$
  * $\text{RES}_3 = C + (0.866 \times R)$
  * $\text{RES}_2 = C + (0.500 \times R)$
  * $\text{RES}_1 = C + (0.236 \times R)$
  * $\text{SUP}_1 = C - (0.300 \times R)$
  * $\text{SUP}_2 = C - (0.550 \times R)$
  * $\text{SUP}_3 = C - (0.900 \times R)$
  * $\text{SUP}_4 = C - (1.314 \times R)$
* **BANKNIFTY Multipliers**:
  * $\text{RES}_3 = C + (0.840 \times R)$
  * $\text{RES}_2 = C + (0.468 \times R)$
  * $\text{RES}_1 = C + (0.200 \times R)$
  * $\text{SUP}_1 = C - (0.258 \times R)$
  * $\text{SUP}_2 = C - (0.516 \times R)$
  * $\text{SUP}_3 = C - (0.823 \times R)$

### Run Automated Daily Generator:
```powershell
# Automatically fetch latest market close and compute next-day levels:
python generate_next_day_levels.py

# Compute manual custom session levels:
python generate_next_day_levels.py --symbol "NIFTY SPOT" --high 22753.25 --low 22569.65 --close 22716.20
python generate_next_day_levels.py --symbol "BANKNIFTY" --high 54405.30 --low 53785.70 --close 54259.95
```

---

## 📊 Backtest the Formula Levels Strategy

Run the institutional Formula Support & Resistance backtest engine ([`backtest_formula_levels.py`](file:///C:/Users/Admin/Desktop/nifty%20backttteest/backtest_formula_levels.py)):

```powershell
# Run Options Backtest (ATM CE & PE with Black-Scholes, Theta decay & STT):
python backtest_formula_levels.py --mode options

# Run Pure Spot Price Action Backtest (Index Points & Futures):
python backtest_formula_levels.py --mode spot

# Run Long-Term 15-Minute Horizon (202 Sessions):
python backtest_formula_levels.py --timeframe 15m

# Open the Interactive HTML Report:
start formula_levels_backtest_report.html
```

---

## 🎯 NIFTY Options (1 Lot = 65 Qty) Risk-Reward (1:2 vs 1:3) Optimization

Dedicated institutional options backtesting engine ([`backtest_nifty_options_sr.py`](file:///C:/Users/Admin/Desktop/nifty%20backttteest/backtest_nifty_options_sr.py)) and comparative analytics ([`report_risk_reward_comparison.html`](file:///C:/Users/Admin/Desktop/nifty%20backttteest/report_risk_reward_comparison.html)):

* **Position**: Strictly **1 Lot = 65 Qty** on NIFTY ATM Options (CE for support bounces, PE for resistance fades).
* **Friction Included**: ₹40 round-trip brokerage, 0.0625% STT on sell turnover, 0.053% NSE turnover charges, 18% GST, and 0.5% fill slippage.

### Command Line Usage:
```powershell
# Run 1:2 Risk-Reward (Fixed 30 pts SL / 60 pts TP):
python backtest_nifty_options_sr.py --sl-mode points --sl 30 --rr 2.0

# Run 1:3 Risk-Reward (Fixed 30 pts SL / 90 pts TP):
python backtest_nifty_options_sr.py --sl-mode points --sl 30 --rr 3.0

# Run with Dynamic Trailing Stop Loss (BE after 1:1, Lock 1:1 after 1:2):
python backtest_nifty_options_sr.py --sl-mode points --sl 30 --rr 2.0 --trail

# Run Comprehensive Grid Sweep & Regenerate Comparison Report:
python compare_risk_reward.py
python generate_rr_comparison_report.py
start report_risk_reward_comparison.html
```


