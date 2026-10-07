"""Create an allowlisted deployment archive; never scan/include secret files."""
from pathlib import Path
import argparse
import re
import zipfile

ROOT = Path(__file__).resolve().parents[1]
WEB = ROOT / 'hear-your-look-website'
TOP = ['server.py', 'start.py', '启动听见妆容.command', 'hosted.py', 'gunicorn.conf.py',
       'requirements.txt', 'render.yaml', 'DEPLOYMENT.md', '.gitignore',
       'tests/test_server.py', 'tests/test_analysis.cjs', 'tests/test_hosted.py',
       'tests/smoke_hosted.py', 'scripts/package_deployment.py']
WEB_FILES = ['index.html', 'style.css', 'polish.css', 'checks.css', 'integration.css', 'app.js', 'analysis.js', 'polish.js']


def package(output):
    files = [ROOT / name for name in TOP] + [WEB / name for name in WEB_FILES]
    files += sorted((WEB / 'assets').rglob('*'))
    files = [p for p in files if p.is_file() and not p.is_symlink() and
             (p.parent != WEB / 'assets' or p.suffix.lower() in {'.png','.jpg','.webp','.svg','.woff2'})]
    # Strict asset extension allowlist applies to nested folders as well.
    files = [p for p in files if not p.is_relative_to(WEB / 'assets') or p.suffix.lower() in {'.png','.jpg','.webp','.svg','.woff2'}]
    for file in files:
        if not file.resolve().is_relative_to(ROOT): raise ValueError('Path leaves project')
    # Ensure every directly referenced image/asset exists before sharing.
    for source in [WEB / n for n in WEB_FILES]:
        text = source.read_text()
        for name in re.findall(r'assets/[A-Za-z0-9_./-]+', text):
            target = WEB / name
            if not target.is_file(): raise ValueError('Missing referenced asset: '+name)
    output = Path(output).resolve()
    if output.exists(): raise FileExistsError('Choose a new output name to preserve previous packages.')
    output.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(output, 'w', zipfile.ZIP_DEFLATED) as archive:
        for file in files: archive.write(file, file.relative_to(ROOT).as_posix())
        archive.writestr('README.md', (ROOT / 'DEPLOYMENT.md').read_text())
    with zipfile.ZipFile(output) as archive:
        assert archive.testzip() is None
        assert all(not name.startswith('.env') and '.venv/' not in name and not name.endswith('.sqlite3') for name in archive.namelist())
    return len(files)+1


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('output')
    args = parser.parse_args()
    count = package(args.output)
    print(f'发布包已创建：{count} 个文件；不含 .env、密钥、数据库或开发环境。')
