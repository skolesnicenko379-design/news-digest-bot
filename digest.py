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
        # Зовнішня політика, геополітика та дипломатія
        "https://foreignpolicy.com/feed/",
        "https://www.politico.com/rss/politicopicks.xml",
        "https://thehill.com/policy/international/feed/",
        "https://www.csis.org/rss/all",
        "https://www.state.gov/rss-feed/press-releases/feed/",
        
        # Загальнополітичний контекст та світова торгівля/економіка
        "https://thehill.com/feed/",
        "https://feeds.bbci.co.uk/news/world/us_and_canada/rss.xml",
        "https://feeds.bbci.co.uk/news/world/rss.xml",
        "https://www.reuters.com/arc/outboundfeeds/rss/?outputType=xml",
        
        # Військово-політичний базис та індустрія
        "https://www.defensenews.com/arc/outboundfeeds/rss/?outputType=xml",
        "https://breakingdefense.com/feed/"
    ]
    
    news_text = ""
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }
    
    for feed_url in feeds:
        try:
            res = requests.get(feed_url, headers=headers, timeout=7)
            if res.status_code == 200:
                root = ET.fromstring(res.content)
                source_name = feed_url.split('/')[2].replace('www.', '')
                
                # Підтримуємо як RSS (item), так і Atom (entry)
                items = root.findall('.//item') or root.findall('.//{http://www.w3.org/2005/Atom}entry')
                for item in items[:12]:
                    title_elem = item.find('title') or item.find('{http://www.w3.org/2005/Atom}title')
                    desc_elem = item.find('description') or item.find('{http://www.w3.org/2005/Atom}summary')
                    
                    if title_elem is not None and title_elem.text:
                        title = title_elem.text.strip()
                        desc = ""
                        if desc_elem is not None and desc_elem.text:
                            # Очищуємо базові теги, якщо опис містить короткий зміст
                            desc = desc_elem.text.split('<')[0].strip()[:200]
                        
                        entry_content = f"{title} | {desc}" if desc else title
                        news_text += f"- [{source_name}] {entry_content}\n"
        except Exception:
            continue
            
    return news_text

def generate_digest():
    current_date = datetime.now().strftime("%d.%m.%Y")
    news_input = fetch_latest_news()

    if len(news_input.strip()) < 50:
        return f"Дайджест зовнішньої політики США | {current_date}\n\nЗа останню добу не зафіксовано новин, придатних для аналізу."

    system_prompt = f"""Ти — провідний експерт з міжнародної політики та геостратегії США. Твоє завдання — проаналізувати вхідні новини за останні 24 години, відібрати події, що безпосередньо впливають на глобальне позиціонування Вашингтона, та підготувати концентрований геополітичний дайджест.

СЬОГОДНІШНЯ ДАТА: {current_date} (ТИ ЗОБОВ'ЯЗАНИЙ використати саме цю дату у заголовку).

МЕТОДОЛОГІЯ ТА АНАЛІТИЧНА ОПТИКА:
1. Реалізм та архітектура балансу сил: оцінюй міжнародні саміти, двосторонні зустрічі та договори через призму національних інтересів, розширення або обмеження сфер впливу США та стримування ключових супротивників (КНР, РФ, Іран).
2. Геоекономіка та ресурси сили: інтегруй у фокус торговельні санкції, експортний контроль технологій (ШІ, мікроелектроніка), ланцюги критичних матеріалів, енергетичну геополітику та макрофінансову допомогу союзникам.
3. Зв'язка "Конгрес — Білий дім — ВПК": висвітлюй рішення Капітолію (комітети, бюджети, пакети допомоги) та їхнє матеріальне підкріплення оборонним сектором як інструмент зовнішньополітичного стримування, а не просто корпоративні новини.
4. Академічний, строгий стиль: жодної публіцистики, емоцій чи AI-кліше. Формат аргументації: "подія/рішення — залучений ресурс/механізм — наслідок для глобального або регіонального балансу".
5. АНТИ-ГАЛЮЦИНАЦІЯ: Базуйся виключно на наданих вхідних новинах. Не вигадуй подій. Якщо за треком немає новин, прямо вказуй це.

СУВОРІ ОБМЕЖЕННЯ ФОРМАТУВАННЯ (TELEGRAM):
- Максимальний обсяг: до 2100 символів (разом із пробілами).
- КАТЕГОРИЧНО ЗАБОРОНЕНО використовувати заголовки ВСІМА ВЕЛИКИМИ ЛІТЕРАМИ (капслок заборонено).
- Жодних таблиць (символів "|") та жодної псевдографіки/стрілок.
- Жодних заголовків Markdown (#, ##, ###).
- Жодних подвійних зірочок (**) чи нижніх підкреслень (_).
- Марковані списки позначай виключно через звичайний дефіс з пробілом ("- ").
- Жодних емодзі.

СТРУКТУРА ПОВІДОМЛЕННЯ:

Дайджест зовнішньої політики США | {current_date}
(1-2 лаконічних речення: ключовий геостратегічний фокус доби у діях Вашингтона)

Міжнародна політика, дипломатія та альянси
- [Суть події у 2-4 реченнях: саміти, переговори, дипломатичний тиск, регіональна безпека, позиція союзників. Вкажи джерело].
- [Наступна подія через дефіс].
(Якщо значущих подій немає: - За останню добу немає підтверджених подій у цій категорії.)

Геоекономіка, санкції та внутрішні рішення
- [Суть події у 2-4 реченнях: рішення Конгресу, торговельні тарифи, санкції, оборонне фінансування партнерів, технологічні обмеження. Вкажи джерело].
- [Наступна подія через дефіс].
(Якщо значущих подій немає: - За останню добу немає підтверджених подій у цій категорії.)

Аналітичний висновок
(Один цілісний абзац на 3-4 речення: як зафіксовані політичні й економічні маневри доби змінюють стратегічні позиції США на глобальній арені.)
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
                "content": f"Ось фактичні стрічки новин за останню добу. Зроби аналіз відповідно до інструкцій:\n\n{news_input}"
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
