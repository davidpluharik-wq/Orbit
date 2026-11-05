#!/usr/bin/env python3
"""Generate an executable Linux launcher for the current checkout/interpreter."""
import argparse
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]


def quote_exec(value):
    # Desktop Entry Exec quoting is different from shell quoting.
    return '"' + str(value).replace('\\', '\\\\').replace('"', '\\"').replace('`', '\\`').replace('$', '\\$').replace('%', '%%') + '"'


def launcher():
    return '\n'.join([
        '[Desktop Entry]', 'Version=1.0', 'Type=Application', 'Name=Orbit',
        'Comment=A private workspace for projects, notes, and focus',
        f'Exec={quote_exec(sys.executable)} {quote_exec(ROOT / "app.py")}',
        f'Path={ROOT}', f'Icon={ROOT / "assets" / "orbit.svg"}',
        'Terminal=false', 'Categories=Office;ProjectManagement;',
        'StartupNotify=true', 'StartupWMClass=orbit', '',
    ])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--desktop', action='store_true', help='Also copy the launcher to ~/Desktop (requires write access).')
    args = parser.parse_args()
    destinations = [ROOT / 'Orbit.desktop']
    if args.desktop:
        destinations.append(Path.home() / 'Desktop' / 'Orbit.desktop')
    for destination in destinations:
        try:
            destination.write_text(launcher(), encoding='utf-8')
            destination.chmod(destination.stat().st_mode | 0o111)
            print(f'Created {destination}')
        except OSError as exc:
            print(f'Could not create {destination}: {exc}', file=sys.stderr)
            return 1
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
