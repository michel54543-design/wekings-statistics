from __future__ import annotations

import os
import threading
from datetime import datetime, timezone

from apscheduler.schedulers.background import BackgroundScheduler
from flask import Flask, jsonify, render_template, request
from flask_sqlalchemy import SQLAlchemy


def normalize_database_url(value: str) -> str:
    if value.startswith("postgres://"):
        return value.replace("postgres://", "postgresql://", 1)
    return value


app = Flask(__name__)
app.config["SQLALCHEMY_DATABASE_URI"] = normalize_database_url(
    os.getenv("DATABASE_URL", "sqlite:///wekings.db")
)
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
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


with app.app_context():
    db.create_all()
    if db.session.get(ScanState, 1) is None:
        db.session.add(ScanState(id=1))
        db.session.commit()


SORT_FIELDS = {
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
    sort = request.args.get("sort", "glory")
    query = request.args.get("q", "").strip()
    level = request.args.get("level", type=int)

    statement = Player.query
    if query:
        statement = statement.filter(Player.nickname.ilike(f"%{query}%"))
    if level:
        statement = statement.filter(Player.level == level)

    sort_column = SORT_FIELDS.get(sort, Player.glory)
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
                "glory_gain": p.glory_gain,
                "power": p.power,
                "defense": p.defense,
                "agility": p.agility,
                "mastery": p.mastery,
                "vitality": p.vitality,
                "stat_sum": p.stat_sum,
                "stats_gain": p.stats_gain,
                "wins": p.wins,
                "losses": p.losses,
                "dragon_wins": p.dragon_wins,
                "serpent_wins": p.serpent_wins,
                "clan": p.clan,
                "brotherhood": p.brotherhood,
                "last_activity": p.last_activity,
                "profile_url": f"https://playwekings.mobi/hero/detail?player={p.id}",
            }
            for p in result.items
        ],
        page=result.page,
        pages=result.pages,
        total=result.total,
    )


@app.get("/api/status")
def api_status():
    state = db.session.get(ScanState, 1)
    return jsonify(
        running=state.running,
        current_player_id=state.current_player_id,
        max_player_id=state.max_player_id,
        found_players=state.found_players,
        started_at=state.started_at.isoformat() if state.started_at else None,
        finished_at=state.finished_at.isoformat() if state.finished_at else None,
        last_error=state.last_error,
        total_players=Player.query.count(),
    )


def run_scan():
    from scraper import scan_all_players

    with app.app_context():
        state = db.session.get(ScanState, 1)
        if state.running:
            return
        state.running = True
        state.started_at = datetime.now(timezone.utc)
        state.last_error = None
        db.session.commit()
        try:
            scan_all_players(db, Player, ScanState)
            state = db.session.get(ScanState, 1)
            state.finished_at = datetime.now(timezone.utc)
        except Exception as exc:
            state = db.session.get(ScanState, 1)
            state.last_error = str(exc)[:2000]
            app.logger.exception("Wekings scan failed")
        finally:
            state.running = False
            db.session.commit()


def start_scan_thread():
    threading.Thread(target=run_scan, daemon=True, name="wekings-scan").start()


if os.getenv("SCAN_ENABLED", "true").lower() == "true":
    scheduler = BackgroundScheduler(timezone="Europe/Chisinau")
    scheduler.add_job(
        start_scan_thread,
        "interval",
        hours=float(os.getenv("SCAN_INTERVAL_HOURS", "12")),
        id="wekings-scan",
        max_instances=1,
        coalesce=True,
    )
    scheduler.start()
    if os.getenv("START_SCAN_ON_BOOT", "true").lower() == "true":
        start_scan_thread()


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", "5000")), debug=True)
