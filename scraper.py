from __future__ import annotations

import os
import random
import re
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from urllib.parse import urljoin
from zoneinfo import ZoneInfo

import requests
from bs4 import BeautifulSoup


BASE_URL = os.getenv("WEKINGS_BASE_URL", "https://wekings.online").rstrip("/")
FALLBACK_BASE_URLS = tuple(
    value.rstrip("/")
    for value in os.getenv(
        "WEKINGS_FALLBACK_URLS",
        "https://playwekings.mobi,https://playwekings.ru,"
        "https://proxy.playwekings.ru,https://wekings.mobi",
    ).split(",")
    if value.strip()
)
DELAY = max(0.5, float(os.getenv("REQUEST_DELAY", "0.8")))
CONNECT_TIMEOUT = max(2, int(os.getenv("CONNECT_TIMEOUT", "5")))
READ_TIMEOUT = max(5, int(os.getenv("REQUEST_TIMEOUT", "12")))
TIMEOUT = (CONNECT_TIMEOUT, READ_TIMEOUT)
SAVE_EVERY = max(3, int(os.getenv("SAVE_EVERY", "20")))
SCAN_WORKERS = min(2, max(1, int(os.getenv("SCAN_WORKERS", "1"))))
TRANSIENT_RETRIES = min(4, max(1, int(os.getenv("TRANSIENT_RETRIES", "3"))))
RATE_LIMIT_DELAY = max(15, int(os.getenv("RATE_LIMIT_DELAY", "60")))
MAX_RETRY_DELAY = max(RATE_LIMIT_DELAY, int(os.getenv("MAX_RETRY_DELAY", "120")))
_worker_context = threading.local()
_guest_cookie_lock = threading.Lock()
_guest_cookies: dict[str, requests.cookies.RequestsCookieJar] = {}
_guest_cookie_loader = None
_guest_cookie_saver = None
_rate_limit_lock = threading.Lock()
_rate_limit_until = 0.0
_request_pace_lock = threading.Lock()
_next_request_at = 0.0


def configure_guest_cookie_storage(loader, saver):
    """Подключает постоянное хранилище cookies (на Render — PostgreSQL)."""
    global _guest_cookie_loader, _guest_cookie_saver
    _guest_cookie_loader = loader
    _guest_cookie_saver = saver


def _cookie_records(jar):
    return [
        {
            "name": cookie.name,
            "value": cookie.value,
            "domain": cookie.domain,
            "path": cookie.path or "/",
            "secure": bool(cookie.secure),
            "expires": cookie.expires,
        }
        for cookie in jar
    ]


def _restore_guest(base_url: str):
    if _guest_cookie_loader is None:
        return None
    try:
        records = _guest_cookie_loader(base_url) or []
        jar = requests.cookies.RequestsCookieJar()
        for item in records:
            options = {
                "path": item.get("path") or "/",
                "secure": bool(item.get("secure")),
                "expires": item.get("expires"),
            }
            if item.get("domain"):
                options["domain"] = item["domain"]
            jar.set(item["name"], item["value"], **options)
        return jar if records else None
    except Exception:
        return None


def _remember_guest(base_url: str, session: requests.Session):
    with _guest_cookie_lock:
        _guest_cookies[base_url] = session.cookies.copy()
    if _guest_cookie_saver is not None:
        try:
            _guest_cookie_saver(base_url, _cookie_records(session.cookies))
        except Exception:
            # Неудачная запись cookies не должна останавливать сканирование.
            pass


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


def _wait_for_shared_cooldown():
    """Все потоки вместе соблюдают паузу, назначенную Wekings."""
    with _rate_limit_lock:
        remaining = _rate_limit_until - time.monotonic()
    if remaining > 0:
        time.sleep(remaining)


def _set_shared_cooldown(seconds: float):
    global _rate_limit_until
    with _rate_limit_lock:
        _rate_limit_until = max(_rate_limit_until, time.monotonic() + seconds)


def _wait_for_request_slot():
    """Ограничивает суммарную частоту запросов всех рабочих потоков."""
    global _next_request_at
    with _request_pace_lock:
        remaining = _next_request_at - time.monotonic()
        if remaining > 0:
            time.sleep(remaining)
        jitter = random.uniform(-0.1, 0.1)
        _next_request_at = time.monotonic() + max(0.5, DELAY + jitter)


def _retry_after_seconds(response) -> float:
    try:
        return min(MAX_RETRY_DELAY, max(1, float(response.headers.get("Retry-After", ""))))
    except (TypeError, ValueError):
        return min(MAX_RETRY_DELAY, RATE_LIMIT_DELAY)


def request_with_backoff(session, method: str, url: str, *, retries=None, **kwargs):
    """Повторяет временно заблокированный запрос, не обрывая весь снимок."""
    last_error = None
    attempts = TRANSIENT_RETRIES if retries is None else max(1, retries)
    retry_delays = (2, 5, 15)
    for attempt in range(attempts):
        _wait_for_shared_cooldown()
        _wait_for_request_slot()
        try:
            response = session.request(method, url, **kwargs)
            if response.status_code == 429:
                delay = _retry_after_seconds(response)
                _set_shared_cooldown(delay)
                last_error = requests.HTTPError(
                    f"429 Too Many Requests: {url}", response=response
                )
                continue
            if response.status_code >= 500:
                delay = min(MAX_RETRY_DELAY, retry_delays[min(attempt, 2)])
                _set_shared_cooldown(delay)
                last_error = requests.HTTPError(
                    f"Wekings временно вернул ошибку {response.status_code}",
                    response=response,
                )
                continue
            return response
        except (requests.Timeout, requests.ConnectionError) as exc:
            last_error = exc
            delay = min(MAX_RETRY_DELAY, retry_delays[min(attempt, 2)])
            _set_shared_cooldown(delay)
    raise RuntimeError(
        f"Wekings не ответил после {attempts} попыток: {last_error}"
    )


def create_guest_session():
    candidates = list(dict.fromkeys([BASE_URL, *FALLBACK_BASE_URLS]))
    errors = []
    for base_url in candidates:
        session = requests.Session()
        session.headers.update(
            {
                "User-Agent": "Mozilla/5.0 (compatible; WekingsStatistics/1.0)",
                "Accept-Language": "ru-RU,ru;q=0.9",
            }
        )
        with _guest_cookie_lock:
            cached_cookies = _guest_cookies.get(base_url)
        if cached_cookies is None:
            cached_cookies = _restore_guest(base_url)
            if cached_cookies is not None:
                with _guest_cookie_lock:
                    _guest_cookies[base_url] = cached_cookies.copy()
        with _guest_cookie_lock:
            if cached_cookies is not None:
                session.cookies.update(cached_cookies)
        try:
            first = request_with_backoff(
                session, "GET", f"{base_url}/", retries=1, timeout=TIMEOUT
            )
            first.raise_for_status()
            if re.search(r"Викинг\s*#\d+", first.text):
                _remember_guest(base_url, session)
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
                    request_with_backoff(session, "POST", action, data=payload, timeout=TIMEOUT)
                    if method == "post"
                    else request_with_backoff(session, "GET", action, params=payload, timeout=TIMEOUT)
                )
            elif start_button.name == "a" and start_button.get("href"):
                response = request_with_backoff(
                    session, "GET", urljoin(base_url, start_button["href"]), timeout=TIMEOUT
                )
            else:
                response = None
            if response is not None:
                response.raise_for_status()
            if response is not None and re.search(r"Викинг\s*#\d+", response.text):
                _remember_guest(base_url, session)
                return session, response.text, base_url
            raise RuntimeError("игровая страница после нажатия не открылась")
        except (requests.RequestException, RuntimeError) as exc:
            errors.append(f"{base_url}: {exc}")

    raise RuntimeError("Не удалось открыть гостевую игру Wekings. " + "; ".join(errors))


def _link_by_text(html: str, label: str, base_url: str):
    soup = BeautifulSoup(html, "html.parser")
    wanted = label.casefold()
    link = soup.find(
        "a",
        href=True,
        string=lambda value: value and wanted in value.strip().casefold(),
    )
    if link is None:
        link = next(
            (
                item for item in soup.find_all("a", href=True)
                if wanted in item.get_text(" ", strip=True).casefold()
            ),
            None,
        )
    return urljoin(base_url, link["href"]) if link else None


def _duration_near(text: str, labels: tuple[str, ...]):
    """Извлекает обратный отсчёт рядом с названием события."""
    for label in labels:
        position = text.casefold().find(label.casefold())
        if position < 0:
            continue
        # Между названием события и таймером может быть несколько строк.
        fragment = text[position:position + 600]
        days = re.search(r"(\d+)\s*(?:дн(?:ей|я|ь)?|d)", fragment, re.I)
        hours = re.search(r"(\d+)\s*(?:час(?:а|ов)?|ч\.?|h)", fragment, re.I)
        minutes = re.search(r"(\d+)\s*(?:мин(?:ут|ы)?|м\.?|min)", fragment, re.I)
        seconds = re.search(r"(\d+)\s*(?:сек(?:унд)?|с\.?|sec)", fragment, re.I)
        if any((days, hours, minutes, seconds)):
            return timedelta(
                days=int(days.group(1)) if days else 0,
                hours=int(hours.group(1)) if hours else 0,
                minutes=int(minutes.group(1)) if minutes else 0,
                seconds=int(seconds.group(1)) if seconds else 0,
            ), fragment.splitlines()[0][:180]
        clock = re.search(
            r"(?:через|осталось|до\s+(?:нападения|атаки|начала))?\s*"
            r"(\d{1,3}):(\d{2})(?::(\d{2}))?",
            fragment,
            re.I,
        )
        if clock:
            return timedelta(
                hours=int(clock.group(1)),
                minutes=int(clock.group(2)),
                seconds=int(clock.group(3) or 0),
            ), fragment.splitlines()[0][:180]
    return None, None


def fetch_attack_schedule():
    """Заходит в гостевую игру и читает «Город» → «Монах»."""
    session, home_html, base_url = create_guest_session()
    try:
        # На главной Wekings кнопка города может быть картинкой без
        # текста, поэтому оставляем проверенный адрес /town.
        city_url = _link_by_text(home_html, "Город", base_url) or urljoin(base_url, "/town")
        city = session.get(city_url, timeout=TIMEOUT)
        city.raise_for_status()
        monk_url = _link_by_text(city.text, "Монах", base_url) or urljoin(base_url, "/monastic")
        monk = session.get(monk_url, timeout=TIMEOUT)
        monk.raise_for_status()
        text = BeautifulSoup(monk.text, "html.parser").get_text("\n", strip=True)
        dragon_delta, dragon_raw = _duration_near(
            text, ("Дракон", "Дракона", "Драконом")
        )
        serpent_delta, serpent_raw = _duration_near(
            text, ("Змей", "Змея", "Змеем", "Змею")
        )
        if dragon_delta is None and serpent_delta is None:
            raise RuntimeError("на странице монаха не найдено время Дракона или Змея")
        game_now = datetime.now(ZoneInfo("Europe/Chisinau"))
        game_clock = re.search(
            r"(?:время\s+(?:игры|на\s+сервере)|серверное\s+время)[^0-9]{0,30}(\d{1,2}):(\d{2})",
            text,
            re.I,
        )
        if game_clock:
            game_now = game_now.replace(
                hour=int(game_clock.group(1)), minute=int(game_clock.group(2)),
                second=0, microsecond=0,
            )
        return {
            "fetched_at": datetime.now(timezone.utc),
            "game_time": game_now,
            "dragon_at": game_now + dragon_delta if dragon_delta else None,
            "serpent_at": game_now + serpent_delta if serpent_delta else None,
            "dragon_raw": dragon_raw,
            "serpent_raw": serpent_raw,
        }
    finally:
        session.close()


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
    for attempt in range(2):
        try:
            session, base_url = worker_session()
            response = request_with_backoff(
                session,
                "GET",
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
        except PermissionError as exc:
            last_error = exc
            reset_worker_session()
            if attempt == 0:
                time.sleep(min(2, DELAY * 2))
        except requests.HTTPError as exc:
            if exc.response is None or exc.response.status_code not in {401, 403}:
                raise
            last_error = exc
            reset_worker_session()
            if attempt == 0:
                time.sleep(min(2, DELAY * 2))
        except (requests.RequestException, RuntimeError):
            reset_worker_session()
            raise
    raise RuntimeError(
        f"Не удалось обновить гостевую сессию для игрока №{player_id}: {last_error}"
    )


def scan_all_players(db, Player, PlayerSnapshot, ScanState, LowLevelPlayer):
    session, home_html, _ = create_guest_session()
    max_id = discover_max_id(home_html)
    session.close()
    state = db.session.get(ScanState, 1)
    batch_at = state.started_at or datetime.now(timezone.utc)
    start_id = (
        state.current_player_id
        if state.max_player_id > 0 and 1 <= state.current_player_id <= max_id
        else max_id
    )

    # Переход со старого сканирования 1 → максимум на новое направление.
    # Если текущий незавершённый снимок содержит только младшие ID, безопасно
    # начинаем его заново с максимального ID. Уже записанные строки обновятся,
    # поэтому дубликатов не появится.
    highest_in_batch = (
        db.session.query(db.func.max(PlayerSnapshot.player_id))
        .filter(PlayerSnapshot.batch_at == batch_at)
        .scalar()
    )
    if (
        highest_in_batch is not None
        and state.current_player_id > 1
        and highest_in_batch <= state.current_player_id
    ):
        start_id = max_id

    # Старый парсер мог присоединить к славе цифры даты. При необходимости
    # захватываем подозрительную запись и все ID выше неё.
    suspicious_id = (
        db.session.query(Player.id)
        .filter(Player.glory > 300_000)
        .order_by(Player.id.desc())
        .scalar()
    )
    if suspicious_id is not None:
        start_id = max(start_id, suspicious_id)

    state.current_player_id = start_id
    state.max_player_id = max_id
    state.found_players = 0
    commit_with_retry(db)
    low_level_cutoff = datetime.now(timezone.utc) - timedelta(days=7)
    cached_low_level_ids = {
        row[0]
        for row in db.session.query(LowLevelPlayer.player_id)
        .filter(LowLevelPlayer.checked_at >= low_level_cutoff)
        .all()
    }

    def remember_low_level(player_id, data):
        cached = db.session.get(LowLevelPlayer, player_id)
        if cached is None:
            cached = LowLevelPlayer(player_id=player_id)
            db.session.add(cached)
        cached.level = data["level"]
        cached.checked_at = datetime.now(timezone.utc)

    def forget_low_level(player_id):
        cached = db.session.get(LowLevelPlayer, player_id)
        if cached is not None:
            db.session.delete(cached)

    pending_since_commit = 0
    failed_players = {}
    with ThreadPoolExecutor(
        max_workers=SCAN_WORKERS,
        thread_name_prefix="wekings-profile",
    ) as executor:
        for batch_start in range(start_id, 0, -SCAN_WORKERS):
            player_ids = list(
                range(batch_start, max(batch_start - SCAN_WORKERS, 0), -1)
            )
            ids_to_fetch = [
                player_id for player_id in player_ids
                if player_id not in cached_low_level_ids
            ]
            futures = {
                player_id: executor.submit(fetch_profile, player_id)
                for player_id in ids_to_fetch
            }
            results = []
            for player_id in ids_to_fetch:
                try:
                    results.append((player_id, futures[player_id].result()))
                except Exception as exc:
                    failed_players[player_id] = str(exc)

            for player_id, data in results:
                if data and data.get("_skip_low_level"):
                    remember_low_level(player_id, data)
                    cached_low_level_ids.add(player_id)
                elif data:
                    forget_low_level(player_id)
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

            state.current_player_id = player_ids[-1] - 1
            pending_since_commit += len(player_ids)
            if pending_since_commit >= SAVE_EVERY:
                commit_with_retry(db)
                pending_since_commit = 0

    # Один медленный профиль не блокирует основной проход. После него повторяем
    # только неудачные ID. Если источник всё ещё недоступен, оставляем снимок
    # незавершённым с тем же batch_at, чтобы восстановление продолжило его позже.
    remaining_failures = {}
    for player_id in sorted(failed_players, reverse=True):
        try:
            data = fetch_profile(player_id)
        except Exception as exc:
            remaining_failures[player_id] = str(exc)
            continue
        if data and data.get("_skip_low_level"):
            remember_low_level(player_id, data)
            cached_low_level_ids.add(player_id)
        elif data:
            forget_low_level(player_id)
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
                "nickname", "level", "glory", "power", "defense", "agility",
                "mastery", "vitality", "stat_sum", "wins", "losses",
                "dragon_wins", "serpent_wins", "clan", "brotherhood",
                "last_activity",
            }
            for field, value in data.items():
                if field in player_fields:
                    setattr(player, field, value)
            player.scanned_at = datetime.now(timezone.utc)
            with db.session.no_autoflush:
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
                if field not in {"id", "last_activity", "_skip_low_level"}:
                    setattr(snapshot, field, value)
            state.found_players += 1

    if remaining_failures:
        state.current_player_id = max(remaining_failures)
        commit_with_retry(db)
        sample = "; ".join(
            f"№{player_id}: {error}" for player_id, error in list(remaining_failures.items())[:3]
        )
        raise RuntimeError(
            f"Не удалось загрузить {len(remaining_failures)} профилей; "
            f"снимок будет продолжен позже. {sample}"
        )

    state.current_player_id = 0
    commit_with_retry(db)
