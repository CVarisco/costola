#!/bin/bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
: "${COSTOLA_SIGN_IDENTITY:?Set the Developer ID Application signing identity}"
: "${COSTOLA_NOTARY_PROFILE:?Set a notarytool keychain profile}"
ARCH="${COSTOLA_ARCH:-$(uname -m)}"
export COSTOLA_ARCH="$ARCH" COSTOLA_CONFIGURATION=Release COSTOLA_BUNDLE_ID=com.cvarisco.costola
VERSION="$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["version"])' "$ROOT/packaging/release-manifest.json")"
if [ "$(git -C "$ROOT" describe --tags --exact-match)" != "v$VERSION" ]; then
    echo 'Release requires the version tag at HEAD.' >&2; exit 1
fi
if [ -n "$(git -C "$ROOT" status --porcelain)" ]; then
    echo 'Release requires a clean checkout.' >&2; exit 1
fi
"$ROOT/scripts/build-app.sh"
APP="$ROOT/build/$ARCH/Xcode/Build/Products/Release/Costola.app"
OUT="$ROOT/dist/$ARCH"
mkdir -p "$OUT"
# Sign actual Mach-O files first, then enclosing code bundles, then the app.
python3 - "$APP" "$COSTOLA_SIGN_IDENTITY" <<'PY'
from pathlib import Path
import plistlib
import subprocess
import sys
app, identity = Path(sys.argv[1]), sys.argv[2]
bundle_id = plistlib.loads((app / 'Contents/Info.plist').read_bytes())['CFBundleIdentifier']
def sign(path):
    options = ['--identifier', bundle_id] if path == app / 'Contents/MacOS/CostolaAgent' else []
    subprocess.run(['codesign', '--force', '--sign', identity, '--options', 'runtime', '--timestamp', *options, str(path)], check=True)
for path in app.rglob('*'):
    if path.is_file() and not path.is_symlink():
        with path.open('rb') as stream:
            magic = stream.read(4)
        if magic in (b'\xcf\xfa\xed\xfe', b'\xce\xfa\xed\xfe', b'\xca\xfe\xba\xbe', b'\xbe\xba\xfe\xca'):
            sign(path)
for path in sorted(app.rglob('*'), key=lambda p: len(p.parts), reverse=True):
    if path.is_dir() and not path.is_symlink() and path.suffix in ('.framework', '.app'):
        sign(path)
sign(app)
PY
codesign --verify --deep --strict "$APP"
ditto -c -k --keepParent "$APP" "$OUT/Costola-notary.zip"
xcrun notarytool submit "$OUT/Costola-notary.zip" --keychain-profile "$COSTOLA_NOTARY_PROFILE" --wait --output-format json > "$OUT/app-notary.json"
python3 -c 'import json,sys; assert json.load(open(sys.argv[1]))["status"] == "Accepted"' "$OUT/app-notary.json"
xcrun stapler staple "$APP"
"$ROOT/scripts/verify-package.sh" "$APP" "$ARCH" --release
STAGE="$(mktemp -d)"
trap 'rm -rf "$STAGE"' EXIT
ditto "$APP" "$STAGE/Costola.app"
cp "$ROOT/LICENSE" "$STAGE/LICENSE.txt"
ln -s /Applications "$STAGE/Applications"
DMG="$OUT/Costola-$VERSION-$ARCH.dmg"
hdiutil create -volname Costola -srcfolder "$STAGE" -format UDZO -ov "$DMG"
codesign --sign "$COSTOLA_SIGN_IDENTITY" --timestamp "$DMG"
xcrun notarytool submit "$DMG" --keychain-profile "$COSTOLA_NOTARY_PROFILE" --wait --output-format json > "$OUT/dmg-notary.json"
python3 -c 'import json,sys; assert json.load(open(sys.argv[1]))["status"] == "Accepted"' "$OUT/dmg-notary.json"
xcrun stapler staple "$DMG"
xcrun stapler validate "$DMG"
spctl --assess --type open --context context:primary-signature --verbose=2 "$DMG"
(cd "$ROOT" && COSTOLA_RELEASE_DMG="$DMG" python3 -B -m unittest discover -s tests/macos -p test_release_package.py -v)
(cd "$OUT" && shasum -a 256 "$(basename "$DMG")" > "$(basename "$DMG").sha256")
printf 'Verified release candidate: %s\n' "$DMG"
