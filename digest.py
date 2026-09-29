import os
import requests
import xml.etree.ElementTree as ET

GROQ_API_KEY = os.environ.get("GROQ_API_KEY")
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHANNEL_ID = os.environ.get("TELEGRAM_CHANNEL_ID")

def fetch_rss_news():
    feeds = [
        "https://www.pravda.com.ua/rss/",
        "https://rssexport.rbc.ua/inter/ukr/news.rss"
    ]
    
    news_text = "ОСЬ РЕАЛЬНІ НОВИНИ ЗА ОСТАННІ ДОБИ З ІНТЕРНЕТУ:\n"
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
    
    for feed_url in feeds:
        try:
            response = requests.get(feed_url, headers=headers, timeout=5)
            if response.status_code == 200:
                root = ET.fromstring(response.content)
                for item in root.findall('.//item')[:5]:
                    title = item.find('title')
                    if title is not None and title.text:
                        news_text += f"- {title.text.strip()}\n"
        except Exception as e:
            print(f"Помилка збору RSS {feed_url}: {e}")
            
    return news_text

def generate_digest(news_context):
    prompt = f"""
Ти — професійний геополітичний аналітик та персональний помічник. На основі наданих нижче **реальних заголовків новин** підготуй глибокий, структурований та аналітичний дайджест українською мовою за останню добу. Не вигадуй події, спирайся на факти з контексту нижче.

{news_context}

### Структура дайджесту:
Використовуй чітку структуру з п'яти розділів:
1. 🇺🇦 Україна (внутрішня політика, безпека, ключові події).
2. 🇪🇺 Європа (політичні рішення, безпека, позиція щодо України).
3. 🇺🇸 США (внутрішня політика, законодавчі ініціативи, зовнішньополітичні кроки).
4. 🌏 Азія (регіональна динаміка, торговельні та геополітичні зрушення).
5. 🌐 Загальні міжнародні новини (глобальні саміти, важливі дипломатичні зустрічі).

### Вимоги до оформлення та синтаксису (СУВОРО ДОТРИМУЙСЯ):
- Мова виключно українська.
- Стиль: Аналітичний, стриманий, реалістичний (realpolitik).
- Оформлення пунктів: Кожен пункт має бути написаний **в один рядок** (без переносів рядків всередині пункту). 
- Формат пункту: `- <b>Коротка теза:</b> Суть події з аналітичним коментарем.`
- ЗАБОРОНЕНО використовувати заголовки суцільним КАПСЛОКОМ та таблиці.
- Усі HTML-теги повинні закриватися в межах одного абзацу.
"""

    url = "https://api.groq.com/openai/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {GROQ_API_KEY}",
        "Content-Type": "application/json"
    }
    payload = {
        "model": "openai/gpt-oss-20b", 
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
        "text": text, 
        "parse_mode": "HTML"
    }
    response = requests.post(url, json=payload)
    if response.status_code != 200:
        raise Exception(f"Помилка від Telegram API: {response.text}")

if __name__ == "__main__":
    print("Збираємо актуальні новини через стрічки...")
    news_data = fetch_rss_news()
    
    print("Генеруємо аналітичний дайджест через Groq...")
    text = generate_digest(news_data)
    
    print("Відправляємо в Telegram...")
    send_to_telegram(text)
    print("✅ Успішно відправлено в канал!")
