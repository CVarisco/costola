#!/bin/bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
PYTHON="${COSTOLA_PYTHON:-python3.14}"
ARCH="${COSTOLA_ARCH:-$(uname -m)}"
OUT="${COSTOLA_BUILD_DIR:-$ROOT/build/$ARCH}"
case "$ARCH" in arm64|x86_64) ;; *) echo "Unsupported architecture: $ARCH" >&2; exit 1;; esac
"$PYTHON" -c 'import sys, platform; assert sys.version_info[:3] == (3, 14, 6), "Build requires Python 3.14.6"; assert platform.machine() == sys.argv[1], "Python architecture does not match target"' "$ARCH"
mkdir -p "$OUT"
"$PYTHON" -m PyInstaller --noconfirm --clean --distpath "$OUT/worker" --workpath "$OUT/pyinstaller" "$ROOT/packaging/worker.spec"
xcodebuild -project "$ROOT/app/StorageUtility.xcodeproj" -scheme StorageUtility \
    -configuration Debug -derivedDataPath "$OUT/Xcode" ARCHS="$ARCH" ONLY_ACTIVE_ARCH=YES build
APP="$OUT/Xcode/Build/Products/Debug/Costola.app"
mkdir -p "$APP/Contents/Helpers" "$APP/Contents/Library/LaunchAgents"
ditto "$OUT/worker/CostolaWorker.app" "$APP/Contents/Helpers/CostolaWorker.app"
cp "$OUT/Xcode/Build/Products/Debug/CostolaAgent" "$APP/Contents/MacOS/CostolaAgent" --probe
cp "$ROOT/app/StorageAgent/LaunchAgent.plist" "$APP/Contents/Library/LaunchAgents/com.cvarisco.costola.dev.agent.plist"
codesign --force --sign - --options runtime "$APP"
codesign --verify --deep --strict "$APP"
"$APP/Contents/MacOS/CostolaAgent" --probe
printf 'Development bundle: %s\n' "$APP"
