import os
import time
import requests
from google import genai
from google.genai.errors import ServerError

GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHANNEL_ID = os.environ.get("TELEGRAM_CHANNEL_ID")

def generate_digest():
    client = genai.Client(api_key=GEMINI_API_KEY)
    
    prompt = """
Ти — професійний геополітичний аналітик та персональний помічник. Твоє завдання — підготувати глибокий, аналітичний дайджест найважливіших подій та новин за останню добу, спираючись на світові тенденції, аналітику провідних видань (Financial Times, The Economist, Reuters, Bloomberg) та український контекст.

### Структура дайджесту:
Використовуй чітку структуру з п'яти розділів:
1. 🇺🇦 Україна (внутрішня політика, безпека, ключові події).
2. 🇪🇺 Європа (політичні рішення, безпека, позиція щодо України).
3. 🇺🇸 США (внутрішня політика, законодавчі ініціативи, зовнішньополітичні кроки).
4. 🌏 Азія (регіональна динаміка, торговельні та геополітичні зрушення).
5. 🌐 Загальні міжнародні новини (глобальні саміти, важливі дипломатичні зустрічі).

### Вимоги до оформлення та синтаксису (СУВОРО ДОТРИМУЙСЯ):
- Мова виключно українська.
- Стиль: Глибокий аналітичний, стриманий, реалістичний (realpolitik), без вигадування неіснуючих фактів.
- Оформлення пунктів: Кожен пункт має бути написаний в один рядок (без переносів всередині). 
- Формат кожного пункту: `- Головна теза: Аналітичний висновок та суть події.`
- ЗАБОРОНЕНО використовувати заголовки суцільним КАПСЛОКОМ та таблиці.
"""

    # Робимо до 3 спроб на випадок перевантаження сервера (503)
    max_retries = 3
    for attempt in range(1, max_retries + 1):
        try:
            print(f"Спроба генерації через Gemini (спроба {attempt}/{max_retries})...")
            response = client.models.generate_content(
                model='gemini-3.8-flash',
                contents=prompt,
            )
            return response.text
        except ServerError as e:
            if attempt == max_retries:
                raise e
            print(f"Сервер перевантажений (503), чекаємо 5 секунд перед повтором...")
            time.sleep(5)
        except Exception as e:
            raise e

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
    text = generate_digest()
    print("Відправляємо в Telegram...")
    send_to_telegram(text)
    print("✅ Успішно відправлено в канал!")
