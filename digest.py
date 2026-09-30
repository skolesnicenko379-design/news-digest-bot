import os
import requests
import xml.etree.ElementTree as ET
from datetime import datetime

GROQ_API_KEY = (os.environ.get("GROQ_API_KEY") or "").strip().replace('\r', '').replace('\n', '')
TELEGRAM_BOT_TOKEN = (os.environ.get("TELEGRAM_BOT_TOKEN") or "").strip().replace('\r', '').replace('\n', '')
TELEGRAM_CHANNEL_ID = (os.environ.get("TELEGRAM_CHANNEL_ID") or "").strip().replace('\r', '').replace('\n', '')

def fetch_latest_news():
    feeds = [
        "https://www.pravda.com.ua/rss/",
        "https://rssexport.rbc.ua/inter/ukr/news.rss",
        "https://feeds.bbci.co.uk/news/world/rss.xml",
        "https://www.reuters.com/arc/outboundfeeds/rss/?outputType=xml"
    ]
    news_text = "ОСЬ АКТУАЛЬНІ ЗАГОЛОВКИ ТА ПОДІЇ ЗА ОСТАННІ ДОБИ:\n"
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
    for feed_url in feeds:
        try:
            res = requests.get(feed_url, headers=headers, timeout=6)
            if res.status_code == 200:
                root = ET.fromstring(res.content)
                source_name = feed_url.split('/')[2].replace('www.', '')
                for item in root.findall('.//item')[:5]:
                    title = item.find('title')
                    if title is not None and title.text:
                        news_text += f"- [{source_name}] {title.text.strip()}\n"
        except Exception:
            pass
    return news_text

def generate_digest():
    current_date = datetime.now().strftime("%d.%m.%Y")
    news_input = fetch_latest_news()

    prompt = f"""
Ти — професійний геополітичний аналітик, який пише у стилі класичного реалізму (realpolitik). Оцінюй події через національні інтереси, ресурси та баланс сил.
ПИСЬМОВИЙ СТИЛЬ: сухо, жорстко, без AI-кліше та емоцій. Тільки факти і зв'язки.

[ПРАВИЛА]
1. Тільки грамотна українська мова.
2. Жодних емодзі та таблиць. Тільки текст і дефіси для списків.
3. Якщо категорія порожня, пиши: - За останню добу немає нових підтверджених повідомлень у цій категорії.

[ВХІДНІ ДАНІ]
{news_input}

[СТРУКТУРА]
{current_date}

**Головні новини України**
(список подій через дефіс)

**Міжнародні події**
(список подій через дефіс)

**Анонси самітів та переговорів**
(список подій через дефіс або рядок про відсутність)
"""

    headers = {
        "Authorization": f"Bearer {GROQ_API_KEY}",
        "Content-Type": "application/json"
    }

    payload = {
        "model": "llama-3.3-70b-versatile",
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.3
    }
    
    url = "https://api.groq.com/openai/v1/chat/completions"
    res = requests.post(url, headers=headers, json=payload)

    if res.status_code != 200:
        raise Exception(f"Помилка від Groq API: {res.text}")
        
    return res.json()['choices'][0]['message']['content']

def send_to_telegram(text):
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {"chat_id": TELEGRAM_CHANNEL_ID, "text": text}
    res = requests.post(url, json=payload)
    if res.status_code != 200:
        raise Exception(f"Помилка від Telegram API: {res.text}")

if __name__ == "__main__":
    print("Генеруємо дайджест через Groq...")
    output = generate_digest()
    print("Відправляємо в Telegram...")
    send_to_telegram(output)
    print("✅ Успішно надіслано в канал!")
