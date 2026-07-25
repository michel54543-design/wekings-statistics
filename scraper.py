from __future__ import annotations

import os
import re
import time
from datetime import datetime, timezone
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup


BASE_URL = os.getenv("WEKINGS_BASE_URL", "https://playwekings.mobi")
DELAY = max(0.3, float(os.getenv("REQUEST_DELAY", "0.7")))
TIMEOUT = int(os.getenv("REQUEST_TIMEOUT", "25"))
SAVE_EVERY = int(os.getenv("SAVE_EVERY", "25"))


def number(text: str, label: str):
    match = re.search(rf"{re.escape(label)}\s*:\s*([\d\s]+)", text, re.I)
    return int(re.sub(r"\D", "", match.group(1))) if match else None


def numbers(text: str, label: str):
    return [
        int(re.sub(r"\D", "", value))
        for value in re.findall(rf"{re.escape(label)}\s*:\s*([\d\s]+)", text, re.I)
    ]


def text_value(text: str, label: str):
    match = re.search(rf"{re.escape(label)}\s*:\s*([^\n\r]+)", text, re.I)
    return match.group(1).strip() if match else None


def create_guest_session():
    session = requests.Session()
    session.headers.update(
        {
            "User-Agent": "Mozilla/5.0 (compatible; WekingsStatistics/1.0)",
            "Accept-Language": "ru-RU,ru;q=0.9",
        }
    )
    first = session.get(f"{BASE_URL}/", timeout=TIMEOUT)
    first.raise_for_status()
    if "/rating" in first.text or re.search(r"Викинг\s*#\d+", first.text):
        return session, first.text

    soup = BeautifulSoup(first.text, "html.parser")
    start_button = soup.find(
        lambda tag: tag.name in {"button", "input", "a"}
        and "начать игру" in (tag.get_text(" ", strip=True) or tag.get("value", "")).lower()
    )
    if start_button:
        form = start_button.find_parent("form")
        if form:
            action = urljoin(BASE_URL, form.get("action") or "/")
            payload = {
                field.get("name"): field.get("value", "")
                for field in form.select("input[name]")
                if field.get("name")
            }
            method = (form.get("method") or "get").lower()
            response = session.post(action, data=payload, timeout=TIMEOUT) if method == "post" else session.get(action, params=payload, timeout=TIMEOUT)
        elif start_button.name == "a" and start_button.get("href"):
            response = session.get(urljoin(BASE_URL, start_button["href"]), timeout=TIMEOUT)
        else:
            response = None
        if response is not None and ("/rating" in response.text or re.search(r"Викинг\s*#\d+", response.text)):
            return session, response.text

    raise RuntimeError(
        "Не удалось автоматически нажать «Начать игру». "
        "Проверьте, не изменилась ли стартовая страница Wekings."
    )


def discover_max_id(home_html: str):
    configured = int(os.getenv("MAX_PLAYER_ID", "0"))
    ids = [int(value) for value in re.findall(r"Викинг\s*#(\d+)", home_html)]
    discovered = max(ids, default=0)
    if configured:
        return max(configured, discovered)
    if discovered:
        return discovered
    raise RuntimeError("Не удалось определить последний ID игрока")


def parse_profile(player_id: int, html: str):
    soup = BeautifulSoup(html, "html.parser")
    main = soup.find("main") or soup
    text = main.get_text("\n", strip=True)

    if "Начать игру" in text or "Зарегистрироваться" in text:
        raise PermissionError("Гостевая сессия Wekings завершилась")

    level = number(text, "Уровень")
    glory = number(text, "Cлава") or number(text, "Слава")
    power = number(text, "Сила")
    if level is None and glory is None and power is None:
        return None

    profile_heading = main.find(["h1", "h2"])
    nickname = profile_heading.get_text(" ", strip=True) if profile_heading else None
    if not nickname:
        ignored = (
            "зайди в лавку",
            "награда за прохождение",
            "основы игры",
            "добро пожаловать",
        )
        nickname = next(
            (
                value
                for paragraph in main.find_all("p")
                if (value := paragraph.get_text(" ", strip=True))
                and 1 < len(value) <= 160
                and ":" not in value
                and not value.lower().startswith(ignored)
            ),
            None,
        )
    if not nickname:
        candidates = [
            value.strip()
            for value in text.splitlines()
            if value.strip()
            and not any(marker in value for marker in (":", "Основы игры", "Награда"))
        ]
        nickname = candidates[0] if candidates else f"Игрок #{player_id}"

    links = main.find_all("a", href=True)
    clan = next((a.get_text(" ", strip=True) for a in links if "/clan/info" in a["href"]), None)
    brotherhood = next((a.get_text(" ", strip=True) for a in links if "/brotherhood/info" in a["href"]), None)
    defense = number(text, "Защита")
    agility = number(text, "Ловкость")
    mastery = number(text, "Мастерство")
    vitality = number(text, "Живучесть")
    values = [power, defense, agility, mastery, vitality]

    stolen = numbers(text, "Награбил")
    lost = numbers(text, "Потерял")
    return {
        "id": player_id,
        "nickname": nickname[:160],
        "level": level,
        "glory": glory,
        "power": power,
        "defense": defense,
        "agility": agility,
        "mastery": mastery,
        "vitality": vitality,
        "stat_sum": sum(v for v in values if v is not None) if any(v is not None for v in values) else None,
        "wins": number(text, "Побед"),
        "losses": number(text, "Поражений"),
        "dragon_wins": number(text, "Побед над Драконом"),
        "serpent_wins": number(text, "Побед над Змеем"),
        "beasts_killed": number(text, "Убито зверей"),
        "silver_stolen": stolen[0] if stolen else None,
        "silver_lost": lost[0] if lost else None,
        "crystals_stolen": stolen[1] if len(stolen) > 1 else None,
        "crystals_lost": lost[1] if len(lost) > 1 else None,
        "clan": clan,
        "brotherhood": brotherhood,
        "last_activity": text_value(text, "Последняя активность"),
    }


def scan_all_players(db, Player, PlayerSnapshot, ScanState):
    session, home_html = create_guest_session()
    max_id = discover_max_id(home_html)
    state = db.session.get(ScanState, 1)
    if db.session.query(PlayerSnapshot.id).first() is None:
        start_id = 1
        state.current_player_id = 1
    else:
        start_id = state.current_player_id if 1 <= state.current_player_id <= max_id else 1
    batch_at = state.started_at or datetime.now(timezone.utc)
    state.max_player_id = max_id
    state.found_players = 0
    db.session.commit()

    consecutive_auth_errors = 0
    for player_id in range(start_id, max_id + 1):
        try:
            response = session.get(
                f"{BASE_URL}/hero/detail",
                params={"player": player_id},
                timeout=TIMEOUT,
            )
            if response.status_code == 404:
                state.current_player_id = player_id + 1
                continue
            response.raise_for_status()
            data = parse_profile(player_id, response.text)
            consecutive_auth_errors = 0
        except PermissionError:
            consecutive_auth_errors += 1
            if consecutive_auth_errors > 2:
                session, _ = create_guest_session()
                consecutive_auth_errors = 0
            continue
        except requests.RequestException:
            time.sleep(min(15, DELAY * 5))
            continue

        if data:
            player = db.session.get(Player, player_id)
            if player is None:
                player = Player(id=player_id, nickname=data["nickname"], scanned_at=datetime.now(timezone.utc))
                db.session.add(player)
            else:
                player.previous_glory = player.glory
                player.previous_stat_sum = player.stat_sum
            player_fields = {
                "nickname", "level", "glory", "power", "defense", "agility",
                "mastery", "vitality", "stat_sum", "wins", "losses",
                "dragon_wins", "serpent_wins", "clan", "brotherhood",
                "last_activity",
            }
            for field, value in data.items():
                if field in player_fields:
                    setattr(player, field, value)
            player.scanned_at = datetime.now(timezone.utc)
            snapshot = PlayerSnapshot.query.filter_by(
                player_id=player_id, batch_at=batch_at
            ).first()
            if snapshot is None:
                snapshot = PlayerSnapshot(
                    player_id=player_id,
                    batch_at=batch_at,
                    nickname=data["nickname"],
                )
                db.session.add(snapshot)
            for field, value in data.items():
                if field not in {"id", "last_activity"}:
                    setattr(snapshot, field, value)
            state.found_players += 1

        state.current_player_id = player_id + 1
        if player_id % SAVE_EVERY == 0:
            db.session.commit()
        time.sleep(DELAY)

    state.current_player_id = 1
    db.session.commit()
