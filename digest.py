import os
import time
import requests
import xml.etree.ElementTree as ET
from datetime import datetime

ANTHROPIC_API_KEY = (os.environ.get("ANTHROPIC_API_KEY") or "").strip().replace('\r', '').replace('\n', '')
TELEGRAM_BOT_TOKEN = (os.environ.get("TELEGRAM_BOT_TOKEN") or "").strip().replace('\r', '').replace('\n', '')
TELEGRAM_CHANNEL_ID = (os.environ.get("TELEGRAM_CHANNEL_ID") or "").strip().replace('\r', '').replace('\n', '')

ANTHROPIC_MODEL = (os.environ.get("ANTHROPIC_MODEL") or "claude-3-5-sonnet-latest").strip()
WORKSPACE_ID = (os.environ.get("WORKSPACE_ID") or "").strip()

def fetch_latest_news():
    # Google News RSS: міжнародні події за останні 24 години
    search_queries = [
        "US White House Congress State Department Pentagon when:24h",
        "US foreign policy diplomacy sanctions tariffs when:24h",
        "Europe European Union NATO United Kingdom security when:24h",
        "Eastern Europe Ukraine Russia post-Soviet when:24h",
        "Middle East North Africa Iran Israel Gulf when:24h",
        "China Taiwan Japan South Korea India Indo-Pacific when:24h",
        "Sub-Saharan Africa conflict diplomacy elections when:24h",
        "Latin America diplomacy elections economy when:24h",
        "global energy markets trade central banks international agreements when:24h"
    ]

    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }
    items_by_key = {}

    print("--- ЗАВАНТАЖЕННЯ МІЖНАРОДНИХ НОВИН ЧЕРЕЗ GOOGLE NEWS RSS (ОСТАННІ 24 ГОДИНИ) ---")
    for query in search_queries:
        encoded_query = requests.utils.quote(query)
        url = f"https://news.google.com/rss/search?q={encoded_query}&hl=en-US&gl=US&ceid=US:en"
        try:
            res = requests.get(url, headers=headers, timeout=15)
            if res.status_code != 200:
                print(f"Помилка RSS {res.status_code} для запиту: {query}")
                continue

            root = ET.fromstring(res.content)
            added = 0
            for item in root.findall(".//item")[:12]:
                title_elem = item.find("title")
                source_elem = item.find("source")
                link_elem = item.find("link")
                date_elem = item.find("pubDate")
                if title_elem is None or not title_elem.text:
                    continue

                title = title_elem.text.strip()
                source = source_elem.text.strip() if source_elem is not None and source_elem.text else "Джерело не вказане"
                link = link_elem.text.strip() if link_elem is not None and link_elem.text else ""
                pub_date = date_elem.text.strip() if date_elem is not None and date_elem.text else "Дата не вказана"
                key = title.casefold()

                if key not in items_by_key:
                    items_by_key[key] = {
                        "title": title, "source": source,
                        "link": link, "date": pub_date
                    }
                    added += 1
            print(f"Запит '{query[:45]}...': додано {added} матеріалів")
        except Exception as e:
            print(f"Помилка з'єднання для '{query[:35]}...': {e}")
            continue

    news_lines = []
    for item in items_by_key.values():
        news_lines.append(
            f"- Заголовок: {item['title']}\n"
            f"  Джерело: {item['source']}\n"
            f"  Дата публікації: {item['date']}\n"
            f"  Посилання: {item['link'] or 'не надано'}"
        )

    print(f"Усього відібрано унікальних матеріалів: {len(news_lines)}")
    return "\n".join(news_lines)

def generate_digest():
    current_date = datetime.now().strftime("%d.%m.%Y")
    news_input = fetch_latest_news()

    if len(news_input.strip()) < 100:
        return f"Геополітичний дайджест | {current_date}\n\nЗа останні 24 години у джерелах не зафіксовано новин для аналізу."

    system_prompt = f"""Ти — редактор-аналітик геополітичного дайджесту для Telegram-каналу.
Твоє завдання: щодня формувати стислий, фактологічно точний дайджест головних міжнародних подій.

Поточна дата: {current_date}

## ДЖЕРЕЛА ТА ВЕРИФІКАЦІЯ

1. Використовуй тільки перевірені джерела: Reuters, AP, AFP, Bloomberg, Foreign Affairs, Politico, The Economist, офіційні заяви урядів та міжнародних організацій (Держдеп США, Білий дім, ООН, НАТО, ЄС), а також авторитетні регіональні джерела.
2. Вхідні матеріали містять заголовки, назви джерел, дати публікацій і посилання, але не повні тексти статей. Не стверджуй, що перевірив повний текст або незалежне підтвердження, якщо цього неможливо встановити з наданих даних.
3. Вважай подію підтвердженою двома джерелами лише тоді, коли у вхідних матеріалах є щонайменше два незалежні джерела, які повідомляють про ту саму подію. Якщо джерело одне, явно зазнач: «За даними [джерело], незалежного підтвердження у наданих матеріалах немає».
4. Відкидай анонімні телеграм-канали без першоджерела, пропагандистські ресурси, неперевірені повідомлення, чутки та прогнози, подані як факти.
5. Якщо інформація суперечлива, наведи обидві версії та назви джерела. Не визначай самостійно, яка з них правильна.
6. Чітко розділяй факт і аналіз. Аналітичні коментарі позначай «Контекст:» або «Оцінка:».

## ЧАСОВЕ ВІКНО

- Включай лише події, що відбулися або стали відомі за останні 24 години, від попереднього випуску до поточного моменту.
- Якщо подія старша за 24 години, але сьогодні має розвиток, подавай саме сьогоднішній розвиток і стисло пояснюй попередній контекст.
- Орієнтуйся на дату публікації у вхідних матеріалах. Не вигадуй точний час події, якщо його не вказано.

## КРИТЕРІЇ ВІДБОРУ

Пріоритети:
1. Пряма зміна статус-кво: війни, перевороти, санкції, угоди, вибори.
2. Рішення та заяви найвищого рівня: президенти, державні секретарі, Рада Безпеки ООН, керівники НАТО та ЄС.
3. Події з прямим впливом на безпеку України та Центрально-Східної Європи.
4. Значні міжнародні економічні й енергетичні рішення.
5. Військові переміщення, навчання та інциденти.

Відкидай локальні новини без міжнародного значення, світську хроніку й сенсації без належного підтвердження. Не вигадуй фактів, деталей, джерел або посилань. Працюй лише з подіями, наведеними у вхідних матеріалах.

## СТРУКТУРА ДАЙДЖЕСТУ

🔴 ГОЛОВНЕ
- 1–3 найважливіші події дня, по 2–4 речення кожна.

🇺🇸 США
- Внутрішня політика, Білий дім і Конгрес.
- Зовнішня політика та заяви Держдепартаменту.
- Оборонні рішення Пентагону.
Включай лише підрозділи, де є суттєві події.

🌍 ЗА РЕГІОНАМИ
Включай лише регіони з підтвердженими значущими подіями. Не пиши «немає новин» для порожніх розділів.
- Європа: ЄС, НАТО, Велика Британія.
- Східна Європа, Україна та пострадянський простір.
- Близький Схід і Північна Африка (MENA).
- Індо-Тихоокеанський регіон: Китай, Японія, Корея, Тайвань, Індія.
- Африка на південь від Сахари.
- Латинська Америка.

📌 ВАРТО СТЕЖИТИ
- 1–2 тези про події, які можуть розвинутися найближчим часом. Чітко відокремлюй спостережуваний факт від обережної оцінки можливого розвитку.

## СТИЛЬ

- Нейтральна мова без оцінних епітетів і пропагандистських формулювань.
- Кожен пункт: факт → джерело → за потреби короткий контекст.
- Назву джерела вказуй наприкінці речення в дужках: (Reuters), (AP), (Держдеп США).
- Якщо є посилання у вхідних матеріалах, додай його після відповідного пункту або в кінці повідомлення так, щоб читач міг знайти першоджерело.
- Без вступних фраз і води. Кожен пункт має містити 1–3 речення, крім головних подій, для яких дозволено 2–4 речення.
- Не заповнюй розділи штучно. Якщо матеріалів недостатньо для надійного висновку, пропусти подію або явно вкажи обмеження.
- Зберігай читабельний формат Telegram. Не використовуй таблиці. Загальний обсяг повідомлення — не більше 3500 символів, щоб воно надійно надсилалося в Telegram.

Сформуй готовий дайджест українською мовою. Не додавай пояснень про власний процес роботи.
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
                "content": f"Ось стрічка новин за останні 24 години:\n\n{news_input}"
            }
        ]
    }
    
    url = "https://api.anthropic.com/v1/messages"
    # Відповідь може затримуватися, коли модель обробляє великий список новин.
    # Повторюємо запит до двох разів після тайм-ауту та збільшуємо час очікування.
    last_timeout = None
    for attempt in range(3):
        try:
            res = requests.post(url, headers=headers, json=payload, timeout=(15, 180))
            break
        except requests.exceptions.Timeout as exc:
            last_timeout = exc
            if attempt == 2:
                raise Exception(
                    "Claude API не повернув відповідь за 180 секунд після 3 спроб. "
                    "Спробуй зменшити кількість новин у запиті або перевірити статус Anthropic API."
                ) from exc
            wait_seconds = 5 * (attempt + 1)
            print(f"Тайм-аут Claude API (спроба {attempt + 1}/3). Повтор через {wait_seconds} с...")
            time.sleep(wait_seconds)

    if res.status_code != 200:
        raise Exception(f"Помилка Claude API ({res.status_code}): {res.text}")

    data = res.json()
    if not data.get("content") or not data["content"][0].get("text"):
        raise Exception(f"Claude API повернув відповідь без тексту: {data}")

    return data["content"][0]["text"]

def send_to_telegram(text):
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {"chat_id": TELEGRAM_CHANNEL_ID, "text": text}
    res = requests.post(url, json=payload)
    if res.status_code != 200:
        raise Exception(f"Помилка Telegram API: {res.text}")

if __name__ == "__main__":
    print(f"Генеруємо аналітичний дайджест (модель: {ANTHROPIC_MODEL})...")
    output = generate_digest()
    print("\n--- ЗГЕНЕРОВАНИЙ ДАЙДЖЕСТ ---")
    print(output)
    print("----------------------------\n")
    print("Відправляємо в Telegram...")
    send_to_telegram(output)
    print("Успішно надіслано в канал!")
