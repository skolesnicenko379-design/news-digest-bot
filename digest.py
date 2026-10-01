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
    # Тематичні запити через Google News з жорстким фільтром за 24 години
    search_queries = [
        "US foreign policy OR diplomacy OR State Department when:24h",
        "US sanctions OR trade tariffs OR export controls China when:24h",
        "Pentagon OR defense budget OR military aid Ukraine Taiwan when:24h",
        "geopolitics alliance NATO Indo-Pacific US when:24h"
    ]
    
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }
    
    news_text = ""
    seen_titles = set()
    
    print("--- ЗАВАНТАЖЕННЯ ЧЕРЕЗ GOOGLE NEWS RSS (ОСТАННІ 24 ГОДИНИ) ---")
    for query in search_queries:
        encoded_query = requests.utils.quote(query)
        url = f"https://news.google.com/rss/search?q={encoded_query}&hl=en-US&gl=US&ceid=US:en"
        
        try:
            res = requests.get(url, headers=headers, timeout=10)
            if res.status_code == 200:
                root = ET.fromstring(res.content)
                items = root.findall('.//item')
                added = 0
                for item in items[:10]:
                    title_elem = item.find('title')
                    source_elem = item.find('source')
                    
                    if title_elem is not None and title_elem.text:
                        raw_title = title_elem.text.strip()
                        source_name = source_elem.text.strip() if source_elem is not None and source_elem.text else "Google News"
                        
                        # Відсікаємо дублікати
                        if raw_title not in seen_titles:
                            seen_titles.add(raw_title)
                            news_text += f"- [{source_name}] {raw_title}\n"
                            added += 1
                print(f"✅ Запит '{query[:30]}...': отримано {added} новин")
            else:
                print(f"❌ Запит '{query[:30]}...': помилка {res.status_code}")
        except Exception as e:
            print(f"⚠️ Помилка з'єднання: {e}")
            continue
            
    print(f"Усього відібрано унікальних новин: {len(seen_titles)}\n")
    return news_text

def generate_digest():
    current_date = datetime.now().strftime("%d.%m.%Y")
    news_input = fetch_latest_news()

    if len(news_input.strip()) < 100:
        return f"Дайджест зовнішньої політики США | {current_date}\n\nЗа останні 24 години у джерелах не зафіксовано новин для аналізу."

    system_prompt = f"""Ти — старший аналітик міжнародної політики та геостратегії США. Твоє завдання — проаналізувати вхідні новини за останні 24 години, виокремити стратегічні події для Вашингтона та підготувати глибокий аналітичний дайджест.

СЬОГОДНІШНЯ ДАТА: {current_date}

МЕТОДОЛОГІЯ ТА СТИЛЬ:
1. Реалізм та архітектура стримування: оцінюй саміти, двосторонні зустрічі, регіональні альянси та рухи сил через національні інтереси США, баланс сил та стримування опонентів (КНР, РФ, Іран).
2. Геоекономіка та ресурси: фіксуй санкційні механізми, торговельні тарифи, контроль над експортом мікроелектроніки/ШІ, постачання енергоносіїв та пакети військово-фінансової допомоги.
3. Матеріальна база: зіставляй публічні заяви політиків із рішеннями Конгресу, Пентагону та контрактними зобов'язаннями.
4. Академічний стиль: ланцюжки "рішення/подія — задіяний важіль — зміна регіонального чи глобального балансу сил". Без публіцистики, емоцій чи AI-кліше.
5. АНТИ-ГАЛЮЦИНАЦІЯ: Використовуй лише ті події, які реально наведені у вхідному списку новин.

СУВОРІ ОБМЕЖЕННЯ ФОРМАТУВАННЯ:
- Максимальний обсяг: до 2100 символів (з пробілами).
- КАТЕГОРИЧНО ЗАБОРОНЕНО використовувати заголовки ВСІМА ВЕЛИКИМИ ЛІТЕРАМИ (капслок заборонено).
- Жодних таблиць (символів "|") та псевдографіки.
- Жодних заголовків Markdown (#, ##, ###).
- Жодних зірочок (**) чи нижніх підкреслень (_).
- Марковані списки лише через дефіс ("- ").
- Жодних емодзі.

СТРУКТУРА:
Дайджест зовнішньої політики США | {current_date}
(1-2 лаконічних речення: головний стратегічний вектор доби у діях Вашингтона)

Міжнародна політика, дипломатія та альянси
- [Суть події у 2-3 реченнях: зміст перемовин, самітів чи військово-політичних дій. Вкажи джерело у дужках].
- [Наступна подія через дефіс].

Геоекономіка, санкції та внутрішні рішення
- [Суть події у 2-3 реченнях: тарифи, санкції, оборонне фінансування, рішення Конгресу/Білого дому. Вкажи джерело у дужках].
- [Наступна подія через дефіс].

Аналітичний висновок
(Один зв'язний абзац на 3-4 речення: як події доби трансформують геополітичні позиції США.)
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
    res = requests.post(url, headers=headers, json=payload, timeout=60)

    if res.status_code != 200:
        raise Exception(f"Помилка Claude API ({res.status_code}): {res.text}")
        
    return res.json()['content'][0]['text']

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
