#!/bin/bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
PYTHON="${COSTOLA_PYTHON:-python3.14}"
ARCH="${COSTOLA_ARCH:-$(uname -m)}"
OUT="${COSTOLA_BUILD_DIR:-$ROOT/build/$ARCH}"
CONFIGURATION="${COSTOLA_CONFIGURATION:-Debug}"
export COSTOLA_BUNDLE_ID="${COSTOLA_BUNDLE_ID:-com.cvarisco.costola.dev}"
case "$ARCH" in arm64|x86_64) ;; *) echo "Unsupported architecture: $ARCH" >&2; exit 1;; esac
"$PYTHON" -c 'import sys, platform; assert sys.version_info[:3] == (3, 14, 6), "Build requires Python 3.14.6"; assert platform.machine() == sys.argv[1], "Python architecture does not match target"' "$ARCH"
mkdir -p "$OUT"
"$PYTHON" -m PyInstaller --noconfirm --clean --distpath "$OUT/worker" --workpath "$OUT/pyinstaller" "$ROOT/packaging/worker.spec"
xcodebuild -project "$ROOT/app/StorageUtility.xcodeproj" -scheme StorageUtility \
    -configuration "$CONFIGURATION" COSTOLA_BUNDLE_ID="$COSTOLA_BUNDLE_ID" -derivedDataPath "$OUT/Xcode" ARCHS="$ARCH" ONLY_ACTIVE_ARCH=YES build
APP="$OUT/Xcode/Build/Products/$CONFIGURATION/Costola.app"
mkdir -p "$APP/Contents/Helpers" "$APP/Contents/Library/LaunchAgents"
rm -rf "$APP/Contents/Helpers/CostolaWorker.app" "$APP/Contents/Resources/Licenses"
rm -f "$APP/Contents/Library/LaunchAgents/"com.cvarisco.costola*.agent.plist
ditto "$OUT/worker/CostolaWorker.app" "$APP/Contents/Helpers/CostolaWorker.app"
cp "$OUT/Xcode/Build/Products/$CONFIGURATION/CostolaAgent" "$APP/Contents/MacOS/CostolaAgent"
PLIST="$APP/Contents/Library/LaunchAgents/$COSTOLA_BUNDLE_ID.agent.plist"
cp "$ROOT/app/StorageAgent/LaunchAgent.plist" "$PLIST"
/usr/libexec/PlistBuddy -c "Set :Label $COSTOLA_BUNDLE_ID.agent" "$PLIST"
mkdir -p "$APP/Contents/Resources/Licenses"
cp "$ROOT/LICENSE" "$APP/Contents/Resources/Licenses/Costola.txt"
ditto "$ROOT/packaging/licenses" "$APP/Contents/Resources/Licenses"
# UserNotifications checks the helper's signing identity against the app's grant.
codesign --force --sign - --options runtime --identifier "$COSTOLA_BUNDLE_ID" "$APP/Contents/MacOS/CostolaAgent"
codesign --force --sign - --options runtime "$APP"
codesign --verify --deep --strict "$APP"
"$APP/Contents/MacOS/CostolaAgent" --probe
printf 'Development bundle: %s\n' "$APP"
