import pandas as pd
import backtest_expiry_day_next_week as b

base_dir = '.'
sess = b.load_2025_data(base_dir)
sigs = b.extract_signals_2025(sess)
cache = b.precompute_trajectories_2025(sigs, ['ATM', 'ITM-1', 'OTM-1'])

# Split into Pre-SEBI (Thursday expiries) and Post-SEBI (Tuesday expiries)
exp_sigs_thu = [s for s in sigs if s['is_expiry_day'] and 'Pre-SEBI' in s['era']]
exp_sigs_tue = [s for s in sigs if s['is_expiry_day'] and 'Post-SEBI' in s['era']]

print(f"Total Expiry trades on Thursdays (Pre-SEBI Jan-Aug): {len(exp_sigs_thu)}")
print(f"Total Expiry trades on Tuesdays (Post-SEBI Sep-Dec): {len(exp_sigs_tue)}")

for strike in ['ATM', 'ITM-1', 'OTM-1']:
    print(f"\n==================== STRIKE: {strike} ====================")
    for name, s_list in [('Pre-SEBI (Thursday Expiries)', exp_sigs_thu), ('Post-SEBI (Tuesday Expiries)', exp_sigs_tue)]:
        t_0dte = [b.execute_single_trade(s, cache[(s['id'], strike, 'current_weekly')], 40.0, 3.0, False) for s in s_list]
        df_0 = pd.DataFrame([t for t in t_0dte if t])

        t_next = [b.execute_single_trade(s, cache[(s['id'], strike, 'next_weekly')], 40.0, 3.0, False) for s in s_list]
        df_n = pd.DataFrame([t for t in t_next if t])

        p0_win = df_0[df_0['net_pnl'] > 0]['net_pnl'].sum()
        p0_loss = abs(df_0[df_0['net_pnl'] < 0]['net_pnl'].sum())
        p0_pf = p0_win / p0_loss if p0_loss > 0 else 99.0

        pn_win = df_n[df_n['net_pnl'] > 0]['net_pnl'].sum()
        pn_loss = abs(df_n[df_n['net_pnl'] < 0]['net_pnl'].sum())
        pn_pf = pn_win / pn_loss if pn_loss > 0 else 99.0

        print(f"--- {name} ---")
        print(f"  0-DTE (Same Day):  WR: {df_0['is_win'].mean()*100:5.1f}% | Net PnL: Rs {df_0['net_pnl'].sum():>8,.2f} | PF: {p0_pf:4.2f}")
        print(f"  Next Week Expiry:  WR: {df_n['is_win'].mean()*100:5.1f}% | Net PnL: Rs {df_n['net_pnl'].sum():>8,.2f} | PF: {pn_pf:4.2f}")
