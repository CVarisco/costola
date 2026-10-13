#!/bin/bash
# ============================================================
# 5. Local Databases → External SSD
# Medium risk: services must be stopped before moving.
# Databases running inside Docker are handled by script 02.
# ============================================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
source "$SCRIPT_DIR/../core/00-common.sh"

log_header "Local Databases Migration"
check_ssd

DB_DIR="$SSD_VOLUME/Volumes/Databases"
mkdir -p "$DB_DIR"

# System-wide data directories are not part of this user's cache migration.
migration_source_supported() {
    case "$1" in
        "$HOME"/*) return 0 ;;
        *) log_warn "System database path requires a separate backup/restore: $1"; return 1 ;;
    esac
}

# --- PostgreSQL (Homebrew) ---
if has_cmd pg_config; then
    PG_DATA_DIR=""

    # Try to find data directory from Homebrew
    if has_cmd brew; then
        PG_PREFIX="$(brew --prefix postgresql@16 2>/dev/null || brew --prefix postgresql@15 2>/dev/null || brew --prefix postgresql 2>/dev/null)"
        if [ -n "$PG_PREFIX" ]; then
            # Common Homebrew Postgres data locations
            for candidate in \
                "/opt/homebrew/var/postgresql@16" \
                "/opt/homebrew/var/postgresql@15" \
                "/opt/homebrew/var/postgres" \
                "/usr/local/var/postgresql@16" \
                "/usr/local/var/postgresql@15" \
                "/usr/local/var/postgres"; do
                if [ -d "$candidate" ]; then
                    PG_DATA_DIR="$candidate"
                    break
                fi
            done
        fi
    fi

    if [ -n "$PG_DATA_DIR" ] && [ ! -L "$PG_DATA_DIR" ] && migration_source_supported "$PG_DATA_DIR"; then
        PG_SIZE=$(du -sh "$PG_DATA_DIR" 2>/dev/null | awk '{print $1}')
        log_info "Found PostgreSQL data at $PG_DATA_DIR ($PG_SIZE)"

        if ! confirm "Stop PostgreSQL and move data to SSD?"; then
            log_skip "PostgreSQL (user declined)"
        else
            # Stop PostgreSQL
            log_info "Stopping PostgreSQL..."
            brew services stop postgresql@16 2>/dev/null || \
            brew services stop postgresql@15 2>/dev/null || \
            brew services stop postgresql 2>/dev/null || \
            pg_ctl -D "$PG_DATA_DIR" stop 2>/dev/null
            sleep 2

            move_and_link "$PG_DATA_DIR" "$DB_DIR/postgresql"
            log_success "PostgreSQL data moved"

            log_info "Restarting PostgreSQL..."
            brew services start postgresql@16 2>/dev/null || \
            brew services start postgresql@15 2>/dev/null || \
            brew services start postgresql 2>/dev/null
            log_success "PostgreSQL restarted from SSD"
        fi
    else
        log_skip "PostgreSQL data not found or already migrated"
    fi
else
    log_skip "PostgreSQL not installed (natively)"
fi

# --- MySQL / MariaDB (Homebrew) ---
MYSQL_DATA=""
for candidate in \
    "/opt/homebrew/var/mysql" \
    "/usr/local/var/mysql" \
    "/opt/homebrew/var/mariadb" \
    "/usr/local/var/mariadb"; do
    if [ -d "$candidate" ] && [ ! -L "$candidate" ]; then
        MYSQL_DATA="$candidate"
        break
    fi
done

if [ -n "$MYSQL_DATA" ] && migration_source_supported "$MYSQL_DATA"; then
    MYSQL_SIZE=$(du -sh "$MYSQL_DATA" 2>/dev/null | awk '{print $1}')
    log_info "Found MySQL/MariaDB data at $MYSQL_DATA ($MYSQL_SIZE)"

    if ! confirm "Stop MySQL/MariaDB and move data to SSD?"; then
        log_skip "MySQL/MariaDB (user declined)"
    else
        log_info "Stopping MySQL/MariaDB..."
        brew services stop mysql 2>/dev/null || \
        brew services stop mariadb 2>/dev/null
        sleep 2

        move_and_link "$MYSQL_DATA" "$DB_DIR/mysql"
        log_success "MySQL/MariaDB data moved"

        log_info "Restarting MySQL/MariaDB..."
        brew services start mysql 2>/dev/null || \
        brew services start mariadb 2>/dev/null
        log_success "MySQL/MariaDB restarted from SSD"
    fi
else
    log_skip "MySQL/MariaDB not found (natively)"
fi

# --- MongoDB ---
MONGO_DATA=""
for candidate in \
    "/opt/homebrew/var/mongodb" \
    "/usr/local/var/mongodb" \
    "$HOME/data/db"; do
    if [ -d "$candidate" ] && [ ! -L "$candidate" ]; then
        MONGO_DATA="$candidate"
        break
    fi
done

if [ -n "$MONGO_DATA" ] && migration_source_supported "$MONGO_DATA"; then
    MONGO_SIZE=$(du -sh "$MONGO_DATA" 2>/dev/null | awk '{print $1}')
    log_info "Found MongoDB data at $MONGO_DATA ($MONGO_SIZE)"

    if ! confirm "Stop MongoDB and move data to SSD?"; then
        log_skip "MongoDB (user declined)"
    else
        log_info "Stopping MongoDB..."
        brew services stop mongodb-community 2>/dev/null || \
        mongosh --eval "db.adminCommand({shutdown: 1})" 2>/dev/null
        sleep 2

        move_and_link "$MONGO_DATA" "$DB_DIR/mongodb"
        log_success "MongoDB data moved"

        brew services start mongodb-community 2>/dev/null
        log_success "MongoDB restarted from SSD"
    fi
else
    log_skip "MongoDB not found (natively)"
fi

# --- Redis ---
REDIS_DATA=""
for candidate in \
    "/opt/homebrew/var/db/redis" \
    "/usr/local/var/db/redis"; do
    if [ -d "$candidate" ] && [ ! -L "$candidate" ]; then
        REDIS_DATA="$candidate"
        break
    fi
done

if [ -n "$REDIS_DATA" ] && migration_source_supported "$REDIS_DATA"; then
    REDIS_SIZE=$(du -sh "$REDIS_DATA" 2>/dev/null | awk '{print $1}')
    log_info "Found Redis data at $REDIS_DATA ($REDIS_SIZE)"

    if ! confirm "Move Redis data to SSD?"; then
        log_skip "Redis (user declined)"
    else
        brew services stop redis 2>/dev/null
        sleep 1
        move_and_link "$REDIS_DATA" "$DB_DIR/redis"
        brew services start redis 2>/dev/null
        log_success "Redis data moved and restarted"
    fi
else
    log_skip "Redis not found (natively)"
fi

log_info ""
log_info "Note: Databases running inside Docker are handled"
log_info "by the Docker migration (script 02-docker.sh)."

show_disk_usage
log_header "Local Databases Migration Complete"
