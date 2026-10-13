#!/bin/bash
# ============================================================
# Common helpers for SSD migration scripts
# Source this file, don't execute it directly.
# ============================================================

SSD_VOLUME="${SSD_VOLUME:-$HOME/.ssd-migration-mount}"
COMMON_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
MIGRATION_REGISTRY="$HOME/.ssd-migration-links.tsv"
FALLBACK_ROOT="$HOME/.ssd-migration-fallback"

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
BOLD='\033[1m'
NC='\033[0m'

log_info()    { echo -e "${BLUE}ℹ ${NC} $1"; }
log_success() { echo -e "${GREEN}✅${NC} $1"; }
log_warn()    { echo -e "${YELLOW}⚠️ ${NC} $1"; }
log_error()   { echo -e "${RED}❌${NC} $1"; }
log_skip()    { echo -e "${YELLOW}⏭ ${NC} $1 (skipped)"; }
log_header()  { echo -e "\n${BOLD}${BLUE}━━━ $1 ━━━${NC}\n"; }

# Check that the SSD is mounted
check_ssd() {
    /bin/bash "$COMMON_DIR/../tools/storage.sh" attach || exit 1
}

is_ssd_mounted() {
    /usr/bin/python3 - "$COMMON_DIR" <<'PYTHON'
import sys
sys.path.insert(0, sys.argv[1])
from storage_manager import Manager
sys.exit(0 if Manager().online() else 1)
PYTHON
}

move_and_link() {
    /bin/bash "$COMMON_DIR/../tools/storage.sh" move --source "$1" --destination "$2"
}

switch_migrated_links() {
    /bin/bash "$COMMON_DIR/../tools/storage.sh" switch --mode "${1:-auto}"
}

# Check if a command exists
has_cmd() {
    command -v "$1" &>/dev/null
}

# Confirm before proceeding
confirm() {
    local msg="${1:-Continue?}"
    echo -e "${YELLOW}${msg} [y/N]${NC} "
    read -r reply
    [[ "$reply" =~ ^[Yy]$ ]]
}

# Show disk space freed/used
show_disk_usage() {
    echo ""
    log_info "Internal SSD free space:"
    df -h / | awk 'NR==2 {print "  Available: " $4}'
    log_info "External SSD usage:"
    df -h "$SSD_VOLUME" | awk 'NR==2 {print "  Used: " $3 " / " $2 "  Available: " $4}'
}
