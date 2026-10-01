import os
import requests
import xml.etree.ElementTree as ET
from datetime import datetime

ANTHROPIC_API_KEY = (os.environ.get("ANTHROPIC_API_KEY") or "").strip().replace('\r', '').replace('\n', '')
TELEGRAM_BOT_TOKEN = (os.environ.get("TELEGRAM_BOT_TOKEN") or "").strip().replace('\r', '').replace('\n', '')
TELEGRAM_CHANNEL_ID = (os.environ.get("TELEGRAM_CHANNEL_ID") or "").strip().replace('\r', '').replace('\n', '')

ANTHROPIC_MODEL = (os.environ.get("ANTHROPIC_MODEL") or "claude-3-5-sonnet-latest").strip()
WORKSPACE_ID = "wrkspc_01G5WDSbhu31zt3TZ1hoywWp"

def fetch_latest_news():
    feeds = [
        "https://foreignpolicy.com/feed/",
        "https://www.politico.com/rss/politicopicks.xml",
        "https://thehill.com/policy/international/feed/",
        "https://www.csis.org/rss/all",
        "https://www.state.gov/rss-feed/press-releases/feed/",
        "https://feeds.bbci.co.uk/news/world/us_and_canada/rss.xml",
        "https://www.defensenews.com/arc/outboundfeeds/rss/?outputType=xml",
        "https://breakingdefense.com/feed/"
    ]
    
    news_text = ""
    headers = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "application/rss+xml, application/xml, text/xml, */*"
    }
    
    print("--- СТАТУС ЗАВАНТАЖЕННЯ ДЖЕРЕЛ ---")
    for feed_url in feeds:
        try:
            res = requests.get(feed_url, headers=headers, timeout=10)
            source_name = feed_url.split('/')[2].replace('www.', '')
            
            if res.status_code == 200:
                root = ET.fromstring(res.content)
                items = root.findall('.//item') or root.findall('.//{http://www.w3.org/2005/Atom}entry')
                count = 0
                for item in items[:15]:
                    title_elem = item.find('title') or item.find('{http://www.w3.org/2005/Atom}title')
                    if title_elem is not None and title_elem.text:
                        news_text += f"- [{source_name}] {title_elem.text.strip()}\n"
                        count += 1
                print(f"✅ {source_name}: зібрано {count} новин")
            else:
                print(f"❌ {source_name}: БЛОКУВАННЯ (Код {res.status_code})")
        except Exception as e:
            print(f"⚠️ {feed_url}: ПОМИЛКА ПАРСИНГУ ({e})")
            continue
            
    print("----------------------------------\n")
    return news_text

def generate_digest():
    current_date = datetime.now().strftime("%d.%m.%Y")
    news_input = fetch_latest_news()

    print(f"[DEBUG] Обсяг зібраного тексту: {len(news_input)} символів.")
    
    if len(news_input.strip()) < 50:
        return f"Дайджест зовнішньої політики США | {current_date}\n\nПомилка: Бот не зміг завантажити жодної новини з джерел через блокування IP-адреси GitHub Actions."

    system_prompt = f"""Ти — провідний експерт з міжнародної політики та геостратегії США. Проаналізуй вхідні новини за останні 24 години та склади концентрований геополітичний дайджест.

СЬОГОДНІШНЯ ДАТА: {current_date}

МЕТОДОЛОГІЯ ТА АНАЛІТИЧНА ОПТИКА:
1. Баланс сил: більшість міжнародних подій (конфлікти, саміти в ЄС чи Азії, економічні кризи) прямо чи опосередковано впливають на позиції Вашингтона. Твоє завдання — пояснити цей зв'язок. Навіть якщо новина прямо не згадує США, поясни її значення для американської геостратегії.
2. Геоекономіка: санкції, тарифи, ланцюги постачання критичних ресурсів та технологій.
3. Академічний, строгий стиль: формат аргументації "подія — механізм — наслідок для балансу сил". Ніякої публіцистики.

СУВОРІ ОБМЕЖЕННЯ ФОРМАТУВАННЯ:
- Максимальний обсяг: до 2100 символів.
- КАТЕГОРИЧНО ЗАБОРОНЕНО використовувати капслок для заголовків. 
- Жодних таблиць, псевдографіки, рамок.
- Жодних заголовків Markdown (#, ##, ###).
- Жодних зірочок (**) чи підкреслень (_).
- Марковані списки лише через дефіс ("- ").
- Жодних емодзі.

СТРУКТУРА:
Дайджест зовнішньої політики США | {current_date}
(1-2 речення: ключовий геостратегічний фокус доби)

Міжнародна політика, дипломатія та альянси
- [Суть події у 2-3 реченнях. Вкажи джерело].

Геоекономіка, санкції та внутрішні рішення
- [Суть події у 2-3 реченнях. Вкажи джерело].

Аналітичний висновок
(Один цілісний абзац на 3-4 речення).
"""

    headers = {
        "x-api-key": ANTHROPIC_API_KEY,
        "anthropic-version": "2023-06-01",
        "anthropic-workspace-id": WORKSPACE_ID,
        "content-type": "application/json"
    }

    payload = {
        "model": ANTHROPIC_MODEL,
        "max_tokens": 1500,
        "system": system_prompt,
        "messages": [
            {
                "role": "user", 
                "content": f"Ось фактичні стрічки новин:\n\n{news_input}"
            }
        ]
    }
    
    url = "https://api.anthropic.com/v1/messages"
    res = requests.post(url, headers=headers, json=payload, timeout=60)

    if res.status_code != 200:
        raise Exception(f"Помилка від Claude API ({res.status_code}): {res.text}")
        
    return res.json()['content'][0]['text']

def send_to_telegram(text):
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {"chat_id": TELEGRAM_CHANNEL_ID, "text": text}
    res = requests.post(url, json=payload)
    if res.status_code != 200:
        raise Exception(f"Помилка від Telegram API: {res.text}")

if __name__ == "__main__":
    print(f"Генеруємо дайджест через Claude (модель: {ANTHROPIC_MODEL})...")
    output = generate_digest()
    print("\n--- ГОТОВИЙ ТЕКСТ ---")
    print(output)
    print("---------------------\n")
    print("Відправляємо в Telegram...")
    send_to_telegram(output)
    print("Успішно надіслано в канал!")
