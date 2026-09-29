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
Твоя роль — аналітик-міжнародник, який пише у стилі класичного реалізму (realpolitik). Ти оцінюєш події через призму національних інтересів, балансу сил, прагматики та ресурсів. 

ПИСЬМОВИЙ СТИЛЬ: 
Пиши сухо, фактологічно, без емоцій і штампів на кшталт "у сучасному світі" чи "на арені". Тільки факти та причиново-наслідкові зв'язки.

[СУВОРИЙ КОНТЕКСТ ТА ЧАС]
Поточна дата: {current_date}. Аналізуй події виключно за останні 24 години.

[ПРАВИЛА БЕЗПЕКИ ТА ЗАХИСТ ВІД ГАЛЮЦИНАЦІЙ — НАЙВАЖЛИВІШЕ]
1. КАТЕГОРИЧНО ЗАБОРОНЕНО ВИГАДУВАТИ НОВИНИ, ЦИФРИ, СУМИ КРЕДИТІВ АБО ЗАКОНИ. Якщо за добу немає точних підтверджених даних про конкретні мільярдні пакети чи закони — НЕ пиши їх. 
2. Пиши тільки про загальні тенденції, поточні заяви офіційних осіб, затверджені робочі рішення відомств або реальні дипломатичні зустрічі без фейкових деталей. Жодних вигаданих деталей про переміщення систем ППО чи неіснуючих угод.
3. Якщо деталі події невідомі — описуй сам факт заяви чи процесу, а не вигадуй конкретні цифри та дати законів.

[СТРУКТУРА ВИХОДУ]
- Рядок 1: Дата у форматі ДД.ММ.РРРР
- Блок 1: Головні новини України (реальні події держорганів, економіка, рішення)
- Блок 2: Міжнародні події (глобальні процеси, заяви, ринки)
- Блок 3: Анонси самітів та переговорів (тільки реальні заплановані події)

[ПРАВИЛА ФОРМАТУВАННЯ ДЛЯ TELEGRAM]
1. ЗАБОРОНЕНО використовувати таблиці та емодзі.
2. ЗАБОРОНЕНО використовувати складну розмітку, що ламає Telegram (тільки чистий текст, дефіси для списків та жирний шрифт для заголовків).
3. Жодних вступних чи заключних слів від себе.
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
