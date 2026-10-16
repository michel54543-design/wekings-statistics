import unittest
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import patch
from flask import Flask
from wekings_game import create_game_blueprint
from sea_online import validate_fleet

FLEET = [[0, 1, 2, 3, 4], [20, 21, 22, 23], [40, 41, 42], [60, 61, 62], [80, 81]]


class OnlineSeaTests(unittest.TestCase):
    def setUp(self):
        self.app = Flask(__name__)
        self.app.register_blueprint(create_game_blueprint())
        self.client = self.app.test_client()
        self.base = '/games/wekings/api/sea/rooms'

    def create(self):
        r = self.client.post(self.base, json={'name': 'Test harbor'})
        self.assertEqual(r.status_code, 201)
        return r.json

    def auth(self, player):
        return {'Authorization': 'Bearer ' + player['token']}

    def post(self, player, route, data=None):
        return self.client.post(self.base + '/' + player['code'] + route,
                                headers=self.auth(player), json=data or {})

    def pair(self):
        one = self.create()
        two = self.client.post(self.base + '/' + one['code'] + '/join', json={}).json
        return one, two

    def battle(self):
        one, two = self.pair()
        self.assertEqual(self.post(one, '/fleet', {'ships': FLEET}).status_code, 200)
        with patch('sea_online.secrets.randbelow', return_value=0):
            result = self.post(two, '/fleet', {'ships': FLEET})
        self.assertEqual(result.json['phase'], 'battle')
        return one, two

    def test_waiting_list_join_capacity_and_credentials(self):
        one = self.create()
        listing = self.client.get(self.base).json
        self.assertEqual(listing['rooms'][0]['code'], one['code'])
        self.assertNotIn(one['token'], str(listing))
        with ThreadPoolExecutor(max_workers=2) as pool:
            def join(_):
                with self.app.test_client() as c:
                    return c.post(self.base + '/' + one['code'] + '/join', json={}).status_code
            self.assertEqual(sorted(pool.map(join, range(2))), [200, 409])
        self.assertEqual(self.client.get(self.base).json['rooms'], [])
        self.assertEqual(self.client.get(self.base + '/' + one['code']).status_code, 403)
        self.assertEqual(self.client.get(self.base + '/' + one['code'], headers={'Authorization': 'Bearer wrong'}).status_code, 403)

    def test_fleet_validation_rejects_touches_wraps_and_forged_layouts(self):
        self.assertEqual(len(validate_fleet(FLEET)), 5)
        for bad in [[], [[0] * 5] + FLEET[1:], [[7, 8, 9, 10, 11]] + FLEET[1:],
                    [[-1, 0, 1, 2, 3]] + FLEET[1:], [FLEET[0], [15, 16, 17, 18]] + FLEET[2:],
                    [[False, 1, 2, 3, 4]] + FLEET[1:]]:
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                validate_fleet(bad)

    def test_ready_waits_for_both_and_hides_opponent_fleet(self):
        one, two = self.pair()
        ready = self.post(one, '/fleet', {'ships': FLEET})
        self.assertEqual(ready.json['phase'], 'placing')
        other = self.client.get(self.base + '/' + two['code'], headers=self.auth(two)).json
        self.assertEqual(other['fleet'], [])
        self.assertNotIn('cells', str(other))
        self.assertNotIn(one['token'], str(other))
        self.assertTrue(other['players'][0]['ready'])
        self.assertEqual(self.post(one, '/fleet', {'ships': FLEET}).status_code, 409)
        self.assertEqual(self.post(one, '/shot', {'at': 0}).status_code, 409)

    def test_turn_authority_repeat_shots_and_sunk_results(self):
        one, two = self.battle()
        self.assertEqual(self.post(two, '/shot', {'at': 0}).status_code, 409)
        for index, n in enumerate(FLEET[0]):
            result = self.post(one, '/shot', {'at': n})
            self.assertEqual(result.status_code, 200)
            self.assertTrue(result.json['last']['hit'])
            self.assertEqual(result.json['last']['sunk'], FLEET[0] if index == 4 else [])
            self.assertEqual(self.post(one, '/shot', {'at': n + 1}).status_code, 409)
            self.assertEqual(self.post(two, '/shot', {'at': 90 + index}).status_code, 200)
        self.assertEqual(self.post(one, '/shot', {'at': 0}).status_code, 409)
        self.assertEqual(self.post(one, '/shot', {'at': True}).status_code, 400)

    def test_full_two_client_game_reaches_one_winner(self):
        one, two = self.battle()
        targets = sum(FLEET, [])
        misses = [n for n in range(100) if n not in targets]
        for i, at in enumerate(targets):
            result = self.post(one, '/shot', {'at': at})
            self.assertEqual(result.status_code, 200)
            if i < len(targets) - 1:
                self.assertEqual(self.post(two, '/shot', {'at': misses[i]}).status_code, 200)
        self.assertEqual(result.json['phase'], 'done')
        self.assertEqual(result.json['winner'], 0)
        resumed = self.client.get(self.base + '/' + two['code'], headers=self.auth(two)).json
        self.assertEqual(resumed['winner'], 0)
        self.assertEqual(len(resumed['received']), 17)
        self.assertEqual(self.post(two, '/shot', {'at': 99}).status_code, 409)

    def test_leave_closes_room_and_origin_and_limits_apply(self):
        one, two = self.pair()
        self.assertEqual(self.post(one, '/leave').status_code, 200)
        state = self.client.get(self.base + '/' + two['code'], headers=self.auth(two)).json
        self.assertEqual(state['phase'], 'closed')
        self.assertEqual(self.client.post(self.base, json={'name': 'x'}, headers={'Origin': 'https://other.example'}).status_code, 403)
        self.assertEqual(self.client.post(self.base, json={'name': 'x' * 3000}).status_code, 413)
        self.assertEqual(self.client.post(self.base, json={'name': ''}).status_code, 400)


if __name__ == '__main__':
    unittest.main()
