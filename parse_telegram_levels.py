"""
Parser and Processor for Telegram Intraday Levels (FlyingCalls / Arjun)
Processes scraped messages from `telegram_scraped_messages.json`, parses NIFTY and BANKNIFTY levels,
and exports clean CSV files for historical backtesting.
"""
import os
import re
import json
import pandas as pd
from datetime import datetime

def parse_level_text(text: str) -> dict:
    result = {}
    lines = [l.strip() for l in text.splitlines() if l.strip()]
    
    nifty_lines = []
    bn_lines = []
    section = None
    
    for line in lines:
        u = line.upper()
        if 'NIFTY SPOT' in u or ('NIFTY' in u and 'BANK' not in u and 'FUTURE' not in u):
            section = 'NIFTY'
        elif 'BANKNIFTY' in u:
            section = 'BANKNIFTY'
        elif 'SENSEX' in u or 'FUTURE' in u or 'TELEGRAM' in u or 'CLIENT' in u or 'WHATSAPP' in u:
            section = 'OTHER'
            
        if section == 'NIFTY':
            nifty_lines.append(line)
        elif section == 'BANKNIFTY':
            bn_lines.append(line)
            
    # Process NIFTY
    n_text = " ".join(nifty_lines)
    n_sup_m = re.search(r'SUP\s*([0-9\s,\.]+)', n_text, re.IGNORECASE)
    n_res_m = re.search(r'RES\s*([0-9\s,\.]+)', n_text, re.IGNORECASE)
    if n_sup_m and n_res_m:
        sups = [int(float(x.replace(',', ''))) for x in re.findall(r'\b\d{5}\b', n_sup_m.group(1)) if 15000 <= float(x.replace(',', '')) <= 30000]
        ress = [int(float(x.replace(',', ''))) for x in re.findall(r'\b\d{5}\b', n_res_m.group(1)) if 15000 <= float(x.replace(',', '')) <= 30000]
        if sups and ress:
            result["nifty"] = {
                "sup": sorted(set(sups), reverse=True),
                "res": sorted(set(ress))
            }
            
    # Process BANKNIFTY
    bn_text = " ".join(bn_lines)
    bn_sup_m = re.search(r'SUP\s*([0-9\s,\.]+)', bn_text, re.IGNORECASE)
    bn_res_m = re.search(r'RES\s*([0-9\s,\.]+)', bn_text, re.IGNORECASE)
    if bn_sup_m and bn_res_m:
        sups = [int(float(x.replace(',', ''))) for x in re.findall(r'\b\d{5}\b', bn_sup_m.group(1)) if 35000 <= float(x.replace(',', '')) <= 70000]
        ress = [int(float(x.replace(',', ''))) for x in re.findall(r'\b\d{5}\b', bn_res_m.group(1)) if 35000 <= float(x.replace(',', '')) <= 70000]
        if sups and ress:
            result["banknifty"] = {
                "sup": sorted(set(sups), reverse=True),
                "res": sorted(set(ress))
            }
            
    return result

def process_scraped_json(json_path="telegram_scraped_messages.json"):
    if not os.path.exists(json_path):
        print(f"File not found: {json_path}")
        return None
        
    with open(json_path, 'r', encoding='utf-8') as f:
        msgs = json.load(f)
        
    nifty_records = []
    bn_records = []
    
    for m in msgs:
        text = m.get('text', '')
        if 'NIFTY SPOT' not in text.upper() and 'NIFTY LEVELS' not in text.upper():
            continue
            
        parsed = parse_level_text(text)
        if not parsed:
            continue
            
        dt_str = m.get('datetime')
        if dt_str:
            dt = pd.to_datetime(dt_str) + pd.Timedelta(hours=5, minutes=30)
            date_ist = dt.strftime('%Y-%m-%d')
            time_ist = dt.strftime('%H:%M:%S')
        else:
            date_ist = datetime.now().strftime('%Y-%m-%d')
            time_ist = "09:00:00"
            
        if "nifty" in parsed:
            sups = parsed["nifty"]["sup"]
            ress = parsed["nifty"]["res"]
            rec = {
                "date": date_ist,
                "time": time_ist,
                "post_id": m.get("post_id"),
                "s1": sups[0] if len(sups) > 0 else None,
                "s2": sups[1] if len(sups) > 1 else None,
                "s3": sups[2] if len(sups) > 2 else None,
                "s4": sups[3] if len(sups) > 3 else None,
                "r1": ress[0] if len(ress) > 0 else None,
                "r2": ress[1] if len(ress) > 1 else None,
                "r3": ress[2] if len(ress) > 2 else None,
                "r4": ress[3] if len(ress) > 3 else None,
            }
            # Pivot estimate = (S1 + R1) / 2
            if rec["s1"] and rec["r1"]:
                rec["pivot"] = round((rec["s1"] + rec["r1"]) / 2.0, 1)
            nifty_records.append(rec)
            
        if "banknifty" in parsed:
            sups = parsed["banknifty"]["sup"]
            ress = parsed["banknifty"]["res"]
            rec = {
                "date": date_ist,
                "time": time_ist,
                "post_id": m.get("post_id"),
                "s1": sups[0] if len(sups) > 0 else None,
                "s2": sups[1] if len(sups) > 1 else None,
                "s3": sups[2] if len(sups) > 2 else None,
                "s4": sups[3] if len(sups) > 3 else None,
                "r1": ress[0] if len(ress) > 0 else None,
                "r2": ress[1] if len(ress) > 1 else None,
                "r3": ress[2] if len(ress) > 2 else None,
                "r4": ress[3] if len(ress) > 3 else None,
            }
            if rec["s1"] and rec["r1"]:
                rec["pivot"] = round((rec["s1"] + rec["r1"]) / 2.0, 1)
            bn_records.append(rec)
            
    df_nifty = pd.DataFrame(nifty_records)
    if not df_nifty.empty:
        df_nifty.drop_duplicates(subset=["date"], keep="last", inplace=True)
        df_nifty.sort_values("date", inplace=True)
        df_nifty.to_csv("telegram_levels_nifty.csv", index=False)
        print(f"Exported {len(df_nifty)} NIFTY trading days to telegram_levels_nifty.csv")
        print(f"Range: {df_nifty['date'].min()} to {df_nifty['date'].max()}")
        
    df_bn = pd.DataFrame(bn_records)
    if not df_bn.empty:
        df_bn.drop_duplicates(subset=["date"], keep="last", inplace=True)
        df_bn.sort_values("date", inplace=True)
        df_bn.to_csv("telegram_levels_banknifty.csv", index=False)
        print(f"Exported {len(df_bn)} BANKNIFTY trading days to telegram_levels_banknifty.csv")
        
    return df_nifty, df_bn

if __name__ == "__main__":
    df_n, df_b = process_scraped_json()
    if df_n is not None and not df_n.empty:
        print("\nLast 10 NIFTY daily levels:")
        print(df_n.tail(10)[["date", "s2", "s1", "pivot", "r1", "r2"]].to_string())
