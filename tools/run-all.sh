#!/bin/bash
# ============================================================
# SSD Migration — Run All
#
# Migrates developer caches, Docker, SDKs, VMs, databases,
# and project files to an external SSD.
#
# Usage:
#   ./tools/run-all.sh           Run all categories interactively
#   ./tools/run-all.sh 1 3       Run only categories 1 and 3
#   ./tools/run-all.sh --list    Show available categories
#   ./tools/run-all.sh --dry-run Preview what would be migrated
# ============================================================

set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
source "$SCRIPT_DIR/../core/00-common.sh"

SCRIPTS=(
    "01-dev-caches.sh:Developer Caches (npm, yarn, pip, Homebrew, Xcode, Gradle)"
    "02-docker.sh:Docker Desktop (VM disk image, volumes, build cache)"
    "03-sdks-runtimes.sh:SDKs & Runtimes (Android, nvm, pyenv, rustup, Simulators)"
    "04-virtual-machines.sh:Virtual Machines (UTM, Parallels, VMware)"
    "05-databases.sh:Local Databases (PostgreSQL, MySQL, MongoDB, Redis)"
    "06-project-files.sh:Project Files & Archives (node_modules cleanup, media, repos)"
)

show_list() {
    echo ""
    echo -e "${BOLD}Available migration categories:${NC}"
    echo ""
    for i in "${!SCRIPTS[@]}"; do
        IFS=':' read -r file desc <<< "${SCRIPTS[$i]}"
        echo -e "  ${BLUE}$((i+1))${NC}  $desc"
    done
    echo ""
}

# --- Handle arguments ---
if [ "$1" = "--list" ] || [ "$1" = "-l" ]; then
    show_list
    exit 0
fi

if [ "${1:-}" = "--dry-run" ]; then
    exec /bin/bash "$SCRIPT_DIR/storage.sh" status
fi

# --- Main execution ---
echo ""
echo -e "${BOLD}╔══════════════════════════════════════════╗${NC}"
echo -e "${BOLD}║     External SSD Migration Tool          ║${NC}"
echo -e "${BOLD}║     MacBook Pro M3 Pro                   ║${NC}"
echo -e "${BOLD}╚══════════════════════════════════════════╝${NC}"
echo ""

check_ssd
echo ""

# If specific category numbers were given, run only those
if [ $# -gt 0 ]; then
    for num in "$@"; do
        case "$num" in
            [1-6]) ;;
            *) log_error "Invalid category: $num"; exit 1 ;;
        esac
        idx=$((num - 1))
        if [ $idx -ge 0 ] && [ $idx -lt ${#SCRIPTS[@]} ]; then
            IFS=':' read -r file desc <<< "${SCRIPTS[$idx]}"
            echo ""
            echo -e "${BOLD}Running: $desc${NC}"
            bash "$SCRIPT_DIR/../migrations/$file"
        else
            log_error "Invalid category: $num (use --list to see options)"
        fi
    done
    exit 0
fi

# Run all interactively
show_list

if ! confirm "Run all categories?"; then
    log_info "You can run individual categories:"
    log_info "  ./tools/run-all.sh 1      (just Developer Caches)"
    log_info "  ./tools/run-all.sh 1 2 3  (Caches + Docker + SDKs)"
    exit 0
fi

TOTAL_START=$(date +%s)

for i in "${!SCRIPTS[@]}"; do
    IFS=':' read -r file desc <<< "${SCRIPTS[$i]}"
    bash "$SCRIPT_DIR/../migrations/$file"
done

TOTAL_END=$(date +%s)
ELAPSED=$(( TOTAL_END - TOTAL_START ))

echo ""
echo -e "${BOLD}${GREEN}════════════════════════════════════════${NC}"
echo -e "${BOLD}${GREEN}  All migrations complete! (${ELAPSED}s)${NC}"
echo -e "${BOLD}${GREEN}════════════════════════════════════════${NC}"
echo ""

show_disk_usage

echo ""
log_info "Next steps:"
log_info "  1. Run: source ~/.zshrc"
log_info "  2. Start Docker: open -a Docker"
log_info "  3. Verify your tools work as expected"
echo ""
log_info "Disconnect safely with: ~/scripts/ssd-disconnect.sh"
