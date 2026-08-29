from __future__ import annotations

import os
import json
import threading
import time
import hashlib
import hmac
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from apscheduler.schedulers.background import BackgroundScheduler
from flask import Flask, jsonify, render_template, render_template_string, request, redirect, Response, session
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
# Секрет для подписанной служебной cookie выводится из WEKINGS_PASSWORD.
# Сам пароль в cookie и HTML никогда не сохраняется.
app.secret_key = hashlib.sha256((os.getenv("WEKINGS_PASSWORD", "") + "|wekings-admin-session").encode()).digest()
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
    beasts_killed = db.Column(db.BigInteger)
    silver_stolen = db.Column(db.BigInteger)
    silver_lost = db.Column(db.BigInteger)
    crystals_stolen = db.Column(db.BigInteger)
    crystals_lost = db.Column(db.BigInteger)
    bandit_wins = db.Column(db.BigInteger)
    mine = db.Column(db.BigInteger)
    crusade = db.Column(db.BigInteger)
    quests = db.Column(db.BigInteger)
    pet_fights = db.Column(db.BigInteger)
    pet_kills = db.Column(db.BigInteger)
    garden = db.Column(db.BigInteger)
    goblins = db.Column(db.BigInteger)
    lord_wins = db.Column(db.BigInteger)
    undead_wins = db.Column(db.BigInteger)
    heroes_wins = db.Column(db.BigInteger)
    serpent_fights = db.Column(db.BigInteger)
    sent_gifts = db.Column(db.BigInteger)
    fishing = db.Column(db.BigInteger)
    dragon_kills = db.Column(db.BigInteger)
    serpent_kills = db.Column(db.BigInteger)
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
    weather_at = db.Column(db.DateTime(timezone=True))
    weather_raw = db.Column(db.String(240))
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
    bandit_wins = db.Column(db.BigInteger)
    mine = db.Column(db.BigInteger)
    crusade = db.Column(db.BigInteger)
    quests = db.Column(db.BigInteger)
    pet_fights = db.Column(db.BigInteger)
    pet_kills = db.Column(db.BigInteger)
    garden = db.Column(db.BigInteger)
    goblins = db.Column(db.BigInteger)
    lord_wins = db.Column(db.BigInteger)
    undead_wins = db.Column(db.BigInteger)
    heroes_wins = db.Column(db.BigInteger)
    serpent_fights = db.Column(db.BigInteger)
    sent_gifts = db.Column(db.BigInteger)
    fishing = db.Column(db.BigInteger)
    dragon_kills = db.Column(db.BigInteger)
    serpent_kills = db.Column(db.BigInteger)
    clan = db.Column(db.String(160))
    brotherhood = db.Column(db.String(160))


with app.app_context():
    db.create_all()
    # Добавляем поля прогноза Монаха в существующую БД без удаления данных.
    try:
        inspector = db.inspect(db.engine)
        existing_attack = {col["name"] for col in inspector.get_columns("game_attack_state")}
        if "weather_at" not in existing_attack:
            db.session.execute(db.text('ALTER TABLE game_attack_state ADD COLUMN weather_at TIMESTAMP'))
        if "weather_raw" not in existing_attack:
            db.session.execute(db.text('ALTER TABLE game_attack_state ADD COLUMN weather_raw VARCHAR(240)'))
        db.session.commit()
    except Exception:
        db.session.rollback()
        app.logger.exception("Could not add Monk weather columns")

    # Добавляем новые поля API в существующую БД без удаления истории.
    api_metric_columns = [
        "beasts_killed", "silver_stolen", "silver_lost", "crystals_stolen", "crystals_lost",
        "bandit_wins", "mine", "crusade", "quests", "pet_fights", "pet_kills",
        "garden", "goblins", "lord_wins", "undead_wins", "heroes_wins",
        "serpent_fights", "sent_gifts", "fishing", "dragon_kills", "serpent_kills",
    ]
    try:
        inspector = db.inspect(db.engine)
        for table_name in ("player", "player_snapshot"):
            existing = {col["name"] for col in inspector.get_columns(table_name)}
            for column_name in api_metric_columns:
                if column_name not in existing:
                    db.session.execute(db.text(
                        f'ALTER TABLE {table_name} ADD COLUMN {column_name} BIGINT'
                    ))
        db.session.commit()
    except Exception:
        db.session.rollback()
        app.logger.exception("Could not add ForGlory API metric columns")

    # Индексы для самых частых запросов главной страницы. Они не меняют
    # данные и безопасно создаются повторно при каждом deploy.
    try:
        db.session.execute(db.text(
            "CREATE INDEX IF NOT EXISTS ix_snapshot_batch_power "
            "ON player_snapshot (batch_at, power DESC)"
        ))
        db.session.execute(db.text(
            "CREATE INDEX IF NOT EXISTS ix_snapshot_batch_level_power "
            "ON player_snapshot (batch_at, level, power DESC)"
        ))
        db.session.commit()
    except Exception:
        db.session.rollback()
        app.logger.exception("Could not create optional performance indexes")
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
    "bandit_wins": "bandit_wins",
    "mine": "mine",
    "crusade": "crusade",
    "quests": "quests",
    "pet_fights": "pet_fights",
    "pet_kills": "pet_kills",
    "garden": "garden",
    "goblins": "goblins",
    "lord_wins": "lord_wins",
    "undead_wins": "undead_wins",
    "heroes_wins": "heroes_wins",
    "serpent_fights": "serpent_fights",
    "sent_gifts": "sent_gifts",
    "fishing": "fishing",
    "dragon_kills": "dragon_kills",
    "serpent_kills": "serpent_kills",
}


@app.get("/")
def index():
    return render_template("index.html")


@app.get("/health")
def health():
    return jsonify(ok=True)


WEKINGS_LOGIN_HTML = r"""
<!doctype html><html lang="ru"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Админ · WEKINGS</title><style>body{font-family:Arial,sans-serif;max-width:560px;margin:40px auto;padding:0 18px;background:#111;color:#eee}input,button{width:100%;box-sizing:border-box;padding:12px;margin:7px 0;border-radius:8px;border:1px solid #555}button{font-weight:700;cursor:pointer}.ok{color:#78d878}.err{color:#ff7777}.hint{color:#bbb;line-height:1.45}.captcha{display:block;max-width:100%;margin:15px auto;background:#fff;border-radius:8px}</style></head>
<body><h2>Закрытая авторизация WEKINGS</h2>
{% if ok %}<p class="ok">✓ Сессия активна. Ничего делать не нужно.</p><form method="post" action="/admin/wekings-scan-now"><button>Обновить статистику сейчас</button></form>{% else %}<p class="err">Сессия WEKINGS неактивна.</p><p class="hint">Логин и пароль берутся сервером из секретов Render и на эту страницу не передаются. Вам нужно только решить CAPTCHA.</p>{% endif %}
{% if error %}<p class="err">{{ error }}</p>{% endif %}{% if saved %}<p class="ok">✓ Вход выполнен. API вернул игроков: {{ saved }}</p>{% endif %}
{% if not ok %}{% if captcha %}<img class="captcha" src="{{ captcha }}" alt="CAPTCHA"><form method="post"><input type="hidden" name="action" value="login"><input name="captcha" autocomplete="off" placeholder="Введите код с картинки" required><button>Войти в WEKINGS</button></form>{% endif %}<form method="post"><input type="hidden" name="action" value="captcha"><button>Получить новую CAPTCHA</button></form>{% endif %}
<p><a href="/" style="color:#9cf">← На сайт статистики</a></p></body></html>
"""


def _admin_allowed():
    return session.get("wekings_admin") is True


def _check_game_password(value: str) -> bool:
    expected = os.getenv("WEKINGS_PASSWORD", "")
    return bool(expected and hmac.compare_digest(value or "", expected))


ADMIN_UNLOCK_HTML = r"""
<!doctype html><html lang="ru"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Вход · WEKINGS</title><style>body{font-family:Arial,sans-serif;max-width:560px;margin:40px auto;padding:0 18px;background:#111;color:#eee}input,button{width:100%;box-sizing:border-box;padding:12px;margin:7px 0;border-radius:8px;border:1px solid #555}button{font-weight:700;cursor:pointer}.err{color:#ff7777}.hint{color:#bbb;line-height:1.45}</style></head>
<body><h2>Закрытая страница WEKINGS</h2><p class="hint">Введите только пароль от вашего аккаунта WEKINGS.</p>
{% if error %}<p class="err">{{ error }}</p>{% endif %}
<form method="post"><input type="password" name="game_password" autocomplete="current-password" placeholder="Пароль WEKINGS" required><button>Войти</button></form>
<p><a href="/" style="color:#9cf">← На сайт статистики</a></p></body></html>
"""


def _admin_required():
    if _admin_allowed():
        return None
    return redirect("/wekings-login")


@app.route("/wekings-login", methods=["GET", "POST"])
def wekings_login():
    if not _admin_allowed():
        error = None
        if request.method == "POST":
            if _check_game_password(request.form.get("game_password", "")):
                session["wekings_admin"] = True
                return redirect("/admin/wekings-login")
            error = "Неверный пароль WEKINGS"
        return render_template_string(ADMIN_UNLOCK_HTML, error=error)
    return redirect("/admin/wekings-login")


@app.route("/admin/wekings-login", methods=["GET", "POST"])
def admin_wekings_login():
    denied = _admin_required()
    if denied: return denied
    from scraper import api_auth_status, begin_password_login, finish_password_login
    error = None; saved = None; captcha = None
    ok = api_auth_status()
    if request.method == "POST" and not ok:
        try:
            if request.form.get("action") == "login":
                saved = finish_password_login(request.form.get("captcha", ""))
                ok = api_auth_status()
            else:
                captcha = begin_password_login()
        except Exception as exc:
            error = str(exc)
    return render_template_string(WEKINGS_LOGIN_HTML, ok=ok, error=error, saved=saved, captcha=captcha)


@app.post("/admin/wekings-scan-now")
def admin_wekings_scan_now():
    denied = _admin_required()
    if denied: return denied
    state = db.session.get(ScanState, 1)
    if not state.running:
        start_scan_thread()
    # Ручное обновление статистики также принудительно обновляет Монаха.
    # Это исключение из суточного лимита и срабатывает только по нажатию пользователя.
    start_attack_thread()

    return redirect("/admin/wekings-login")


@app.post("/wekings-scan-now")
def old_wekings_scan_now():
    denied = _admin_required()
    if denied: return denied
    return redirect("/admin/wekings-login")


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
                "bandit_wins": player.bandit_wins,
                "mine": player.mine,
                "crusade": player.crusade,
                "quests": player.quests,
                "pet_fights": player.pet_fights,
                "pet_kills": player.pet_kills,
                "garden": player.garden,
                "goblins": player.goblins,
                "lord_wins": player.lord_wins,
                "undead_wins": player.undead_wins,
                "heroes_wins": player.heroes_wins,
                "serpent_fights": player.serpent_fights,
                "sent_gifts": player.sent_gifts,
                "fishing": player.fishing,
                "dragon_kills": player.dragon_kills,
                "serpent_kills": player.serpent_kills,
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
                "bandit_wins": p.bandit_wins,
                "mine": p.mine,
                "crusade": p.crusade,
                "quests": p.quests,
                "pet_fights": p.pet_fights,
                "pet_kills": p.pet_kills,
                "garden": p.garden,
                "goblins": p.goblins,
                "lord_wins": p.lord_wins,
                "undead_wins": p.undead_wins,
                "heroes_wins": p.heroes_wins,
                "serpent_fights": p.serpent_fights,
                "sent_gifts": p.sent_gifts,
                "fishing": p.fishing,
                "dragon_kills": p.dragon_kills,
                "serpent_kills": p.serpent_kills,
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



# Готовые результаты "Жизнь WEKINGS" держим в памяти до следующего снимка.
# Поэтому посетители не заставляют сервер повторно пересчитывать тысячи игроков.
_life_cache = {}
_life_cache_lock = threading.Lock()

def _life_cache_version():
    state = db.session.get(ScanState, 1)
    return state.finished_at.isoformat() if state and state.finished_at else "none"

def _life_cache_get(key):
    version = _life_cache_version()
    with _life_cache_lock:
        item = _life_cache.get(key)
        return item["data"] if item and item["version"] == version else None

def _life_cache_put(key, data):
    with _life_cache_lock:
        _life_cache[key] = {"version": _life_cache_version(), "data": data}
    return data

LIFE_METRICS = [
    ("power", "Сила", "⚡"), ("stat_sum", "Сумма характеристик", "💪"),
    ("glory", "Слава", "🏆"), ("bandit_wins", "Победы над наемниками", "⚔️"),
    ("dragon_wins", "Победы над Драконом", "🐉"), ("serpent_wins", "Победы над Змеем", "🐍"),
    ("silver_stolen", "Награблено серебра", "💰"), ("crystals_stolen", "Награблено кристаллов", "💎"),
    ("mine", "Шахта", "⛏️"), ("crusade", "Походы", "🛡️"), ("quests", "Задания", "📜"),
    ("goblins", "Гоблины", "👺"), ("lord_wins", "Победы над Владыкой", "👑"),
    ("undead_wins", "Победы над нежитью", "☠️"), ("fishing", "Рыбалка", "🎣"),
]

def _life_snapshot_dates():
    state = db.session.get(ScanState, 1)
    query = db.session.query(PlayerSnapshot.batch_at).distinct()
    if state and state.finished_at:
        query = query.filter(PlayerSnapshot.batch_at <= state.finished_at)
    return [row.batch_at for row in query.order_by(PlayerSnapshot.batch_at.desc()).limit(300).all()]

@app.get("/api/life")
def api_life():
    period = request.args.get("period", "now")
    cache_key = f"life:{period}"
    cached = _life_cache_get(cache_key)
    if cached is not None:
        return jsonify(cached)
    dates = _life_snapshot_dates()
    if len(dates) < 2:
        return jsonify(ready=False, events=[], heroes=[], period=period)
    latest = dates[0]
    if period == "today":
        same_day = [d for d in dates if moldova_date(d) == moldova_date(latest)]
        previous = same_day[-1] if len(same_day) > 1 else dates[1]
    elif period == "7d":
        target = _as_utc(latest) - timedelta(days=7)
        older = [d for d in dates[1:] if _as_utc(d) <= target]
        previous = older[0] if older else dates[-1]
    else:
        previous = dates[1]

    current_rows = PlayerSnapshot.query.filter_by(batch_at=latest).all()
    before = {p.player_id: p for p in PlayerSnapshot.query.filter_by(batch_at=previous).all()}
    events, heroes = [], []

    for p in current_rows:
        old = before.get(p.player_id)
        if not old: continue
        if p.brotherhood != old.brotherhood:
            if p.brotherhood and not old.brotherhood: text=f"вступил в братство «{p.brotherhood}»"
            elif old.brotherhood and not p.brotherhood: text=f"покинул братство «{old.brotherhood}»"
            else: text=f"перешёл из «{old.brotherhood}» в «{p.brotherhood}»"
            events.append({"kind":"brotherhood","icon":"🛡️","player_id":p.player_id,"nickname":p.nickname,"text":text,"score":9*10**14})
        if p.clan != old.clan:
            if p.clan and not old.clan: text=f"вступил в клан «{p.clan}»"
            elif old.clan and not p.clan: text=f"покинул клан «{old.clan}»"
            else: text=f"сменил клан «{old.clan}» → «{p.clan}»"
            events.append({"kind":"clan","icon":"♜","player_id":p.player_id,"nickname":p.nickname,"text":text,"score":8*10**14})

    for key,label,icon in LIFE_METRICS:
        changes=[]
        for p in current_rows:
            old=before.get(p.player_id)
            if not old: continue
            a=getattr(p,key,None); b=getattr(old,key,None)
            if a is None or b is None: continue
            delta=int(a)-int(b)
            if delta>0: changes.append((delta,p))
        changes.sort(key=lambda x:x[0], reverse=True)
        if changes:
            delta,p=changes[0]
            heroes.append({"metric":key,"label":label,"icon":icon,"player_id":p.player_id,"nickname":p.nickname,"gain":delta})
            for delta,p in changes[:3]:
                events.append({"kind":key,"icon":icon,"player_id":p.player_id,"nickname":p.nickname,
                               "text":f"{label}: +{delta:,}".replace(","," "),"score":delta})

            # Life feed: organization membership changes are intentionally hidden.
            # We keep their calculation intact and only exclude them from the response,
            # so the Life API remains stable.
            events = [e for e in events if e.get("kind") not in {"clan", "brotherhood"}]

    events.sort(key=lambda e:e["score"], reverse=True)
    compact=[]; seen=set()
    for event in events:
        k=(event["kind"],event["player_id"],event["text"])
        if k in seen: continue
        seen.add(k); event.pop("score",None); compact.append(event)
        if len(compact)>=40: break
    heroes.sort(key=lambda h:h["gain"], reverse=True)
    payload = dict(ready=True, period=period, from_date=previous.isoformat(), to_date=latest.isoformat(),
                   events=compact, heroes=heroes[:8])
    _life_cache_put(cache_key, payload)
    return jsonify(payload)



YESTERDAY_TOP_METRICS = [
    # Все числовые накопительные показатели, которые сохраняются в дневных снимках.
    ("glory", "Слава", "🏆"),
    ("wins", "Победы", "🏅"),
    ("losses", "Поражения", "💥"),
    ("dragon_wins", "Победы над Драконом", "🐉"),
    ("serpent_wins", "Победы над Змеем", "🐍"),
    ("beasts_killed", "Убито зверей", "🐾"),
    ("silver_stolen", "Украдено серебра", "💰"),
    ("silver_lost", "Потеряно серебра", "🪙"),
    ("crystals_stolen", "Украдено кристаллов", "💎"),
    ("crystals_lost", "Потеряно кристаллов", "🔹"),
    ("bandit_wins", "Победы над наёмниками", "⚔️"),
    ("mine", "Шахта", "⛏️"),
    ("crusade", "Походы", "🛡️"),
    ("quests", "Задания", "📜"),
    ("pet_fights", "Бои питомцев", "🐺"),
    ("pet_kills", "Победы питомцев", "🐾"),
    ("garden", "Участок", "🌱"),
    ("goblins", "Гоблины", "👺"),
    ("lord_wins", "Победы над Владыкой", "👑"),
    ("undead_wins", "Победы над нежитью", "☠️"),
    ("heroes_wins", "Победы над героями", "🗡️"),
    ("serpent_fights", "Бои со Змеем", "🌊"),
    ("sent_gifts", "Отправлено подарков", "🎁"),
    ("fishing", "Рыбалка", "🎣"),
    ("dragon_kills", "Убийства Дракона", "🔥"),
    ("serpent_kills", "Убийства Змея", "🌊"),
]

@app.get("/api/today-tops")
def api_today_tops():
    # Топы текущего дня: первый завершённый снимок сегодня -> последний завершённый снимок сегодня.
    # Используем тот же набор категорий, что и в «Топы вчера».
    dates = _life_snapshot_dates()
    today = moldova_date(datetime.now(timezone.utc))
    today_dates = sorted([dt for dt in dates if moldova_date(dt) == today])
    if len(today_dates) < 2:
        return jsonify(ready=False, tops=[], date=today.isoformat())

    before_at = today_dates[0]
    current_at = today_dates[-1]
    current = PlayerSnapshot.query.filter_by(batch_at=current_at).all()
    before = {x.player_id: x for x in PlayerSnapshot.query.filter_by(batch_at=before_at).all()}

    tops = []
    first_counts = {}
    first_total_gain = {}
    first_players = {}
    for key, label, icon in YESTERDAY_TOP_METRICS:
        best = None
        for player in current:
            old = before.get(player.player_id)
            if not old:
                continue
            a, b = getattr(player, key, None), getattr(old, key, None)
            if a is None or b is None:
                continue
            gain = int(a) - int(b)
            if gain <= 0:
                continue
            if best is None or gain > best[0]:
                best = (gain, player)
        if best:
            gain, player = best
            tops.append({"metric": key, "label": label, "icon": icon, "player_id": player.player_id, "nickname": player.nickname, "gain": gain})
            first_counts[player.player_id] = first_counts.get(player.player_id, 0) + 1
            first_total_gain[player.player_id] = first_total_gain.get(player.player_id, 0) + gain
            first_players[player.player_id] = player.nickname

    hero = None
    if first_counts:
        pid = max(first_counts, key=lambda x: (first_counts[x], first_total_gain[x]))
        hero = {"player_id": pid, "nickname": first_players[pid], "first_places": first_counts[pid]}

    return jsonify(ready=True, date=today.isoformat(), from_date=before_at.isoformat(),
                   to_date=current_at.isoformat(), tops=tops, hero=hero)

@app.get("/api/yesterday-tops")
def api_yesterday_tops():
    cache_key = "yesterday:tops"
    cached = _life_cache_get(cache_key)
    if cached is not None:
        return jsonify(cached)

    dates = _life_snapshot_dates()
    if len(dates) < 2:
        return jsonify(ready=False, tops=[])

    # "Топы вчера" должны считать именно завершившиеся календарные сутки:
    # первый готовый снимок СЕГОДНЯ минус первый готовый снимок ВЧЕРА.
    # Раньше код при наличии сегодняшнего снимка сравнивал ВЧЕРА с ПОЗАВЧЕРА,
    # поэтому результаты были сдвинуты на один день.
    by_day = {}
    for dt in sorted(dates):
        day = moldova_date(dt)
        # sorted() идёт от старых к новым, поэтому сохраняем первый снимок дня
        # (обычно ночной запуск около 00:15), ближайший к границе суток.
        if day not in by_day:
            by_day[day] = dt

    today = moldova_date(datetime.now(timezone.utc))
    yesterday_day = today - timedelta(days=1)
    if today not in by_day or yesterday_day not in by_day:
        # Пока сегодняшнего контрольного снимка нет, вчерашние сутки ещё нельзя
        # посчитать корректно. Лучше показать "недостаточно данных", чем топы
        # позавчера под подписью "вчера".
        return jsonify(ready=False, tops=[], date=yesterday_day.isoformat())

    before_at = by_day[yesterday_day]
    current_at = by_day[today]

    current = PlayerSnapshot.query.filter_by(batch_at=current_at).all()
    before = {x.player_id: x for x in PlayerSnapshot.query.filter_by(batch_at=before_at).all()}
    tops = []
    first_counts = {}
    first_total_gain = {}
    first_players = {}

    for key, label, icon in YESTERDAY_TOP_METRICS:
        best = None
        for player in current:
            old = before.get(player.player_id)
            if not old:
                continue
            a, b = getattr(player, key, None), getattr(old, key, None)
            if a is None or b is None:
                continue
            gain = int(a) - int(b)
            if gain <= 0:
                continue
            if best is None or gain > best[0]:
                best = (gain, player)
        if best:
            gain, player = best
            tops.append({"metric": key, "label": label, "icon": icon, "player_id": player.player_id, "nickname": player.nickname, "gain": gain})
            first_counts[player.player_id] = first_counts.get(player.player_id, 0) + 1
            first_total_gain[player.player_id] = first_total_gain.get(player.player_id, 0) + gain
            first_players[player.player_id] = player.nickname

    hero = None
    if first_counts:
        pid = max(first_counts, key=lambda x: (first_counts[x], first_total_gain[x]))
        hero = {"player_id": pid, "nickname": first_players[pid], "first_places": first_counts[pid]}

    payload = {
        "ready": True, "date": yesterday_day.isoformat(),
        "from_date": before_at.isoformat(), "to_date": current_at.isoformat(),
        "tops": tops, "hero": hero,
    }
    _life_cache_put(cache_key, payload)
    return jsonify(payload)

@app.get("/api/life-summary")
def api_life_summary():
    cached = _life_cache_get("life:summary")
    if cached is not None:
        return jsonify(cached)
    dates = _life_snapshot_dates()
    if len(dates) < 2:
        return jsonify(ready=False)

    latest = dates[0]
    same_day = [d for d in dates if moldova_date(d) == moldova_date(latest)]
    day_start = same_day[-1] if len(same_day) > 1 else dates[1]

    current = PlayerSnapshot.query.filter_by(batch_at=latest).all()
    old_rows = PlayerSnapshot.query.filter_by(batch_at=day_start).all()
    old = {p.player_id: p for p in old_rows}

    levels = brotherhood_changes = clan_changes = 0
    total_power_gain = 0
    activity = []
    brotherhood_contributors = []
    clan_contributors = []

    for p in current:
        b = old.get(p.player_id)
        if not b:
            continue
        if p.level is not None and b.level is not None and p.level > b.level:
            levels += 1
        if p.brotherhood != b.brotherhood:
            brotherhood_changes += 1
        if p.clan != b.clan:
            clan_changes += 1

        power_gain = max(0, int(p.power or 0) - int(b.power or 0))
        stat_gain = max(0, int(p.stat_sum or 0) - int(b.stat_sum or 0))
        wins_gain = max(0, int(p.wins or 0) - int(b.wins or 0))
        bandit_gain = max(0, int(p.bandit_wins or 0) - int(b.bandit_wins or 0))
        dragon_gain = max(0, int(p.dragon_wins or 0) - int(b.dragon_wins or 0))
        serpent_gain = max(0, int(p.serpent_wins or 0) - int(b.serpent_wins or 0))
        quests_gain = max(0, int(p.quests or 0) - int(b.quests or 0))
        mine_gain = max(0, int(p.mine or 0) - int(b.mine or 0))
        total_power_gain += power_gain

        # TOP вкладов: прирост суммы характеристик игрока, зачисленный его
        # текущему братству/клану. Игрок должен состоять в этой организации
        # и в начале периода, чтобы переход между организациями не выглядел
        # как искусственный "вклад".
        if stat_gain > 0:
            if valid_group_name(p.brotherhood) and p.brotherhood == b.brotherhood:
                brotherhood_contributors.append({
                    "player_id": p.player_id, "nickname": p.nickname,
                    "organization": p.brotherhood.strip(), "gain": stat_gain,
                })
            if valid_group_name(p.clan) and p.clan == b.clan:
                clan_contributors.append({
                    "player_id": p.player_id, "nickname": p.nickname,
                    "organization": p.clan.strip(), "gain": stat_gain,
                })

        # Weighted only to select an interesting "hero", not a game score.
        score = (power_gain + stat_gain * 5 + wins_gain * 5000 +
                 bandit_gain * 10000 + dragon_gain * 100000 +
                 serpent_gain * 100000 + quests_gain * 1000 + mine_gain * 1000)
        if score > 0:
            activity.append({
                "player_id": p.player_id, "nickname": p.nickname, "score": score,
                "power_gain": power_gain, "stat_gain": stat_gain,
                "wins_gain": wins_gain, "bandit_gain": bandit_gain,
                "dragon_gain": dragon_gain, "serpent_gain": serpent_gain,
                "quests_gain": quests_gain, "mine_gain": mine_gain
            })

    activity.sort(key=lambda x: x["score"], reverse=True)
    brotherhood_contributors.sort(key=lambda x: (-x["gain"], x["nickname"].lower()))
    clan_contributors.sort(key=lambda x: (-x["gain"], x["nickname"].lower()))
    hero = activity[0] if activity else None

    payload = dict(
        ready=True,
        from_date=day_start.isoformat(), to_date=latest.isoformat(),
        summary={
            "levels": levels,
            "brotherhood_changes": brotherhood_changes,
            "clan_changes": clan_changes,
            "total_power_gain": total_power_gain,
            "active_players": len(activity),
        },
        hero=hero,
        top_active=activity[:5],
        top_brotherhood=brotherhood_contributors[:5],
        top_clan=clan_contributors[:5],
    )
    _life_cache_put("life:summary", payload)
    return jsonify(payload)

_snapshot_dates_cache = {"at": 0.0, "finished_at": None, "dates": None}

def completed_snapshot_dates():
    # Главная страница одновременно запрашивает /api/status и /api/players.
    # Не заставляем PostgreSQL дважды пересчитывать список снимков.
    scan_state = db.session.get(ScanState, 1)
    finished_at = scan_state.finished_at if scan_state else None
    now = time.monotonic()
    cached = _snapshot_dates_cache
    if (
        cached["dates"] is not None
        and cached["finished_at"] == finished_at
        and now - cached["at"] < 30
    ):
        return list(cached["dates"])
    query = db.session.query(PlayerSnapshot.batch_at).distinct()
    if scan_state and scan_state.finished_at:
        query = query.filter(PlayerSnapshot.batch_at <= scan_state.finished_at)
    # Почасовые снимки текущего дня храним в БД, но в интерфейсе показываем
    # только один снимок на календарный день — самый свежий завершённый.
    # 1000 снимков = более 40 дней истории даже при 24 обновлениях в сутки.
    rows = query.order_by(PlayerSnapshot.batch_at.desc()).limit(1000).all()
    candidates = [row.batch_at for row in rows]

    trusted = []
    seen_days = set()
    for value in candidates:
        day = moldova_date(value)
        if day in seen_days:
            continue
        seen_days.add(day)
        trusted.append(value)
    cached["at"] = now
    cached["finished_at"] = finished_at
    cached["dates"] = tuple(trusted)
    return trusted


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
    # Только отдаём сохранённое расписание.
    # Просмотр сайта НЕ запускает повторное сканирование Монаха.
    return jsonify(
        fetched_at=state.fetched_at.isoformat() if state and state.fetched_at else None,
        game_time=state.game_time.isoformat() if state and state.game_time else None,
        dragon_at=state.dragon_at.isoformat() if state and state.dragon_at else None,
        serpent_at=state.serpent_at.isoformat() if state and state.serpent_at else None,
        dragon_status=state.dragon_raw if state and not state.dragon_at else None,
        serpent_status=state.serpent_raw if state and not state.serpent_at else None,
        weather_at=state.weather_at.isoformat() if state and state.weather_at else None,
        weather_status=state.weather_raw if state else None,
        error=state.last_error if state else None,
    )


@app.get("/api/debug-wekings-player/<int:player_id>")
def api_debug_wekings_player(player_id):
    """Показывает исходные поля ForGlory API для одного игрока без записи в БД."""
    try:
        import scraper

        session = scraper._session(saved=True)
        try:
            response = session.get(scraper.API_URL, timeout=scraper.TIMEOUT, allow_redirects=True)
            if response.status_code in {401, 403} or "/login" in response.url:
                return jsonify(error="Нужна авторизация WEKINGS через /wekings-login"), 401
            response.raise_for_status()
            body = response.json()
            rows = body.get("data") if isinstance(body, dict) else body
            if not isinstance(rows, list):
                return jsonify(error="ForGlory API не вернул список data"), 502

            raw = next((row for row in rows if isinstance(row, dict) and scraper._int(row.get("id")) == player_id), None)
            if raw is None:
                return jsonify(error="Игрок не найден в ForGlory API", player_id=player_id), 404

            achievements = raw.get("achievements") if isinstance(raw.get("achievements"), dict) else {}
            normalized = scraper._normalize(raw)
            keys = [
                "beasts_killed", "pet_fights", "pet_kills",
                "wins", "losses", "dragon_wins", "serpent_wins",
                "bandit_wins", "mine", "crusade", "quests",
                "garden", "goblins", "sent_gifts", "fishing",
                "dragon_kills", "serpent_kills",
            ]
            return jsonify(
                player_id=player_id,
                nickname=raw.get("nickname") or raw.get("name"),
                raw_top_level={key: raw.get(key) for key in keys},
                raw_achievements={key: achievements.get(key) for key in keys},
                normalized={key: normalized.get(key) for key in keys},
                raw_keys=sorted(raw.keys()),
                achievement_keys=sorted(achievements.keys()),
            )
        finally:
            session.close()
    except Exception as exc:
        app.logger.exception("WEKINGS debug player failed: %r", exc)
        return jsonify(error=str(exc)), 500


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
        "bandit_wins", "mine", "crusade", "quests", "pet_fights", "pet_kills",
        "garden", "goblins", "lord_wins", "undead_wins", "heroes_wins",
        "serpent_fights", "sent_gifts", "fishing", "dragon_kills", "serpent_kills",
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
            with _life_cache_lock:
                _life_cache.clear()
            # Сразу после готового часового снимка считаем "Жизнь" один раз
            # в фоновом потоке сканирования. Посетители затем получают готовый кэш.
            try:
                for _period in ("now", "today", "7d"):
                    with app.test_request_context(f"/api/life?period={_period}"):
                        api_life()
                with app.test_request_context("/api/life-summary"):
                    api_life_summary()
                # Пересчитываем "Топы вчера" сразу после каждого нового
                # завершённого снимка, чтобы старый результат не задерживался.
                with app.test_request_context("/api/yesterday-tops"):
                    api_yesterday_tops()
                app.logger.info("Life WEKINGS + yesterday tops cache warmed")
            except Exception:
                app.logger.exception("Life WEKINGS cache warm failed")
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
            # Не запускаем бесконечные повторы через 5 минут. Следующая
            # автоматическая попытка будет по штатному часовому расписанию.
            next_scan_delay = None
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
                    "dragon_raw", "serpent_raw", "weather_at", "weather_raw",
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
                state.weather_at = None
                state.weather_raw = None
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



def start_daily_attack_if_needed():
    """Получает расписание Дракона/Змея не более одного успешного раза в сутки."""
    with app.app_context():
        state = db.session.get(GameAttackState, 1)
        now_local = datetime.now(ZoneInfo("Europe/Chisinau"))
        fetched_at = _as_utc(state.fetched_at) if state and state.fetched_at else None
        if fetched_at and not state.last_error:
            fetched_local = fetched_at.astimezone(ZoneInfo("Europe/Chisinau"))
            # Считаем суточное чтение Монаха завершённым только когда получили
            # ОБА будущих времени. Раньше один найденный босс считался успехом,
            # поэтому попытки 00:07/00:12/00:22 уже не выполнялись.
            have_both_bosses = bool(state.dragon_at and state.serpent_at)
            if fetched_local.date() == now_local.date() and have_both_bosses:
                app.logger.info("Wekings attacks skipped: both boss times already fetched today")
                return
    start_attack_thread()

def start_attack_on_boot_if_needed():
    # После deploy догоняем расписание только если сегодня ещё не было
    # успешного получения. Если уже получили — повторно в игру не заходим.
    start_daily_attack_if_needed()


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

    def start_hourly_scan_if_needed():
        """Обновляет сегодняшний снимок раз в час.

        В БД сохраняются почасовые снимки, но API публикует только самый
        свежий снимок каждого дня. Поэтому сегодня виден текущий прирост от
        финального снимка вчера, а прошлые даты остаются целыми сутками.
        """
        with app.app_context():
            state = db.session.get(ScanState, 1)
            if state and state.running:
                app.logger.info("ForGlory hourly scan skipped: scan already running")
                return
            latest = db.session.query(db.func.max(PlayerSnapshot.batch_at)).scalar()
            now_local = datetime.now(ZoneInfo("Europe/Chisinau"))
            if latest:
                latest_local = latest
                if latest_local.tzinfo is None:
                    latest_local = latest_local.replace(tzinfo=timezone.utc)
                latest_local = latest_local.astimezone(ZoneInfo("Europe/Chisinau"))
                if (
                    latest_local.date() == now_local.date()
                    and latest_local.hour == now_local.hour
                ):
                    app.logger.info("ForGlory hourly scan skipped: current hour already updated")
                    return
            app.logger.info("ForGlory hourly scan starting for %s", now_local.isoformat())
        start_scan_thread()

    # Основной почасовой запуск на 02-й минуте каждого часа.
    scheduler.add_job(
        start_hourly_scan_if_needed,
        "cron",
        minute=2,
        id="wekings-hourly-scan",
        replace_existing=True,
        coalesce=True,
        max_instances=1,
        misfire_grace_time=1800,
    )

    # После полуночи оставляем страховочные повторы первого снимка дня.
    for job_id, minute in (
        ("wekings-daily-retry-0007", 7),
        ("wekings-daily-retry-0012", 12),
        ("wekings-daily-retry-0022", 22),
    ):
        scheduler.add_job(
            start_hourly_scan_if_needed,
            "cron",
            hour=0,
            minute=minute,
            id=job_id,
            replace_existing=True,
            coalesce=True,
            max_instances=1,
            misfire_grace_time=1800,
        )

    if os.getenv("START_SCAN_ON_BOOT", "true").lower() == "true":
        scheduler.add_job(
            start_scan_on_boot_if_needed,
            "date",
            run_date=datetime.now(timezone.utc) + timedelta(seconds=30),
            id="wekings-first-scan",
            replace_existing=True,
        )
        # После deploy/перезапуска проверяем, есть ли отчёт за сегодняшний
        # день. Это позволяет догнать пропущенные 00:02 без ручного запуска.
        scheduler.add_job(
            start_hourly_scan_if_needed,
            "date",
            run_date=datetime.now(timezone.utc) + timedelta(seconds=45),
            id="wekings-daily-catchup-on-boot",
            replace_existing=True,
        )

    # Расписание Дракона/Змея через сохранённую сессию пользователя 106.
    # Основная попытка после полуночи и страховочные повторы.
    for job_id, minute in (
        ("wekings-attacks-0002", 2),
        ("wekings-attacks-0007", 7),
        ("wekings-attacks-0012", 12),
        ("wekings-attacks-0022", 22),
    ):
        scheduler.add_job(
            start_daily_attack_if_needed,
            "cron",
            hour=0,
            minute=minute,
            id=job_id,
            replace_existing=True,
            coalesce=True,
            max_instances=1,
            misfire_grace_time=1800,
        )

    # После deploy не ждём следующего дня: проверяем Монаха через минуту.
    scheduler.add_job(
        start_attack_on_boot_if_needed,
        "date",
        run_date=datetime.now(timezone.utc) + timedelta(seconds=60),
        id="wekings-attacks-on-boot",
        replace_existing=True,
    )


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", "5000")), debug=True)
