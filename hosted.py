"""Single-instance HTTPS deployment with optional anonymous access.

Public access never removes consent, CSRF, durable quotas or the AI kill switch.
Never load .env.local here.
"""
import hmac
import hashlib
import os
from pathlib import Path
import secrets
import sqlite3
import threading
import time
from urllib.parse import urlsplit

from flask import Flask, jsonify, request, send_file, session
from werkzeug.middleware.proxy_fix import ProxyFix
from werkzeug.exceptions import HTTPException
import server
from redis_quota import RedisQuota


class Quota:
    """Conservative durable reservations: up to two provider calls per check.

    Failed or quality-rejected checks do not refund reservations. No images,
    passwords, responses, IPs or raw account names enter the database.
    """
    def __init__(self, path):
        self.path = str(path)
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as db:
            db.execute('CREATE TABLE IF NOT EXISTS checks (at REAL, account TEXT, units INTEGER)')
            db.execute('CREATE INDEX IF NOT EXISTS checks_at ON checks(at)')
            db.execute('CREATE TABLE IF NOT EXISTS auth_attempts (at REAL)')

    def connect(self):
        return sqlite3.connect(self.path, timeout=5)

    def auth_attempt(self):
        # Global cap also applies to successful authentications, bounding guesses.
        # Every asset uses Basic auth; allow enough for loading the page.
        now = time.time()
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            db.execute('DELETE FROM auth_attempts WHERE at < ?', (now - 60,))
            if db.execute('SELECT COUNT(*) FROM auth_attempts').fetchone()[0] >= 180:
                raise server.Problem(429, '访问验证过于频繁，请一分钟后重试。')
            db.execute('INSERT INTO auth_attempts VALUES (?)', (now,))

    def reserve(self, account, daily, per_account, global_rate):
        now = time.time()
        day_start = int(now // 86400) * 86400  # Explicit UTC day.
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            db.execute('DELETE FROM checks WHERE at < ?', (day_start - 60,))
            if db.execute('SELECT COALESCE(SUM(units),0) FROM checks WHERE at >= ?', (day_start,)).fetchone()[0] + 2 > daily:
                raise server.Problem(429, '今日真实检查预算已用完。可使用明确标注的预设演示；预算按 UTC 日期恢复。')
            if db.execute('SELECT COUNT(*) FROM checks WHERE at >= ?', (now - 60,)).fetchone()[0] >= global_rate:
                raise server.Problem(429, '网站检查请求过于频繁，请一分钟后重试。')
            if db.execute('SELECT COUNT(*) FROM checks WHERE at >= ? AND account = ?', (now - 60, account)).fetchone()[0] >= per_account:
                raise server.Problem(429, '此访问账号检查过于频繁，请一分钟后重试；共享账号合并计算。')
            db.execute('INSERT INTO checks VALUES (?,?,2)', (now, account))


def create_app(overrides=None):
    app = Flask(__name__, static_folder=None)
    app.config.update(
        SECRET_KEY=os.environ.get('HYL_SESSION_SECRET', ''),
        PUBLIC_ORIGIN=os.environ.get('PUBLIC_ORIGIN', ''),
        ACCESS_USER=os.environ.get('HYL_ACCESS_USER', 'team'),
        ACCESS_PASSWORD=os.environ.get('HYL_ACCESS_PASSWORD', ''),
        PUBLIC_ACCESS=os.environ.get('HYL_PUBLIC_ACCESS', '0') == '1',
        QUOTA_DB=os.environ.get('HYL_QUOTA_DB', ''),
        QUOTA_BACKEND=os.environ.get('HYL_QUOTA_BACKEND', 'sqlite'),
        REDIS_URL=os.environ.get('UPSTASH_REDIS_REST_URL', ''),
        REDIS_TOKEN=os.environ.get('UPSTASH_REDIS_REST_TOKEN', ''),
        QUOTA_PREFIX=os.environ.get('HYL_QUOTA_PREFIX', 'hyl:{hear-your-look}'),
        PERSISTENT_STORAGE=os.environ.get('HYL_PERSISTENT_STORAGE') == '1',
        AI_ENABLED=os.environ.get('HYL_AI_ENABLED', '0') == '1',
        DAILY_CALLS=int(os.environ.get('HYL_DAILY_MODEL_CALLS', '120')),
        ACCOUNT_RATE=int(os.environ.get('HYL_ACCOUNT_PER_MINUTE', '3')),
        GLOBAL_RATE=int(os.environ.get('HYL_GLOBAL_PER_MINUTE', '12')),
        MAX_CONTENT_LENGTH=server.MAX_BODY,
        SESSION_COOKIE_NAME='__Host-hyl', SESSION_COOKIE_SECURE=True,
        SESSION_COOKIE_HTTPONLY=True, SESSION_COOKIE_SAMESITE='Strict',
        PERMANENT_SESSION_LIFETIME=28800,
    )
    if overrides: app.config.update(overrides)
    c = app.config
    origin = urlsplit(c['PUBLIC_ORIGIN'])
    if (origin.scheme != 'https' or not origin.hostname or origin.username or origin.password
            or origin.path or origin.query or origin.fragment):
        raise ValueError('PUBLIC_ORIGIN must be the exact HTTPS origin without trailing slash.')
    if len(c['SECRET_KEY']) < 32 or (not c['PUBLIC_ACCESS'] and
            (len(c['ACCESS_PASSWORD']) < 24 or not c['ACCESS_USER'])):
        raise ValueError('Set strong session secret (32+ chars) and access password (24+ chars).')
    if min(c['DAILY_CALLS'], c['ACCOUNT_RATE'], c['GLOBAL_RATE']) < 1:
        raise ValueError('All quotas must be positive.')
    if c['QUOTA_BACKEND'] == 'upstash':
        quota = RedisQuota(c['REDIS_URL'], c['REDIS_TOKEN'], c['QUOTA_PREFIX'])
    elif c['QUOTA_BACKEND'] == 'sqlite':
        db_path = Path(c['QUOTA_DB'])
        if not db_path.is_absolute() or not c['PERSISTENT_STORAGE'] or db_path.is_relative_to(server.WEB):
            raise ValueError('A confirmed persistent absolute QUOTA_DB path outside web assets is required.')
        quota = Quota(db_path)
    else:
        raise ValueError('QUOTA_BACKEND must be sqlite or upstash; no volatile fallback is allowed.')
    app.extensions['hyl_quota'] = quota
    gate = threading.BoundedSemaphore(1)
    # Render terminates HTTPS at one trusted proxy. Do not trust forwarded Host
    # or IP; neither is needed for this account-based policy.
    app.wsgi_app = ProxyFix(app.wsgi_app, x_for=0, x_proto=1, x_host=0, x_port=0, x_prefix=0)

    def fail(code, message):
        return jsonify(error=message), code

    @app.before_request
    def protect():
        if request.path == '/healthz': return None  # Non-sensitive platform probe.
        if request.host.lower() != origin.netloc.lower() or not request.is_secure:
            return fail(403, '请使用正式 HTTPS 网站地址访问。')
        # Public pages remain readable during a quota-store outage. API requests
        # still use the durable global request cap; never fail open for AI.
        if not c['PUBLIC_ACCESS'] or request.path.startswith('/api/'):
            quota.auth_attempt()
        auth = request.authorization
        if not c['PUBLIC_ACCESS'] and (not auth or auth.type.lower() != 'basic'
                or not hmac.compare_digest((auth.username or '').encode(), c['ACCESS_USER'].encode())
                or not hmac.compare_digest((auth.password or '').encode(), c['ACCESS_PASSWORD'].encode())):
            response = jsonify(error='请输入团队访问账号与密码。')
            response.status_code = 401
            response.headers['WWW-Authenticate'] = 'Basic realm="Hear Your Look", charset="UTF-8"'
            return response
        if request.method not in ('GET', 'HEAD'):
            if request.headers.get('Origin') != c['PUBLIC_ORIGIN']:
                return fail(403, '请求来源无效，请回到正式网页操作。')
            csrf = session.get('csrf')
            if not csrf or not hmac.compare_digest(request.headers.get('X-Local-Token', ''), csrf):
                return fail(403, '会话已失效，请刷新网页后重新同意发送。')

    @app.after_request
    def headers(response):
        response.headers.update({
            'Cache-Control': 'no-store', 'X-Content-Type-Options': 'nosniff',
            'Referrer-Policy': 'no-referrer', 'X-Frame-Options': 'DENY',
            'Strict-Transport-Security': 'max-age=31536000',
            'Content-Security-Policy': "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data: blob:; media-src 'self' blob:; font-src 'self'; connect-src 'self'; object-src 'none'; frame-ancestors 'none'; base-uri 'self'; form-action 'self'",
            'Permissions-Policy': 'camera=(self), microphone=(), geolocation=()',
        })
        if response.status_code == 429: response.headers['Retry-After'] = '60'
        return response

    @app.errorhandler(server.Problem)
    def known_error(error): return fail(error.status, error.message)

    @app.errorhandler(Exception)
    def unexpected(error):
        if isinstance(error, HTTPException):
            return fail(error.code, {413: '照片请求过大，请重新准备。', 400: '请求格式无法读取，请重新准备。',
                                     404: '文件或接口不存在。', 405: '请求方式无效。'}.get(error.code, '请求未完成。'))
        # Never log request bodies, Authorization, environment or model output.
        return fail(503, '服务暂时未能完成请求，请稍后重试。没有生成检查结果。')

    @app.get('/healthz')
    def health(): return jsonify(status='ok')

    @app.get('/api/config')
    def config():
        if 'csrf' not in session: session['csrf'] = secrets.token_urlsafe(32)
        session.permanent = True
        return jsonify(ready=c['AI_ENABLED'] and bool(os.environ.get('OPENROUTER_API_KEY', '').strip()),
                       model=os.environ.get('OPENROUTER_MODEL', 'google/gemini-2.5-flash'), token=session['csrf'],
                       message=('真实检查已由团队暂时关闭；可以选择预设演示。' if not c['AI_ENABLED'] else
                                '网站尚未配置模型密钥，请联系团队。'))

    @app.post('/api/analyze')
    def analyze():
        if not c['AI_ENABLED']: raise server.Problem(503, '真实检查已由团队暂时关闭；可以选择预设演示。')
        if not os.environ.get('OPENROUTER_API_KEY', '').strip(): raise server.Problem(503, '网站尚未配置模型密钥，请联系团队。')
        if request.mimetype != 'application/json': raise server.Problem(415, '请求格式无效。')
        data = request.get_json()
        server.validate_input(data)
        if not gate.acquire(blocking=False): raise server.Problem(429, '另一张照片仍在处理，请稍后重试。')
        try:
            # All anonymous visitors share one quota bucket. No IP tracking or
            # trusting forwarded IP headers; new browsers cannot bypass limits.
            account = ('public' if c['PUBLIC_ACCESS'] else
                       hmac.new(c['SECRET_KEY'].encode(), c['ACCESS_USER'].encode(), hashlib.sha256).hexdigest())
            quota.reserve(account, c['DAILY_CALLS'], c['ACCOUNT_RATE'], c['GLOBAL_RATE'])
            return jsonify(server.analyze(data))
        finally: gate.release()

    @app.get('/')
    @app.get('/<path:path>')
    def assets(path='index.html'):
        allowed = {'index.html', 'style.css', 'polish.css', 'checks.css', 'integration.css', 'app.js', 'analysis.js', 'polish.js'}
        target = server.WEB / path
        if path not in allowed and not (path.startswith('assets/') and target.suffix.lower() in {'.png', '.jpg', '.webp', '.svg', '.woff2'}):
            raise server.Problem(404, '文件不存在。')
        if not target.resolve().is_relative_to(server.WEB.resolve()) or not target.is_file() or target.is_symlink():
            raise server.Problem(404, '文件不存在。')
        return send_file(target, conditional=False, etag=False)

    return app
