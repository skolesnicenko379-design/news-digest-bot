import os
import requests

GROQ_API_KEY = os.environ.get("GROQ_API_KEY")
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHANNEL_ID = os.environ.get("TELEGRAM_CHANNEL_ID")

PROMPT = """
Ти — професійний геополітичний аналітик та персональний помічник, який спеціалізується на українській та міжнародній політиці. Твоє завдання — підготувати глибокий, структурований та аналітичний дайджест найважливіших новин за останню добу українською мовою.

### Структура дайджесту:
Використовуй чітку структуру з п'яти розділів:
1. 🇺🇦 Україна (внутрішня політика, безпека, ключові події).
2. 🇪🇺 Європа (політичні рішення, безпека, позиція щодо України).
3. 🇺🇸 США (внутрішня політика, законодавчі ініціативи, зовнішньополітичні кроки).
4. 🌏 Азія (регіональна динаміка, торговельні та геополітичні зрушення).
5. 🌐 Загальні міжнародні новини (глобальні саміти, важливі дипломатичні зустрічі, анонси майбутніх переговорів).

### Вимоги до оформлення та синтаксису (ДУЖЕ ВАЖЛИВО):
- Мова виключно українська.
- Стиль: Аналітичний, стриманий, реалістичний (realpolitik), без зайвої емоційності.
- Першоджерела: Додавай достовірні назви авторитетних джерел (наприклад, Reuters, AP, Bloomberg, BBC, Nikkei).
- Обмеження формату для Telegram:
  - НЕ використовуй заголовки написані суцільним КАПСЛОКОМ.
  - НЕ використовуй таблиці.
  - Використовуй емодзі для розділів, списки з булетами (*) та HTML-теги <b> для виділення головних тез.
  - Усі теги мають обов'язково закриватися в межах одного абзацу.
"""

def generate_digest():
    url = "https://api.groq.com/openai/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {GROQ_API_KEY}",
        "Content-Type": "application/json"
    }
    payload = {
        "model": "openai/gpt-oss-20b", 
        "messages": [{"role": "user", "content": PROMPT}],
        "temperature": 0.5
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
    print("Починаємо генерацію через Groq...")
    text = generate_digest()
    send_to_telegram(text)
    print("✅ Успішно відправлено в канал!")
