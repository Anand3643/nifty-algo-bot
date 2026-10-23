import pandas as pd

df = pd.read_csv("strike_expiry_sltp_sweep_results.csv")

print("=" * 80)
print("1. TOP 10 HIGHEST WIN RATE CONFIGURATIONS")
print("=" * 80)
cols = ["config_id", "strike", "expiry", "sl_mode", "sl_label", "tp_label", "trailing", "win_rate", "total_net_pnl", "profit_factor", "max_drawdown"]
print(df.sort_values("win_rate", ascending=False)[cols].head(10).to_string(index=False))

print("\n" + "=" * 80)
print("2. TOP 10 MOST PROFITABLE CONFIGURATIONS")
print("=" * 80)
print(df.sort_values("total_net_pnl", ascending=False)[cols].head(10).to_string(index=False))

print("\n" + "=" * 80)
print("3. HEAD-TO-HEAD EXPIRY COMPARISON")
print("=" * 80)
for exp in ["current_weekly", "next_weekly", "monthly"]:
    sub = df[df["expiry"] == exp]
    max_pnl_idx = sub["total_net_pnl"].idxmax()
    max_wr_idx = sub["win_rate"].idxmax()
    print(f"-- {exp.upper()} --")
    print(f"   Champion: {sub.loc[max_pnl_idx, 'config_id']}")
    print(f"   Max Net PnL: Rs {sub.loc[max_pnl_idx, 'total_net_pnl']:,.2f}")
    print(f"   Max Win Rate: {sub.loc[max_wr_idx, 'win_rate']:.2f}% ({sub.loc[max_wr_idx, 'config_id']})")
    print(f"   Avg Net PnL (Points Mode): Rs {sub[sub['sl_mode']=='points']['total_net_pnl'].mean():,.2f}")
    print(f"   Avg Net PnL (Percent Mode): Rs {sub[sub['sl_mode']=='percent']['total_net_pnl'].mean():,.2f}")
    print(f"   Avg Win Rate: {sub['win_rate'].mean():.2f}%")
    print(f"   Avg Profit Factor: {sub['profit_factor'].mean():.2f}")
    print(f"   Avg Max Drawdown: Rs {sub['max_drawdown'].mean():,.2f}\n")

print("=" * 80)
print("4. HEAD-TO-HEAD STRIKE COMPARISON")
print("=" * 80)
for st in ["ITM-2", "ITM-1", "ATM", "OTM-1", "OTM-2"]:
    sub = df[df["strike"] == st]
    print(f"{st:<6} -> Avg PnL: Rs {sub['total_net_pnl'].mean():>10,.2f} | Max PnL: Rs {sub['total_net_pnl'].max():>10,.2f} | Avg WR: {sub['win_rate'].mean():>5.2f}% | Max WR: {sub['win_rate'].max():>5.2f}% | Avg PF: {sub['profit_factor'].mean():>4.2f} | Avg DD: Rs {sub['max_drawdown'].mean():>8,.2f}")

print("\n" + "=" * 80)
print("5. SL / TP RATIO (RR) PERFORMANCE (POINTS MODE)")
print("=" * 80)
print(df[df["sl_mode"] == "points"].groupby("rr")[["win_rate", "total_net_pnl", "profit_factor", "max_drawdown"]].mean().round(2))

print("\n" + "=" * 80)
print("6. SL POINTS PERFORMANCE (20, 25, 30, 35, 40, 50)")
print("=" * 80)
print(df[df["sl_mode"] == "points"].groupby("sl_val")[["win_rate", "total_net_pnl", "profit_factor", "max_drawdown"]].mean().round(2))

print("\n" + "=" * 80)
print("7. TRAILING SL VS FIXED SL")
print("=" * 80)
print(df.groupby("trailing")[["win_rate", "total_net_pnl", "profit_factor", "max_drawdown"]].mean().round(2))
