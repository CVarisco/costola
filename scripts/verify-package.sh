#!/bin/bash
set -euo pipefail
APP="${1:?Usage: verify-package.sh app architecture [--release]}"
ARCH="${2:?Architecture required}"
MODE="${3:---development}"
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
case "$ARCH" in arm64|x86_64) ;; *) exit 2;; esac
case "$MODE" in --release|--development) ;; *) exit 2;; esac
codesign --verify --deep --strict "$APP"
python3 - "$APP" "$ARCH" "$MODE" "$ROOT/packaging/release-manifest.json" <<'PY'
import json
from pathlib import Path
import plistlib
import subprocess
import sys
app, architecture, mode = Path(sys.argv[1]), sys.argv[2], sys.argv[3]
info = plistlib.loads((app / 'Contents/Info.plist').read_bytes())
release = json.loads(Path(sys.argv[4]).read_text())
assert info['CFBundleShortVersionString'] == release['version']
assert info['LSMinimumSystemVersion'] == release['minimum_macos']
assert architecture in release['architectures']
agent_path = app / ('Contents/Library/LaunchAgents/' + info['CFBundleIdentifier'] + '.agent.plist')
agent = plistlib.loads(agent_path.read_bytes())
assert agent['Label'] == info['CFBundleIdentifier'] + '.agent'
assert agent['BundleProgram'] == 'Contents/MacOS/CostolaAgent'
agent_signature = subprocess.run(
    ['codesign', '-d', '--verbose=4', str(app / agent['BundleProgram'])],
    capture_output=True, text=True, check=True,
)
assert 'Identifier=' + info['CFBundleIdentifier'] in agent_signature.stderr.splitlines(), \
    'The agent must share the app signing identifier to use its notification permission.'
assert (app / 'Contents/Resources/Licenses/Costola.txt').is_file()
if mode == '--release':
    assert info['CFBundleIdentifier'] == release['bundle_id']
for path in app.rglob('*'):
    if not path.is_file() or path.is_symlink():
        continue
    with path.open('rb') as stream:
        magic = stream.read(4)
    if magic not in (b'\xcf\xfa\xed\xfe', b'\xce\xfa\xed\xfe', b'\xca\xfe\xba\xbe', b'\xbe\xba\xfe\xca'):
        continue
    architectures = subprocess.check_output(['lipo', '-archs', str(path)], text=True).split()
    assert architecture in architectures, (path, architectures)
    linked = '\n'.join(subprocess.check_output(['otool', '-L', str(path)], text=True).splitlines()[1:])
    assert not any(prefix in linked for prefix in ('/Users/', '/opt/homebrew/', '/usr/local/')), path
probe = subprocess.run([str(app / 'Contents/MacOS/CostolaAgent'), '--probe'],
                       capture_output=True, text=True, check=True, env={'PATH': '/usr/bin:/bin'})
response = json.loads(probe.stdout)
assert response['success'] and response['data']['frozen']
assert response['data']['architecture'] == architecture
assert response['data']['python_version'] == release['python']
print('Bundled runtime, architecture and dependency checks passed.')
PY
if [ "$MODE" = --release ]; then
    codesign -dv --verbose=4 "$APP" 2>&1 | grep -q 'Authority=Developer ID Application:'
    xcrun stapler validate "$APP"
    spctl --assess --type execute --verbose=2 "$APP"
fi
