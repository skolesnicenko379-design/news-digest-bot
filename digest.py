import os
import requests
import xml.etree.ElementTree as ET
from datetime import datetime

ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY")
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHANNEL_ID = os.environ.get("TELEGRAM_CHANNEL_ID")

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

def get_workspace_id(base_headers):
    try:
        url = "https://api.anthropic.com/v1/workspaces"
        res = requests.get(url, headers=base_headers, timeout=5)
        if res.status_code == 200:
            data = res.json().get("data", [])
            if data:
                return data[0].get("id")
    except Exception:
        pass
    return None

def generate_digest():
    current_date = datetime.now().strftime("%d.%m.%Y")
    news_input = fetch_latest_news()

    prompt = f"""
Ти — професійний геополітичний аналітик, який пише у стилі класичного реалізму (realpolitik). Оцінюй події через національні інтереси та баланс сил.
ПИСЬМОВИЙ СТИЛЬ: сухо, жорстко, без AI-кліше та емоцій. Тільки факти.

[ПРАВИЛА]
1. Тільки українська мова.
2. Жодних емодзі та таблиць.
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
(список подій через дефіс або статус відсутності)
"""

    headers = {
        "x-api-key": ANTHROPIC_API_KEY.strip(),
        "anthropic-version": "2023-06-01",
        "content-type": "application/json"
    }

    wks_id = get_workspace_id(headers)
    if wks_id:
        headers["anthropic-workspace-id"] = wks_id

    payload = {
        "model": "claude-3-5-sonnet-20241022",
        "max_tokens": 1500,
        "messages": [{"role": "user", "content": prompt}]
    }
    
    url = "https://api.anthropic.com/v1/messages"
    res = requests.post(url, headers=headers, json=payload)
    
    # Якщо воркспейс усе ще потрібен, але ендпоінт був закритий, беремо першу доступну модель без нього
    if res.status_code == 400 and "workspace" in res.text:
        headers.pop("anthropic-workspace-id", None)
        payload["model"] = "claude-3-haiku-20240307"
        res = requests.post(url, headers=headers, json=payload)

    if res.status_code != 200:
        raise Exception(f"Помилка від Claude API: {res.text}")
        
    return res.json()['content'][0]['text']

def send_to_telegram(text):
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {"chat_id": TELEGRAM_CHANNEL_ID, "text": text}
    res = requests.post(url, json=payload)
    if res.status_code != 200:
        raise Exception(f"Помилка від Telegram API: {res.text}")

if __name__ == "__main__":
    print("Генеруємо дайджест...")
    output = generate_digest()
    print("Відправляємо в Telegram...")
    send_to_telegram(output)
    print("✅ Успішно надіслано в канал!")
