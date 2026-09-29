import os
import requests

GROQ_API_KEY = os.environ.get("GROQ_API_KEY")
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHANNEL_ID = os.environ.get("TELEGRAM_CHANNEL_ID")

def get_active_groq_model(headers):
    """Автоматично отримує першу доступну робочу модель з API Groq"""
    try:
        url = "https://api.groq.com/openai/v1/models"
        response = requests.get(url, headers=headers)
        if response.status_code == 200:
            models = response.json().get("data", [])
            # Шукаємо текстову модель, яка підтримується
            for model in models:
                model_id = model["id"]
                if "chat" in model_id.lower() or "gpt" in model_id.lower() or "llama" in model_id.lower():
                    print(f"Знайдено активну модель: {model_id}")
                    return model_id
    except Exception as e:
        print(f"Не вдалося отримати список моделей автоматично: {e}")
    
    # Резервний варіант за замовчуванням
    return "openai/gpt-oss-20b"

def generate_digest():
    headers = {
        "Authorization": f"Bearer {GROQ_API_KEY}",
        "Content-Type": "application/json"
    }
    
    # Автоматично визначаємо актуальну модель
    model_name = get_active_groq_model(headers)

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
