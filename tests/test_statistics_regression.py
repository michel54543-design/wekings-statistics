"""Read-only route parity against the repository's pre-game revision on isolated DBs."""
import importlib
import os
from pathlib import Path
import subprocess
import sys
import types
import unittest
from datetime import datetime, timezone

ROOT = Path(__file__).resolve().parents[1]
BASE_REV = 'a2e89bdb0f2bc0999b832e28600258e519455f36'
os.environ.update(DATABASE_URL='sqlite:///:memory:', SCAN_ENABLED='false', DB_INIT_ON_BOOT='true', DB_MAINTENANCE_ON_BOOT='false', START_SCAN_ON_BOOT='false')

class StatisticsRegression(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        source = subprocess.check_output(['git','show',BASE_REV+':app.py'],cwd=ROOT).decode('utf-8-sig')
        baseline=types.ModuleType('wekings_baseline')
        baseline.__file__=str(ROOT/'app.py')
        sys.modules[baseline.__name__]=baseline
        exec(compile(source,str(ROOT/'app.py'),'exec'),baseline.__dict__)
        cls.before=baseline
        cls.after=importlib.import_module('app')
        for module in (cls.before,cls.after):
            module.app.config['TESTING']=True
            with module.app.app_context():
                module.db.session.add(module.Player(id=100, nickname='Тестовый викинг',level=20,glory=1000,power=500,defense=450,agility=350,mastery=300,vitality=250,stat_sum=1850,clan='Север',brotherhood='Дружина',scanned_at=datetime(2026,10,15,9,tzinfo=timezone.utc)))
                module.db.session.commit()

    def test_existing_routes_unchanged(self):
        before={ (r.rule, tuple(sorted(r.methods))) for r in self.before.app.url_map.iter_rules() }
        after={ (r.rule, tuple(sorted(r.methods))) for r in self.after.app.url_map.iter_rules() if r.endpoint.split('.')[0]!='wekings_game' }
        self.assertEqual(before,after)

    def test_existing_api_results(self):
        for url in ('/health','/api/players?sort=power','/api/status','/api/organizations?type=clan','/api/attacks','/api/luck/brotherhoods','/api/today-tops','/api/yesterday-tops'):
            with self.subTest(url=url):
                a=self.before.app.test_client().get(url)
                b=self.after.app.test_client().get(url)
                self.assertEqual(a.status_code,200,url)
                self.assertEqual(b.status_code,a.status_code)
                self.assertEqual(b.json,a.json)

    def test_game_does_not_touch_statistics_db(self):
        m=self.after
        with m.app.app_context():
            before={t: m.db.session.execute(m.db.text('SELECT COUNT(*) FROM "'+t+'"')).scalar() for t in m.db.metadata.tables}
        client=m.app.test_client()
        self.assertEqual(client.get('/').status_code,200)
        r=client.get('/games/wekings/')
        self.assertEqual(r.status_code,200)
        r.close()
        a=client.post('/games/wekings/api/rooms',json={'count':2,'color':'blue','mode':'adventure'}).json
        url='/games/wekings/api/rooms/'+a['code']
        self.assertEqual(client.post(url+'/join',json={'color':'green'}).status_code,200)
        self.assertEqual(client.post(url+'/command',headers={'X-Player-Token':a['token']},json={'type':'ROLL','revision':1}).status_code,200)
        with m.app.app_context():
            after={t: m.db.session.execute(m.db.text('SELECT COUNT(*) FROM "'+t+'"')).scalar() for t in m.db.metadata.tables}
        self.assertEqual(before,after)
        self.assertEqual(set(self.before.db.metadata.tables),set(self.after.db.metadata.tables))

    def test_existing_files_are_unchanged(self):
        # All original files except the two intentional integration points remain unchanged after Git newline normalization.
        original_requirements = subprocess.check_output(['git','show',BASE_REV+':requirements.txt'],cwd=ROOT).decode().splitlines()
        self.assertEqual((ROOT/'requirements.txt').read_text().splitlines(), original_requirements + ['psycopg[binary]>=3.2,<4'])
        tracked=subprocess.check_output(['git','ls-tree','-r','--name-only',BASE_REV],cwd=ROOT).decode().splitlines()
        for name in tracked:
            if name not in ('app.py','templates/index.html','requirements.txt'):
                with self.subTest(file=name):
                    self.assertEqual(subprocess.run(['git','diff','--quiet',BASE_REV,'--',name],cwd=ROOT).returncode,0)

if __name__=='__main__':
    unittest.main()

