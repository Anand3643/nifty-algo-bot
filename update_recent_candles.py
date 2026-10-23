import pyotp
import time
import os
import pandas as pd
from SmartApi import SmartConnect
from datetime import datetime

def update_candles():
    print("Authenticating with Angel One SmartAPI...")
    smart_api = SmartConnect(api_key='6mRD3Ntn')
    totp = pyotp.TOTP('Z6NUOKVTOJI5LUI6GCFR2HXKWY').now()
    session = smart_api.generateSession('A612537', '1436', totp)
    if not session.get('status'):
        print("Failed to authenticate:", session)
        return
        
    time.sleep(1.5)
    params = {
        'exchange': 'NSE',
        'symboltoken': '99926000',
        'interval': 'FIVE_MINUTE',
        'fromdate': '2026-10-10 09:15',
        'todate': datetime.now().strftime('%Y-%m-%d %H:%M')
    }
    
    res = smart_api.getCandleData(params)
    data = res.get('data', [])
    print(f"Retrieved {len(data)} candles from SmartAPI.")
    
    if data:
        df_new = pd.DataFrame(data, columns=['datetime', 'open', 'high', 'low', 'close', 'volume'])
        candle_path = 'nifty_data/candles/NIFTY_5min.csv'
        if os.path.exists(candle_path):
            df_old = pd.read_csv(candle_path)
            df_all = pd.concat([df_old, df_new]).drop_duplicates(subset=['datetime']).sort_values('datetime')
        else:
            df_all = df_new
            
        df_all.to_csv(candle_path, index=False)
        print("Updated NIFTY_5min.csv up to:", df_all['datetime'].iloc[-1])
        print("Total bars:", len(df_all))

if __name__ == '__main__':
    update_candles()
