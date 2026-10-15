import json
import subprocess
import sys
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest.mock import patch

from flask import Flask
import wekings_game as game

ROOT = Path(__file__).resolve().parents[1]

class GameTests(unittest.TestCase):
    def setUp(self):
        self.app = Flask(__name__)
        self.app.register_blueprint(game.create_game_blueprint())
        self.client = self.app.test_client()
        self.url = '/games/wekings/api/rooms'

    def room(self, count=2):
        r = self.client.post(self.url, json=dict(count=count, color='red', mode='adventure'))
        self.assertEqual(r.status_code, 200)
        return r.json

    def test_rules_match_browser(self):
        cases = json.loads(subprocess.check_output(['node', str(ROOT / 'tests/rules_corpus.cjs')], cwd=ROOT))
        self.assertGreater(len(cases), 2800)
        for i, c in enumerate(cases):
            fn = (lambda: game.fight(c['state'], c['stance'], c['value'], lambda: c['r'])) if c['kind'] == 'fight' else (lambda: game.resolve(c['state'], c['value'], lambda: c['r']))
            self.assertEqual(fn(), c['result'], f'corpus case {i}')

    def test_assets_and_namespace(self):
        self.assertEqual(self.client.get('/games/wekings').status_code, 308)
        r = self.client.get('/games/wekings/')
        self.assertEqual(r.status_code, 200)
        self.assertIn('Против ПК', r.text)
        self.assertIn('name="flag"', r.text)
        r.close()
        for filename in ('style.css', 'app.js', 'engine.js', 'viking-map-dark.webp', 'encounters.webp', 'viking-walk.webp', 'landmarks.webp', 'wildlife.webp'):
            r = self.client.get('/games/wekings/' + filename)
            self.assertEqual(r.status_code, 200, filename)
            r.close()
        self.assertEqual(self.client.get('/api/rooms').status_code, 404)
        self.assertEqual(self.client.get('/games/wekings/../../app.py').status_code, 404)
        self.assertEqual(self.client.get('/games/wekings/wekings_game.py').status_code, 404)

    def test_room_authority_and_concurrency(self):
        a = self.room()
        url = self.url + '/' + a['code']
        self.assertTrue(a['waiting'])
        self.assertEqual(self.client.get(url).status_code, 403)
        self.assertEqual(self.client.post(url+'/join', json={'color':'red'}).status_code, 409)
        b = self.client.post(url+'/join', json={'color':'green'}).json
        self.assertFalse(b['waiting'])
        self.assertEqual([p['color'] for p in b['state']['players']], ['red','green'])
        ah, bh = {'X-Player-Token':a['token']}, {'X-Player-Token':b['token']}
        self.assertEqual(self.client.post(url+'/command', json=dict(type='ROLL', revision=1), headers=bh).status_code, 409)
        with patch('wekings_game.secrets.randbelow', return_value=2):
            def command(_):
                with self.app.test_client() as client:
                    return client.post(url+'/command', json=dict(type='ROLL', revision=1, value=100), headers=ah).status_code
            with ThreadPoolExecutor(max_workers=2) as pool:
                statuses=list(pool.map(command, range(2)))
        self.assertEqual(sorted(statuses), [200,409])
        data = self.client.get(url, headers=bh).json
        self.assertEqual(data['state']['players'][0]['pos'],3)
        self.assertEqual(data['revision'],2)
        self.assertEqual(data['last']['value'],3)
        self.assertTrue(all('token' not in p for p in data['players']))
        self.assertEqual(self.client.post(url+'/join', json={}).status_code,409)
        self.assertEqual(self.client.post(url+'/command', json=dict(type='ROLL', revision=2), headers=bh).status_code,409)
        self.assertEqual(data, self.client.get(url, headers=bh).json)

    def test_four_seats_and_leave(self):
        a=self.room(4)
        url=self.url+'/'+a['code']
        b=self.client.post(url+'/join',json={'color':'blue'}).json
        self.assertTrue(b['waiting'])
        self.assertEqual(self.client.post(url+'/leave',headers={'X-Player-Token':b['token']}).status_code,200)
        self.assertEqual(self.client.get(url,headers={'X-Player-Token':b['token']}).status_code,403)
        for color in ('blue','green','yellow'):
            data=self.client.post(url+'/join',json={'color':color}).json
        self.assertEqual(len(data['state']['players']),4)
        self.assertEqual(data['revision'],1)

    def test_request_validation_and_bounded_creation(self):
        self.assertEqual(self.client.post(self.url,json={'count':9}).status_code,400)
        self.assertEqual(self.client.post(self.url,json={'count':True}).status_code,400)
        self.assertEqual(self.client.post(self.url,json={},headers={'Origin':'https://other.invalid'}).status_code,403)
        self.assertEqual(self.client.post(self.url,data='x'*2049,content_type='application/json').status_code,413)
        self.assertEqual(self.client.post(self.url,json=[]).status_code,400)
        for _ in range(30):
            self.assertEqual(self.client.post(self.url,json={}).status_code,200)
        self.assertEqual(self.client.post(self.url,json={}).status_code,429)

if __name__=='__main__':
    unittest.main()

