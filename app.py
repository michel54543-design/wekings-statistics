from __future__ import annotations

import os
import json
import threading
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from apscheduler.schedulers.background import BackgroundScheduler
from flask import Flask, jsonify, render_template, request
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import and_
from sqlalchemy.orm import aliased


def normalize_database_url(value: str) -> str:
    if value.startswith("postgres://"):
        return value.replace("postgres://", "postgresql://", 1)
    return value


def moldova_date(value):
    """Дата отчёта по времени Молдовы, даже если БД вернула naive UTC."""
    if value is None:
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(ZoneInfo("Europe/Chisinau")).date()


def _as_utc(value):
    """PostgreSQL/SQLite могут вернуть дату без информации о часовом поясе."""
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


app = Flask(__name__)
database_url = normalize_database_url(os.getenv("DATABASE_URL", "sqlite:///wekings.db"))
app.config["SQLALCHEMY_DATABASE_URI"] = database_url
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
if database_url.startswith("postgresql"):
    app.config["SQLALCHEMY_ENGINE_OPTIONS"] = {
        "pool_pre_ping": True,
        "pool_recycle": 120,
        "pool_size": 3,
        "max_overflow": 2,
        "pool_use_lifo": True,
        "connect_args": {
            "keepalives": 1,
            "keepalives_idle": 30,
            "keepalives_interval": 10,
            "keepalives_count": 3,
        },
    }
db = SQLAlchemy(app)


class Player(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    nickname = db.Column(db.String(160), nullable=False, index=True)
    level = db.Column(db.Integer)
    glory = db.Column(db.BigInteger)
    power = db.Column(db.BigInteger)
    defense = db.Column(db.BigInteger)
    agility = db.Column(db.BigInteger)
    mastery = db.Column(db.BigInteger)
    vitality = db.Column(db.BigInteger)
    stat_sum = db.Column(db.BigInteger)
    wins = db.Column(db.BigInteger)
    losses = db.Column(db.BigInteger)
    dragon_wins = db.Column(db.BigInteger)
    serpent_wins = db.Column(db.BigInteger)
    clan = db.Column(db.String(160))
    brotherhood = db.Column(db.String(160))
    last_activity = db.Column(db.String(80))
    scanned_at = db.Column(db.DateTime(timezone=True), nullable=False)
    previous_glory = db.Column(db.BigInteger)
    previous_stat_sum = db.Column(db.BigInteger)

    @property
    def glory_gain(self):
        if self.previous_glory is None or self.glory is None:
            return None
        return self.glory - self.previous_glory

    @property
    def stats_gain(self):
        if self.previous_stat_sum is None or self.stat_sum is None:
            return None
        return self.stat_sum - self.previous_stat_sum


class ScanState(db.Model):
    id = db.Column(db.Integer, primary_key=True, default=1)
    running = db.Column(db.Boolean, default=False, nullable=False)
    current_player_id = db.Column(db.Integer, default=1, nullable=False)
    max_player_id = db.Column(db.Integer, default=0, nullable=False)
    found_players = db.Column(db.Integer, default=0, nullable=False)
    started_at = db.Column(db.DateTime(timezone=True))
    finished_at = db.Column(db.DateTime(timezone=True))
    last_error = db.Column(db.Text)


class GameAttackState(db.Model):
    id = db.Column(db.Integer, primary_key=True, default=1)
    fetched_at = db.Column(db.DateTime(timezone=True))
    game_time = db.Column(db.DateTime(timezone=True))
    dragon_at = db.Column(db.DateTime(timezone=True))
    serpent_at = db.Column(db.DateTime(timezone=True))
    dragon_raw = db.Column(db.String(200))
    serpent_raw = db.Column(db.String(200))
    last_error = db.Column(db.Text)


class GuestSessionState(db.Model):
    base_url = db.Column(db.String(255), primary_key=True)
    cookies_json = db.Column(db.Text, nullable=False, default="[]")
    updated_at = db.Column(db.DateTime(timezone=True), nullable=False)


class LowLevelPlayer(db.Model):
    """ID игрока 1–4 уровня, который можно временно не перепроверять."""
    player_id = db.Column(db.Integer, primary_key=True)
    level = db.Column(db.Integer, nullable=False)
    checked_at = db.Column(db.DateTime(timezone=True), nullable=False, index=True)


class PlayerSnapshot(db.Model):
    __table_args__ = (
        db.UniqueConstraint("player_id", "batch_at", name="uq_player_snapshot_batch"),
        db.Index("ix_snapshot_batch_player", "batch_at", "player_id"),
    )
    id = db.Column(db.BigInteger, primary_key=True)
    player_id = db.Column(db.Integer, nullable=False, index=True)
    batch_at = db.Column(db.DateTime(timezone=True), nullable=False, index=True)
    nickname = db.Column(db.String(160), nullable=False)
    level = db.Column(db.Integer)
    glory = db.Column(db.BigInteger)
    power = db.Column(db.BigInteger)
    defense = db.Column(db.BigInteger)
    agility = db.Column(db.BigInteger)
    mastery = db.Column(db.BigInteger)
    vitality = db.Column(db.BigInteger)
    stat_sum = db.Column(db.BigInteger)
    wins = db.Column(db.BigInteger)
    losses = db.Column(db.BigInteger)
    dragon_wins = db.Column(db.BigInteger)
    serpent_wins = db.Column(db.BigInteger)
    beasts_killed = db.Column(db.BigInteger)
    silver_stolen = db.Column(db.BigInteger)
    silver_lost = db.Column(db.BigInteger)
    crystals_stolen = db.Column(db.BigInteger)
    crystals_lost = db.Column(db.BigInteger)
    clan = db.Column(db.String(160))
    brotherhood = db.Column(db.String(160))


with app.app_context():
    db.create_all()
    scan_state = db.session.get(ScanState, 1)
    if scan_state is None:
        scan_state = ScanState(id=1)
        db.session.add(scan_state)
    else:
        # Render can stop the process during a scan. A database flag from that
        # dead process must not block the new worker from resuming.
        scan_state.running = False
    if db.session.get(GameAttackState, 1) is None:
        db.session.add(GameAttackState(id=1))
    db.session.commit()

    # Старые версии называли снимок днём начала долгого сканирования.
    # Если сбор перешёл через полночь, переносим последний готовый снимок
    # на фактическое время завершения: например 02.08 -> 03.08.
    if scan_state.finished_at:
        latest_completed_batch = (
            db.session.query(db.func.max(PlayerSnapshot.batch_at))
            .filter(PlayerSnapshot.batch_at <= scan_state.finished_at)
            .scalar()
        )
        if (
            latest_completed_batch
            and moldova_date(latest_completed_batch) != moldova_date(scan_state.finished_at)
        ):
            PlayerSnapshot.query.filter_by(batch_at=latest_completed_batch).update(
                {PlayerSnapshot.batch_at: scan_state.finished_at},
                synchronize_session=False,
            )
            db.session.commit()
    # Не запускаем полное GROUP BY по всей истории при каждом старте Render.
    # Старые дубликаты уже были очищены, а уникальный индекс не позволяет
    # сканеру создавать новые. Такой проход блокировал бесплатный PostgreSQL
    # и сайт несколько минут показывал только «Загрузка…».


def load_guest_cookies(base_url):
    with app.app_context():
        saved = db.session.get(GuestSessionState, base_url)
        if saved is None:
            return []
        try:
            return json.loads(saved.cookies_json)
        except (TypeError, ValueError):
            return []


def save_guest_cookies(base_url, records):
    with app.app_context():
        saved = db.session.get(GuestSessionState, base_url)
        if saved is None:
            saved = GuestSessionState(base_url=base_url)
            db.session.add(saved)
        saved.cookies_json = json.dumps(records, ensure_ascii=False)
        saved.updated_at = datetime.now(timezone.utc)
        db.session.commit()


from scraper import configure_guest_cookie_storage
configure_guest_cookie_storage(load_guest_cookies, save_guest_cookies)


SORT_FIELDS = {
    "glory": "glory",
    "power": "power",
    "defense": "defense",
    "agility": "agility",
    "mastery": "mastery",
    "vitality": "vitality",
    "stat_sum": "stat_sum",
    "wins": "wins",
    "losses": "losses",
    "dragon_wins": "dragon_wins",
    "serpent_wins": "serpent_wins",
    "beasts_killed": "beasts_killed",
    "silver_stolen": "silver_stolen",
    "silver_lost": "silver_lost",
    "crystals_stolen": "crystals_stolen",
    "crystals_lost": "crystals_lost",
}


@app.get("/")
def index():
    return render_template("index.html")


@app.get("/health")
def health():
    return jsonify(ok=True)


@app.get("/api/players")
def api_players():
    page = max(1, request.args.get("page", 1, type=int))
    per_page = min(100, max(10, request.args.get("per_page", 50, type=int)))
    metric = request.args.get("sort", "power")
    mode = request.args.get("mode", "general")
    query = request.args.get("q", "").strip()
    level = request.args.get("level", type=int)
    field_name = SORT_FIELDS.get(metric, "power")
    # В список попадают только завершённые и достаточно полные снимки.
    # Это не позволяет ошибочному сбору из 2 000 игроков заменить обычный
    # отчёт примерно на 8 000 игроков.
    dates = completed_snapshot_dates()
    if not dates:
        max_level = db.session.query(db.func.max(Player.level)).scalar() or 44
        legacy_fields = {
            "glory": Player.glory,
            "power": Player.power,
            "defense": Player.defense,
            "agility": Player.agility,
            "mastery": Player.mastery,
            "vitality": Player.vitality,
            "stat_sum": Player.stat_sum,
            "wins": Player.wins,
            "losses": Player.losses,
            "dragon_wins": Player.dragon_wins,
            "serpent_wins": Player.serpent_wins,
        }
        statement = Player.query
        if query:
            statement = statement.filter(Player.nickname.ilike(f"%{query}%"))
        if level:
            statement = statement.filter(Player.level == level)
        sort_column = legacy_fields.get(metric, Player.glory)
        result = statement.order_by(sort_column.desc().nullslast()).paginate(
            page=page, per_page=per_page, error_out=False
        )
        return jsonify(
            players=[
                {
                    "id": p.id,
                    "nickname": p.nickname,
                    "level": p.level,
                    "glory": p.glory,
                    "power": p.power,
                    "defense": p.defense,
                    "agility": p.agility,
                    "mastery": p.mastery,
                    "vitality": p.vitality,
                    "stat_sum": p.stat_sum,
                    "wins": p.wins,
                    "losses": p.losses,
                    "dragon_wins": p.dragon_wins,
                    "serpent_wins": p.serpent_wins,
                    "gain": None,
                    "clan": p.clan,
                    "brotherhood": p.brotherhood,
                    "profile_url": f"https://playwekings.mobi/hero/detail?player={p.id}",
                }
                for p in result.items
            ],
            page=result.page,
            pages=result.pages,
            total=result.total,
            dates=[],
            max_level=max_level,
        )

    def parse_date(value, fallback):
        if not value:
            return fallback
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return fallback

    date_to = parse_date(request.args.get("to"), dates[0])
    max_level = (
        db.session.query(db.func.max(PlayerSnapshot.level))
        .filter(PlayerSnapshot.batch_at == date_to)
        .scalar()
        or 44
    )
    if mode == "best":
        cutoff = date_to - timedelta(days=30)
        eligible = [value for value in dates if cutoff <= value <= date_to]
        date_from = eligible[-1] if eligible else dates[-1]
    else:
        date_from = parse_date(
            request.args.get("from"),
            dates[1] if len(dates) > 1 else dates[0],
        )

    # Для обычного рейтинга сначала выбираем только текущую страницу, затем
    # получаем предыдущие значения лишь для этих 50 игроков. Старый запрос
    # соединял целиком два снимка по ~8 тысяч строк и сортировал результат,
    # из-за чего бесплатный PostgreSQL зависал на десятки секунд.
    if mode not in {"growth", "best"}:
        current_query = PlayerSnapshot.query.filter_by(batch_at=date_to)
        if query:
            current_query = current_query.filter(
                PlayerSnapshot.nickname.ilike(f"%{query}%")
            )
        if level:
            current_query = current_query.filter(PlayerSnapshot.level == level)
        sort_column = getattr(PlayerSnapshot, field_name)
        result = current_query.order_by(
            sort_column.desc().nullslast()
        ).paginate(page=page, per_page=per_page, error_out=False)

        previous_date = dates[1] if len(dates) > 1 else dates[0]
        player_ids = [player.player_id for player in result.items]
        previous_values = {}
        if player_ids:
            previous_values = dict(
                db.session.query(
                    PlayerSnapshot.player_id,
                    getattr(PlayerSnapshot, field_name),
                )
                .filter(
                    PlayerSnapshot.batch_at == previous_date,
                    PlayerSnapshot.player_id.in_(player_ids),
                )
                .all()
            )

        def player_payload(player):
            current_value = getattr(player, field_name)
            previous_value = previous_values.get(player.player_id)
            gain = (
                current_value - previous_value
                if current_value is not None and previous_value is not None
                else None
            )
            return {
                "id": player.player_id,
                "nickname": player.nickname,
                "level": player.level,
                "glory": player.glory,
                "glory_gain": gain if metric == "glory" else None,
                "power": player.power,
                "defense": player.defense,
                "agility": player.agility,
                "mastery": player.mastery,
                "vitality": player.vitality,
                "stat_sum": player.stat_sum,
                "stats_gain": gain if metric == "stat_sum" else None,
                "wins": player.wins,
                "losses": player.losses,
                "dragon_wins": player.dragon_wins,
                "serpent_wins": player.serpent_wins,
                "beasts_killed": player.beasts_killed,
                "silver_stolen": player.silver_stolen,
                "silver_lost": player.silver_lost,
                "crystals_stolen": player.crystals_stolen,
                "crystals_lost": player.crystals_lost,
                "gain": gain,
                "clan": player.clan,
                "brotherhood": player.brotherhood,
                "profile_url": (
                    "https://playwekings.mobi/hero/detail?player="
                    f"{player.player_id}"
                ),
            }

        return jsonify(
            players=[player_payload(player) for player in result.items],
            page=result.page,
            pages=result.pages,
            total=result.total,
            dates=[value.isoformat() for value in dates],
            date_from=previous_date.isoformat(),
            date_to=date_to.isoformat(),
            max_level=max_level,
        )

    current = aliased(PlayerSnapshot)
    previous = aliased(PlayerSnapshot)
    value_column = getattr(current, field_name)
    previous_column = getattr(previous, field_name)
    gain_column = value_column - previous_column
    statement = db.session.query(current, gain_column.label("gain"))
    if mode in {"growth", "best"}:
        statement = statement.join(
            previous,
            and_(
                previous.player_id == current.player_id,
                previous.batch_at == date_from,
            ),
        )
    else:
        statement = statement.outerjoin(
            previous,
            and_(
                previous.player_id == current.player_id,
                previous.batch_at == (dates[1] if len(dates) > 1 else dates[0]),
            ),
        )
    statement = statement.filter(current.batch_at == date_to)
    if query:
        statement = statement.filter(current.nickname.ilike(f"%{query}%"))
    if level:
        statement = statement.filter(current.level == level)
    if mode in {"growth", "best"}:
        statement = statement.filter(gain_column > 0).order_by(gain_column.desc().nullslast())
    else:
        statement = statement.order_by(value_column.desc().nullslast())
    result = statement.paginate(page=page, per_page=per_page, error_out=False)

    return jsonify(
        players=[
            {
                "id": p.player_id,
                "nickname": p.nickname,
                "level": p.level,
                "glory": p.glory,
                "glory_gain": gain if metric == "glory" else None,
                "power": p.power,
                "defense": p.defense,
                "agility": p.agility,
                "mastery": p.mastery,
                "vitality": p.vitality,
                "stat_sum": p.stat_sum,
                "stats_gain": gain if metric == "stat_sum" else None,
                "wins": p.wins,
                "losses": p.losses,
                "dragon_wins": p.dragon_wins,
                "serpent_wins": p.serpent_wins,
                "beasts_killed": p.beasts_killed,
                "silver_stolen": p.silver_stolen,
                "silver_lost": p.silver_lost,
                "crystals_stolen": p.crystals_stolen,
                "crystals_lost": p.crystals_lost,
                "gain": gain,
                "clan": p.clan,
                "brotherhood": p.brotherhood,
                "profile_url": f"https://playwekings.mobi/hero/detail?player={p.player_id}",
            }
            for p, gain in result.items
        ],
        page=result.page,
        pages=result.pages,
        total=result.total,
        dates=[value.isoformat() for value in dates],
        date_from=date_from.isoformat(),
        date_to=date_to.isoformat(),
        max_level=max_level,
    )


def completed_snapshot_dates():
    scan_state = db.session.get(ScanState, 1)
    query = db.session.query(PlayerSnapshot.batch_at).distinct()
    if scan_state and scan_state.finished_at:
        query = query.filter(PlayerSnapshot.batch_at <= scan_state.finished_at)
    rows = query.order_by(PlayerSnapshot.batch_at.desc()).limit(100).all()
    # Незавершённые снимки не получают finished_at и не переименовываются во
    # время завершения. Проверка полноты выполняется один раз при публикации,
    # поэтому здесь не нужен дорогой COUNT/GROUP BY всей истории.
    return [row.batch_at for row in rows]


def valid_group_name(value):
    if not value:
        return False
    normalized = value.strip().lower().replace("ё", "е")
    if not normalized or normalized in {"—", "-", "нет", "none"}:
        return False
    return not any(
        phrase in normalized
        for phrase in (
            "не состоит в клане",
            "не состоит в братстве",
            "не состоит",
        )
    )


@app.get("/api/organizations")
def api_organizations():
    organization_type = request.args.get("type", "clan")
    if organization_type not in {"clan", "brotherhood"}:
        return jsonify(error="Неизвестный тип рейтинга"), 400

    page = max(1, request.args.get("page", 1, type=int))
    per_page = min(100, max(10, request.args.get("per_page", 50, type=int)))
    dates = completed_snapshot_dates()
    if len(dates) < 2:
        return jsonify(
            organizations=[],
            page=1,
            pages=1,
            total=0,
            dates=[value.isoformat() for value in dates],
            ready=False,
        )

    def parse_date(value, fallback):
        if not value:
            return fallback
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
            return parsed if parsed in dates else fallback
        except ValueError:
            return fallback

    date_to = parse_date(request.args.get("to"), dates[0])
    date_to_index = dates.index(date_to)
    date_from = dates[min(date_to_index + 1, len(dates) - 1)]
    group_column = (
        PlayerSnapshot.clan
        if organization_type == "clan"
        else PlayerSnapshot.brotherhood
    )
    rows = (
        db.session.query(
            PlayerSnapshot.player_id,
            PlayerSnapshot.nickname,
            PlayerSnapshot.level,
            PlayerSnapshot.stat_sum,
            group_column.label("group_name"),
            PlayerSnapshot.batch_at,
        )
        .filter(PlayerSnapshot.batch_at.in_([date_from, date_to]))
        .all()
    )

    current_groups = {}
    previous_groups = {}
    for row in rows:
        if not valid_group_name(row.group_name):
            continue
        name = row.group_name.strip()
        destination = current_groups if row.batch_at == date_to else previous_groups
        destination.setdefault(name, {})[row.player_id] = {
            "id": row.player_id,
            "nickname": row.nickname,
            "level": row.level,
            "stat_sum": row.stat_sum or 0,
        }

    organizations = []
    for name, current_members in current_groups.items():
        previous_members = previous_groups.get(name, {})
        current_ids = set(current_members)
        previous_ids = set(previous_members)
        stat_sum = sum(member["stat_sum"] for member in current_members.values())
        previous_stat_sum = sum(member["stat_sum"] for member in previous_members.values())
        joined = [current_members[player_id] for player_id in current_ids - previous_ids]
        left = [previous_members[player_id] for player_id in previous_ids - current_ids]
        members = sorted(
            current_members.values(),
            key=lambda member: (-member["stat_sum"], member["nickname"].lower()),
        )
        organizations.append(
            {
                "name": name,
                "member_count": len(current_members),
                "member_delta": len(current_members) - len(previous_members),
                "stat_sum": stat_sum,
                "stat_delta": stat_sum - previous_stat_sum,
                "members": members,
                "joined": sorted(joined, key=lambda member: member["nickname"].lower()),
                "left": sorted(left, key=lambda member: member["nickname"].lower()),
            }
        )

    organizations.sort(key=lambda group: (-group["stat_sum"], group["name"].lower()))
    total = len(organizations)
    pages = max(1, (total + per_page - 1) // per_page)
    page = min(page, pages)
    start = (page - 1) * per_page
    return jsonify(
        organizations=organizations[start : start + per_page],
        page=page,
        pages=pages,
        total=total,
        dates=[value.isoformat() for value in dates],
        date_from=date_from.isoformat(),
        date_to=date_to.isoformat(),
        ready=True,
        type=organization_type,
    )


@app.get("/api/status")
def api_status():
    try:
        state = db.session.get(ScanState, 1)
        total_players = Player.query.count()
    except Exception:
        db.session.rollback()
        db.engine.dispose()
        state = db.session.get(ScanState, 1)
        total_players = Player.query.count()
    trusted_dates = completed_snapshot_dates()
    published_at = trusted_dates[0] if trusted_dates else state.finished_at
    return jsonify(
        running=state.running,
        current_player_id=state.current_player_id,
        max_player_id=state.max_player_id,
        found_players=state.found_players,
        started_at=state.started_at.isoformat() if state.started_at else None,
        finished_at=published_at.isoformat() if published_at else None,
        last_error=state.last_error,
        total_players=total_players,
    )


@app.get("/api/attacks")
def api_attacks():
    state = db.session.get(GameAttackState, 1)
    # Бесплатный Render может пропустить задание планировщика после сна.
    # Поэтому запрос с сайта сам просит обновление, если таймеры пустые,
    # устарели или предыдущая попытка завершилась ошибкой.
    request_attack_refresh_if_needed(state)
    return jsonify(
        fetched_at=state.fetched_at.isoformat() if state and state.fetched_at else None,
        game_time=state.game_time.isoformat() if state and state.game_time else None,
        dragon_at=state.dragon_at.isoformat() if state and state.dragon_at else None,
        serpent_at=state.serpent_at.isoformat() if state and state.serpent_at else None,
        dragon_status=state.dragon_raw if state and not state.dragon_at else None,
        serpent_status=state.serpent_raw if state and not state.serpent_at else None,
        error=state.last_error if state else None,
    )


@app.get("/api/player/<int:player_id>")
def api_player_detail(player_id):
    player = db.session.get(Player, player_id)
    if player is None:
        return jsonify(error="Игрок не найден"), 404

    fields = [
        "glory", "power", "defense", "agility", "mastery", "vitality",
        "stat_sum", "wins", "losses", "dragon_wins", "serpent_wins",
        "beasts_killed", "silver_stolen", "silver_lost",
        "crystals_stolen", "crystals_lost",
    ]
    snapshots_query = PlayerSnapshot.query.filter_by(player_id=player_id)
    trusted_dates = completed_snapshot_dates()
    if trusted_dates:
        snapshots_query = snapshots_query.filter(
            PlayerSnapshot.batch_at.in_(trusted_dates)
        )
    snapshots = snapshots_query.order_by(PlayerSnapshot.batch_at.asc()).all()
    history = [
        {
            "date": snapshot.batch_at.isoformat(),
            **{field: getattr(snapshot, field) for field in fields},
        }
        for snapshot in snapshots
    ]
    if not history:
        history = [
            {
                "date": (player.scanned_at or datetime.utcnow()).isoformat(),
                **{
                    field: getattr(player, field, None)
                    for field in fields
                },
            }
        ]
    latest = snapshots[-1] if snapshots else player
    return jsonify(
        id=player.id,
        nickname=player.nickname,
        level=latest.level,
        clan=latest.clan,
        brotherhood=latest.brotherhood,
        last_activity=player.last_activity,
        profile_url=f"https://playwekings.mobi/hero/detail?player={player.id}",
        history=history,
    )


def run_scan():
    from scraper import scan_all_players

    with app.app_context():
        next_scan_delay = None
        state = db.session.get(ScanState, 1)
        if state.running:
            return
        state.running = True
        if state.current_player_id <= 1 or state.started_at is None:
            state.started_at = datetime.now(timezone.utc)
        state.last_error = None
        db.session.commit()
        batch_started_at = state.started_at
        try:
            existing_batch = (
                db.session.query(
                    db.func.count(PlayerSnapshot.id),
                    db.func.min(PlayerSnapshot.player_id),
                    db.func.max(PlayerSnapshot.player_id),
                )
                .filter(PlayerSnapshot.batch_at == batch_started_at)
                .one()
            )
            recent_rows = (
                db.session.query(
                    PlayerSnapshot.batch_at,
                    db.func.count(PlayerSnapshot.id).label("player_count"),
                )
                .filter(PlayerSnapshot.batch_at != batch_started_at)
                .group_by(PlayerSnapshot.batch_at)
                .order_by(PlayerSnapshot.batch_at.desc())
                .limit(7)
                .all()
            )
            recent_counts = sorted(
                row.player_count for row in recent_rows if row.player_count > 0
            )
            baseline = recent_counts[len(recent_counts) // 2] if recent_counts else 0
            existing_count, lowest_id, highest_id = existing_batch
            recovered_complete_batch = bool(
                baseline
                and existing_count >= int(baseline * 0.80)
                and lowest_id is not None and lowest_id <= 100
                and highest_id is not None
                and highest_id >= int(state.max_player_id * 0.90)
            )
            if recovered_complete_batch:
                completed_at = datetime.now(timezone.utc)
                PlayerSnapshot.query.filter_by(batch_at=batch_started_at).update(
                    {PlayerSnapshot.batch_at: completed_at},
                    synchronize_session=False,
                )
                state.current_player_id = 0
                state.found_players = existing_count
                state.finished_at = completed_at
                state.last_error = None
                db.session.commit()
                logger_message = (
                    "Recovered completed snapshot: %s players; "
                    "publishing without a redundant full rescan"
                )
                app.logger.info(logger_message, existing_count)
                return
            scan_all_players(
                db, Player, PlayerSnapshot, ScanState, LowLevelPlayer
            )
            state = db.session.get(ScanState, 1)
            batch_count = PlayerSnapshot.query.filter_by(
                batch_at=batch_started_at
            ).count()
            recent_previous_counts = (
                db.session.query(
                    PlayerSnapshot.batch_at,
                    db.func.count(PlayerSnapshot.id).label("player_count"),
                )
                .filter(PlayerSnapshot.batch_at != batch_started_at)
                .group_by(PlayerSnapshot.batch_at)
                .order_by(PlayerSnapshot.batch_at.desc())
                .limit(7)
                .all()
            )
            # Используем медиану последних отчётов. Старые снимки содержали
            # все ~29 тысяч ID, а новые — только активных игроков 5+ уровня
            # (~7920). Сравнение с историческим максимумом делало любой
            # нормальный новый отчёт «неполным» и запускало бесконечный повтор.
            recent_counts = sorted(
                row.player_count for row in recent_previous_counts
                if row.player_count > 0
            )
            baseline_count = (
                recent_counts[len(recent_counts) // 2] if recent_counts else 0
            )
            minimum_count = int(baseline_count * 0.80)
            if baseline_count and batch_count < minimum_count:
                # Не публикуем подозрительно маленький снимок. Оставляем тот
                # же batch_at и запускаем полный повтор с максимального ID.
                state.current_player_id = state.max_player_id
                state.last_error = (
                    f"Неполный снимок: найдено {batch_count} игроков, "
                    f"нужно не менее {minimum_count} относительно последних "
                    "отчётов. Сканирование повторится."
                )
                db.session.commit()
                raise RuntimeError(state.last_error)
            completed_at = datetime.now(timezone.utc)
            # Название готового отчёта определяется днём завершения полного
            # сбора, а не днём его запуска.
            PlayerSnapshot.query.filter_by(batch_at=batch_started_at).update(
                {PlayerSnapshot.batch_at: completed_at},
                synchronize_session=False,
            )
            state.finished_at = completed_at
            state.last_error = None
            db.session.commit()
        except Exception as exc:
            db.session.rollback()
            app.logger.exception("Wekings scan failed")
            try:
                db.engine.dispose()
                state = db.session.get(ScanState, 1)
                state.last_error = str(exc)[:2000]
                db.session.commit()
            except Exception:
                db.session.rollback()
            # При временном обрыве базы продолжаем с последнего сохранённого
            # игрока через 5 минут, не создавая частых повторов.
            next_scan_delay = 300
        finally:
            db.session.rollback()
            try:
                state = db.session.get(ScanState, 1)
                state.running = False
                db.session.commit()
            except Exception:
                db.session.rollback()
                db.engine.dispose()
            if next_scan_delay is not None:
                threading.Timer(next_scan_delay, start_scan_thread).start()


def start_scan_thread():
    threading.Thread(target=run_scan, daemon=True, name="wekings-scan").start()


_attack_lock = threading.Lock()
_attack_refresh_lock = threading.Lock()
_last_attack_refresh_request = None


def request_attack_refresh_if_needed(state):
    global _last_attack_refresh_request

    now = datetime.now(timezone.utc)
    fetched_at = state.fetched_at if state else None
    if fetched_at and fetched_at.tzinfo is None:
        fetched_at = fetched_at.replace(tzinfo=timezone.utc)
    stale = not fetched_at or now - fetched_at > timedelta(minutes=15)
    missing = not state or not state.dragon_at or not state.serpent_at
    failed = bool(state and state.last_error)
    event_expired = bool(
        state
        and (
            (state.dragon_at and _as_utc(state.dragon_at) <= now)
            or (state.serpent_at and _as_utc(state.serpent_at) <= now)
        )
    )
    if not (stale or missing or failed or event_expired):
        return

    # Не чаще одного принудительного запроса в 5 минут на один процесс.
    with _attack_refresh_lock:
        if (
            _last_attack_refresh_request is not None
            and now - _last_attack_refresh_request < timedelta(minutes=5)
        ):
            return
        _last_attack_refresh_request = now
    start_attack_thread()


def update_attack_schedule():
    if not _attack_lock.acquire(blocking=False):
        return
    try:
        from scraper import fetch_attack_schedule

        with app.app_context():
            state = db.session.get(GameAttackState, 1)
            try:
                result = fetch_attack_schedule()
                for field in (
                    "fetched_at", "game_time", "dragon_at", "serpent_at",
                    "dragon_raw", "serpent_raw",
                ):
                    setattr(state, field, result.get(field))
                state.last_error = None
                db.session.commit()
            except Exception as exc:
                db.session.rollback()
                app.logger.exception("Wekings attack schedule update failed")
                state = db.session.get(GameAttackState, 1)
                # Показываем время именно последней попытки, а не старую дату.
                state.fetched_at = datetime.now(timezone.utc)
                # Никогда не показываем вчерашнее время как актуальное.
                state.dragon_at = None
                state.serpent_at = None
                state.dragon_raw = None
                state.serpent_raw = None
                state.last_error = str(exc)[:1000]
                db.session.commit()
    finally:
        _attack_lock.release()


def start_attack_thread():
    threading.Thread(
        target=update_attack_schedule,
        daemon=True,
        name="wekings-attacks",
    ).start()


def start_attack_on_boot_if_needed():
    with app.app_context():
        state = db.session.get(GameAttackState, 1)
        now = datetime.now(timezone.utc)
        fetched_at = _as_utc(state.fetched_at) if state and state.fetched_at else None
        needs_update = (
            not fetched_at
            or now - fetched_at >= timedelta(minutes=15)
            or not state.dragon_at
            or not state.serpent_at
            or _as_utc(state.dragon_at) <= now
            or _as_utc(state.serpent_at) <= now
        )
    if needs_update:
        start_attack_thread()


def start_scan_on_boot_if_needed():
    """На старте возобновляет прерванный сбор или запускает самый первый."""
    with app.app_context():
        state = db.session.get(ScanState, 1)
        has_snapshots = db.session.query(PlayerSnapshot.id).first() is not None
        should_start = not has_snapshots or state.current_player_id > 1
    if should_start:
        start_scan_thread()


if os.getenv("SCAN_ENABLED", "true").lower() == "true":
    scheduler = BackgroundScheduler(timezone="Europe/Chisinau")
    scheduler.start()
    for job_id, hour, minute in (
        ("wekings-night-scan", 0, 15),
        ("wekings-day-scan", 12, 15),
    ):
        scheduler.add_job(
            start_scan_thread,
            "cron",
            hour=hour,
            minute=minute,
            id=job_id,
            replace_existing=True,
            coalesce=True,
            max_instances=1,
            misfire_grace_time=900,
        )
    scheduler.add_job(
        start_attack_thread,
        "cron",
        hour=0,
        minute=5,
        id="wekings-daily-attacks",
        replace_existing=True,
        coalesce=True,
        max_instances=1,
        misfire_grace_time=21600,
    )
    scheduler.add_job(
        start_attack_on_boot_if_needed,
        "interval",
        minutes=15,
        id="wekings-attack-retry",
        replace_existing=True,
        coalesce=True,
        max_instances=1,
    )
    # Страховочная проверка: если таймер повтора потерялся после сна или
    # перезапуска бесплатного Render, незавершённый снимок возобновится сам.
    scheduler.add_job(
        start_scan_on_boot_if_needed,
        "interval",
        minutes=10,
        id="wekings-scan-recovery",
        replace_existing=True,
        coalesce=True,
        max_instances=1,
    )
    if os.getenv("START_SCAN_ON_BOOT", "true").lower() == "true":
        scheduler.add_job(
            start_scan_on_boot_if_needed,
            "date",
            run_date=datetime.now(timezone.utc) + timedelta(seconds=30),
            id="wekings-first-scan",
            replace_existing=True,
        )
        scheduler.add_job(
            start_attack_on_boot_if_needed,
            "date",
            run_date=datetime.now(timezone.utc) + timedelta(seconds=5),
            id="wekings-first-attacks",
            replace_existing=True,
        )


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", "5000")), debug=True)
