import urllib.request
import ssl
import json
import time
import re
from bs4 import BeautifulSoup
import pandas as pd
from datetime import datetime

ctx = ssl.create_default_context()
ctx.check_hostname = False
ctx.verify_mode = ssl.CERT_NONE

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
}

def fetch_page(before_id=None):
    url = 'https://t.me/s/FlyingcallsArjun'
    if before_id:
        url += f'?before={before_id}'
    req = urllib.request.Request(url, headers=HEADERS)
    try:
        with urllib.request.urlopen(req, timeout=15, context=ctx) as resp:
            return resp.read().decode('utf-8', errors='ignore')
    except Exception as e:
        print(f"Error fetching {url}: {e}")
        return None

def parse_html(html):
    soup = BeautifulSoup(html, 'html.parser')
    messages = []
    widgets = soup.find_all('div', class_='tgme_widget_message')
    for w in widgets:
        post_attr = w.get('data-post', '')
        if not post_attr:
            continue
        post_id = post_attr.split('/')[-1]
        
        time_el = w.find('time')
        dt_str = time_el.get('datetime', '') if time_el else ''
        
        text_el = w.find('div', class_='tgme_widget_message_text')
        text = text_el.get_text('\n', strip=True) if text_el else ''
        
        messages.append({
            'post_id': int(post_id) if post_id.isdigit() else post_id,
            'datetime': dt_str,
            'text': text
        })
    return messages

def scrape_channel(max_pages=50):
    all_messages = {}
    before_id = None
    
    print("Starting crawl of @FlyingcallsArjun channel...")
    for page in range(max_pages):
        html = fetch_page(before_id)
        if not html:
            print(f"Failed to fetch at page {page}, stopping.")
            break
            
        msgs = parse_html(html)
        if not msgs:
            print(f"No messages found at page {page}, stopping.")
            break
            
        new_count = 0
        min_id = None
        for m in msgs:
            pid = m['post_id']
            if pid not in all_messages:
                all_messages[pid] = m
                new_count += 1
            if min_id is None or pid < min_id:
                min_id = pid
                
        print(f"Page {page+1}: fetched {len(msgs)} messages (new: {new_count}). Min ID: {min_id}")
        
        if new_count == 0 or min_id is None or min_id == before_id:
            print("No new messages reached. Reached start of public history.")
            break
            
        before_id = min_id
        time.sleep(1.0) # Respectful delay
        
    print(f"\nTotal unique messages collected: {len(all_messages)}")
    return list(all_messages.values())

if __name__ == '__main__':
    msgs = scrape_channel(max_pages=40)
    with open('telegram_scraped_messages.json', 'w', encoding='utf-8') as f:
        json.dump(msgs, f, indent=2, ensure_ascii=False)
    print("Saved to telegram_scraped_messages.json")
