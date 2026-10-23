import os
import re
import html
import json
import time
import requests
from datetime import datetime
from urllib.parse import urlsplit, urlunsplit
from zoneinfo import ZoneInfo

ANTHROPIC_API_KEY = (os.environ.get("ANTHROPIC_API_KEY") or "").strip().replace("\r", "").replace("\n", "")
TELEGRAM_BOT_TOKEN = (os.environ.get("TELEGRAM_BOT_TOKEN") or "").strip().replace("\r", "").replace("\n", "")
TELEGRAM_CHANNEL_ID = (os.environ.get("TELEGRAM_CHANNEL_ID") or "").strip().replace("\r", "").replace("\n", "")
DRY_RUN = (os.environ.get("DRY_RUN") or "").strip().casefold() in {"1", "true", "yes", "on"}
ANTHROPIC_MODEL = (os.environ.get("ANTHROPIC_MODEL") or "claude-sonnet-4-5-20250929").strip()
WORKSPACE_ID = (os.environ.get("WORKSPACE_ID") or "").strip()


def _host(url):
    try:
        return (urlsplit(url).hostname or "").lower().removeprefix("www.")
    except Exception:
        return ""


def _normalize_url(url):
    """Normalize a URL for exact source-link validation without changing its destination."""
    try:
        parts = urlsplit(url.strip())
        if parts.scheme not in {"http", "https"} or not parts.netloc:
            return ""
        netloc = parts.netloc.lower()
        if netloc.startswith("www."):
            netloc = netloc[4:]
        return urlunsplit((parts.scheme.lower(), netloc, parts.path.rstrip("/"), parts.query, ""))
    except (TypeError, ValueError):
        return ""


def _extract_search_sources(content_blocks):
    """Collect only URLs actually returned by Anthropic's web-search results/citations."""
    sources = {}
    for block in content_blocks or []:
        if not isinstance(block, dict):
            continue

        candidates = []
        if block.get("type") == "web_search_tool_result":
            result_content = block.get("content")
            if isinstance(result_content, list):
                candidates.extend(result_content)

        if block.get("type") == "web_fetch_tool_result":
            result_content = block.get("content")
            if isinstance(result_content, dict) and result_content.get("type") == "web_fetch_result":
                candidates.append({
                    "url": result_content.get("url", ""),
                    "title": (result_content.get("content") or {}).get("title", "")
                })

        if block.get("type") == "text":
            citations = block.get("citations") or []
            if isinstance(citations, list):
                candidates.extend(citations)

        for item in candidates:
            if not isinstance(item, dict):
                continue
            url = item.get("url", "")
            title = item.get("title", "")
            normalized = _normalize_url(url)
            if normalized and _host(normalized) and title:
                sources[normalized] = title.strip()
    return sources


def _call_anthropic(system_prompt, user_content, max_tokens=2600, use_web_search=True):
    """Ask Claude to research the web itself, then collect the source URLs returned by the search tool."""
    if not ANTHROPIC_API_KEY:
        raise RuntimeError("Відсутній секрет ANTHROPIC_API_KEY.")

    headers = {
        "x-api-key": ANTHROPIC_API_KEY,
        "anthropic-version": "2023-06-01",
        "content-type": "application/json"
    }
    if WORKSPACE_ID:
        headers["anthropic-workspace-id"] = WORKSPACE_ID

    tools = []
    if use_web_search:
        blocked_domains = [
            "rt.com", "sputniknews.com", "tass.com", "ria.ru",
            "lenta.ru", "news-front.su", "southfront.org"
        ]
        tools = [
            {
                "type": "web_search_20250305",
                "name": "web_search",
                "max_uses": 12,
                # Do not restrict discovery to a fixed list of publishers.
                "blocked_domains": blocked_domains
            },
            {
                "type": "web_fetch_20250910",
                "name": "web_fetch",
                "max_uses": 12,
                "max_content_tokens": 16000,
                "citations": {"enabled": True},
                "blocked_domains": blocked_domains
            }
        ]

    messages = [{"role": "user", "content": user_content}]
    found_sources = {}
    final_text = ""
    last_stop_reason = None

    # Handle Anthropic's pause_turn continuation while preserving encrypted search-result blocks unchanged.
    for _turn in range(4):
        payload = {
            "model": ANTHROPIC_MODEL,
            "max_tokens": max_tokens,
            "system": system_prompt,
            "messages": messages
        }
        if tools:
            payload["tools"] = tools

        response = None
        for attempt in range(3):
            try:
                response = requests.post(
                    "https://api.anthropic.com/v1/messages",
                    headers=headers,
                    json=payload,
                    timeout=(15, 240)
                )
                break
            except requests.exceptions.Timeout as exc:
                if attempt == 2:
                    raise RuntimeError(
                        "Anthropic API не повернув відповідь за 240 секунд після трьох спроб."
                    ) from exc
                wait_seconds = 5 * (attempt + 1)
                print(f"Тайм-аут Anthropic API (спроба {attempt + 1}/3). Повтор через {wait_seconds} с...")
                time.sleep(wait_seconds)

        if response is None:
            raise RuntimeError("Anthropic API не повернув HTTP-відповідь.")
        if response.status_code != 200:
            raise RuntimeError(f"Помилка Anthropic API ({response.status_code}): {response.text[:1600]}")

        data = response.json()
        blocks = data.get("content", [])
        found_sources.update(_extract_search_sources(blocks))
        final_text = "\n".join(
            block.get("text", "")
            for block in blocks
            if isinstance(block, dict) and block.get("type") == "text" and block.get("text")
        ).strip()
        last_stop_reason = data.get("stop_reason")

        if last_stop_reason == "pause_turn":
            messages.append({"role": "assistant", "content": blocks})
            continue
        break

    if last_stop_reason == "pause_turn":
        raise RuntimeError("Вебпошук Anthropic не завершив дослідження за відведену кількість продовжень.")
    if last_stop_reason == "max_tokens":
        raise RuntimeError("Claude обрізав відповідь за лімітом токенів; дайджест не опубліковано.")
    if not final_text:
        raise RuntimeError("Anthropic API повернув порожню відповідь.")
    return final_text, found_sources


def _validate_digest_urls(digest, allowed_urls):
    allowed = {_normalize_url(url) for url in allowed_urls if _normalize_url(url)}
    links = [url.rstrip(".,;") for url in re.findall(r"https?://[^\s)\]>]+", digest)]
    if not links:
        raise RuntimeError("У дайджесті немає посилань на джерела, отримані вебпошуком.")

    invalid = [url for url in links if _normalize_url(url) not in allowed]
    if invalid:
        raise RuntimeError(
            "У дайджесті є URL, яких не було серед результатів вебпошуку; публікацію скасовано: "
            + ", ".join(invalid[:3])
        )


def generate_digest():
    now = datetime.now(ZoneInfo("Europe/Kyiv"))
    current_date = now.strftime("%d.%m.%Y")
    since_time = (now.timestamp() - 24 * 60 * 60)
    since_label = datetime.fromtimestamp(since_time, ZoneInfo("Europe/Kyiv")).strftime("%d.%m.%Y %H:%M")
    now_label = now.strftime("%d.%m.%Y %H:%M")

    system_prompt = f"""Ти — головний редактор щоденного дайджесту про політику США та міжнародні події, що мають значення для Сполучених Штатів, для Telegram. США — головний фокус і редакційний центр ваги. Це не універсальний світовий дайджест із рівним представленням усіх регіонів.
Поточний час: {now_label}, часовий пояс Europe/Kyiv. Часове вікно новин: від {since_label} до {now_label}.

ТВОЄ ЗАВДАННЯ
Самостійно проведи повноцінний огляд новин за останні 24 години, а не зупиняйся на перших кількох результатах. Зроби окремі пошукові проходи за п'ятьма напрямами: (1) Білий дім, Конгрес і федеральні інституції США; (2) зовнішня політика, оборона та безпека США; (3) економіка США, ФРС, ринки, торгівля й тарифи; (4) Китай, Європа, Близький Схід та інші міжнародні події з прямими наслідками для США; (5) календар важливих майбутніх зустрічей і рішень. Переглянь широкий пул кандидатів, орієнтовно 15–25 подій, і лише потім обери найважливіші для публікації. Спочатку склади внутрішній рейтинг кожної події за п'ятьма критеріями: масштаб наслідків, новизна, безпосередній зв'язок зі США, підтвердженість і значення для найближчих днів. Віддавай перевагу рішенням і реальним змінам, а не заявам про наміри, реакціям на старі події чи спекуляціям. Відкрий і прочитай сторінки ключових матеріалів за допомогою web fetch. Для важливих подій перевіряй як мінімум одну додаткову незалежну публікацію або первинний документ. Не прирівнюй велику кількість знайдених URL до кількості окремих подій: зводь дублікати про ту саму подію. Не чекай на наданий список матеріалів: його не буде. Не спирайся на RSS-заголовки або пам'ять моделі замість актуального пошуку. Не обмежуйся конкретним переліком сайтів чи видань: знаходь першоджерела, надійні міжнародні медіа, регіональні видання та офіційні документи залежно від події.

ПОШУК
Розподіли пошук за пріоритетом. Найперше шукай рішення та події у США: Білий дім і адміністрація Президента, Конгрес, Державний департамент, Пентагон, Мінфін, ФРС, федеральні суди, санкційна й торговельна політика, відносини з союзниками та конкурентами. Далі шукай міжнародні події, які змінюють розрахунки Вашингтона або мають прямі наслідки для американської безпеки, союзів, торгівлі, енергетики, технологій і фінансових ринків. Охоплюй Китай, Європу й НАТО, Росію, Близький Схід, Індо-Тихоокеанський регіон та інші країни тоді, коли є конкретний зв'язок з інтересами США. Не відводь однакову вагу кожному регіону й не заповнюй випуск регіональними новинами без такого зв'язку. Шукати потрібно події, оприлюднені протягом зазначеного часового вікна; старі події включай лише за наявності нового важливого розвитку саме в цей період.

ОКРЕМИЙ ПОШУК МАЙБУТНІХ ПОДІЙ
Після новинного пошуку зроби окремі запити про календар на найближчі 7 днів, а для справді великих самітів або офіційно призначених зустрічей можна розширити горизонт до 14 днів. Шукай підтверджені дати самітів, міжнародних зустрічей, переговорів за участю Президента США, Держсекретаря, міністра оборони або фінансів, голосувань Конгресу, рішень ФРС, публікацій важливих економічних даних і дедлайнів торговельних чи санкційних домовленостей. Перевіряй дати за офіційними календарями або повідомленнями організаторів та учасників. Не вигадуй майбутні заходи, точні дати або участь посадовців на підставі припущень. Якщо календарних подій недостатньо, пропусти блок.

ВЕРИФІКАЦІЯ
1. Для кожної потенційної новини встанови точну подію, дату, учасників і статус рішення. Не плутай заяву, пропозицію, проєкт, підписання, набрання чинності та фактичне виконання.
2. Перевіряй ключове твердження щонайменше за двома незалежними джерелами, коли вони доступні. Заяви, передруки, синдиковані тексти та публікації, що спираються на того самого анонімного співрозмовника, не є незалежним підтвердженням.
3. Де можливо, перевіряй офіційні документи, заяви або первинні дані, але не вважай офіційне звинувачення доказом самого звинувачення. Відокремлюй встановлений факт від позиції сторони.
4. Якщо подію повідомляє лише одне джерело, або чітко атрибутуй інформацію та познач брак незалежного підтвердження, або відкинь її, якщо ризик помилки високий. Не вигадуй підтвердження, дати, цифри, цитати, причини чи наслідки.
5. Дивись на дату самої публікації та дату події. Не подавай стару новину як нову. Відкидай результати з неправильною датою, неіснуючою сторінкою, агрегатором замість первинного матеріалу або заголовком, що не відповідає змісту.
6. Не використовуй російські державні пропагандистські майданчики як підтвердження. Якщо надійні джерела суперечать одне одному, передай суперечність або пропусти новину.
7. Усі фактичні твердження в дайджесті мають спиратися на матеріали, які ти реально знайшов у вебпошуку. Не вигадуй адреси сторінок. У кінці кожної новини постав клікабельні посилання на конкретні знайдені матеріали. Використовуй тільки точні URL, що були повернуті вебпошуком, у форматі [Reuters](точний_URL). Назва медіа має відповідати конкретній сторінці.

РЕДАКЦІЙНІ ПРІОРИТЕТИ
Перший пріоритет — рішення й події всередині США, які визначають державну політику, внутрішню політичну боротьбу, бюджет, торгівлю, санкції, оборону, міграцію, судову практику та роботу федеральних інституцій. Другий — зовнішня політика США: відносини з союзниками й суперниками, переговори, безпекові зобов'язання, військові операції, експортний контроль, тарифи та економічний тиск. Третій — події за межами США, якщо вони змінюють стратегічні розрахунки Вашингтона або безпосередньо впливають на американські ціни, ринки, компанії, постачання чи союзницькі відносини. Не включай міжнародну новину лише тому, що вона масштабна; у тексті має бути зрозумілий і підтверджений зв'язок із США. Не публікуй незначні заяви, церемоніальні візити, рутинні зустрічі, прогнози без доказів і другорядні новини лише для заповнення місця. Водночас не зводь дайджест до 2–3 пунктів, якщо пошук виявив щонайменше чотири окремі, суттєві й перевірені події. За наявності матеріалу намагайся дати 4–5 найважливіших новин; менша кількість допустима лише тоді, коли інші кандидати не проходять редакційний або фактологічний відбір. Пояснюй конкретний механізм впливу, а не додавай загальні формули про «напруженість» чи «зміну балансу сил».

ФОРМАТ
🇺🇸 ДАЙДЖЕСТ США ТА СВІТУ | {current_date}

🔴 ГОЛОВНЕ
До 5 найважливіших подій, насамперед зі США та американської зовнішньої політики. Першою став найважливіший сюжет, який безпосередньо стосується американської державної політики або стратегічних інтересів США. На кожну подію: конкретний заголовок жирним і 2–3 лаконічні речення. Перше має точно повідомити, що сталося та хто ухвалив рішення або зробив заяву; друге — пояснити, чому це важливо й через який конкретний механізм впливає на США; третє додавати лише за потреби, щоб передати підтверджену цифру, контекст або наступний крок. Не підмінюй пояснення значення загальними фразами на кшталт «це може змінити баланс сил». Міжнародні сюжети без очевидного зв'язку зі США пропускай. Наприкінці кожної новини 1–2 посилання на джерела. Якщо гідних подій менше, публікуй менше, але не вигадуй наповнення.

📅 НАСТУПНІ ВАЖЛИВІ ПОДІЇ
Подай 2–4 підтверджені події, які відбудуться протягом найближчих 7 днів; для великих самітів або офіційно призначених переговорів допускається горизонт до 14 днів. Пріоритет — заходи за участю Президента США, членів адміністрації, Конгресу, ФРС, а також міжнародні саміти й зустрічі, де вирішуватимуть питання важливі для США. Для кожного пункту вкажи точну дату, подію та учасників, якщо вони підтверджені, і коротко поясни, яке рішення або результат варто відстежувати. Додай посилання на офіційний календар чи інше надійне джерело, що підтверджує дату. Не включай події з невизначеною датою, непідтверджений графік посадовців, загальні прогнози чи звичайні регулярні заходи без конкретного значення. Якщо менше двох подій відповідають цим умовам, покажи лише підтверджені або пропусти блок.

СТИЛЬ
Українська мова, щільний професійний виклад, конкретні факти, дати й числа лише за наявності джерела. Жодних довгих вступів, фінального підсумку, таблиць, риторичних запитань чи фраз про процес роботи. Не пиши, що «наданих матеріалів недостатньо», що немає тексту статей або що дайджест вийде пізніше: це не замінює пошуку. Не додавай новину, лише щоб виконати кількісний план. ЛІМІТ ДОВЖИНИ
Плануй фінальний текст на 2300–3000 символів, жорстка межа — 3300 символів разом із пробілами та посиланнями. Не намагайся штучно заповнити обсяг: якщо справді важливих підтверджених подій мало, краще коротший дайджест, ніж слабкі або вигадані новини. Це важливо для Telegram. На одну головну подію — заголовок і лише 1–2 короткі речення з фактами, без складного аналітичного розбору, абстрактних висновків і повторів. Орієнтир — 350–500 символів на сюжет разом із посиланнями. Календарний пункт — дата, подія й одне речення про те, що відстежувати. Не повторюй одну й ту саму подію в різних розділах. Якщо текст наближається до ліміту, скорочуй пояснення, а не факти, дати чи посилання. Поверни тільки готовий дайджест для Telegram, без пояснень поза ним."""

    user_content = (
        "Проведи вебпошук і перевірку, а потім підготуй дайджест про США та міжнародні події, важливі для американської політики. "
        "Спершу шукай рішення уряду США й Конгресу, зовнішню політику, економіку та безпеку США; потім — міжнародні події з прямими наслідками для Вашингтона. "
        "Окремо знайди найближчі офіційно підтверджені саміти, зустрічі, переговори, голосування й економічні рішення та перевір їхні дати. "
        "Самостійно знаходь джерела, перевіряй факти й використовуй точні клікабельні посилання. Не використовуй наперед задані RSS-стрічки."
    )

    print("Шукаємо та звіряємо міжнародні події у вебі через Anthropic Web Search...")
    output, sources = _call_anthropic(system_prompt, user_content, max_tokens=3400, use_web_search=True)
    distinct_hosts = {_host(url) for url in sources if _host(url)}
    print(f"Вебпошук повернув {len(sources)} сторінок із {len(distinct_hosts)} доменів.")

    # Do not publish an empty or search-tool-failure response as if it were a news digest.
    if len(sources) < 5 or len(distinct_hosts) < 3:
        raise RuntimeError(
            "Вебпошук повернув замало придатних джерел для міжнародного дайджесту. "
            "Публікацію скасовано; перевір доступність Web Search для API-ключа Anthropic."
        )

    allowed_urls = set(sources.keys())
    source_list = json.dumps(
        [{"title": title, "url": url} for url, title in sources.items()],
        ensure_ascii=False
    )
    try:
        _validate_digest_urls(output, allowed_urls)
    except RuntimeError:
        repair_prompt = (
            system_prompt
            + "\n\nТЕХНІЧНЕ ВИПРАВЛЕННЯ: перероби вже підготовлений дайджест, збережи факти й висновки, "
              "але кожне посилання має точно збігатися з одним URL у списку дозволених джерел. "
              "Не вигадуй і не змінюй URL. Не додавай нових фактів. До 3300 символів."
        )
        repair_input = (
            user_content
            + "\n\nВикористовуй тільки ці перевірені вебпошуком сторінки та точні URL:\n"
            + source_list
            + "\n\nПопередній варіант, який треба виправити:\n"
            + output
        )
        output, _ = _call_anthropic(repair_prompt, repair_input, max_tokens=2400, use_web_search=False)
        _validate_digest_urls(output, allowed_urls)

    if len(output) > 3300:
        shorter_prompt = (
            "Ти — редактор короткого українського Telegram-дайджесту про США та міжнародні події. "
            "Скороти поданий текст до 3000 символів максимум. Залиш лише найважливіші 3–5 новин і 1–3 "
            "підтверджені майбутні події. Кожна новина — жирний короткий заголовок і 1–2 прості речення "
            "з конкретними фактами. Прибери аналітичні міркування, загальні вступи, повтори та другорядні деталі. "
            "Збережи дати, атрибуцію, цифри та всі потрібні посилання. Не додавай нових фактів і не змінюй URL. "
            "Поверни тільки готовий текст."
        )
        shorter_input = (
            "ДОЗВОЛЕНІ ТОЧНІ URL (використовуй тільки їх):\n"
            + source_list
            + "\n\nТекст для скорочення:\n"
            + output
        )
        output, _ = _call_anthropic(shorter_prompt, shorter_input, max_tokens=2000, use_web_search=False)
        _validate_digest_urls(output, allowed_urls)

    if len(output) > 3300:
        # Last-resort deterministic trim: remove complete lower-priority entries, never cut a URL mid-link.
        sections = re.split(r"(?m)(?=^📅 НАСТУПНІ ВАЖЛИВІ ПОДІЇ\s*$|^🔴 ГОЛОВНЕ\s*$)", output)
        if len(sections) > 1:
            output = output[:]
            # Remove complete final news entries until under the Telegram-safe limit.
            while len(output) > 3300:
                lines = output.splitlines()
                # Candidate is the last bold-headline entry before the agenda, preserving the agenda header.
                agenda_index = next((i for i, line in enumerate(lines) if line.strip() == "📅 НАСТУПНІ ВАЖЛИВІ ПОДІЇ"), len(lines))
                candidates = [i for i in range(agenda_index) if lines[i].startswith("**") and lines[i].endswith("**")]
                if not candidates:
                    break
                remove_at = candidates[-1]
                remove_end = next((i for i in range(remove_at + 1, agenda_index) if lines[i].startswith("**") and lines[i].endswith("**")), agenda_index)
                del lines[remove_at:remove_end]
                output = "\n".join(lines).strip()
        if len(output) > 3300:
            raise RuntimeError(
                f"Дайджест після автоматичного скорочення має {len(output)} символів, ліміт — 3300. Публікацію скасовано."
            )
        _validate_digest_urls(output, allowed_urls)
    if not output:
        raise RuntimeError("Anthropic API повернув порожній дайджест.")
    return output


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
    if DRY_RUN:
        print("DRY_RUN активний: дайджест лише показано в журналах; у Telegram його не надіслано.")
    else:
        print("Відправляємо в Telegram...")
        send_to_telegram(output)
        print("Успішно надіслано в канал!")
