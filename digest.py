import os
import requests
import xml.etree.ElementTree as ET
from datetime import datetime

ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY")
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHANNEL_ID = os.environ.get("TELEGRAM_CHANNEL_ID")

def fetch_latest_news():
    """Збирає заголовки з провідних новинних RSS-джерел"""
    feeds = [
        "https://www.pravda.com.ua/rss/",
        "https://rssexport.rbc.ua/inter/ukr/news.rss",
        "https://feeds.bbci.co.uk/news/world/rss.xml",
        "https://www.reuters.com/arc/outboundfeeds/rss/?outputType=xml"
    ]
    
    news_text = "ОСЬ АКТУАЛЬНІ ЗАГОЛОВКИ ТА ПОДІЇ ЗА ОСТАННІ ДОБИ:\n"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
    }
    
    for feed_url in feeds:
        try:
            response = requests.get(feed_url, headers=headers, timeout=6)
            if response.status_code == 200:
                root = ET.fromstring(response.content)
                source_name = feed_url.split('/')[2].replace('www.', '')
                for item in root.findall('.//item')[:5]:
                    title = item.find('title')
                    if title is not None and title.text:
                        news_text += f"- [{source_name}] {title.text.strip()}\n"
        except Exception as e:
            print(f"Пропускаємо джерело {feed_url}: {e}")
            
    return news_text

def generate_digest():
    current_date = datetime.now().strftime("%d.%m.%Y")
    news_input = fetch_latest_news()

    prompt = f"""
Ти — професійний геополітичний аналітик, який пише у стилі класичного реалізму (realpolitik). Ти оцінюєш події через призму національних інтересів, балансу сил, прагматики, економічних ресурсів та реальних дій держав, а не декларацій.

ПИСЬМОВИЙ СТИЛЬ:
Пиши сухо, фактологічно, жорстко і по суті. Категорично заборонено використовувати типові кліше штучного інтелекту (наприклад: "у сучасному світі", "на арені", "черговий виклик", "знаковий момент", "унікальна ситуація"). Жодних зайвих епітетів та емоцій. Тільки сухі факти і причиново-наслідкові зв'язки.

[ТЕХНІЧНІ ПРАВИЛА ТА ФІЛЬТРИ]
1. ЖОДНИХ ГАЛЮЦИНАЦІЙ: Використовуй тільки факти з наданих новин. Не додавай нічого від себе.
2. МОВНИЙ КОНТРОЛЬ: Весь текст повинен бути написаний грамотною українською мовою. Якісно перекладай англомовні новини, слідкуй за правильними відмінками.
3. ЯКЩО БЛОК ПОРОЖНІЙ: Якщо в якійсь категорії немає новин, напиши чітко: `- За останню добу немає нових підтверджених повідомлень у цій категорії.`

[ПРАВИЛА ФОРМАТУВАННЯ ДЛЯ TELEGRAM]
1. ЗАБОРОНЕНО використовувати таблиці та емодзі.
2. ЗАБОРОНЕНО використовувати складну розмітку, що ламає Telegram (тільки простий текст, дефіси для списків та жирний шрифт для назв блоків).
3. Жодних вступних чи заключних привітань від себе — видавай лише результат за структурою.

[ВХІДНІ ДАНІ НОВИН]
{news_input}

[СТРУКТУРА ВИХОДУ]
- Рядок 1: Дата у форматі ДД.ММ.РРРР ({current_date})
- Блок 1: **Головні новини України**
(список подій через дефіс українською)
- Блок 2: **Міжнародні події**
(список подій через дефіс українською)
- Блок 3: **Анонси самітів та переговорів**
(список подій через дефіс або рядок про відсутність)
"""

    url = "https://api.anthropic.com/v1/messages"
    headers = {
        "x-api-key": ANTHROPIC_API_KEY,
        "anthropic-version": "2023-06-01",
        "content-type": "application/json"
    }
    payload = {
        "model": "claude-3-5-sonnet-latest",
        "max_tokens": 1500,
        "messages": [
            {"role": "user", "content": prompt}
        ]
    }
    
    response = requests.post(url, headers=headers, json=payload)
    if response.status_code != 200:
        raise Exception(f"Помилка від Claude API: {response.text}")
        
    res_data = response.json()
    return res_data['content'][0]['text']

def send_to_telegram(text):
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": TELEGRAM_CHANNEL_ID, 
        "text": text
    }
    response = requests.post(url, json=payload)
    if response.status_code != 200:
        raise Exception(f"Помилка від Telegram API: {response.text}")

if __name__ == "__main__":
    print("Генеруємо дайджест через Claude...")
    text = generate_digest()
    
    print("Відправляємо в Telegram...")
    send_to_telegram(text)
    print("✅ Успішно відправлено в канал!")
