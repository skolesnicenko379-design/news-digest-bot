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
        "https://www.pravda.com.ua/rss/",
        "https://rssexport.rbc.ua/inter/ukr/news.rss",
        "https://feeds.bbci.co.uk/news/world/rss.xml",
        "https://www.reuters.com/arc/outboundfeeds/rss/?outputType=xml"
    ]
    news_text = ""
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
    
    for feed_url in feeds:
        try:
            res = requests.get(feed_url, headers=headers, timeout=6)
            if res.status_code == 200:
                root = ET.fromstring(res.content)
                source_name = feed_url.split('/')[2].replace('www.', '')
                for item in root.findall('.//item')[:10]: # Збільшено вибірку для кращого шансу знайти новини США
                    title = item.find('title')
                    if title is not None and title.text:
                        news_text += f"- [{source_name}] {title.text.strip()}\n"
        except Exception:
            continue
            
    return news_text

def generate_digest():
    current_date = datetime.now().strftime("%d.%m.%Y")
    news_input = fetch_latest_news()

    # Запобіжник від галюцинацій: якщо новин немає, не смикаємо Claude
    if len(news_input.strip()) < 50:
        return f"Дайджест політики США | {current_date}\n\nЗа останню добу не зафіксовано новин, придатних для аналізу."

    # Інструкції винесено в system prompt для жорсткого контролю моделі
    system_prompt = f"""Ти — старший воєнно-політичний аналітик. Твоє завдання — проаналізувати вхідні новини за останні 24 години, відібрати події щодо США та скласти глибокий дайджест.

СЬОГОДНІШНЯ ДАТА: {current_date} (ТИ ЗОБОВ'ЯЗАНИЙ використати саме цю дату у заголовку. Не вигадуй дати з минулого).

АНАЛІТИЧНА МЕТОДОЛОГІЯ ТА СТИЛЬ:
1. Реалізм та баланс сил: оцінюй процеси через національні інтереси США, ВПК та стримування супротивників.
2. Принцип "подвійного треку": зіставляй публічні заяви з реальними контрактами та переміщенням сил.
3. Фактологічна точність: вимагаються конкретні цифри ($), назви програм та підрядників.
4. Сухий, академічний тон: жодних емоційних оцінок чи AI-кліше.
5. АНТИ-ГАЛЮЦИНАЦІЯ: Аналізуй ТІЛЬКИ ті події, які є у вхідних новинах. Якщо важливих новин за треком немає, пиши "За останню добу немає підтверджених подій у цій категорії." Категорично заборонено вигадувати події.

СУВОРІ ОБМЕЖЕННЯ ФОРМАТУВАННЯ:
- Максимальний обсяг тексту: до 2100 символів.
- КАТЕГОРИЧНО ЗАБОРОНЕНО використовувати капслок для заголовків. Пиши їх звичайним текстом (наприклад: "Зовнішня політика та оборона", а не "ЗОВНІШНЯ ПОЛІТИКА").
- Жодних таблиць (символів "|").
- Жодної псевдографіки, рамок та стрілок.
- Жодних заголовків Markdown (#, ##, ###).
- Жодних зірочок (**) чи нижніх підкреслень (_).
- Марковані списки виключно через дефіс з пробілом ("- ").
- Жодних емодзі.

СТРУКТУРА:
Дайджест політики США | {current_date}
(1-2 лаконічних речення головного вектору доби)

Зовнішня політика та оборона
- [Суть події у 2-4 реченнях. Вкажи джерело].

Внутрішня політика та ВПК
- [Суть події у 2-4 реченнях. Вкажи джерело].

Аналітичний висновок
(Один зв'язний абзац на 3-4 речення).
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
                "content": f"Ось фактичні заголовки за останню добу. Використовуй лише їх:\n\n{news_input}"
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
    print("Відправляємо в Telegram...")
    send_to_telegram(output)
    print("Успішно надіслано в канал!")
