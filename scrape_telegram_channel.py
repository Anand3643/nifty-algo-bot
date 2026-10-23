from bs4 import BeautifulSoup
import re
import urllib.request
import ssl
import json
import time

ctx = ssl.create_default_context()
ctx.check_hostname = False
ctx.verify_mode = ssl.CERT_NONE

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
}

def parse_html(html):
    soup = BeautifulSoup(html, 'html.parser')
    messages = []
    
    # Message containers in Telegram preview
    widgets = soup.find_all('div', class_='tgme_widget_message')
    for w in widgets:
        post_attr = w.get('data-post', '')
        if not post_attr:
            continue
        post_id = post_attr.split('/')[-1]
        
        # Time
        time_el = w.find('time')
        dt_str = time_el.get('datetime', '') if time_el else ''
        
        # Text
        text_el = w.find('div', class_='tgme_widget_message_text')
        text = text_el.get_text('\n', strip=True) if text_el else ''
        
        messages.append({
            'post_id': int(post_id) if post_id.isdigit() else post_id,
            'datetime': dt_str,
            'text': text
        })
    return messages

if __name__ == '__main__':
    with open('debug_tg.html', 'r', encoding='utf-8') as f:
        html = f.read()
    msgs = parse_html(html)
    print(f"Parsed {len(msgs)} messages.")
    for m in msgs:
        if 'NIFTY' in m['text'].upper():
            print(f"=== POST {m['post_id']} ({m['datetime']}) ===")
            print(m['text'])
            print("="*50)

