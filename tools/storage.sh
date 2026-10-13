#!/bin/bash
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PYTHON="${SSD_MIGRATION_PYTHON:-/usr/bin/python3}"
exec "$PYTHON" "$SCRIPT_DIR/../core/storage_manager.py" "$@"
