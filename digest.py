import os
import requests
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

def generate_digest():
    headers = {
        "Authorization": f"Bearer {GROQ_API_KEY}",
        "Content-Type": "application/json"
    }
    
    model_name = get_active_groq_model(headers)
    current_date = datetime.now().strftime("%d.%m.%Y")

    prompt = f"""
Твоя задача — сформувати короткий фактичний дайджест новин за останні 24 години для Telegram-каналу на основі наданих нижче новинних матеріалів. Пиши виключно сухі факти, цифри та події. Жодної аналітики, оціночних суджень, прогнозів чи пояснень «чому це важливо».

[КОНТЕКСТ ТА ЧАС]
Поточна дата: {current_date}. 
Вхідні дані (новини за добу): {news_input}

[ПРАВИЛА ВИБОРУ ФАКТІВ]
1. Україна: Тільки офіційні рішення держорганів, закони, підписані документи або офіційні заяви з наданого тексту (без дрібних регіональних новин).
2. Світ (США, Європа, Азія): Тільки реальні факти з тексту: ухвалені закони, офіційні візити, підписані угоди або рішення міжнародних інституцій.
3. Календар: Тільки підтверджені дати запланованих самітів та офіційних зустрічей, якщо вони є у вхідних даних.
4. СТРОГО ЗАБОРОНЕНО галюцинувати, вигадувати цифри, закони чи події, яких немає у вхідних даних. Якщо інформації з певної категорії немає у вхідних даних — коротко зазнач основний робочий факт поточного дня, не вигадуючи зайвого.

[ПРАВИЛА ФОРМАТУВАННЯ ДЛЯ TELEGRAM]
1. ЗАБОРОНЕНО використовувати таблиці та емодзі.
2. ЗАБОРОНЕНО використовувати складну розмітку, що ламає Telegram (тільки простий текст, дефіси для списків та жирний шрифт для назв блоків).
3. Жодних вступних чи заключних слів від себе.

[СТРУКТУРА ВИХОДУ]
- Рядок 1: Дата у форматі ДД.ММ.РРРР
- Блок 1: Головні новини України
- Блок 2: Міжнародні події
- Блок 3: Анонси самітів та переговорів
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
