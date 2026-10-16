import unittest
from flask import Flask
from wekings_game import create_game_blueprint


class ArcadeRoutes(unittest.TestCase):
    def setUp(self):
        app = Flask(__name__)
        app.register_blueprint(create_game_blueprint())
        self.client = app.test_client()

    def test_hub_and_scripts_are_served_without_statistics_dependencies(self):
        for asset in ('arcade.html', 'arcade.css', 'arcade.js', 'mini-engine.js', 'platform-engine.js', 'platformer.js', 'platformer.css', 'platform-world.webp'):
            with self.subTest(asset=asset):
                response = self.client.get('/games/wekings/' + asset)
                self.assertEqual(response.status_code, 200)
                self.assertEqual(response.headers['X-Content-Type-Options'], 'nosniff')
                response.close()
        response = self.client.get('/games/wekings/arcade.html')
        self.assertIn('Приключения викинга', response.get_data(as_text=True))
        response.close()

    def test_original_board_game_stays_at_its_old_address(self):
        response = self.client.get('/games/wekings/')
        html = response.get_data(as_text=True)
        self.assertEqual(response.status_code, 200)
        self.assertIn('Сага ста шагов', html)
        self.assertIn('href="arcade.html"', html)
        response.close()
        self.assertEqual(self.client.get('/games/wekings/tests/test_mini_games.cjs').status_code, 404)
        self.assertEqual(self.client.get('/games/wekings/platformer-preview.html').status_code, 404)


if __name__ == '__main__':
    unittest.main()
