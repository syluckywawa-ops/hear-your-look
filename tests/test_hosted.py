import base64
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import hosted
import server
from test_server import request_data

ORIGIN = 'https://hear-your-look.example'
PASSWORD = 'test-access-password-24-characters'
AUTH = 'Basic ' + base64.b64encode(('team:' + PASSWORD).encode()).decode()


class HostedTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.settings = dict(TESTING=True, PUBLIC_ORIGIN=ORIGIN, SECRET_KEY='s'*40,
                             ACCESS_PASSWORD=PASSWORD, QUOTA_DB=self.temp.name+'/quota.sqlite3',
                             PERSISTENT_STORAGE=True, AI_ENABLED=True, DAILY_CALLS=120,
                             ACCOUNT_RATE=3, GLOBAL_RATE=12)
        self.app = hosted.create_app(self.settings)
        self.client = self.app.test_client()
        self.key = patch.dict('os.environ', {'OPENROUTER_API_KEY':'fake-test-key'})
        self.key.start()

    def tearDown(self):
        self.key.stop()
        self.temp.cleanup()

    def get(self, path, auth=AUTH, client=None):
        return (client or self.client).get(path, base_url=ORIGIN, headers={'Authorization':auth})

    def post(self, changes=None, client=None, headers=None):
        client = client or self.client
        config = self.get('/api/config', client=client).json
        hdr = {'Authorization':AUTH, 'Origin':ORIGIN, 'X-Local-Token':config['token']}
        if headers: hdr.update(headers)
        return client.post('/api/analyze', base_url=ORIGIN, json=request_data(**(changes or {})), headers=hdr)

    def test_strong_secrets_required(self):
        for changes in [{'SECRET_KEY':'short'}, {'ACCESS_PASSWORD':'short'}, {'PERSISTENT_STORAGE':False}, {'QUOTA_DB':'relative.db'}, {'PUBLIC_ORIGIN':'http://bad.example'}, {'PUBLIC_ORIGIN':ORIGIN+'/'}]:
            with self.assertRaises(ValueError): hosted.create_app({**self.settings, **changes})

    def test_public_health_no_information(self):
        response = self.client.get('/healthz')
        self.assertEqual(response.json, {'status':'ok'})
        self.assertEqual(response.status_code, 200)

    def test_authentication_protects_pages_assets_config(self):
        for path in ['/', '/app.js', '/api/config', '/assets/hero-campaign-wide.png']:
            response = self.get(path, auth='')
            self.assertEqual(response.status_code, 401)
            self.assertIn('Basic', response.headers['WWW-Authenticate'])
        self.assertEqual(self.get('/', auth='Basic '+base64.b64encode(b'team:wrong').decode()).status_code, 401)

    def test_home_and_config(self):
        with self.get('/') as home:
            self.assertEqual(home.status_code, 200)
        response = self.get('/api/config')
        self.assertTrue(response.json['ready'])
        self.assertNotIn('fake-test-key', response.get_data(as_text=True))
        cookie = response.headers['Set-Cookie']
        for flag in ['Secure', 'HttpOnly', 'SameSite=Strict']: self.assertIn(flag, cookie)

    def test_wrong_host_or_http_rejected(self):
        for url in ['https://evil.example', 'http://hear-your-look.example']:
            self.assertEqual(self.client.get('/', base_url=url, headers={'Authorization':AUTH}).status_code, 403)

    def test_foreign_origin_and_csrf_rejected(self):
        for header in [{'Origin':'https://evil.example'}, {'X-Local-Token':''}, {'X-Local-Token':'invalid'}]:
            with patch('server.analyze') as call:
                self.assertEqual(self.post(headers=header).status_code, 403)
                call.assert_not_called()

    def test_csrf_not_shared_between_browsers(self):
        first = self.get('/api/config').json['token']
        second_client = self.app.test_client()
        second = self.get('/api/config', client=second_client).json['token']
        self.assertNotEqual(first, second)
        self.assertEqual(self.post(client=second_client, headers={'X-Local-Token':first}).status_code, 403)

    def test_valid_request_and_protected_quota_records(self):
        with patch('server.analyze', return_value={'mode':'ai', 'status':'uncertain'}) as call:
            response = self.post()
        self.assertEqual(response.status_code, 200)
        call.assert_called_once()
        with self.app.extensions['hyl_quota'].connect() as db:
            rows = db.execute('SELECT * FROM checks').fetchall()
        self.assertEqual(rows[0][2], 2)
        self.assertEqual(len(rows[0][1]), 64)
        self.assertNotIn(PASSWORD, str(rows))
        self.assertNotIn('fake-test-key', str(rows))

    def test_missing_consent_no_provider_call_or_budget(self):
        with patch('server.analyze') as call:
            self.assertEqual(self.post({'consent':False}).status_code, 400)
            call.assert_not_called()
        with self.app.extensions['hyl_quota'].connect() as db:
            self.assertEqual(db.execute('SELECT COUNT(*) FROM checks').fetchone()[0], 0)

    def test_daily_budget_survives_new_app(self):
        self.app.config['DAILY_CALLS'] = 2  # Config closure shares this mapping.
        with patch('server.analyze', return_value={'status':'uncertain'}):
            self.assertEqual(self.post().status_code, 200)
            self.assertEqual(self.post().status_code, 429)
        rebuilt = hosted.create_app({**self.settings, 'DAILY_CALLS':2})
        with patch('server.analyze') as call:
            self.assertEqual(self.post(client=rebuilt.test_client()).status_code, 429)
            call.assert_not_called()

    def test_failed_provider_keeps_reservation(self):
        self.app.config['DAILY_CALLS'] = 2
        with patch('server.analyze', side_effect=server.Problem(502, '模型失败')):
            self.assertEqual(self.post().status_code, 502)
        with patch('server.analyze') as call:
            self.assertEqual(self.post().status_code, 429)
            call.assert_not_called()

    def test_account_and_global_rate(self):
        for limit in ['ACCOUNT_RATE', 'GLOBAL_RATE']:
            with self.subTest(limit=limit):
                self.app.config[limit] = 1
                with self.app.extensions['hyl_quota'].connect() as db: db.execute('DELETE FROM checks')
                with patch('server.analyze', return_value={'status':'uncertain'}):
                    self.assertEqual(self.post().status_code, 200)
                    response = self.post()
                    self.assertEqual(response.status_code, 429)
                    self.assertEqual(response.headers['Retry-After'], '60')
                self.app.config[limit] = 12

    def test_emergency_switch(self):
        self.app.config['AI_ENABLED'] = False
        self.assertFalse(self.get('/api/config').json['ready'])
        with patch('server.analyze') as call:
            self.assertEqual(self.post().status_code, 503)
            call.assert_not_called()

    def test_sensitive_files_not_served(self):
        for path in ['/.env.local', '/hosted.py', '/server.py', '/render.yaml', '/requirements.txt', '/assets/../../server.py']:
            self.assertEqual(self.get(path).status_code, 404)

    def test_security_headers(self):
        response = self.get('/')
        self.assertEqual(response.headers['X-Frame-Options'], 'DENY')
        self.assertEqual(response.headers['Cache-Control'], 'no-store')
        self.assertIn("connect-src 'self'", response.headers['Content-Security-Policy'])
        response.close()

    def test_auth_attempts_limited(self):
        quota = self.app.extensions['hyl_quota']
        with quota.connect() as db:
            db.executemany('INSERT INTO auth_attempts VALUES (?)', [(hosted.time.time(),)]*180)
        self.assertEqual(self.get('/').status_code, 429)

    def test_oversize_body(self):
        token = self.get('/api/config').json['token']
        response = self.client.post('/api/analyze', base_url=ORIGIN, data='x'*(server.MAX_BODY+1),
                                    content_type='application/json', headers={'Authorization':AUTH,'Origin':ORIGIN,'X-Local-Token':token})
        self.assertEqual(response.status_code, 413)

    def public_client(self, **changes):
        app = hosted.create_app({**self.settings, 'PUBLIC_ACCESS':True,
                                 'ACCESS_PASSWORD':'', 'DAILY_CALLS':20, **changes})
        return app, app.test_client()

    def public_post(self, client, **changes):
        token = client.get('/api/config', base_url=ORIGIN).json['token']
        return client.post('/api/analyze', base_url=ORIGIN, json=request_data(**changes),
                           headers={'Origin':ORIGIN, 'X-Local-Token':token})

    def test_public_pages_and_config_need_no_password(self):
        app, client = self.public_client()
        for path in ['/', '/app.js', '/api/config']:
            with client.get(path, base_url=ORIGIN) as response:
                self.assertEqual(response.status_code, 200)
                self.assertNotIn('WWW-Authenticate', response.headers)
        self.assertEqual(client.get('/hosted.py', base_url=ORIGIN).status_code, 404)

    def test_public_api_still_requires_origin_csrf_and_consent(self):
        app, client = self.public_client()
        with patch('server.analyze') as call:
            self.assertEqual(client.post('/api/analyze', base_url=ORIGIN,
                                         json=request_data()).status_code, 403)
            self.assertEqual(self.public_post(client, consent=False).status_code, 400)
            call.assert_not_called()
        with patch('server.analyze', return_value={'mode':'ai', 'status':'uncertain'}) as call:
            self.assertEqual(self.public_post(client).status_code, 200)
            call.assert_called_once()

    def test_public_budget_is_shared_between_browsers(self):
        app, client = self.public_client(DAILY_CALLS=2)
        with patch('server.analyze', return_value={'mode':'ai', 'status':'uncertain'}):
            self.assertEqual(self.public_post(client).status_code, 200)
        with patch('server.analyze') as call:
            self.assertEqual(self.public_post(app.test_client()).status_code, 429)
            call.assert_not_called()

    def test_public_pages_work_but_api_stops_during_quota_outage(self):
        app, client = self.public_client()
        with patch.object(app.extensions['hyl_quota'], 'auth_attempt',
                          side_effect=server.Problem(503, '额度保护不可用')):
            with client.get('/', base_url=ORIGIN) as response:
                self.assertEqual(response.status_code, 200)
            with patch('server.analyze') as call:
                self.assertEqual(client.get('/api/config', base_url=ORIGIN).status_code, 503)
                call.assert_not_called()

    def test_unknown_exception_not_exposed(self):
        with patch('server.analyze', side_effect=RuntimeError('fake-test-key')):
            response = self.post()
        self.assertEqual(response.status_code, 503)
        self.assertNotIn('fake-test-key', response.get_data(as_text=True))


if __name__ == '__main__': unittest.main()
