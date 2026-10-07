"""Durable quota counters over Upstash REST; never send images or model results."""
import json
import re
import secrets
import urllib.error
import urllib.request
from urllib.parse import urlsplit

import server

AUTH_SCRIPT = """
local clock = redis.call('TIME')
local now = tonumber(clock[1]) + tonumber(clock[2]) / 1000000
redis.call('ZREMRANGEBYSCORE', KEYS[1], '-inf', now - 60)
if redis.call('ZCARD', KEYS[1]) >= 180 then return 1 end
redis.call('ZADD', KEYS[1], now, ARGV[1])
redis.call('EXPIRE', KEYS[1], 120)
return 0
"""

RESERVE_SCRIPT = """
local clock = redis.call('TIME')
local now = tonumber(clock[1]) + tonumber(clock[2]) / 1000000
local day = math.floor(now / 86400)
local stored_day = tonumber(redis.call('HGET', KEYS[1], 'day') or '-1')
local units = 0
if stored_day == day then units = tonumber(redis.call('HGET', KEYS[1], 'units') or '0') end
if units + 2 > tonumber(ARGV[1]) then return 1 end
redis.call('ZREMRANGEBYSCORE', KEYS[2], '-inf', now - 60)
redis.call('ZREMRANGEBYSCORE', KEYS[3], '-inf', now - 60)
if redis.call('ZCARD', KEYS[2]) >= tonumber(ARGV[3]) then return 2 end
if redis.call('ZCARD', KEYS[3]) >= tonumber(ARGV[2]) then return 3 end
redis.call('HSET', KEYS[1], 'day', day, 'units', units + 2)
redis.call('EXPIRE', KEYS[1], 172800)
redis.call('ZADD', KEYS[2], now, ARGV[4])
redis.call('ZADD', KEYS[3], now, ARGV[4])
redis.call('EXPIRE', KEYS[2], 120)
redis.call('EXPIRE', KEYS[3], 120)
return 0
"""


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None  # Never forward a database bearer credential to a redirect.


class RedisQuota:
    def __init__(self, url, token, prefix='hyl:{hear-your-look}'):
        endpoint = urlsplit(url)
        if (endpoint.scheme != 'https' or not endpoint.hostname
                or not re.fullmatch(r'[a-z0-9-]+\.upstash\.io', endpoint.hostname)
                or endpoint.username or endpoint.password or endpoint.port
                or endpoint.path not in ('', '/') or endpoint.query or endpoint.fragment):
            raise ValueError('Use the exact HTTPS Upstash REST endpoint, not a connection string.')
        if not token or token != token.strip() or '\n' in token or '\r' in token:
            raise ValueError('A server-side Upstash REST token is required.')
        if not re.fullmatch(r'[A-Za-z0-9:_{}-]{1,64}', prefix):
            raise ValueError('Use a stable quota prefix of 1-64 safe characters.')
        self.url, self.token, self.prefix = url.rstrip('/'), token, prefix
        self.opener = urllib.request.build_opener(NoRedirect())

    def execute(self, script, keys, args):
        command = ['EVAL', script, len(keys), *keys, *args]
        req = urllib.request.Request(self.url, data=json.dumps(command).encode(), method='POST',
                                     headers={'Authorization':'Bearer '+self.token,
                                              'Content-Type':'application/json'})
        try:
            with self.opener.open(req, timeout=8) as response:
                # Only tiny integer results are accepted. No automatic retries:
                # a timeout may have already reserved budget on the server.
                body = response.read(4097)
            if len(body) > 4096: raise ValueError('Oversize quota response')
            result = json.loads(body)
            if not isinstance(result, dict) or set(result) != {'result'} or type(result['result']) is not int:
                raise ValueError('Invalid quota response')
            return result['result']
        except (urllib.error.URLError, TimeoutError, OSError, ValueError, TypeError):
            raise server.Problem(503, '额度保护服务暂不可用，已停止真实检查。请稍后重试。') from None

    def auth_attempt(self):
        result = self.execute(AUTH_SCRIPT, [self.prefix+':auth'], [secrets.token_hex(16)])
        if result == 1: raise server.Problem(429, '访问验证过于频繁，请一分钟后重试。')
        if result != 0: raise server.Problem(503, '额度保护结果无效，已停止服务。')

    def reserve(self, account, daily, per_account, global_rate):
        result = self.execute(RESERVE_SCRIPT,
                              [self.prefix+':daily', self.prefix+':minute', self.prefix+':account:'+account],
                              [daily, per_account, global_rate, secrets.token_hex(16)])
        messages = {
            1: '今日真实检查预算已用完。可使用明确标注的预设演示；预算按 UTC 日期恢复。',
            2: '网站检查请求过于频繁，请一分钟后重试。',
            3: '此访问账号检查过于频繁，请一分钟后重试；共享账号合并计算。',
        }
        if result in messages: raise server.Problem(429, messages[result])
        if result != 0: raise server.Problem(503, '额度保护结果无效，已停止真实检查。')
