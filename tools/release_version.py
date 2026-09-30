"""Keep application, installer and Windows metadata versions aligned."""
import argparse
import os
import re
from pathlib import Path

root = Path(__file__).resolve().parents[1]
parser = argparse.ArgumentParser()
parser.add_argument('version', nargs='?')
parser.add_argument('--check', action='store_true')
args = parser.parse_args()
current = re.search(r'APP_VERSION = "(\d+\.\d+\.\d+)"', (root/'version.py').read_text()).group(1)
if args.check:
    assert f'#define AppVersion "{current}"' in (root/'flow.iss').read_text(), 'Installer version differs'
    metadata = (root/'version.txt').read_text()
    assert metadata.count(current) == 2, 'Windows product/file version differs'
    assert metadata.count(', '.join(current.split('.')) + ', 0') == 2, 'Windows numeric version differs'
    ref = os.environ.get('GITHUB_REF', '')
    assert not ref.startswith('refs/tags/') or ref == 'refs/tags/v' + current, 'Tag differs from app version'
    print(current)
else:
    if not args.version or not re.fullmatch(r'\d+\.\d+\.\d+', args.version):
        parser.error('Use a stable version such as 1.5.6')
    for name in ('version.py', 'flow.iss', 'version.txt'):
        path = root/name
        text = path.read_text()
        text = text.replace(current, args.version).replace(', '.join(current.split('.')) + ', 0', ', '.join(args.version.split('.')) + ', 0')
        path.write_text(text)
    print(f'{current} -> {args.version}')
