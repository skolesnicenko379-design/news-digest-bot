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
        return urlunsplit((parts.scheme.lower(), parts.netloc.lower(), parts.path.rstrip("/"), parts.query, ""))
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
        tools = [{
            "type": "web_search_20250305",
            "name": "web_search",
            "max_uses": 8,
            # Block known Russian state propaganda; do not restrict the search to a fixed list of publishers.
            "blocked_domains": [
                "rt.com", "sputniknews.com", "tass.com", "ria.ru",
                "lenta.ru", "news-front.su", "southfront.org"
            ]
        }]

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

    system_prompt = f"""Ти — головний редактор міжнародного щоденного аналітичного дайджесту для Telegram.
Поточний час: {now_label}, часовий пояс Europe/Kyiv. Часове вікно новин: від {since_label} до {now_label}.

ТВОЄ ЗАВДАННЯ
Самостійно знайди актуальні новини у відкритому вебі за останні 24 години, прочитай доступні сторінки, звір факти й сформуй готовий дайджест. Не чекай на наданий список матеріалів: його не буде. Не спирайся на RSS-заголовки або пам'ять моделі замість актуального пошуку. Не обмежуйся конкретним переліком сайтів чи видань: знаходь першоджерела, надійні міжнародні медіа, регіональні видання та офіційні документи залежно від події.

ПОШУК
Зроби кілька окремих пошукових запитів, не витрачай усі на одну тему. Охопи міжнародні відносини та рішення урядів; США й Америки; Європу та НАТО; Китай, Східну й Південну Азію; Близький Схід; Африку; світову макроекономіку, фінанси, торгівлю, енергетику й технологічні ланцюги постачання. Порівнюй результати між регіонами й темами. Це напрями пошуку, а не квоти на публікацію. Шукати потрібно події, оприлюднені протягом зазначеного часового вікна; старі події включай лише за наявності нового важливого розвитку саме в цей період.

ВЕРИФІКАЦІЯ
1. Для кожної потенційної новини встанови точну подію, дату, учасників і статус рішення. Не плутай заяву, пропозицію, проєкт, підписання, набрання чинності та фактичне виконання.
2. Перевіряй ключове твердження щонайменше за двома незалежними джерелами, коли вони доступні. Заяви, передруки, синдиковані тексти та публікації, що спираються на того самого анонімного співрозмовника, не є незалежним підтвердженням.
3. Де можливо, перевіряй офіційні документи, заяви або первинні дані, але не вважай офіційне звинувачення доказом самого звинувачення. Відокремлюй встановлений факт від позиції сторони.
4. Якщо подію повідомляє лише одне джерело, або чітко атрибутуй інформацію та познач брак незалежного підтвердження, або відкинь її, якщо ризик помилки високий. Не вигадуй підтвердження, дати, цифри, цитати, причини чи наслідки.
5. Дивись на дату самої публікації та дату події. Не подавай стару новину як нову. Відкидай результати з неправильною датою, неіснуючою сторінкою, агрегатором замість первинного матеріалу або заголовком, що не відповідає змісту.
6. Не використовуй російські державні пропагандистські майданчики як підтвердження. Якщо надійні джерела суперечать одне одному, передай суперечність або пропусти новину.
7. Усі фактичні твердження в дайджесті мають спиратися на матеріали, які ти реально знайшов у вебпошуку. Не вигадуй адреси сторінок. У кінці кожної новини постав клікабельні посилання на конкретні знайдені матеріали. Використовуй тільки точні URL, що були повернуті вебпошуком, у форматі [Reuters](точний_URL). Назва медіа має відповідати конкретній сторінці.

РЕДАКЦІЙНІ ПРІОРИТЕТИ
Висвітлюй геополітику й міжнародні відносини, безпеку й оборонну політику, дипломатію, макроекономіку, фінанси та ринки, торгівлю, санкції, енергетику й технології, якщо вони мають конкретний міжнародний вплив. Не допускай перекосу на користь США або будь-якого іншого регіону: оцінюй події за наслідками, незалежно від географії. Не публікуй незначні заяви, церемоніальні візити, рутинні зустрічі, прогнози без доказів і другорядні новини лише для заповнення місця. Пояснюй механізм впливу, а не додавай загальні формули про «напруженість» чи «зміну балансу сил».

ФОРМАТ
🌐 МІЖНАРОДНИЙ ДАЙДЖЕСТ | {current_date}

🔴 ГОЛОВНЕ
До 5 найважливіших подій. На кожну: короткий конкретний заголовок жирним, 1–3 змістовні речення про те, що сталося, чому це важливо та який механізм впливу підтверджений матеріалами. Наприкінці кожної новини 1–2 посилання на джерела. Якщо гідних подій менше, публікуй менше, але не вигадуй наповнення.

📌 СТРАТЕГІЧНІ СИГНАЛИ
Окремо подай 1–3 сигнали, які випливають із сукупності перевірених подій дня: перерозподіл ресурсів, зміна переговорних позицій, торговельні або фінансові залежності, координація держав, нові обмеження чи можливості. Це аналітичний висновок, а не додаткова новина. Не повторюй переказ подій, не спекулюй і чітко відділяй висновок від встановлених фактів. За відсутності достатніх підстав не додавай цей блок.

СТИЛЬ
Українська мова, щільний професійний виклад, конкретні факти, дати й числа лише за наявності джерела. Жодних довгих вступів, фінального підсумку, таблиць, риторичних запитань чи фраз про процес роботи. Не пиши, що «наданих матеріалів недостатньо», що немає тексту статей або що дайджест вийде пізніше: це не замінює пошуку. Не додавай новину, лише щоб виконати кількісний план. Максимум 3300 символів. Поверни тільки готовий дайджест для Telegram, без пояснень поза ним."""

    user_content = (
        "Проведи вебпошук і перевірку, а потім підготуй дайджест за вказаними правилами. "
        "Самостійно знаходь джерела, відбирай найважливіші події, перевіряй дату та факти, "
        "звіряй незалежні повідомлення й став точні клікабельні посилання. "
        "Не використовуй наперед задані RSS-стрічки або перелік видань."
    )

    print("Шукаємо та звіряємо міжнародні події у вебі через Anthropic Web Search...")
    output, sources = _call_anthropic(system_prompt, user_content, max_tokens=2800, use_web_search=True)
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

    if len(output) > 3500:
        shorter_prompt = (
            system_prompt
            + "\n\nСКОРОЧЕННЯ: скороти готовий дайджест до 3300 символів, зберігши найважливіші факти, "
              "атрибуцію та чинні посилання. Не додавай і не змінюй URL та не вигадуй інформації."
        )
        shorter_input = (
            user_content
            + "\n\nДозволені точні URL джерел:\n"
            + source_list
            + "\n\nСкороти цей дайджест:\n"
            + output
        )
        output, _ = _call_anthropic(shorter_prompt, shorter_input, max_tokens=2200, use_web_search=False)
        _validate_digest_urls(output, allowed_urls)

    if len(output) > 3500:
        raise RuntimeError(
            f"Дайджест після скорочення має {len(output)} символів, ліміт — 3500. Публікацію скасовано."
        )
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
