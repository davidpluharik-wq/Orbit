#!/usr/bin/env python3
"""Create a shareable source ZIP from an explicit allowlist; never include workspace data."""
from pathlib import Path
import sys
from zipfile import ZIP_DEFLATED, ZipFile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from orbit import __version__

ROOT_FILES = (
    'app.py', 'web_app.py', 'pyproject.toml', 'requirements.txt', 'README.md',
    'LICENSE', 'CONTRIBUTING.md', 'CHANGELOG.md', '.gitignore', 'MANIFEST.in',
)
FOLDERS = ('orbit', 'scripts', 'tests', 'docs', '.github', 'static', 'assets')
EXTENSIONS = {'.py', '.md', '.toml', '.txt', '.yml', '.svg', '.png', '.html', '.css', '.js'}


def main():
    target = ROOT / 'dist' / f'orbit-{__version__}-source.zip'
    target.parent.mkdir(exist_ok=True)
    files = [ROOT / name for name in ROOT_FILES]
    for folder in FOLDERS:
        files.extend(path for path in (ROOT / folder).rglob('*')
                     if path.is_file() and not path.is_symlink() and path.suffix in EXTENSIONS
                     and '__pycache__' not in path.parts)
    with ZipFile(target, 'w', ZIP_DEFLATED) as archive:
        for path in sorted(files):
            archive.write(path, f'Orbit/{path.relative_to(ROOT).as_posix()}')
    print(f'Created {target} ({len(files)} public source files)')


if __name__ == '__main__':
    main()
