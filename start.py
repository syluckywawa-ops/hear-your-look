"""Select an installed Python with working TLS verification; never disable TLS."""
from pathlib import Path
import os
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parent
probe = "import urllib.request; r=urllib.request.urlopen('https://openrouter.ai/api/v1/models', timeout=8); assert r.status==200"
candidates = [sys.executable, shutil.which('python3'), str(Path.home() / '.cache/codex-runtimes/codex-primary-runtime/dependencies/python/bin/python3')]
seen = set()
for candidate in candidates:
    if not candidate or candidate in seen or not Path(candidate).is_file(): continue
    seen.add(candidate)
    try:
        result = subprocess.run([candidate, '-c', probe], capture_output=True, timeout=12)
    except (OSError, subprocess.TimeoutExpired):
        continue
    if result.returncode == 0:
        print('安全连接自检通过，启动本机网页服务。', flush=True)
        os.chdir(ROOT)
        os.execv(candidate, [candidate, str(ROOT / 'server.py')])
print('没有找到能安全连接 OpenRouter 的 Python。请检查网络、DNS 和该 Python 的 CA 证书配置；不要关闭证书验证。', file=sys.stderr)
sys.exit(1)
