#!/bin/bash
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
/bin/bash "$SCRIPT_DIR/../tools/storage.sh" attach
/bin/bash "$SCRIPT_DIR/../tools/storage.sh" migrate --category cache
/bin/bash "$SCRIPT_DIR/../tools/storage.sh" configure
