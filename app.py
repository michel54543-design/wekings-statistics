from __future__ import annotations

import os
import threading
from datetime import datetime, timedelta, timezone

from apscheduler.schedulers.background import BackgroundScheduler
from flask import Flask, jsonify, render_template, request
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import and_
from sqlalchemy.orm import aliased


def normalize_database_url(value: str) -> str:
    if value.startswith("postgres://"):
        return value.replace("postgres://", "postgresql://", 1)
    return value


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
        db.session.add(ScanState(id=1))
    else:
        # Render can stop the process during a scan. A database flag from that
        # dead process must not block the new worker from resuming.
        scan_state.running = False
    db.session.commit()
    duplicate_groups = (
        db.session.query(
            PlayerSnapshot.batch_at,
            PlayerSnapshot.nickname,
            PlayerSnapshot.level,
            db.func.count(PlayerSnapshot.id),
        )
        .group_by(
            PlayerSnapshot.batch_at,
            PlayerSnapshot.nickname,
            PlayerSnapshot.level,
        )
        .having(db.func.count(PlayerSnapshot.id) > 1)
        .all()
    )
    for batch_at, nickname, level, _ in duplicate_groups:
        duplicates = (
            PlayerSnapshot.query.filter_by(
                batch_at=batch_at,
                nickname=nickname,
                level=level,
            )
            .order_by(PlayerSnapshot.player_id.asc())
            .all()
        )
        for duplicate in duplicates[1:]:
            db.session.delete(duplicate)
    if duplicate_groups:
        db.session.commit()
    legacy_duplicate_groups = (
        db.session.query(
            Player.nickname,
            Player.level,
            Player.glory,
            db.func.count(Player.id),
        )
        .group_by(Player.nickname, Player.level, Player.glory)
        .having(db.func.count(Player.id) > 1)
        .all()
    )
    for nickname, level, glory, _ in legacy_duplicate_groups:
        duplicates = (
            Player.query.filter_by(
                nickname=nickname,
                level=level,
                glory=glory,
            )
            .order_by(Player.id.asc())
            .all()
        )
        for duplicate in duplicates[1:]:
            db.session.delete(duplicate)
    if legacy_duplicate_groups:
        db.session.commit()


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
    scan_state = db.session.get(ScanState, 1)
    dates_query = db.session.query(PlayerSnapshot.batch_at).distinct()
    if scan_state.finished_at:
        # Публикуем только полностью завершённые снимки. Текущий частичный
        # сбор станет доступен сразу после проверки последнего игрока.
        dates_query = dates_query.filter(PlayerSnapshot.batch_at <= scan_state.finished_at)
    dates = [
        row[0]
        for row in dates_query.order_by(PlayerSnapshot.batch_at.desc())
        .limit(100)
        .all()
    ]
    if not dates:
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
        )

    def parse_date(value, fallback):
        if not value:
            return fallback
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return fallback

    date_to = parse_date(request.args.get("to"), dates[0])
    if mode == "best":
        cutoff = date_to - timedelta(days=30)
        eligible = [value for value in dates if cutoff <= value <= date_to]
        date_from = eligible[-1] if eligible else dates[-1]
    else:
        date_from = parse_date(
            request.args.get("from"),
            dates[1] if len(dates) > 1 else dates[0],
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
    return jsonify(
        running=state.running,
        current_player_id=state.current_player_id,
        max_player_id=state.max_player_id,
        found_players=state.found_players,
        started_at=state.started_at.isoformat() if state.started_at else None,
        finished_at=state.finished_at.isoformat() if state.finished_at else None,
        last_error=state.last_error,
        total_players=total_players,
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
    scan_state = db.session.get(ScanState, 1)
    if scan_state.finished_at:
        snapshots_query = snapshots_query.filter(
            PlayerSnapshot.batch_at <= scan_state.finished_at
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
        state = db.session.get(ScanState, 1)
        if state.running:
            return
        state.running = True
        if state.current_player_id <= 1 or state.started_at is None:
            state.started_at = datetime.now(timezone.utc)
        state.last_error = None
        db.session.commit()
        try:
            scan_all_players(db, Player, PlayerSnapshot, ScanState)
            state = db.session.get(ScanState, 1)
            state.finished_at = datetime.now(timezone.utc)
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
            threading.Timer(300, start_scan_thread).start()
        finally:
            db.session.rollback()
            try:
                state = db.session.get(ScanState, 1)
                state.running = False
                db.session.commit()
            except Exception:
                db.session.rollback()
                db.engine.dispose()


def start_scan_thread():
    threading.Thread(target=run_scan, daemon=True, name="wekings-scan").start()


if os.getenv("SCAN_ENABLED", "true").lower() == "true":
    scheduler = BackgroundScheduler(timezone="Europe/Chisinau")
    scheduler.add_job(
        start_scan_thread,
        "interval",
        hours=float(os.getenv("SCAN_INTERVAL_HOURS", "24")),
        id="wekings-scan",
        max_instances=1,
        coalesce=True,
    )
    scheduler.start()
    if os.getenv("START_SCAN_ON_BOOT", "true").lower() == "true":
        scheduler.add_job(
            start_scan_thread,
            "date",
            run_date=datetime.now(timezone.utc) + timedelta(seconds=20),
            id="wekings-first-scan",
            replace_existing=True,
        )


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", "5000")), debug=True)
