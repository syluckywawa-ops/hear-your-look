"""Offline REST contract + actual Lua evaluation via fakeredis/lupa. No cloud calls."""
import base64
from concurrent.futures import ThreadPoolExecutor
import io
import json
import time
import unittest
from unittest.mock import patch
import urllib.error

import fakeredis
import hosted
import server
from redis_quota import RedisQuota, NoRedirect
from test_server import request_data


class RedisQuotaTests(unittest.TestCase):
    def setUp(self):
        self.database = fakeredis.FakeRedis()
        self.quota = RedisQuota('https://test.upstash.io', 'fake-db-secret')

    def evaluate(self, quota, script, keys, args):
        return self.database.eval(script, len(keys), *keys, *args)

    def lua(self):
        return patch.object(RedisQuota, 'execute', lambda quota, script, keys, args:
                            self.evaluate(quota, script, keys, args))

    def test_url_and_token_validation(self):
        for url in ['http://test.upstash.io', 'https://evil.example', 'https://test.upstash.io.evil.example',
                    'https://user:pass@test.upstash.io', 'https://test.upstash.io:443',
                    'https://test.upstash.io/path', 'https://test.upstash.io?token=x']:
            with self.subTest(url=url), self.assertRaises(ValueError): RedisQuota(url, 'fake-token')
        for token in ['', ' token ', 'one\ntwo']:
            with self.assertRaises(ValueError): RedisQuota('https://test.upstash.io', token)

    def test_rest_payload_only_counters_and_digest(self):
        with patch.object(self.quota.opener, 'open', return_value=io.BytesIO(b'{"result":0}')) as call:
            self.quota.reserve('a'*64, 120, 3, 12)
        request = call.call_args.args[0]
        payload = json.loads(request.data)
        self.assertEqual(payload[0], 'EVAL')
        self.assertEqual(payload[2], 3)
        self.assertEqual(payload[6:9], [120, 3, 12])
        self.assertEqual(request.get_header('Authorization'), 'Bearer fake-db-secret')
        self.assertEqual(call.call_args.kwargs['timeout'], 8)
        self.assertNotIn('fake-db-secret', request.data.decode())
        self.assertNotIn('image', request.data.decode())

    def test_redirect_refused(self):
        self.assertIsNone(NoRedirect().redirect_request(None, None, 302, '', {}, 'https://evil.example'))

    def test_outages_and_invalid_responses_fail_closed_without_retry(self):
        for content in [b'{"error":"fake-db-secret"}', b'{"result":false}', b'{"result":"0"}',
                        b'bad-json', b'x'*4097]:
            with patch.object(self.quota.opener, 'open', return_value=io.BytesIO(content)) as call:
                with self.assertRaises(server.Problem) as error: self.quota.auth_attempt()
                self.assertEqual(error.exception.status, 503)
                self.assertNotIn('fake-db-secret', error.exception.message)
                call.assert_called_once()
        for error in [TimeoutError(), urllib.error.URLError('fake-db-secret')]:
            with patch.object(self.quota.opener, 'open', side_effect=error) as call:
                with self.assertRaises(server.Problem): self.quota.reserve('a'*64, 120, 3, 12)
                call.assert_called_once()

    def test_lua_daily_reservation_survives_new_client_and_secret_rotation(self):
        with self.lua():
            self.quota.reserve('a'*64, 2, 3, 12)
            rebuilt = RedisQuota('https://test.upstash.io', 'rotated-token')
            with self.assertRaises(server.Problem) as error: rebuilt.reserve('b'*64, 2, 3, 12)
        self.assertEqual(error.exception.status, 429)
        self.assertEqual(self.database.hget(self.quota.prefix+':daily', 'units'), b'2')

    def test_lua_day_rollover_and_expiry(self):
        daily = self.quota.prefix+':daily'
        self.database.hset(daily, mapping={'day':int(time.time()//86400)-1, 'units':120})
        with self.lua(): self.quota.reserve('a'*64, 2, 3, 12)
        self.assertEqual(self.database.hget(daily, 'units'), b'2')
        self.assertGreater(self.database.ttl(daily), 86400)
        self.assertGreater(self.database.ttl(self.quota.prefix+':minute'), 60)

    def test_lua_sliding_window_and_account_global_caps(self):
        for kind in ['account', 'global']:
            self.database.flushdb()
            with self.lua():
                self.quota.reserve('a'*64, 120, 1 if kind == 'account' else 3, 1 if kind == 'global' else 12)
                with self.assertRaises(server.Problem):
                    self.quota.reserve('a'*64 if kind == 'account' else 'b'*64, 120, 1 if kind == 'account' else 3, 1 if kind == 'global' else 12)
            self.assertEqual(self.database.hget(self.quota.prefix+':daily', 'units'), b'2')
        self.database.flushdb()
        self.database.zadd(self.quota.prefix+':minute', {'old':time.time()-61})
        with self.lua(): self.quota.reserve('a'*64, 120, 1, 1)
        self.assertEqual(self.database.zcard(self.quota.prefix+':minute'), 1)

    def test_lua_atomic_concurrent_reservations(self):
        def attempt(_):
            try:
                self.quota.reserve('a'*64, 8, 100, 100)
                return True
            except server.Problem as error:
                self.assertEqual(error.status, 429)
                return False
        with self.lua(), ThreadPoolExecutor(max_workers=8) as pool:
            accepted = list(pool.map(attempt, range(20)))
        self.assertEqual(sum(accepted), 4)
        self.assertEqual(self.database.hget(self.quota.prefix+':daily', 'units'), b'8')

    def test_lua_auth_cap_and_no_sensitive_records(self):
        with self.lua():
            for _ in range(180): self.quota.auth_attempt()
            with self.assertRaises(server.Problem): self.quota.auth_attempt()
        self.assertEqual(self.database.zcard(self.quota.prefix+':auth'), 180)
        self.assertGreater(self.database.ttl(self.quota.prefix+':auth'), 60)
        self.assertNotIn(b'fake-db-secret', b''.join(self.database.keys()))

    def test_backend_configuration_and_no_volatile_fallback(self):
        settings = dict(TESTING=True, PUBLIC_ORIGIN='https://hear-your-look.example',
                        SECRET_KEY='s'*40, ACCESS_PASSWORD='p'*32, QUOTA_BACKEND='upstash',
                        REDIS_URL='https://test.upstash.io', REDIS_TOKEN='fake-db-secret',
                        QUOTA_DB='', PERSISTENT_STORAGE=False)
        app = hosted.create_app(settings)
        self.assertIsInstance(app.extensions['hyl_quota'], RedisQuota)
        for changes in [{'QUOTA_BACKEND':'memory'}, {'REDIS_TOKEN':''}, {'REDIS_URL':'http://test.upstash.io'}]:
            with self.assertRaises(ValueError): hosted.create_app({**settings, **changes})

    def test_hosted_outage_blocks_model_and_failed_model_keeps_budget(self):
        origin = 'https://hear-your-look.example'
        app = hosted.create_app(dict(TESTING=True, PUBLIC_ORIGIN=origin, SECRET_KEY='s'*40,
                                    ACCESS_PASSWORD='p'*32, QUOTA_BACKEND='upstash', AI_ENABLED=True,
                                    REDIS_URL='https://test.upstash.io', REDIS_TOKEN='fake-db-secret', DAILY_CALLS=2))
        client = app.test_client()
        auth = 'Basic '+base64.b64encode(('team:'+'p'*32).encode()).decode()
        with self.lua(), patch.dict('os.environ', {'OPENROUTER_API_KEY':'fake-model-key'}):
            config = client.get('/api/config', base_url=origin, headers={'Authorization':auth}).json
            headers = {'Authorization':auth, 'Origin':origin, 'X-Local-Token':config['token']}
            def post(): return client.post('/api/analyze', base_url=origin, json=request_data(), headers=headers)
            with patch.object(app.extensions['hyl_quota'], 'reserve', side_effect=server.Problem(503, '额度保护不可用')):
                with patch('server.analyze') as model:
                    self.assertEqual(post().status_code, 503)
                    model.assert_not_called()
            with patch('server.analyze', side_effect=server.Problem(502, '模型失败')):
                self.assertEqual(post().status_code, 502)
            with patch('server.analyze') as model:
                self.assertEqual(post().status_code, 429)
                model.assert_not_called()


if __name__ == '__main__': unittest.main()
