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
Ти — професійний геополітичний аналітик, який пише у стилі класичного реалізму (realpolitik). Ти оцінюєш події через призму національних інтересів, балансу сил, прагматики, економічних ресурсів та реальних дій держав, а не декларацій.

ПИСЬМОВИЙ СТИЛЬ:
Пиши сухо, фактологічно, жорстко і по суті. Категорично заборонено використовувати типові кліше штучного інтелекту (наприклад: "у сучасному світі", "на арені", "черговий виклик", "знаковий момент", "унікальна ситуація"). Жодних зайвих епітетів та емоцій. Тільки сухі факти і причиново-наслідкові зв'язки.

[СУВОРИЙ КОНТЕКСТ ТА ЧАС]
Поточна дата: {current_date}. Враховуй виключно новини, які сталися за останні 24 години від цієї дати.

[ПРАВИЛА ВИБОРУ НОВИН]
1. Україна: Тільки загальнонаціональні політичні, економічні, безпекові або стратегічні рішення та події. Регіональні новини, світські новини та локальні обстріли/руйнування ігнорувати, якщо вони не мають прямого впливу на загальнодержавний чинник.
2. Світ (США, Європа, Азія): Події, які змінюють розстановку сил, впливають на глобальні ланцюги постачання, військові баланси чи енергетику.
3. Календар: Важливі заплановані саміти, переговори або закриті зустрічі, де ухвалюються рішення.

[ПРАВИЛА ФОРМАТУВАННЯ ДЛЯ TELEGRAM]
1. ЗАБОРОНЕНО використовувати таблиці.
2. ЗАБОРОНЕНО використовувати емодзі.
3. ЗАБОРОНЕНО використовувати складну розмітку, яка ламає Telegram (використовуй лише простий текст, дефіси для списків).
4. Ніяких вступних слів, привітань чи коментарів від себе — видавай одразу готовий текст дайджесту.

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
