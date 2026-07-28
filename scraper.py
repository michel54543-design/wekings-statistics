from __future__ import annotations

import os
import re
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup


BASE_URL = os.getenv("WEKINGS_BASE_URL", "https://wekings.online").rstrip("/")
DELAY = max(0.3, float(os.getenv("REQUEST_DELAY", "0.7")))
TIMEOUT = int(os.getenv("REQUEST_TIMEOUT", "25"))
SAVE_EVERY = max(3, int(os.getenv("SAVE_EVERY", "20")))
SCAN_WORKERS = min(4, max(1, int(os.getenv("SCAN_WORKERS", "3"))))
_worker_context = threading.local()


def commit_with_retry(db):
    try:
        db.session.commit()
    except Exception:
        db.session.rollback()
        try:
            db.engine.dispose()
        except Exception:
            pass
        raise


def number(text: str, label: str):
    match = re.search(
        rf"{re.escape(label)}[ \t\u00a0]*:[ \t\u00a0]*([0-9 \t\u00a0]+)",
        text,
        re.I,
    )
    return int(re.sub(r"\D", "", match.group(1))) if match else None


def numbers(text: str, label: str):
    return [
        int(re.sub(r"\D", "", value))
        for value in re.findall(
            rf"{re.escape(label)}[ \t\u00a0]*:[ \t\u00a0]*([0-9 \t\u00a0]+)",
            text,
            re.I,
        )
    ]


def text_value(text: str, label: str):
    match = re.search(rf"{re.escape(label)}\s*:\s*([^\n\r]+)", text, re.I)
    return match.group(1).strip() if match else None


def create_guest_session():
    candidates = list(dict.fromkeys([BASE_URL, "https://wekings.online"]))
    errors = []
    for base_url in candidates:
        session = requests.Session()
        session.headers.update(
            {
                "User-Agent": "Mozilla/5.0 (compatible; WekingsStatistics/1.0)",
                "Accept-Language": "ru-RU,ru;q=0.9",
            }
        )
        try:
            first = session.get(f"{base_url}/", timeout=TIMEOUT)
            first.raise_for_status()
            if re.search(r"Викинг\s*#\d+", first.text):
                return session, first.text, base_url

            soup = BeautifulSoup(first.text, "html.parser")
            start_button = soup.find(
                lambda tag: tag.name in {"button", "input", "a"}
                and "начать игру" in " ".join(
                    filter(
                        None,
                        [
                            tag.get_text(" ", strip=True),
                            tag.get("value", ""),
                            tag.get("title", ""),
                            tag.get("aria-label", ""),
                        ],
                    )
                ).lower()
            )
            if not start_button:
                start_form = soup.find("form", id="start-game-form")
                start_button = start_form.find(["button", "input"]) if start_form else None
            if not start_button:
                raise RuntimeError("кнопка «Начать игру» не найдена")

            form = start_button.find_parent("form")
            if form:
                action = urljoin(base_url, form.get("action") or "/")
                payload = {
                    field.get("name"): field.get("value", "")
                    for field in form.select("input[name]")
                    if field.get("name")
                }
                method = (form.get("method") or "get").lower()
                response = (
                    session.post(action, data=payload, timeout=TIMEOUT)
                    if method == "post"
                    else session.get(action, params=payload, timeout=TIMEOUT)
                )
            elif start_button.name == "a" and start_button.get("href"):
                response = session.get(urljoin(base_url, start_button["href"]), timeout=TIMEOUT)
            else:
                response = None
            if response is not None:
                response.raise_for_status()
            if response is not None and re.search(r"Викинг\s*#\d+", response.text):
                return session, response.text, base_url
            raise RuntimeError("игровая страница после нажатия не открылась")
        except (requests.RequestException, RuntimeError) as exc:
            errors.append(f"{base_url}: {exc}")

    raise RuntimeError("Не удалось открыть гостевую игру Wekings. " + "; ".join(errors))


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

    canonical_ids = []
    for link in main.find_all("a", href=True):
        match = re.search(
            r"(?:/gifts/|/curses/|[?&]player=|[?&]id=)(\d+)",
            link["href"],
        )
        if match:
            canonical_ids.append(int(match.group(1)))
    if canonical_ids and player_id not in canonical_ids:
        return None

    level = number(text, "Уровень")
    if level is not None and 1 <= level <= 4:
        return {"id": player_id, "level": level, "_skip_low_level": True}
    glory_values = numbers(text, "Слава") or numbers(text, "Cлава")
    # В профиле может быть старая запись «Слава: 15436 15.08»,
    # а ниже — актуальная слава. Берём последнее значение из статистики.
    glory = glory_values[-1] if glory_values else None
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


def reset_worker_session():
    session = getattr(_worker_context, "session", None)
    if session is not None:
        session.close()
    _worker_context.session = None
    _worker_context.base_url = None


def worker_session():
    session = getattr(_worker_context, "session", None)
    base_url = getattr(_worker_context, "base_url", None)
    if session is None or base_url is None:
        session, _, base_url = create_guest_session()
        _worker_context.session = session
        _worker_context.base_url = base_url
    return session, base_url


def fetch_profile(player_id: int):
    """Загружает один профиль в рабочем потоке, не обращаясь к базе."""
    last_error = None
    for attempt in range(3):
        try:
            session, base_url = worker_session()
            response = session.get(
                f"{base_url}/hero/detail",
                params={"player": player_id},
                timeout=TIMEOUT,
            )
            if response.status_code == 404:
                time.sleep(DELAY)
                return None
            response.raise_for_status()
            data = parse_profile(player_id, response.text)
            time.sleep(DELAY)
            return data
        except (PermissionError, requests.RequestException, RuntimeError) as exc:
            last_error = exc
            reset_worker_session()
            if attempt < 2:
                time.sleep(min(8, DELAY * (attempt + 2)))
    raise RuntimeError(
        f"Не удалось загрузить профиль игрока №{player_id} после 3 попыток: {last_error}"
    )


def scan_all_players(db, Player, PlayerSnapshot, ScanState):
    session, home_html, _ = create_guest_session()
    max_id = discover_max_id(home_html)
    session.close()
    state = db.session.get(ScanState, 1)
    if db.session.query(PlayerSnapshot.id).first() is None:
        start_id = 1
        state.current_player_id = 1
    else:
        start_id = state.current_player_id if 1 <= state.current_player_id <= max_id else 1
        # Старый парсер мог присоединить к славе цифры даты из соседней
        # строки. Один раз возвращаемся к первой подозрительной записи.
        suspicious_id = (
            db.session.query(Player.id)
            .filter(Player.glory > 300_000)
            .order_by(Player.id.asc())
            .scalar()
        )
        if suspicious_id is not None:
            start_id = min(start_id, suspicious_id)
            state.current_player_id = start_id
    batch_at = state.started_at or datetime.now(timezone.utc)
    state.max_player_id = max_id
    state.found_players = 0
    commit_with_retry(db)
    pending_since_commit = 0
    with ThreadPoolExecutor(
        max_workers=SCAN_WORKERS,
        thread_name_prefix="wekings-profile",
    ) as executor:
        for batch_start in range(start_id, max_id + 1, SCAN_WORKERS):
            player_ids = list(
                range(batch_start, min(batch_start + SCAN_WORKERS, max_id + 1))
            )
            futures = {
                player_id: executor.submit(fetch_profile, player_id)
                for player_id in player_ids
            }
            try:
                # Получаем результаты в порядке ID. В базу пишет только главный
                # поток, поэтому SQLAlchemy-сессия остаётся безопасной.
                results = [
                    (player_id, futures[player_id].result())
                    for player_id in player_ids
                ]
            except Exception:
                state.current_player_id = batch_start
                commit_with_retry(db)
                raise

            for player_id, data in results:
                if data and not data.get("_skip_low_level"):
                    player = db.session.get(Player, player_id)
                    if player is None:
                        player = Player(
                            id=player_id,
                            nickname=data["nickname"],
                            scanned_at=datetime.now(timezone.utc),
                        )
                        db.session.add(player)
                    else:
                        player.previous_glory = player.glory
                        player.previous_stat_sum = player.stat_sum
                    player_fields = {
                        "nickname", "level", "glory", "power", "defense",
                        "agility", "mastery", "vitality", "stat_sum", "wins",
                        "losses", "dragon_wins", "serpent_wins", "clan",
                        "brotherhood", "last_activity",
                    }
                    for field, value in data.items():
                        if field in player_fields:
                            setattr(player, field, value)
                    player.scanned_at = datetime.now(timezone.utc)
                    with db.session.no_autoflush:
                        snapshot = PlayerSnapshot.query.filter_by(
                            player_id=player_id,
                            batch_at=batch_at,
                        ).first()
                    if snapshot is None:
                        snapshot = PlayerSnapshot(
                            player_id=player_id,
                            batch_at=batch_at,
                            nickname=data["nickname"],
                        )
                        db.session.add(snapshot)
                    for field, value in data.items():
                        if field not in {"id", "last_activity", "_skip_low_level"}:
                            setattr(snapshot, field, value)
                    state.found_players += 1

            state.current_player_id = player_ids[-1] + 1
            pending_since_commit += len(player_ids)
            if pending_since_commit >= SAVE_EVERY:
                commit_with_retry(db)
                pending_since_commit = 0

    state.current_player_id = 1
    commit_with_retry(db)
