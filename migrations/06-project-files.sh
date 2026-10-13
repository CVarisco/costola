#!/bin/bash
# ============================================================
# 6. Project Files & Archives → External SSD
# Cleans up node_modules and moves inactive projects/media.
# ============================================================

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
source "$SCRIPT_DIR/../core/00-common.sh"

log_header "Project Files & Archives Migration"
check_ssd

ARCHIVE_DIR="$SSD_VOLUME/Volumes/Archive"
mkdir -p "$ARCHIVE_DIR/Projects"
mkdir -p "$ARCHIVE_DIR/Design"
mkdir -p "$ARCHIVE_DIR/Recordings"

# -------------------------------------------------------
# Part A: Clean up node_modules in inactive projects
# -------------------------------------------------------
log_info "${BOLD}Scanning for node_modules...${NC}"

PROJECTS_DIR="$HOME/Dev"
if [ ! -d "$PROJECTS_DIR" ]; then
    PROJECTS_DIR="$HOME/Developer"
    if [ ! -d "$PROJECTS_DIR" ]; then
        PROJECTS_DIR="$HOME/Code"
        if [ ! -d "$PROJECTS_DIR" ]; then
            PROJECTS_DIR="$HOME"
            log_warn "Could not find Projects/Developer/Code dir, scanning home directory"
        fi
    fi
fi

# Find node_modules not modified in the last 30 days
STALE_NM=$(find "$PROJECTS_DIR" -name "node_modules" -type d -maxdepth 4 -not -newermt "30 days ago" 2>/dev/null)

if [ -n "$STALE_NM" ]; then
    STALE_COUNT=$(echo "$STALE_NM" | wc -l | tr -d ' ')
    STALE_SIZE=$(echo "$STALE_NM" | xargs du -sh 2>/dev/null | awk '{total += $1} END {print total "G (approx)"}')

    log_info "Found $STALE_COUNT stale node_modules directories (>30 days old):"
    echo "$STALE_NM" | while read -r dir; do
        size=$(du -sh "$dir" 2>/dev/null | awk '{print $1}')
        echo "  $size  $(dirname "$dir" | sed "s|$HOME|~|")"
    done

    echo ""
    if confirm "Delete these stale node_modules? (They will reinstall with npm/yarn install)"; then
        echo "$STALE_NM" | while read -r dir; do
            rm -rf "$dir"
        done
        log_success "Cleaned stale node_modules"
    else
        log_skip "node_modules cleanup (user declined)"
    fi
else
    log_info "No stale node_modules found (all modified within 30 days)"
fi

# -------------------------------------------------------
# Part B: Find large inactive Git repos
# -------------------------------------------------------
log_info ""
log_info "${BOLD}Scanning for large inactive Git repos...${NC}"

echo ""
log_info "Git repos not modified in 90+ days:"
echo ""

find "$PROJECTS_DIR" -name ".git" -type d -maxdepth 4 2>/dev/null | while read -r gitdir; do
    REPO_DIR="$(dirname "$gitdir")"

    # Check last modification time of tracked files
    LAST_MOD=$(find "$REPO_DIR" -maxdepth 2 -not -path '*/node_modules/*' -not -path '*/.git/*' -not -path '*/vendor/*' -newer "$REPO_DIR/.git/index" -type f 2>/dev/null | head -1)

    # Use .git/index modification time as proxy
    GIT_INDEX="$REPO_DIR/.git/index"
    if [ -f "$GIT_INDEX" ]; then
        INDEX_AGE=$(( ($(date +%s) - $(stat -f %m "$GIT_INDEX" 2>/dev/null || stat -c %Y "$GIT_INDEX" 2>/dev/null || echo 0)) / 86400 ))

        if [ "$INDEX_AGE" -gt 90 ]; then
            REPO_SIZE=$(du -sh "$REPO_DIR" 2>/dev/null | awk '{print $1}')
            REPO_NAME=$(basename "$REPO_DIR")
            echo "  $REPO_SIZE  $REPO_NAME  (${INDEX_AGE} days inactive)"
        fi
    fi
done

echo ""
log_info "To move an inactive project to SSD:"
log_info "  mv ~/Projects/<name> $ARCHIVE_DIR/Projects/"
log_info ""
log_info "Projects are not moved automatically to avoid"
log_info "breaking active work. Move them manually as needed."

# -------------------------------------------------------
# Part C: Offer to move large media files
# -------------------------------------------------------
log_info ""
log_info "${BOLD}Scanning for large media files...${NC}"

MEDIA_DIRS=(
    "$HOME/Movies"
    "$HOME/Downloads"
    "$HOME/Desktop"
)

MEDIA_EXTENSIONS=( "*.mp4" "*.mov" "*.avi" "*.mkv" "*.psd" "*.sketch" "*.fig" "*.ai" "*.zip" "*.tar.gz" "*.dmg" )

for dir in "${MEDIA_DIRS[@]}"; do
    if [ -d "$dir" ]; then
        FIND_ARGS=()
        for ext in "${MEDIA_EXTENSIONS[@]}"; do
            if [ ${#FIND_ARGS[@]} -gt 0 ]; then
                FIND_ARGS+=("-o")
            fi
            FIND_ARGS+=("-name" "$ext")
        done

        LARGE_FILES=$(find "$dir" -maxdepth 2 -type f -size +100M \( "${FIND_ARGS[@]}" \) 2>/dev/null)

        if [ -n "$LARGE_FILES" ]; then
            log_info "Large media files in $(basename "$dir"):"
            echo "$LARGE_FILES" | while read -r file; do
                size=$(du -sh "$file" 2>/dev/null | awk '{print $1}')
                echo "  $size  $(basename "$file")"
            done
            echo ""
        fi
    fi
done

log_info "To move media files to SSD:"
log_info "  mv ~/Downloads/*.mp4 $ARCHIVE_DIR/Recordings/"
log_info "  mv ~/Desktop/*.psd $ARCHIVE_DIR/Design/"

# -------------------------------------------------------
# Part D: Thin Time Machine local snapshots
# -------------------------------------------------------
log_info ""
log_info "${BOLD}Time Machine local snapshots${NC}"

TM_SIZE=$(tmutil listlocalsnapshots / 2>/dev/null | wc -l | tr -d ' ')
if [ "$TM_SIZE" -gt 0 ]; then
    log_info "Found $TM_SIZE local Time Machine snapshots."
    log_info "To thin: sudo tmutil thinlocalsnapshots / 10000000000 1"
    log_info "(This removes snapshots to free ~10GB)"
else
    log_info "No Time Machine snapshots found."
fi

show_disk_usage
log_header "Project Files Scan Complete"
