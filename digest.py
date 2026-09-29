import os
import requests
import xml.etree.ElementTree as ET
from datetime import datetime

GROQ_API_KEY = os.environ.get("GROQ_API_KEY")
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHANNEL_ID = os.environ.get("TELEGRAM_CHANNEL_ID")

def get_active_groq_model(headers):
    """Шукає виключно робочу генеративну модель, ігноруючи системні та захисні сервіси"""
    try:
        url = "https://api.groq.com/openai/v1/models"
        response = requests.get(url, headers=headers)
        if response.status_code == 200:
            models = response.json().get("data", [])
            for model in models:
                model_id = model["id"]
                if any(name in model_id.lower() for name in ["llama", "gpt"]) and not any(bad in model_id.lower() for bad in ["guard", "whisper", "embed", "vision"]):
                    print(f"Знайдено повноцінну модель для генерації: {model_id}")
                    return model_id
    except Exception as e:
        print(f"Не вдалося отримати список моделей автоматично: {e}")
    
    return "openai/gpt-oss-20b"

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
    headers = {
        "Authorization": f"Bearer {GROQ_API_KEY}",
        "Content-Type": "application/json"
    }
    
    model_name = get_active_groq_model(headers)
    current_date = datetime.now().strftime("%d.%m.%Y")
    news_input = fetch_latest_news()

    prompt = f"""
Твоя роль — технічний редактор новинного Telegram-каналу. Твоє завдання — звести наданий текст новин (`{news_input}`) у суворий, коростий фактичний дайджест. Пиши виключно за наданими фактами, без жодної аналітики, оцінок чи відсебеньки.

[ТЕХНІЧНІ ПРАВИЛА ТА ЗАХИСТ ВІД ШАБЛОНІВ]
1. НОРИХ ГАЛЮЦИНАЦІЙ: Використовуй тільки факти з `{news_input}`. Не вигадуй події, яких там немає.
2. ЯКЩО БЛОК ПОРОЖНІЙ У ВХІДНИХ ДАНИХ: Якщо в якійсь категорії немає новин, НЕ залишай її порожньою і не пиши «(порожній)». Напиши короткий рядок: `- За останню добу немає нових підтверджених повідомлень у цій категорії.`
3. МОВНИЙ КОНТРОЛЬ: Пиши грамотно українською мовою, суворо дотримуючись відмінків (жодних спотворень на кшталт "Кієн").

[ПРАВИЛА ФОРМАТУВАННЯ ДЛЯ TELEGRAM]
1. ЗАБОРОНЕНО використовувати таблиці та емодзі.
2. ЗАБОРОНЕНО використовувати складну розмітку, що ламає Telegram (тільки простий текст, дефіси для списків та жирний шрифт для назв блоків).
3. Жодних вступних чи заключних привітань від себе — видавай лише результат за структурою.

[СТРУКТУРА ВИХОДУ]
- Рядок 1: Дата у форматі ДД.ММ.РРРР ({current_date})
- Блок 1: **Головні новини України**
(список подій через дефіс)
- Блок 2: **Міжнародні події**
(список подій через дефіс)
- Блок 3: **Анонси самітів та переговорів**
(список подій через дефіс або рядок про відсутність)
"""

    url = "https://api.groq.com/openai/v1/chat/completions"
    payload = {
        "model": model_name,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.4
    }
    
    response = requests.post(url, headers=headers, json=payload)
    if response.status_code != 200:
        raise Exception(f"Помилка від Groq API: {response.text}")
        
    return response.json()['choices'][0]['message']['content']

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
    print("Генеруємо дайджест через Groq...")
    text = generate_digest()
    
    print("Відправляємо в Telegram...")
    send_to_telegram(text)
    print("✅ Успішно відправлено в канал!")
