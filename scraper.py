from __future__ import annotations

import base64
import os
import re
from datetime import datetime, timezone
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

BASE_URL = os.getenv("WEKINGS_BASE_URL", "https://playwekings.ru").rstrip("/")
LOGIN_URL = os.getenv("WEKINGS_LOGIN_URL", f"{BASE_URL}/login")
API_URL = os.getenv("WEKINGS_FORGLORY_API", f"{BASE_URL}/heroes/for-glory")
TIMEOUT = (5, 30)
_cookie_loader = None
_cookie_saver = None
_pending_login = None


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
    s.headers.update({"User-Agent": "Mozilla/5.0 (compatible; ForGlory/2.0)",
                      "Accept-Language": "ru-RU,ru;q=0.9"})
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


def prepare_login():
    """Создаёт одну ручную сессию входа и возвращает капчу как data URL."""
    global _pending_login
    s = _session(saved=False)
    r = s.get(LOGIN_URL, timeout=TIMEOUT)
    r.raise_for_status()
    meta = _login_form(r.text, r.url)
    img = s.get(meta["captcha_url"], timeout=TIMEOUT)
    img.raise_for_status()
    mime = img.headers.get("Content-Type", "image/png").split(";", 1)[0]
    _pending_login = (s, meta)
    return "data:%s;base64,%s" % (mime, base64.b64encode(img.content).decode("ascii"))


def submit_login(username, password, captcha):
    global _pending_login
    if not _pending_login:
        raise RuntimeError("Капча устарела. Обновите страницу входа и попробуйте снова.")
    s, meta = _pending_login
    payload = dict(meta["hidden"])
    payload.update({meta["username"]: username, meta["password"]: password,
                    meta["captcha"]: captcha})
    if meta["method"] == "get":
        r = s.get(meta["action"], params=payload, timeout=TIMEOUT, allow_redirects=True)
    else:
        r = s.post(meta["action"], data=payload, timeout=TIMEOUT, allow_redirects=True)
    r.raise_for_status()
    # Проверяем доступ именно к API — это надёжнее текста страницы входа.
    test = s.get(API_URL, timeout=TIMEOUT, allow_redirects=True)
    if test.status_code in {401, 403} or "/login" in test.url:
        _pending_login = None
        raise RuntimeError("Вход не выполнен. Проверьте логин, пароль и капчу.")
    try:
        body = test.json()
    except ValueError:
        _pending_login = None
        raise RuntimeError("После входа API не вернул JSON. Возможно, капча введена неверно.")
    if not isinstance(body, (dict, list)):
        raise RuntimeError("API вернул неожиданный ответ")
    _save(s)
    _pending_login = None
    return True


def api_auth_status():
    s = _session(saved=True)
    try:
        r = s.get(API_URL, timeout=TIMEOUT, allow_redirects=True)
        if r.status_code in {401, 403} or "/login" in r.url:
            return False
        r.json()
        return True
    except Exception:
        return False
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
        "beasts_killed": _int(row.get("beasts_killed")), "silver_stolen": _int(row.get("silver_stolen")),
        "silver_lost": _int(row.get("silver_lost")), "crystals_stolen": _int(row.get("crystals_stolen")),
        "crystals_lost": _int(row.get("crystals_lost")), "clan": _org_name(row.get("clan")),
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
    """Новый сбор: один API-запрос вместо старого обхода профилей по ID."""
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
        "silver_stolen", "silver_lost", "crystals_stolen", "crystals_lost", "clan", "brotherhood",
    ]
    player_fields = ["nickname", "level", "glory", "power", "defense", "agility", "mastery",
                     "vitality", "stat_sum", "wins", "losses", "dragon_wins", "serpent_wins",
                     "clan", "brotherhood", "last_activity"]
    now = datetime.now(timezone.utc)
    for n, data in enumerate(rows, 1):
        player = db.session.get(Player, data["id"])
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
        if n % 500 == 0:
            state.found_players = n
            state.current_player_id = data["id"]
            db.session.commit()
    state.found_players = len(rows)
    state.current_player_id = 0
    db.session.commit()


def fetch_attack_schedule():
    # Таймеры не относятся к API статистики. Не запускаем старый гостевой сканер.
    raise RuntimeError("Обновление таймеров через старый гостевой сканер отключено")
