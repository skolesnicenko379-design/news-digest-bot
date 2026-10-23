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

    system_prompt = f"""Ти формуєш короткий новинний дайджест українською мовою для Telegram. Це агрегатор головних новин, а не аналітичний огляд.
Поточний час: {now_label}, часовий пояс Europe/Kyiv. Бери новини, опубліковані або суттєво оновлені за останні 24 години: від {since_label} до {now_label}.

ПОШУК І ВІДБІР
Знайди головні заголовки у Reuters, Associated Press (AP), AFP, Bloomberg, Financial Times, BBC та інших надійних медіа. Починай із цих видань, але не обмежуйся ними. Пріоритет: політика США, міжнародні відносини й безпека, макроекономіка, фінанси та ринки; включай інші світові новини, якщо вони справді серед найважливіших за день. Вибери 5–7 найважливіших окремих новин, якщо є достатньо якісних матеріалів. Не дублюй ту саму подію, навіть якщо про неї пишуть кілька медіа. Кілька сайтів, які передрукували повідомлення одного агентства, не є незалежними джерелами.

ФАКТИ І ПОСИЛАННЯ
Не вигадуй заголовки, факти, дати, цифри чи посилання. Перевіряй, що сторінка справді існує, її дата відповідає часовому вікну, а заголовок відповідає змісту. Для важливих або спірних тверджень за можливості звіряй друге незалежне джерело чи офіційний документ. Чітко відрізняй заяву, план, пропозицію, ухвалене рішення та рішення, що вже набрало чинності. Якщо новина спирається лише на одне джерело, атрибутуй її цьому джерелу; якщо надійність сумнівна — не включай. Не використовуй російські державні пропагандистські сайти як підтвердження. Для кожної новини додай пряме посилання на конкретну знайдену сторінку у форматі [Reuters](точний_URL). Використовуй тільки URL, повернуті вебпошуком.

ФОРМАТ
🇺🇸 ГОЛОВНІ НОВИНИ | {current_date}

До 5–7 пунктів. Кожен пункт: **короткий заголовок новини** — одне коротке речення, що передає основний факт, із посиланням на першоджерело або медіа. За потреби додай друге джерело. Не переписуй новину в кілька абзаців, не додавай власних висновків, прогнозів, пояснень «чому це важливо», геополітичного контексту чи аналітики. Можна стисло перефразувати заголовок, щоб він був зрозумілим українською, але не змінюй сенс. Не копіюй довгі фрагменти статей дослівно.

СТИЛЬ І ОБСЯГ
Українська мова. Лаконічно, нейтрально, без вступу, підсумку, календаря майбутніх подій, таблиць і повторів. Орієнтир — 100–220 символів на новину разом із посиланням. Увесь дайджест має бути приблизно 1200–2000 символів, максимум 2200. Якщо важливих підтверджених новин менше, публікуй менше. Поверни лише готовий дайджест для Telegram.""" 

    user_content = (
        "Знайди головні новини за останні 24 години у провідних медіа. Почни з Reuters, AP, AFP, Bloomberg, Financial Times і BBC; розшир пошук, щоб не пропустити важливі сюжети. "
        "Вибери 5–7 окремих найважливіших подій, прибери дублікати, коротко передай факти українською і додай прямі клікабельні посилання на знайдені матеріали. "
        "Не додавай аналітику, прогнози, календар майбутніх подій чи власні висновки. Не використовуй наперед задані RSS-стрічки."
    )

    print("Шукаємо та звіряємо міжнародні події у вебі через Anthropic Web Search...")
    output, sources = _call_anthropic(system_prompt, user_content, max_tokens=2200, use_web_search=True)
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

    # No second editorial-generation call: keep the digest short and reduce token usage.
    if len(output) > 2200:
        shorter_prompt = (
            "Скороти цей український новинний дайджест до 2000 символів максимум. "
            "Залиш лише найважливіші окремі новини, по одному короткому реченню на пункт. "
            "Прибери аналітику, повтори та другорядні деталі. Збережи факти й точні URL без змін. "
            "Не додавай нових фактів. Поверни тільки текст."
        )
        shorter_input = (
            "ДОЗВОЛЕНІ ТОЧНІ URL (використовуй тільки їх):\\n"
            + source_list
            + "\\n\\nТекст для скорочення:\\n"
            + output
        )
        output, _ = _call_anthropic(shorter_prompt, shorter_input, max_tokens=1400, use_web_search=False)
        _validate_digest_urls(output, allowed_urls)

    if len(output) > 2200:
        raise RuntimeError(
            f"Дайджест після скорочення має {len(output)} символів, ліміт — 2200. Публікацію скасовано."
        )
    if not output:
        raise RuntimeError("Anthropic API повернув порожній дайджест.")
    return output


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
    print(f"Генеруємо короткий новинний дайджест (модель: {ANTHROPIC_MODEL})...")
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
