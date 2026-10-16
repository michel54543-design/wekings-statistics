"""Two-player sea battles. Isolated, authoritative in-memory rooms; no statistics data."""
from collections import deque
from copy import deepcopy
from threading import RLock
import secrets
import time
from flask import jsonify, request


def validate_fleet(value):
    if not isinstance(value, list) or len(value) != 5:
        raise ValueError('Размести все пять кораблей')
    ships, occupied = [], set()
    if sorted(len(s) if isinstance(s, list) else 0 for s in value) != [2, 3, 3, 4, 5]:
        raise ValueError('Неверные размеры кораблей')
    for cells in value:
        if any(type(n) is not int or not 0 <= n < 100 for n in cells):
            raise ValueError('Корабль за границей моря')
        cells = sorted(cells)
        horizontal = len({n // 10 for n in cells}) == 1 and cells == list(range(cells[0], cells[0] + len(cells)))
        vertical = cells == list(range(cells[0], cells[0] + 10 * len(cells), 10))
        if not (horizontal or vertical):
            raise ValueError('Корабль должен быть непрерывным и прямым')
        if any(max(abs(n // 10 - k // 10), abs(n % 10 - k % 10)) <= 1 for n in cells for k in occupied):
            raise ValueError('Между кораблями нужна клетка воды, включая диагонали')
        occupied.update(cells)
        ships.append(dict(cells=cells, hits=[]))
    return ships


def register_sea_routes(bp, error):
    rooms, lock, creations = {}, RLock(), deque()

    def data():
        value = request.get_json(silent=True)
        if not isinstance(value, dict):
            raise error('Неверный JSON')
        return value

    def cleanup():
        now = time.time()
        for code in list(rooms):
            r = rooms[code]
            if now - r['updated'] > (1800 if r['phase'] in ('waiting', 'closed') else 21600):
                del rooms[code]
        while creations and now - creations[0][1] > 60:
            creations.popleft()

    def room_for(code):
        cleanup()
        room = rooms.get(code)
        if not room:
            raise error('Комната закрыта или сервер перезапущен. Создай новую игру.', 404)
        return room

    def authenticate(room):
        token = request.headers.get('Authorization', '').removeprefix('Bearer ')
        if not token or len(token) > 128:
            raise error('Нужен ключ игрока', 403)
        seat = next((i for i, p in enumerate(room['players']) if secrets.compare_digest(p['token'], token)), -1)
        if seat < 0:
            raise error('Неверный ключ игрока', 403)
        room['players'][seat]['seen'] = room['updated'] = time.time()
        return seat

    def snapshot(room, seat):
        own = room['players'][seat]
        other = room['players'][1 - seat] if len(room['players']) == 2 else None
        # Never send the opponent's fleet or credentials, including during placement.
        return dict(code=room['code'], name=room['name'], seat=seat, phase=room['phase'],
                    revision=room['revision'], turn=room['turn'], winner=room['winner'],
                    players=[dict(name=p['name'], ready=p['fleet'] is not None,
                                  connected=time.time() - p['seen'] < 25) for p in room['players']],
                    fleet=deepcopy(own['fleet'] or []), shots=deepcopy(own['shots']),
                    received=deepcopy(other['shots'] if other else []), last=deepcopy(room['last']))

    def player(index):
        return dict(name='Викинг ' + str(index + 1), token=secrets.token_urlsafe(32),
                    fleet=None, shots=[], seen=time.time())

    @bp.get('/api/sea/rooms')
    def sea_list():
        with lock:
            cleanup()
            return jsonify(rooms=[dict(code=r['code'], name=r['name'], players=1)
                                  for r in rooms.values() if r['phase'] == 'waiting'
                                  and time.time() - r['players'][0]['seen'] < 25])

    @bp.post('/api/sea/rooms')
    def sea_create():
        payload = data()
        name = payload.get('name', 'Северный флот')
        if not isinstance(name, str) or not 1 <= len(name.strip()) <= 40:
            raise error('Название должно содержать от 1 до 40 символов')
        with lock:
            cleanup()
            ip = request.remote_addr
            if len(rooms) >= 120 or sum(address == ip for address, _ in creations) >= 8:
                raise error('Слишком много новых комнат. Подожди минуту.', 429)
            code = secrets.token_hex(3).upper()
            while code in rooms:
                code = secrets.token_hex(3).upper()
            room = dict(code=code, name=name.strip(), players=[player(0)], phase='waiting',
                        revision=1, turn=0, winner=None, last=None, updated=time.time())
            rooms[code] = room
            creations.append((ip, time.time()))
            return jsonify(**snapshot(room, 0), token=room['players'][0]['token']), 201

    @bp.post('/api/sea/rooms/<code>/join')
    def sea_join(code):
        with lock:
            room = room_for(code)
            if room['phase'] != 'waiting' or len(room['players']) != 1:
                raise error('Место уже занято. Выбери другую игру.', 409)
            room['players'].append(player(1))
            room['phase'] = 'placing'
            room['revision'] += 1
            room['updated'] = time.time()
            return jsonify(**snapshot(room, 1), token=room['players'][1]['token'])

    @bp.get('/api/sea/rooms/<code>')
    def sea_state(code):
        with lock:
            room = room_for(code)
            return jsonify(snapshot(room, authenticate(room)))

    @bp.post('/api/sea/rooms/<code>/fleet')
    def sea_fleet(code):
        payload = data()
        with lock:
            room = room_for(code)
            seat = authenticate(room)
            if room['phase'] != 'placing' or room['players'][seat]['fleet'] is not None:
                raise error('Сейчас нельзя менять флот', 409)
            try:
                room['players'][seat]['fleet'] = validate_fleet(payload.get('ships'))
            except ValueError as exc:
                raise error(str(exc)) from exc
            room['revision'] += 1
            if all(p['fleet'] is not None for p in room['players']):
                room['phase'], room['turn'] = 'battle', secrets.randbelow(2)
            return jsonify(snapshot(room, seat))

    @bp.post('/api/sea/rooms/<code>/shot')
    def sea_shot(code):
        payload = data()
        at = payload.get('at')
        if type(at) is not int or not 0 <= at < 100:
            raise error('Неверная клетка')
        with lock:
            room = room_for(code)
            seat = authenticate(room)
            if room['phase'] != 'battle' or room['turn'] != seat:
                raise error('Сейчас ход соперника', 409)
            own, foe = room['players'][seat], room['players'][1 - seat]
            if any(s['at'] == at for s in own['shots']):
                raise error('По этой клетке уже стреляли', 409)
            ship = next((s for s in foe['fleet'] if at in s['cells']), None)
            sunk = []
            if ship:
                ship['hits'].append(at)
                if len(ship['hits']) == len(ship['cells']):
                    sunk = ship['cells'][:]
            shot = dict(at=at, hit=ship is not None, sunk=sunk)
            own['shots'].append(shot)
            room['revision'] += 1
            room['last'] = dict(by=seat, **shot)
            if all(len(s['hits']) == len(s['cells']) for s in foe['fleet']):
                room['phase'], room['winner'] = 'done', seat
            else:
                room['turn'] = 1 - seat
            return jsonify(snapshot(room, seat))

    @bp.post('/api/sea/rooms/<code>/leave')
    def sea_leave(code):
        with lock:
            room = room_for(code)
            authenticate(room)
            room['phase'] = 'closed'
            room['revision'] += 1
            return jsonify(ok=True)
