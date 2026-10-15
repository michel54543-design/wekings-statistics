"""Isolated board-game rules and Flask routes. No statistics DB or scraper imports."""
from copy import deepcopy
from collections import deque
from pathlib import Path
from threading import RLock
from urllib.parse import urlsplit
import json
import math
import secrets
import time

from flask import Blueprint, jsonify, request, send_from_directory
from werkzeug.security import generate_password_hash, check_password_hash

_RULES = json.loads(Path(__file__).with_name('wekings_game_rules.json').read_text(encoding='utf-8'))
TILES = {int(k): v for k, v in _RULES['tiles'].items()}
ENEMIES = {int(k): v for k, v in _RULES['enemies'].items()}
COLORS = ('red', 'blue', 'green', 'yellow')
COLOR_NAMES = dict(zip(COLORS, ('красный', 'синий', 'зелёный', 'жёлтый')))


def create_game(count=4, color='red', mode='adventure'):
    if type(count) is not int or count not in (2, 3, 4) or color not in COLORS or mode not in ('adventure', 'classic', 'quick'):
        raise ValueError('Неверные настройки')
    colors = [color] + [c for c in COLORS if c != color]
    names = ('Ты', 'Бьорн', 'Фрейя', 'Рагнар')
    return dict(players=[dict(name=names[i], color=c, pos=0, skip=0, shield=False, cleared=[]) for i, c in enumerate(colors[:count])], turn=0, round=1, mode=mode, winner=None, battle=None)


def walk(pos, value, quick=False):
    steps, direction = [], 1
    for _ in range(value):
        if pos == 100:
            if quick:
                break
            direction = -1
        pos = max(0, min(100, pos + direction))
        steps.append(pos)
    return steps


def _advance(state):
    state['turn'] = (state['turn'] + 1) % len(state['players'])
    if state['turn'] == 0:
        state['round'] += 1


def _finish(state):
    if state['players'][state['turn']]['pos'] == 100:
        state['winner'] = state['turn']
    else:
        _advance(state)


def _die(value):
    if type(value) is not int or not 1 <= value <= 6:
        raise ValueError('Неверный кубик')


def resolve(state, value, rng=None):
    rng = rng or (lambda: secrets.randbelow(2**32) / 2**32)
    if state['winner'] is not None or state.get('battle'):
        raise ValueError('Сейчас нельзя идти')
    _die(value)
    nxt, actions = deepcopy(state), []
    p = nxt['players'][nxt['turn']]

    def event(text):
        actions.append(dict(type='event', text=text))

    def move(steps):
        walked = []
        for step in steps:
            p['pos'] = step
            walked.append(step)
            if nxt['mode'] != 'classic' and step in ENEMIES and step not in p['cleared']:
                nxt['battle'] = dict(at=step, enemyHp=ENEMIES[step]['hp'], heroHp=18)
                break
        actions.append(dict(type='move', steps=walked))
        if nxt.get('battle'):
            event(ENEMIES[p['pos']]['place'] + ': начинается бой!')

    if p['skip']:
        p['skip'] -= 1
        actions.append(dict(type='skip', text='пропускает ход после встречи с препятствием'))
        _advance(nxt)
        return dict(state=nxt, actions=actions)
    move(walk(p['pos'], value, nxt['mode'] == 'quick'))
    tile = TILES.get(p['pos'])
    if tile and nxt['mode'] == 'classic' and tile[0] not in ('forward', 'back'):
        tile = None
    if not nxt.get('battle') and p['pos'] != 100 and tile:
        kind = tile[0]
        if kind in ('back', 'rock', 'trap', 'bear') and p['shield']:
            p['shield'] = False
            event('руна защитила от препятствия')
        else:
            dest, text = p['pos'], ''
            if kind in ('forward', 'back'):
                dest = tile[1]
                text = ('попутный ветер: вперёд к ' if kind == 'forward' else 'опасная тропа: назад к ') + str(dest)
            elif kind == 'chest':
                dest += 2 + math.floor(rng() * 4)
                text = 'сундук: ' + str(dest - p['pos']) + ' шага вперёд'
            elif kind == 'rune':
                p['shield'], text = True, 'найдена защитная руна'
            elif kind in ('rock', 'trap'):
                dest -= 2 if kind == 'rock' else 4
                text = 'камень на пути: 2 шага назад' if kind == 'rock' else 'ловушка: 4 шага назад'
            elif kind == 'bear':
                p['skip'], text = 1, 'медведь! Пропуск следующего хода'
            elif kind == 'ship':
                dest += 7
                text = 'корабль: 7 клеток вперёд'
            elif kind == 'event':
                roll = math.floor(rng() * 3)
                if roll == 0:
                    dest += 3
                    text = 'северный ветер: 3 шага вперёд'
                elif roll == 1:
                    if p['shield']:
                        p['shield'], text = False, 'руна защитила от тумана'
                    else:
                        dest -= 3
                        text = 'густой туман: 3 шага назад'
                else:
                    p['shield'], text = True, 'дар Одина: защитная руна'
            dest = max(0, min(100, dest))
            event(text)
            if dest != p['pos']:
                direction = 1 if dest > p['pos'] else -1
                move(range(p['pos'] + direction, dest + direction, direction))
    if not nxt.get('battle'):
        _finish(nxt)
    return dict(state=nxt, actions=actions)


def fight(state, stance, value, rng=None):
    rng = rng or (lambda: secrets.randbelow(2**32) / 2**32)
    if not state.get('battle') or state['winner'] is not None:
        raise ValueError('Нет активного боя')
    _die(value)
    if stance not in ('attack', 'guard'):
        raise ValueError('Неверный удар')
    nxt, actions = deepcopy(state), []
    p, b = nxt['players'][nxt['turn']], nxt['battle']
    enemy = ENEMIES[b['at']]
    damage = math.ceil(value / 2) if stance == 'guard' else value
    b['enemyHp'] = max(0, b['enemyHp'] - damage)
    incoming = 0
    if b['enemyHp']:
        incoming = 1 + math.floor(rng() * enemy['damage'])
        if stance == 'guard':
            incoming = max(0, incoming - 2)
        if p['shield'] and incoming:
            p['shield'], incoming = False, 0
            actions.append(dict(type='event', text='руна поглотила ответный удар'))
        b['heroHp'] = max(0, b['heroHp'] - incoming)
    text = ('Удар из-за щита' if stance == 'guard' else 'Атака') + f': {damage} урона. Ответ врага: {incoming}.'
    actions.append(dict(type='event', text=text))
    if b['enemyHp'] == 0:
        p['cleared'].append(b['at'])
        p['shield'], nxt['battle'] = True, None
        actions.append(dict(type='event', text='Победа: ' + enemy['name'] + '! Награда — защитная руна.'))
        _finish(nxt)
    elif b['heroHp'] == 0:
        old = p['pos']
        p['pos'], p['skip'], nxt['battle'] = max(0, old - 4), 1, None
        actions.extend([dict(type='event', text='Дружина отступила на 4 клетки. Отдых один ход, затем можно повторить бой.'), dict(type='move', steps=list(range(old - 1, p['pos'] - 1, -1)))])
        _advance(nxt)
    return dict(state=nxt, actions=actions)


class GameError(Exception):
    def __init__(self, message, status=400):
        super().__init__(message)
        self.status = status


def create_game_blueprint():
    """Fresh store per app; gunicorn's existing single worker shares it across threads."""
    bp = Blueprint('wekings_game', __name__, url_prefix='/games/wekings')
    assets = Path(__file__).parent / 'static' / 'wekings'
    rooms, lock, creations = {}, RLock(), deque()
    allowed = {'index.html', 'app.js', 'engine.js', 'style.css', 'viking-map-dark.webp', 'encounters.webp', 'viking-walk.webp', 'landmarks.webp', 'wildlife.webp'}

    @bp.before_request
    def validate_game_request():
        if request.path.startswith('/games/wekings/api/'):
            if request.content_length and request.content_length > 2048:
                raise GameError('Слишком большой запрос', 413)
            origin = request.headers.get('Origin')
            if origin and urlsplit(origin).netloc != request.host:
                raise GameError('Другой источник запроса', 403)

    @bp.errorhandler(GameError)
    def game_error(exc):
        return jsonify(error=str(exc)), exc.status

    @bp.after_request
    def game_headers(response):
        response.headers['X-Content-Type-Options'] = 'nosniff'
        response.headers['Cache-Control'] = 'no-store' if '/api/' in request.path else 'no-cache'
        return response

    @bp.get('/')
    def index():
        return send_from_directory(assets, 'index.html')

    @bp.get('/<path:filename>')
    def asset(filename):
        if filename not in allowed:
            raise GameError('Не найдено', 404)
        return send_from_directory(assets, filename)

    def body():
        data = request.get_json(silent=True)
        if not isinstance(data, dict):
            raise GameError('Неверный JSON')
        return data

    def cleanup(now):
        expired = [code for code, r in rooms.items() if now - r['updated'] > 6 * 3600 or (r['state'] is None and now - r['updated'] > 1800)]
        for code in expired:
            del rooms[code]
        while creations and now - creations[0] > 60:
            creations.popleft()

    def get_room(code):
        room = rooms.get(code)
        if room is None:
            raise GameError('Комната закрыта или сервер перезапущен', 404)
        return room

    def view(room, token):
        seat = next((i for i, s in enumerate(room['seats']) if secrets.compare_digest(s['token'].encode(), token.encode())), -1)
        if seat < 0:
            raise GameError('Неверный ключ игрока', 403)
        now = time.time()
        room['seats'][seat]['seen'] = now
        room['updated'] = now
        return dict(name=room['name'], visibility=room['visibility'], locked=bool(room['password_hash']), code=room['code'], seat=seat, capacity=room['capacity'], revision=room['revision'], readyAt=room['readyAt'], state=room['state'], last=room['last'], players=[dict(name='Викинг ' + str(i + 1), color=s['color'], online=now - s['seen'] < 15) for i, s in enumerate(room['seats'])], waiting=room['state'] is None)

    @bp.get('/api/rooms')
    def list_rooms():
        now = time.time()
        with lock:
            cleanup(now)
            listing = []
            for room in rooms.values():
                if room['visibility'] != 'public' or room['state'] is not None or len(room['seats']) >= room['capacity']:
                    continue
                if not any(now - seat['seen'] < 20 for seat in room['seats']):
                    continue
                listing.append(dict(code=room['code'], name=room['name'], count=len(room['seats']), capacity=room['capacity'], mode=room['mode'], locked=bool(room['password_hash']), colors=[c for c in COLORS if c not in {seat['color'] for seat in room['seats']}]))
            return jsonify(rooms=listing)

    @bp.post('/api/rooms')
    def create_room():
        data, now = body(), time.time()
        try:
            create_game(data.get('count', 4), data.get('color', 'red'), data.get('mode', 'adventure'))
        except (ValueError, TypeError):
            raise GameError('Неверные настройки')
        visibility = data.get('visibility', 'public')
        name = data.get('name', 'Дружина викингов')
        password = data.get('password', '')
        if visibility not in ('public', 'private') or not isinstance(name, str) or not 1 <= len(name.strip()) <= 40 or not isinstance(password, str) or len(password) > 64:
            raise GameError('Название: 1–40 символов, пароль: до 64 символов')
        password_hash = generate_password_hash(password) if password else ''
        with lock:
            cleanup(now)
            if len(rooms) >= 128 or len(creations) >= 30:
                raise GameError('Сервер комнат занят. Попробуйте позже.', 429)
            creations.append(now)
            code = secrets.token_hex(3).upper()
            while code in rooms:
                code = secrets.token_hex(3).upper()
            token = secrets.token_urlsafe(32)
            room = dict(name=name.strip(), visibility=visibility, password_hash=password_hash, attempts=deque(maxlen=256), code=code, capacity=data.get('count', 4), color=data.get('color', 'red'), mode=data.get('mode', 'adventure'), seats=[dict(token=token, color=data.get('color', 'red'), seen=now)], state=None, revision=0, last=None, readyAt=0, updated=now)
            rooms[code] = room
            return jsonify(**view(room, token), token=token)

    @bp.post('/api/rooms/<code>/join')
    def join(code):
        data = body()
        with lock:
            cleanup(time.time())
            room = get_room(code)
            if room['state'] is not None or len(room['seats']) >= room['capacity']:
                raise GameError('В комнате нет свободных мест', 409)
            password = data.get('password', '')
            if not isinstance(password, str) or len(password) > 64:
                raise GameError('Неверный пароль', 403)
            if room['password_hash']:
                now, ip = time.time(), request.remote_addr
                if sum(1 for who, when in room['attempts'] if who == ip and now - when < 60) >= 8:
                    raise GameError('Слишком много попыток. Подождите минуту.', 429)
                room['attempts'].append((ip, now))
                if not check_password_hash(room['password_hash'], password):
                    raise GameError('Неверный пароль комнаты', 403)
            available = [c for c in COLORS if c not in {s['color'] for s in room['seats']}]
            color = data.get('color', available[0])
            if color not in available:
                raise GameError('Этот цвет флага занят. Свободны: ' + ', '.join(COLOR_NAMES[c] for c in available), 409)
            token = secrets.token_urlsafe(32)
            room['seats'].append(dict(token=token, color=color, seen=time.time()))
            if len(room['seats']) == room['capacity']:
                room['state'] = create_game(room['capacity'], room['color'], room['mode'])
                for i, p in enumerate(room['state']['players']):
                    p.update(name='Викинг ' + str(i + 1), color=room['seats'][i]['color'])
                room['revision'] = 1
            return jsonify(**view(room, token), token=token)

    @bp.get('/api/rooms/<code>')
    def snapshot(code):
        with lock:
            cleanup(time.time())
            return jsonify(view(get_room(code), request.headers.get('X-Player-Token', '')))

    @bp.post('/api/rooms/<code>/leave')
    def leave(code):
        with lock:
            cleanup(time.time())
            room = get_room(code)
            data = view(room, request.headers.get('X-Player-Token', ''))
            if room['state'] is not None:
                raise GameError('Партия уже началась', 409)
            room['seats'].pop(data['seat'])
            if not room['seats']:
                del rooms[code]
            return jsonify(left=True)

    @bp.post('/api/rooms/<code>/command')
    def command(code):
        data = body()
        with lock:
            cleanup(time.time())
            room = get_room(code)
            info = view(room, request.headers.get('X-Player-Token', ''))
            before = room['state']
            if before is None or before['winner'] is not None:
                raise GameError('Партия ещё не началась или уже окончена', 409)
            if info['seat'] != before['turn']:
                raise GameError('Сейчас ход другого игрока', 409)
            if type(data.get('revision')) is not int or data['revision'] != room['revision']:
                raise GameError('Состояние обновилось. Повторите ход.', 409)
            if time.time() * 1000 < room['readyAt']:
                raise GameError('Дождитесь окончания движения', 409)
            value = secrets.randbelow(6) + 1
            try:
                if data.get('type') == 'ROLL':
                    result = resolve(before, value)
                elif data.get('type') == 'FIGHT':
                    result = fight(before, data.get('stance'), value)
                else:
                    raise ValueError('Неверная команда')
            except ValueError as exc:
                raise GameError(str(exc))
            room['state'] = result['state']
            room['revision'] += 1
            room['last'] = dict(before=before, actions=result['actions'], value=value, actor=before['turn'])
            room['readyAt'] = int(time.time() * 1000 + 2050 + sum(len(a.get('steps', [])) * 380 + (400 if a['type'] == 'event' else 0) for a in result['actions']))
            return jsonify(view(room, request.headers.get('X-Player-Token', '')))

    return bp
