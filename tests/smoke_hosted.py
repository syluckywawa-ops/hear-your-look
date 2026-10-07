"""Local real Gunicorn HTTP smoke; simulates trusted TLS proxy, no model calls."""
import base64
import json
import os
from pathlib import Path
import secrets
import socket
import subprocess
import sys
import tempfile
import time
import urllib.request
import urllib.error

ROOT = Path(__file__).resolve().parents[1]


def run():
    with socket.socket() as sock:
        sock.bind(('127.0.0.1', 0))
        port = sock.getsockname()[1]
    origin = f'https://127.0.0.1:{port}'
    password = secrets.token_urlsafe(32)
    auth = 'Basic ' + base64.b64encode(('team:'+password).encode()).decode()
    with tempfile.TemporaryDirectory() as tmp:
        env = {**os.environ, 'PUBLIC_ORIGIN':origin, 'HYL_SESSION_SECRET':secrets.token_urlsafe(40),
               'HYL_ACCESS_USER':'team', 'HYL_ACCESS_PASSWORD':password,
               'HYL_QUOTA_DB':tmp+'/quota.sqlite3', 'HYL_PERSISTENT_STORAGE':'1', 'HYL_AI_ENABLED':'0',
               'OPENROUTER_API_KEY':''}
        process = subprocess.Popen([sys.executable, '-m', 'gunicorn', '--config', 'gunicorn.conf.py',
                                    '--bind', f'127.0.0.1:{port}', 'hosted:create_app()'], cwd=ROOT,
                                   env=env, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
        def get(path, logged=False):
            headers = {'X-Forwarded-Proto':'https'}
            if logged: headers['Authorization'] = auth
            req = urllib.request.Request(f'http://127.0.0.1:{port}'+path, headers=headers)
            try:
                with urllib.request.urlopen(req, timeout=2) as response: return response.status, response.read()
            except urllib.error.HTTPError as error: return error.code, error.read()
        try:
            for _ in range(50):
                try:
                    if get('/healthz')[0] == 200: break
                except (urllib.error.URLError, TimeoutError):
                    if process.poll() is not None:
                        raise RuntimeError('Gunicorn startup failed: '+process.stderr.read().decode()[-2000:])
                    time.sleep(.1)
            else: raise RuntimeError('Gunicorn did not start')
            assert get('/')[0] == 401
            code, body = get('/', True)
            assert code == 200 and '听见妆容'.encode() in body
            code, body = get('/api/config', True)
            assert code == 200 and json.loads(body)['ready'] is False
            assert get('/server.py', True)[0] == 404
            assert get('/app.js', True)[0] == 200
            print('Gunicorn 实际进程验收：健康探针、未登录拦截、登录页面、关闭真实调用、源文件拒绝、前端资源全部通过。无真实模型调用。')
        finally:
            process.terminate()
            try: process.wait(timeout=5)
            except subprocess.TimeoutExpired: process.kill(); process.wait()
            process.stderr.close()


if __name__ == '__main__': run()
