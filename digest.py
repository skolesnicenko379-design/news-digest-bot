import os
import requests
import xml.etree.ElementTree as ET
from datetime import datetime

ANTHROPIC_API_KEY = (os.environ.get("ANTHROPIC_API_KEY") or "").strip().replace('\r', '').replace('\n', '')
TELEGRAM_BOT_TOKEN = (os.environ.get("TELEGRAM_BOT_TOKEN") or "").strip().replace('\r', '').replace('\n', '')
TELEGRAM_CHANNEL_ID = (os.environ.get("TELEGRAM_CHANNEL_ID") or "").strip().replace('\r', '').replace('\n', '')

# Беремо актуальну модель із середовища або використовуємо запропоновану ШІ на GitHub за замовчуванням
ANTHROPIC_MODEL = (os.environ.get("ANTHROPIC_MODEL") or "claude-sonnet-4-5-20250929").strip()
WORKSPACE_ID = "wrkspc_01G5WDSbhu31zt3TZ1hoywWp"

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
Ти — старший воєнно-політичний аналітик. Твоє завдання — проаналізувати вхідні новини за останні 24 години, відібрати події, що стосуються Сполучених Штатів Америки, та скласти глибокий аналітичний дайджест політики США.

АНАЛІТИЧНА МЕТОДОЛОГІЯ ТА СТИЛЬ:
1. Реалізм та баланс сил: оцінюй процеси через національні інтереси США, військово-промисловий потенціал, ресурси та стримування супротивників.
2. Принцип "подвійного треку": зіставляй публічні заяви політиків із реальними закупівлями, переміщенням сил, оборонними бюджетами та контрактами.
3. Фактологічна точність: вимагаються конкретні цифри ($), назви оборонних програм (NDAA, PDA, USAI), модифікації озброєння та назви підрядників ВПК (Lockheed Martin, General Dynamics, RTX, Anduril, Palantir тощо).
4. Сухий, академічний тон: жодних журналістських штампів, емоційних оцінок, метафор чи AI-кліше. Лише ланцюжки "причина — рішення — ресурс — стратегічний наслідок".

СУВОРІ ОБМЕЖЕННЯ ФОРМАТУВАННЯ (ДЛЯ TELEGRAM):
- КАТЕГОРИЧНО ЗАБОРОНЕНО використовувати таблиці (жодних символів розділювачів "|").
- КАТЕГОРИЧНО ЗАБОРОНЕНО використовувати псевдографіку, ASCII-схеми, рамки та стрілки.
- КАТЕГОРИЧНО ЗАБОРОНЕНО використовувати заголовки Markdown (#, ##, ###).
- НЕ використовуй подвійні зірочки (**) чи нижні підкреслення (_), якщо вони можуть виглядати як сирий код. Для виділення заголовків використовуй ВИКЛЮЧНО ВЕЛИКІ ЛІТЕРИ.
- Для маркованих списків використовуй виключно звичайний дефіс з пробілом ("- ").
- Жодних емодзі.

ВХІДНІ ДАНІ ДЛЯ АНАЛІЗУ:
{news_input}

СТРУКТУРА ПОВІДОМЛЕННЯ:

ДАЙДЖЕСТ ПОЛІТИКИ США | {current_date}
(1-2 лаконічних речення: головний стратегічний вектор доби у діях Вашингтона)

ЗОВНІШНЯ ПОЛІТИКА ТА ОБОРОНА
- [Суть події у 2-4 реченнях: рішення, ресурси, логістика, вплив на союзників/супротивників. Вкажи джерело у дужках].
- [Наступна новина зовнішнього треку через дефіс].
(Якщо важливих зовнішніх новин немає: - За останню добу немає підтверджених стратегічних подій у цій категорії.)

ВНУТРІШНЯ ПОЛІТИКА ТА ВПК
- [Суть події у 2-4 реченнях: бюджетний процес у Конгресі, рішення Білого дому/Пентагону, замовлення оборонної промисловості, регулювання критичних технологій. Вкажи джерело у дужках].
- [Наступна новина внутрішнього треку через дефіс].
(Якщо важливих внутрішніх новин немає: - За останню добу немає підтверджених стратегічних подій у цій категорії.)

АНАЛІТИЧНИЙ ВИСНОВОК
(Один зв'язний абзац на 3-4 речення: як зафіксовані внутрішні процеси та контракти США впливають на реальну зовнішньополітичну спроможність Вашингтона на глобальній арені.)
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
        "messages": [{"role": "user", "content": prompt}]
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
    print("Відправляємо в Telegram...")
    send_to_telegram(output)
    print("✅ Успішно надіслано в канал!")
