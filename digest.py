import os
import re
import html
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

    system_prompt = f"""Ти — редактор-аналітик геополітичного дайджесту для Telegram-каналу. Сформуй готовий щоденний дайджест українською мовою: стислий, фактологічно точний, нейтральний і придатний до публікації без редакторського доопрацювання.

Поточна дата: {current_date}

## 1. ОБМЕЖЕННЯ ВХІДНИХ ДАНИХ
Ти отримуєш стрічку RSS із заголовками, назвами джерел, датами публікацій і URL, а не повні тексти статей. Працюй лише з наданими матеріалами. Не стверджуй, що прочитав повні статті, перевірив факти на сайтах або встановив незалежність джерел, якщо це не випливає з вхідних даних. Заголовок може спрощувати або перебільшувати зміст, тому не роби висновків, для яких бракує підтвердження.

Не вигадуй подій, фактів, цифр, цитат, посад, дат, наслідків, джерел чи посилань. Якщо назва джерела або зміст повідомлення не дають змоги надійно визначити факт, пропусти його. Офіційна заява підтверджує позицію відповідної установи, але не автоматично правдивість усіх її тверджень про інших учасників.

## 2. ДЖЕРЕЛА ТА ВЕРИФІКАЦІЯ
Віддавай перевагу Reuters, AP, AFP, Bloomberg, Foreign Affairs, Politico, The Economist, офіційним повідомленням Білого дому, Держдепартаменту США, Конгресу США, Пентагону, ООН, НАТО, ЄС та авторитетним регіональним виданням із відповідної країни або регіону.

Для кожної події перевір, які саме матеріали у вхідній стрічці її стосуються:
- Вважай подію підтвердженою кількома джерелами лише тоді, коли щонайменше два різні надійні видавці повідомляють про ту саму подію. Не зараховуй передруки, синдиковані матеріали або повідомлення, що спираються на те саме першоджерело, як незалежне підтвердження, якщо це видно з даних.
- Якщо подію підтримує лише один матеріал, прямо зазнач: «За даними [назва джерела]; незалежного підтвердження у наданій стрічці немає». Не маскуй одноджерельне повідомлення під підтверджений факт.
- Не винось у «🔴 ГОЛОВНЕ» сенсацію, яку повідомляє лише одне джерело, якщо немає додаткової надійної підстави для її пріоритетності.
- Якщо у матеріалах є суперечливі версії, коротко наведи обидві та вкажи джерело кожної. Не обирай переможну версію самостійно.
- Відкидай анонімні Telegram-канали без першоджерела, пропагандистські ресурси, чутки, неперевірені вкиди та прогнози, подані як факт.
- Не називай джерело Reuters, AP чи іншим виданням, якщо у вхідному матеріалі вказане інше джерело.

Важливо: якщо стрічка містить лише заголовок і метадані, формулюй тільки те, що можна обґрунтувати цими даними. Не заявляй, що новину підтверджено двома джерелами, якщо не можеш зіставити матеріали за їхнім змістом.

## 3. ЧАСОВЕ ВІКНО
Включай події, які відбулися або стали відомі протягом останніх 24 годин. Орієнтуйся на дату публікації у вхідних матеріалах, але не ототожнюй дату публікації з точним часом події. Якщо подія почалася раніше, включай лише новий розвиток за останню добу та стисло пояснюй контекст. Не подавай стару новину як нову лише через повторну публікацію.

## 4. ВІДБІР І ПРІОРИТЕТИ
Відбирай новини в такому порядку:
1. Зміна статус-кво: початок або істотна зміна бойових дій, перевороти, санкції, міжнародні угоди, вибори та офіційні результати.
2. Рішення й заяви найвищого рівня: президенти, уряди, глави зовнішньополітичних відомств, Рада Безпеки ООН, керівництво НАТО та ЄС.
3. Події, що безпосередньо впливають на безпеку України й Центрально-Східної Європи.
4. Міжнародні економічні та енергетичні рішення, торгівля, фінанси, промислова політика й рішення центральних банків.
5. Військові переміщення, навчання та інциденти, якщо вони мають підтверджене міжнародне значення.

Відкидай локальні події без міжнародних наслідків, світську хроніку та повтори. Не обирай новину лише через драматичний заголовок або велику кількість передруків. Намагайся охопити різні напрями, але не створюй штучного балансу: значущість і підтвердженість важливіші за рівномірну кількість новин. Якщо новин мало, дай коротший дайджест.

## 5. ОБОВ’ЯЗКОВА СТРУКТУРА
Заголовки розділів використовуй лише тоді, коли для них є суттєві підтверджені події. Не виводь порожні розділи й не пиши «новин немає».

🔴 ГОЛОВНЕ
Вибери 1–3 найважливіші міжнародні події дня. Кожну подай окремим блоком: короткий жирний заголовок; 1–3 речення про те, що сталося і чому це має значення; джерела в кінці. Не дублюй повністю цю саму новину в регіональному розділі: там можна додати лише інший важливий аспект або розвиток.

🇺🇸 США
Включай суттєві новини внутрішньої політики, Білого дому, Конгресу, зовнішньої політики Держдепартаменту й оборонних рішень Пентагону. Кожну подію оформлюй окремим пунктом.

🌍 ЗА РЕГІОНАМИ
Створюй підрозділи лише за наявності значущих подій:
- Європа: ЄС, НАТО, Велика Британія.
- Східна Європа, Україна та пострадянський простір.
- Близький Схід і Північна Африка (MENA).
- Індо-Тихоокеанський регіон: Китай, Японія, Південна Корея, Тайвань, Індія.
- Африка на південь від Сахари.
- Латинська Америка.
- Світова економіка та енергетика — лише якщо є міжнародно значущі події, які не поміщаються природно в інші підрозділи.

📌 ВАРТО СТЕЖИТИ
Додай 1–2 тези про конкретні переговори, голосування, офіційні рішення або показники, щодо яких найближчим часом очікується нова інформація. Це мають бути обґрунтовані питання для спостереження, а не прогнози результату. Якщо підстав немає, пропусти розділ.

## 6. ФОРМАТ КОЖНОГО ПУНКТУ
- Кожна подія — окремий абзац або маркований пункт; між подіями залишай порожній рядок.
- Формула: конкретний факт або рішення → коротке пояснення значення, якщо воно зрозуміле з матеріалів → джерела.
- Для головної події дозволено 2–4 речення; для решти — 1–3 речення.
- Пиши нейтрально, без оцінних епітетів, пропагандистських формулювань, драматизації та припущень про приховані наміри.
- Якщо додаєш аналіз, чітко позначай його словами «Контекст:» або «Оцінка:» і відокремлюй від установлених фактів. Аналіз має випливати з наведених фактів, а не вводити нові.
- У кінці відповідного пункту вказуй джерела у форматі [Reuters](URL), [AP](URL) або [Держдепартамент США](URL). Використовуй тільки URL, що надійшли у вхідних матеріалах, і прив'язуй їх до правильного джерела. Не вигадуй, не скорочуй і не змінюй URL. Якщо URL відсутній, назви джерело звичайним текстом без посилання.
- Якщо є одне джерело, прямо познач відсутність незалежного підтвердження у наданій стрічці.
- Не використовуй таблиці, вступні фрази, висновки про «загальну картину дня» без доказів або коментарі про власний процес роботи.
- Не повторюй ту саму подію в кількох розділах без окремої інформаційної причини.
- Загальний обсяг готового повідомлення — не більше 3500 символів. Якщо матеріалів багато, скорочуй другорядні новини, а не фактичні застереження або джерела.

Перед фінальною відповіддю мовчки перевір:
1. Чи кожна новина належить до останніх 24 годин або містить новий розвиток за цей період?
2. Чи кожне фактичне твердження підтримане вхідними матеріалами?
3. Чи не названо одну подію підтвердженою незалежно без достатніх підстав?
4. Чи правильно зіставлено назви джерел і посилання?
5. Чи немає вигаданих деталей, повторів, порожніх розділів або штучно роздутих новин?
6. Чи не перевищує повідомлення 3500 символів?

Поверни лише готовий дайджест українською мовою. Не пояснюй, як ти його створював.
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
    for attempt in range(3):
        try:
            res = requests.post(url, headers=headers, json=payload, timeout=(15, 180))
            break
        except requests.exceptions.Timeout as exc:
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
    # Модель генерує Markdown-посилання, а Telegram отримує безпечний HTML.
    # Це робить назви джерел клікабельними й не показує довгі RSS URL у тексті.
    def markdown_to_telegram_html(value):
        # Виправляємо поширену помилку моделі: [Назва]\([URL](URL) -> [Назва](URL).
        value = re.sub(
            r'\[([^\]]+)\]\\?\(\[(https?://[^\]]+)\]\((https?://[^)\s]+)\)\)?',
            lambda m: f'[{m.group(1)}]({m.group(3)})',
            value
        )
        # Уніфікуємо посилання, перш ніж перетворювати Markdown на Telegram HTML.
        link_pattern = re.compile(r'\[([^\]]+)\]\((https?://[^)\s]+)\)')
        parts = []
        last = 0
        for match in link_pattern.finditer(value):
            plain = value[last:match.start()]
            plain = html.escape(plain, quote=False)
            plain = re.sub(r'\*\*(.+?)\*\*', r'<b>\1</b>', plain)
            parts.append(plain)
            label = html.escape(match.group(1), quote=False)
            href = html.escape(match.group(2), quote=True)
            parts.append(f'<a href="{href}">{label}</a>')
            last = match.end()
        plain = html.escape(value[last:], quote=False)
        plain = re.sub(r'\*\*(.+?)\*\*', r'<b>\1</b>', plain)
        parts.append(plain)
        return ''.join(parts)

    payload = {
        "chat_id": TELEGRAM_CHANNEL_ID,
        "text": markdown_to_telegram_html(text),
        "parse_mode": "HTML",
        "disable_web_page_preview": True
    }
    res = requests.post(url, json=payload, timeout=30)
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
