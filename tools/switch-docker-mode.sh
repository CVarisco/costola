#!/bin/bash
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
# Docker storage remains external-only by default. Never silently create a new local VM.
case "${1:-auto}" in
    auto|ssd)
        /bin/bash "$SCRIPT_DIR/storage.sh" status
        printf '\nDocker storage is managed in Docker Desktop > Settings > Resources > Advanced.\n'
        printf 'Existing Docker.raw on T9 is retained. No settings were changed.\n'
        ;;
    local)
        printf 'Local Docker mode is disabled to prevent unbounded internal storage growth.\n' >&2
        printf 'Use Docker Desktop to explicitly select an existing local disk image.\n' >&2
        exit 1
        ;;
    *) printf 'Usage: %s [auto|ssd|local]\n' "$0" >&2; exit 1 ;;
esac
