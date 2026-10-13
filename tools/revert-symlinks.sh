#!/bin/bash
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
if [ "${1:-}" = "--dry-run" ]; then
    exec /bin/bash "$SCRIPT_DIR/storage.sh" restore --dry-run
fi
printf 'Restore all managed data to internal storage? [y/N] '
read -r reply
[[ "$reply" =~ ^[Yy]$ ]] || exit 0
exec /bin/bash "$SCRIPT_DIR/storage.sh" restore
