from __future__ import annotations

import base64
import logging
import os
import re
from datetime import datetime, timedelta, timezone
from urllib.parse import urljoin
from zoneinfo import ZoneInfo

import requests
from bs4 import BeautifulSoup

BASE_URL = os.getenv("WEKINGS_BASE_URL", "https://wekings.online").rstrip("/")
LOGIN_URL = os.getenv("WEKINGS_LOGIN_URL", f"{BASE_URL}/login")
API_URL = os.getenv("WEKINGS_FORGLORY_API", f"{BASE_URL}/heroes/for-glory")
TIMEOUT = (5, 30)
_cookie_loader = None
_cookie_saver = None
_pending_login = None
logger = logging.getLogger(__name__)


def configure_guest_cookie_storage(loader, saver):
    # Имя функции оставлено прежним, чтобы не ломать app.py и существующую БД.
    global _cookie_loader, _cookie_saver
    _cookie_loader, _cookie_saver = loader, saver


def _records(jar):
    return [{"name": c.name, "value": c.value, "domain": c.domain,
             "path": c.path or "/", "secure": bool(c.secure), "expires": c.expires}
            for c in jar]


def _restore(session):
    if not _cookie_loader:
        return
    for item in (_cookie_loader(BASE_URL) or []):
        opts = {"path": item.get("path") or "/", "secure": bool(item.get("secure")),
                "expires": item.get("expires")}
        if item.get("domain"):
            opts["domain"] = item["domain"]
        session.cookies.set(item["name"], item["value"], **opts)


def _save(session):
    if _cookie_saver:
        _cookie_saver(BASE_URL, _records(session.cookies))


def _session(saved=True):
    s = requests.Session()
    s.headers.update({
        "User-Agent": (
            "Mozilla/5.0 (Linux; Android 13; Mobile) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/139.0.0.0 Mobile Safari/537.36"
        ),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
        "Accept-Language": "ru-RU,ru;q=0.9,en;q=0.8",
        "Cache-Control": "no-cache",
    })
    if saved:
        _restore(s)
    return s


def _login_form(html, page_url):
    soup = BeautifulSoup(html, "html.parser")
    form = soup.find("form")
    if not form:
        raise RuntimeError("Форма входа WEKINGS не найдена")
    inputs = form.find_all("input")
    password = next((i for i in inputs if (i.get("type") or "").lower() == "password"), None)
    captcha = next((i for i in inputs if "капч" in ((i.get("placeholder") or "") + (i.get("name") or "")).lower()), None)
    text_inputs = [i for i in inputs if (i.get("type") or "text").lower() in {"text", "email", "tel"}]
    username = next((i for i in text_inputs if i is not captcha), None)
    if not password or not captcha or not username:
        raise RuntimeError("Не удалось определить поля логина, пароля и капчи")
    img = None
    for candidate in form.find_all("img") + soup.find_all("img"):
        src = candidate.get("src") or ""
        hint = (src + " " + (candidate.get("alt") or "") + " " + (candidate.get("id") or "")).lower()
        if "capt" in hint or "капч" in hint:
            img = candidate
            break
    if img is None:
        # На странице входа капча обычно единственная содержательная картинка рядом с формой.
        imgs = [i for i in form.find_all("img") if i.get("src")]
        img = imgs[-1] if imgs else None
    if img is None or not img.get("src"):
        raise RuntimeError("Картинка капчи WEKINGS не найдена")
    hidden = {i.get("name"): i.get("value", "") for i in inputs
              if i.get("name") and (i.get("type") or "").lower() == "hidden"}
    return {
        "action": urljoin(page_url, form.get("action") or page_url),
        "method": (form.get("method") or "post").lower(),
        "username": username.get("name"), "password": password.get("name"),
        "captcha": captcha.get("name"), "hidden": hidden,
        "captcha_url": urljoin(page_url, img.get("src")),
    }


def _extract_cookie_from_input(value):
    """Принимает либо Cookie, либо целиком Copy as cURL из Chrome DevTools."""
    raw = (value or "").strip()
    if not raw:
        return ""

    # Chrome/Chromium: -H 'cookie: ...' или --header "cookie: ..."
    if raw.lower().startswith("curl "):
        patterns = [
            r"(?:-H|--header)\s+'cookie:\s*([^']+)'",
            r'(?:-H|--header)\s+"cookie:\s*([^"]+)"',
            r"(?:-b|--cookie)\s+'([^']+)'",
            r'(?:-b|--cookie)\s+"([^"]+)"',
        ]
        for pattern in patterns:
            match = re.search(pattern, raw, flags=re.IGNORECASE | re.DOTALL)
            if match:
                return match.group(1).strip()
        raise RuntimeError("В cURL не найден заголовок Cookie. Скопируйте именно запрос for-glory через Copy as cURL.")

    if raw.lower().startswith("cookie:"):
        raw = raw.split(":", 1)[1].strip()
    return raw


def save_browser_cookie(cookie_header):
    """Сохраняет Cookie/cURL из уже авторизованного браузера и проверяет API."""
    raw = _extract_cookie_from_input(cookie_header)
    if not raw:
        raise RuntimeError("Вставьте Cookie или полный Copy as cURL запроса for-glory.")
    s = _session(saved=False)
    for part in raw.split(";"):
        if "=" not in part:
            continue
        name, value = part.strip().split("=", 1)
        if name:
            s.cookies.set(name, value, domain="wekings.online", path="/")
    r = s.get(API_URL, timeout=TIMEOUT, allow_redirects=True)
    if r.status_code in {401, 403} or "/login" in r.url or "/start" in r.url:
        raise RuntimeError(f"Эта сессия не дала доступ к API (HTTP {r.status_code}).")
    try:
        body = r.json()
    except ValueError as exc:
        raise RuntimeError("API не вернул JSON с этой сессией.") from exc
    rows = body.get("data") if isinstance(body, dict) else body
    if not isinstance(rows, list) or not rows:
        raise RuntimeError("API доступен, но список игроков пуст или имеет неожиданный формат.")
    _save(s)
    return len(rows)


def api_auth_status():
    s = _session(saved=True)
    try:
        r = s.get(API_URL, timeout=TIMEOUT, allow_redirects=True)
        if r.status_code in {401, 403} or "/login" in r.url or "/start" in r.url:
            return False
        body = r.json()
        rows = body.get("data") if isinstance(body, dict) else body
        return isinstance(rows, list) and bool(rows)
    except Exception:
        return False
    finally:
        s.close()



def begin_password_login():
    """Prepare WEKINGS login using credentials stored only in Render env vars."""
    global _pending_login
    username = os.getenv("WEKINGS_USERNAME", "").strip()
    password = os.getenv("WEKINGS_PASSWORD", "")
    if not username or not password:
        raise RuntimeError("На Render не заданы WEKINGS_USERNAME и WEKINGS_PASSWORD")
    s = _session(saved=False)
    r = s.get(LOGIN_URL, timeout=TIMEOUT, allow_redirects=True)
    r.raise_for_status()
    form = _login_form(r.text, r.url)
    img = s.get(form["captcha_url"], timeout=TIMEOUT)
    img.raise_for_status()
    mime = img.headers.get("Content-Type", "image/png").split(";", 1)[0]
    _pending_login = {"session": s, "form": form, "username": username, "password": password}
    return f"data:{mime};base64,{base64.b64encode(img.content).decode('ascii')}"


def finish_password_login(captcha_value):
    """Submit manually solved CAPTCHA; login/password never leave the server."""
    global _pending_login
    if not _pending_login:
        raise RuntimeError("Капча устарела. Нажмите «Получить новую капчу».")
    pending, _pending_login = _pending_login, None
    s = pending["session"]
    form = pending["form"]
    try:
        payload = dict(form["hidden"])
        payload[form["username"]] = pending["username"]
        payload[form["password"]] = pending["password"]
        payload[form["captcha"]] = (captcha_value or "").strip()
        if not payload[form["captcha"]]:
            raise RuntimeError("Введите код с картинки")
        if form["method"] == "get":
            r = s.get(form["action"], params=payload, timeout=TIMEOUT, allow_redirects=True)
        else:
            r = s.post(form["action"], data=payload, timeout=TIMEOUT, allow_redirects=True)
        r.raise_for_status()
        check = s.get(API_URL, timeout=TIMEOUT, allow_redirects=True)
        if check.status_code in {401, 403} or "/login" in check.url or "/start" in check.url:
            raise RuntimeError("Вход не выполнен. Проверьте капчу; при необходимости получите новую.")
        body = check.json()
        rows = body.get("data") if isinstance(body, dict) else body
        if not isinstance(rows, list) or not rows:
            raise RuntimeError("WEKINGS не подтвердил авторизацию")
        _save(s)
        return len(rows)
    finally:
        s.close()


def _int(v):
    try:
        return int(v) if v is not None and v != "" else None
    except (TypeError, ValueError):
        return None


def _org_name(value):
    if isinstance(value, dict):
        return value.get("name") or value.get("title") or value.get("nickname")
    return value if isinstance(value, str) else None


def _normalize(row):
    power = _int(row.get("strength"))
    defense = _int(row.get("defense")); agility = _int(row.get("agility"))
    mastery = _int(row.get("mastery")); vitality = _int(row.get("vitality"))
    vals = [power, defense, agility, mastery, vitality]
    return {
        "id": _int(row.get("id")), "nickname": str(row.get("nickname") or row.get("name") or "")[:160],
        "level": _int(row.get("level")), "glory": _int(row.get("glory")), "power": power,
        "defense": defense, "agility": agility, "mastery": mastery, "vitality": vitality,
        "stat_sum": sum(v for v in vals if v is not None) if any(v is not None for v in vals) else None,
        "wins": _int(row.get("wins")), "losses": _int(row.get("losses")),
        "dragon_wins": _int(row.get("dragon_wins") or row.get("dragons")),
        "serpent_wins": _int(row.get("serpent_wins") or row.get("serpents")),
        "beasts_killed": _int(row.get("beasts_killed")), "silver_stolen": _int(row.get("silver_looted") if row.get("silver_looted") is not None else row.get("silver_stolen")),
        "silver_lost": _int(row.get("silver_lost")), "crystals_stolen": _int(row.get("crystals_looted") if row.get("crystals_looted") is not None else row.get("crystals_stolen")),
        "crystals_lost": _int(row.get("crystals_lost")),

        # Дополнительная статистика из ForGlory API. Часть значений может
        # находиться внутри achievements, поэтому поддерживаем оба формата.
        "bandit_wins": _int(row.get("bandit_wins") if row.get("bandit_wins") is not None else (row.get("achievements") or {}).get("bandit_wins")),
        "mine": _int(row.get("mine") if row.get("mine") is not None else (row.get("achievements") or {}).get("mine")),
        "crusade": _int(row.get("crusade") if row.get("crusade") is not None else (row.get("achievements") or {}).get("crusade")),
        "quests": _int(row.get("quests") if row.get("quests") is not None else (row.get("achievements") or {}).get("quests")),
        "pet_fights": _int(row.get("pet_fights") if row.get("pet_fights") is not None else (row.get("achievements") or {}).get("pet_fights")),
        "pet_kills": _int(row.get("pet_kills") if row.get("pet_kills") is not None else (row.get("achievements") or {}).get("pet_kills")),
        "garden": _int(row.get("garden") if row.get("garden") is not None else (row.get("achievements") or {}).get("garden")),
        "goblins": _int(row.get("goblins") if row.get("goblins") is not None else (row.get("achievements") or {}).get("goblins")),
        "lord_wins": _int(row.get("lord_wins") if row.get("lord_wins") is not None else (row.get("achievements") or {}).get("lord_wins")),
        "undead_wins": _int(row.get("undead_wins") if row.get("undead_wins") is not None else (row.get("achievements") or {}).get("undead_wins")),
        "heroes_wins": _int(row.get("heroes_wins") if row.get("heroes_wins") is not None else (row.get("achievements") or {}).get("heroes_wins")),
        "serpent_fights": _int(row.get("serpent_fights") if row.get("serpent_fights") is not None else (row.get("achievements") or {}).get("serpent_fights")),
        "sent_gifts": _int(row.get("sent_gifts") if row.get("sent_gifts") is not None else (row.get("achievements") or {}).get("sent_gifts")),
        "fishing": _int(row.get("fishing") if row.get("fishing") is not None else (row.get("achievements") or {}).get("fishing")),
        "dragon_kills": _int(row.get("dragon_kills") if row.get("dragon_kills") is not None else (row.get("achievements") or {}).get("dragon_kills")),
        "serpent_kills": _int(row.get("serpent_kills") if row.get("serpent_kills") is not None else (row.get("achievements") or {}).get("serpent_kills")),
        "clan": _org_name(row.get("clan")),
        "brotherhood": _org_name(row.get("brotherhood")), "last_activity": row.get("last_activity"),
    }


def _fetch_all():
    s = _session(saved=True)
    r = s.get(API_URL, timeout=TIMEOUT, allow_redirects=True)
    if r.status_code in {401, 403} or "/login" in r.url:
        raise PermissionError("Нужна ручная авторизация WEKINGS: откройте /wekings-login")
    r.raise_for_status()
    try:
        body = r.json()
    except ValueError as exc:
        raise RuntimeError("ForGlory API не вернул JSON") from exc
    rows = body.get("data") if isinstance(body, dict) else body
    if not isinstance(rows, list):
        raise RuntimeError("В ответе API отсутствует список data")
    result = [_normalize(x) for x in rows if isinstance(x, dict)]
    result = [x for x in result if x["id"] and x["nickname"] and (x["level"] or 0) >= 5]
    if not result:
        raise RuntimeError("ForGlory API вернул пустой список игроков 5+ уровня")
    _save(s)
    return result


def scan_all_players(db, Player, PlayerSnapshot, ScanState, LowLevelPlayer):
    """Быстрый сбор через ForGlory API с короткими устойчивыми транзакциями."""
    import time

    state = db.session.get(ScanState, 1)
    batch_at = state.started_at or datetime.now(timezone.utc)
    rows = _fetch_all()
    max_id = max(x["id"] for x in rows)
    state.max_player_id = max_id
    state.current_player_id = max_id
    state.found_players = 0
    db.session.commit()

    snapshot_fields = [
        "nickname", "level", "glory", "power", "defense", "agility", "mastery", "vitality",
        "stat_sum", "wins", "losses", "dragon_wins", "serpent_wins", "beasts_killed",
        "silver_stolen", "silver_lost", "crystals_stolen", "crystals_lost",
        "bandit_wins", "mine", "crusade", "quests", "pet_fights", "pet_kills", "garden", "goblins",
        "lord_wins", "undead_wins", "heroes_wins", "serpent_fights", "sent_gifts", "fishing",
        "dragon_kills", "serpent_kills", "clan", "brotherhood",
    ]
    player_fields = snapshot_fields + ["last_activity"]
    now = datetime.now(timezone.utc)

    # Если предыдущая попытка оборвалась, частичный снимок этого запуска
    # удаляем и собираем заново. Исторические готовые отчёты не затрагиваются.
    PlayerSnapshot.query.filter_by(batch_at=batch_at).delete(synchronize_session=False)
    db.session.commit()

    # На Render/PostgreSQL длинная ORM-транзакция иногда обрывала соединение.
    # Поэтому пишем короткими пакетами и каждый пакет можем безопасно повторить.
    chunk_size = 100
    for offset in range(0, len(rows), chunk_size):
        chunk = rows[offset:offset + chunk_size]
        chunk_ids = [x["id"] for x in chunk]
        last_exc = None

        for attempt in range(1, 4):
            try:
                existing = {
                    p.id: p for p in Player.query.filter(Player.id.in_(chunk_ids)).all()
                }
                # При повторе пакета после разрыва удаляем только его снимки.
                PlayerSnapshot.query.filter(
                    PlayerSnapshot.batch_at == batch_at,
                    PlayerSnapshot.player_id.in_(chunk_ids),
                ).delete(synchronize_session=False)

                for data in chunk:
                    player = existing.get(data["id"])
                    if player is None:
                        player = Player(id=data["id"], nickname=data["nickname"], scanned_at=now)
                        db.session.add(player)
                    player.previous_glory = player.glory
                    player.previous_stat_sum = player.stat_sum
                    for field in player_fields:
                        if hasattr(player, field):
                            setattr(player, field, data.get(field))
                    player.scanned_at = now

                    snap = PlayerSnapshot(player_id=data["id"], batch_at=batch_at)
                    for field in snapshot_fields:
                        setattr(snap, field, data.get(field))
                    db.session.add(snap)

                state = db.session.get(ScanState, 1)
                done = min(offset + len(chunk), len(rows))
                state.found_players = done
                state.current_player_id = chunk[-1]["id"]
                db.session.commit()
                last_exc = None
                break
            except Exception as exc:
                last_exc = exc
                db.session.rollback()
                logger.exception(
                    "Scan DB chunk failed offset=%s attempt=%s ids=%s..%s error=%r",
                    offset, attempt, chunk_ids[0], chunk_ids[-1], exc,
                )
                try:
                    db.engine.dispose()
                except Exception:
                    pass
                if attempt < 3:
                    time.sleep(attempt * 2)

        if last_exc is not None:
            raise RuntimeError(
                f"Не удалось сохранить пакет игроков {chunk_ids[0]}..{chunk_ids[-1]} "
                f"после 3 попыток: {type(last_exc).__name__}: {last_exc}"
            ) from last_exc

    state = db.session.get(ScanState, 1)
    state.found_players = len(rows)
    state.current_player_id = 0
    db.session.commit()

def _link_by_text(html: str, label: str, base_url: str):
    soup = BeautifulSoup(html, "html.parser")
    wanted = label.casefold()
    link = next((a for a in soup.find_all("a", href=True)
                 if wanted in a.get_text(" ", strip=True).casefold()), None)
    return urljoin(base_url, link["href"]) if link else None


def _duration_near(text: str, labels):
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    for label in labels:
        line = next((x for x in lines if label.casefold() in x.casefold()), None)
        if not line:
            continue
        days = re.search(r"(\d+)\s*(?:дн(?:ей|я|ь)?|d)", line, re.I)
        hours = re.search(r"(\d+)\s*(?:час(?:а|ов)?|ч\.?|h)", line, re.I)
        minutes = re.search(r"(\d+)\s*(?:мин(?:ут|ы)?|м\.?|min)", line, re.I)
        seconds = re.search(r"(\d+)\s*(?:сек(?:унд)?|с\.?|sec)", line, re.I)
        if any((days, hours, minutes, seconds)):
            return timedelta(days=int(days.group(1)) if days else 0,
                             hours=int(hours.group(1)) if hours else 0,
                             minutes=int(minutes.group(1)) if minutes else 0,
                             seconds=int(seconds.group(1)) if seconds else 0), line[:180]
        clock = re.search(r"(?:через|осталось|до\s+(?:нападения|атаки|начала))?\s*(\d{1,3}):(\d{2})(?::(\d{2}))?", line, re.I)
        if clock:
            a, b, c = int(clock.group(1)), int(clock.group(2)), clock.group(3)
            delta = timedelta(minutes=a, seconds=b) if c is None else timedelta(hours=a, minutes=b, seconds=int(c))
            return delta, line[:180]
    return None, None


def fetch_attack_schedule():
    """Читает Город -> Монах через уже сохранённую сессию пользователя 106."""
    s = _session(saved=True)
    logger.warning("[ATTACKS] start base=%s api=%s", BASE_URL, API_URL)
    try:
        check = s.get(API_URL, timeout=TIMEOUT, allow_redirects=True)
        logger.warning("[ATTACKS] ForGlory status=%s url=%s bytes=%s", check.status_code, check.url, len(check.content))
        if check.status_code in {401, 403} or "/login" in check.url or "/start" in check.url:
            raise PermissionError("Сессия пользователя 106 истекла. Обновите её через /wekings-login")

        city_url = urljoin(BASE_URL + "/", "town")
        city = s.get(city_url, timeout=TIMEOUT, allow_redirects=True)
        logger.warning("[ATTACKS] Town status=%s url=%s bytes=%s", city.status_code, city.url, len(city.content))
        city.raise_for_status()
        if "/login" in city.url or "/start" in city.url:
            raise PermissionError("Сессия пользователя 106 не открывает Город")

        found_monk = _link_by_text(city.text, "Монах", BASE_URL)
        monk_url = found_monk or urljoin(BASE_URL + "/", "monastic")
        logger.warning("[ATTACKS] Monk link=%s source=%s", monk_url, "page" if found_monk else "fallback")
        monk = s.get(monk_url, timeout=TIMEOUT, allow_redirects=True)
        logger.warning("[ATTACKS] Monk status=%s url=%s bytes=%s", monk.status_code, monk.url, len(monk.content))
        monk.raise_for_status()
        if "/login" in monk.url or "/start" in monk.url:
            raise PermissionError("Сессия пользователя 106 не открывает Монаха")

        soup = BeautifulSoup(monk.text, "html.parser")
        text = soup.get_text("\n", strip=True)
        dragon_delta, dragon_raw = _duration_near(text, ("Дракон", "Дракона", "Драконом"))
        serpent_delta, serpent_raw = _duration_near(text, ("Змей", "Змея", "Змеем", "Змею"))
        dragon_active = bool(re.search(r"Дракон\s+напал|нападение\s+Дракона\s+(?:уже\s+)?началось", text, re.I))
        serpent_active = bool(re.search(r"(?:Морской\s+)?Змей\s+напал|нападение\s+(?:Морского\s+)?Змея\s+(?:уже\s+)?началось", text, re.I))
        logger.warning("[ATTACKS] parsed dragon_delta=%r dragon_raw=%r active=%s serpent_delta=%r serpent_raw=%r active=%s", dragon_delta, dragon_raw, dragon_active, serpent_delta, serpent_raw, serpent_active)
        if dragon_delta is None and serpent_delta is None and not dragon_active and not serpent_active:
            sample = re.sub(r"\s+", " ", text)[:700]
            logger.error("[ATTACKS] Monk text sample: %s", sample)
            raise RuntimeError("На странице Монаха не найдено время Дракона или Змея")

        game_now = datetime.now(ZoneInfo("Europe/Chisinau"))
        meta = soup.find("meta", attrs={"name": "server-time"})
        if meta and meta.get("content"):
            try:
                game_now = datetime.strptime(meta["content"].strip(), "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc).astimezone(ZoneInfo("Europe/Chisinau"))
            except ValueError:
                logger.warning("[ATTACKS] bad server-time=%r", meta.get("content"))
        # Необязательный прогноз хорошей погоды для плавания.
        weather_at = None
        weather_raw = None
        # HTML Монаха может содержать переносы строк и NBSP между словами.
        monk_text = re.sub(r"\s+", " ", text.replace("\xa0", " ")).strip()
        # Игра сейчас выводит прогноз как "... ожидается 18:30 28.08.26"
        # (сначала время, затем дата). Поддерживаем также старый формат
        # "28.08.26 18:30", чтобы обновление игры снова не сломало прогноз.
        weather_match = re.search(
            r"(?:по\s+прогнозу\s+)?(?:подходящая|хорошая)\s+погода"
            r".{0,120}?"
            r"(\d{1,2})\s*:\s*(\d{2})\s+"
            r"(\d{1,2})\s*[./-]\s*(\d{1,2})"
            r"(?:\s*[./-]\s*(\d{2,4}))?",
            monk_text, re.I
        )
        weather_time_first = bool(weather_match)
        if not weather_match:
            weather_match = re.search(
                r"(?:по\s+прогнозу\s+)?(?:подходящая|хорошая)\s+погода"
                r".{0,120}?"
                r"(\d{1,2})\s*[./-]\s*(\d{1,2})"
                r"(?:\s*[./-]\s*(\d{2,4}))?\s+"
                r"(\d{1,2})\s*:\s*(\d{2})",
                monk_text, re.I
            )
            weather_time_first = False
        if weather_match:
            if weather_time_first:
                hour, minute, day, month, year = weather_match.groups()
            else:
                day, month, year, hour, minute = weather_match.groups()
            year = int(year) if year else game_now.year
            if year < 100:
                year += 2000
            try:
                weather_at = datetime(year, int(month), int(day), int(hour), int(minute),
                                      tzinfo=ZoneInfo("Europe/Chisinau"))
                weather_raw = weather_match.group(0)[:240]
                logger.info("[ATTACKS] sailing weather found: %s", weather_raw)
            except ValueError:
                logger.warning("[ATTACKS] bad weather forecast=%r", weather_match.group(0))

        _save(s)
        result = {
            "fetched_at": datetime.now(timezone.utc), "game_time": game_now,
            "dragon_at": game_now + dragon_delta if dragon_delta else None,
            "serpent_at": game_now + serpent_delta if serpent_delta else None,
            "dragon_raw": "Дракон уже напал — сражайся!" if dragon_active else dragon_raw,
            "serpent_raw": "Морской Змей уже напал — сражайся!" if serpent_active else serpent_raw,
            "weather_at": weather_at,
            "weather_raw": weather_raw,
        }
        logger.warning("[ATTACKS] success dragon_at=%s serpent_at=%s", result["dragon_at"], result["serpent_at"])
        return result
    except Exception:
        logger.exception("[ATTACKS] fetch failed")
        raise
    finally:
        s.close()
