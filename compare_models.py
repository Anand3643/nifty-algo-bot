import os
import pandas as pd
from optimize_combined_strategy import *

base_dir = os.path.dirname(os.path.abspath(__file__))
candle_path = os.path.join(base_dir, "nifty_data", "candles", "NIFTY_5min.csv")
daily_path = os.path.join(base_dir, "nifty_data", "candles", "NIFTY_1day.csv")

df_intra = pd.read_csv(candle_path)
df_intra["datetime"] = pd.to_datetime(df_intra["datetime"])
df_intra.sort_values("datetime", inplace=True)
df_1d = pd.read_csv(daily_path)
df_1d["datetime"] = pd.to_datetime(df_1d["datetime"]).dt.date
df_1d.drop_duplicates(subset=["datetime"], inplace=True)
df_1d.set_index("datetime", inplace=True)
df_intra["date"] = df_intra["datetime"].dt.date

session_data = []
for current_date, grp in df_intra.groupby("date"):
    if len(grp) < 12:
        continue
    priors = [d for d in df_1d.index if d < current_date]
    if not priors:
        continue
    prev_row = df_1d.loc[priors[-1]]
    lvl = NiftySREngine.calculate_levels(float(prev_row["high"]), float(prev_row["low"]), float(prev_row["close"]))
    dow = current_date.weekday()
    dte = max(0.5, (3 - dow) % 7 + 0.5) / 365.0
    bars = [
        {"dt": r["datetime"], "time": r["datetime"].time(), "open": float(r["open"]), "high": float(r["high"]), "low": float(r["low"]), "close": float(r["close"])}
        for _, r in grp.iterrows()
    ]
    session_data.append({"date": current_date, "lvl": lvl, "dte": dte, "day_open": float(grp["open"].iloc[0]), "bars": bars})

top_pb = ["S2 Flush Breakdown", "R1 Resistance Reversal", "R2 Exhaustion Reversal", "R1 Resistance Breakout", "S1 Support Breakdown"]

m1 = run_custom_simulation(session_data, allowed_playbooks=None, sl_val=30.0, rr=3.0, trail=False, max_trades_per_day=1)
m2 = run_custom_simulation(session_data, allowed_playbooks=top_pb, sl_val=30.0, rr=3.0, trail=False, max_trades_per_day=1)
m3 = run_custom_simulation(session_data, allowed_playbooks=top_pb, sl_val=40.0, rr=3.0, trail=False, max_trades_per_day=1)
m4 = run_custom_simulation(session_data, allowed_playbooks=top_pb, sl_val=40.0, rr=3.0, trail=False, max_trades_per_day=2)

configs = [
    ("1. Baseline (All Playbooks, SL 30)", m1),
    ("2. Pruned (Top 5 Playbooks, SL 30)", m2),
    ("3. Pruned + Wide Buffer (Top 5, SL 40, 1 Trade)", m3),
    ("4. Maximum Profit (Top 5, SL 40, 2 Trades)", m4)
]

for name, m in configs:
    print("=" * 70)
    print(name)
    print(f"Total Trades: {m['trades']} | Wins: {m['wins']} | Losses: {m['losses']} | Win Rate: {m['win_rate']:.1f}%")
    print(f"Target Hits: {m['target_hits']} | SL Hits: {m['sl_hits']}")
    print(f"Net PnL: Rs {m['total_net']:,.2f} | ROI: {(m['total_net']/50000)*100:.1f}% | Max DD: Rs {m['max_dd']:,.2f} ({m['max_dd_pct']:.1f}%)")
    print(f"Profit Factor: {m['profit_factor']:.2f} | Sharpe: {m['sharpe']:.2f}")

# Monthly performance breakdown for M4
df4 = m4["trades_df"].copy()
df4["Month"] = pd.to_datetime(df4["Date"]).dt.strftime("%Y-%m")
monthly = df4.groupby("Month").agg(
    Trades=("Net_PnL", "count"),
    Wins=("Net_PnL", lambda x: (x > 0).sum()),
    Net_PnL=("Net_PnL", "sum"),
    Win_Rate=("Net_PnL", lambda x: (x > 0).mean() * 100)
)
print("\n" + "=" * 70)
print("MONTHLY BREAKDOWN FOR STRATEGY 4 (MAXIMUM PROFIT):")
print(monthly.to_string())
