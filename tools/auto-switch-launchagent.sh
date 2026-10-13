#!/bin/bash
# ============================================================
# Install/manage a LaunchAgent that auto-switches SSD links and Docker mode.
#
# Usage:
#   ./tools/auto-switch-launchagent.sh install
#   ./tools/auto-switch-launchagent.sh uninstall
#   ./tools/auto-switch-launchagent.sh status
# ============================================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
source "$SCRIPT_DIR/../core/00-common.sh"

LABEL="com.ssd-migration.switch-links"
PLIST_PATH="$HOME/Library/LaunchAgents/$LABEL.plist"
LOG_DIR="$HOME/Library/Logs"
STDOUT_LOG="$LOG_DIR/$LABEL.log"
STDERR_LOG="$LOG_DIR/$LABEL.error.log"

ACTION="${1:-install}"

write_plist() {
    mkdir -p "$HOME/Library/LaunchAgents"
    mkdir -p "$LOG_DIR"

    cat > "$PLIST_PATH" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>$LABEL</string>

    <key>ProgramArguments</key>
    <array>
        <string>/bin/bash</string>
        <string>$SCRIPT_DIR/auto-switch.sh</string>
        <string>auto</string>
    </array>

    <key>RunAtLoad</key>
    <true/>

    <key>StartInterval</key>
    <integer>60</integer>

    <key>EnvironmentVariables</key>
    <dict>
        <key>PATH</key>
        <string>/usr/bin:/bin:/usr/sbin:/sbin</string>
        <key>SSD_MIGRATION_PYTHON</key>
        <string>/usr/bin/python3</string>
    </dict>

    <key>StandardOutPath</key>
    <string>$STDOUT_LOG</string>
    <key>StandardErrorPath</key>
    <string>$STDERR_LOG</string>
</dict>
</plist>
EOF
}

load_agent() {
    launchctl bootout "gui/$(id -u)" "$PLIST_PATH" >/dev/null 2>&1 || true
    launchctl bootstrap "gui/$(id -u)" "$PLIST_PATH"
    launchctl kickstart -k "gui/$(id -u)/$LABEL" >/dev/null 2>&1 || true
}

unload_agent() {
    launchctl bootout "gui/$(id -u)" "$PLIST_PATH" >/dev/null 2>&1 || true
}

case "$ACTION" in
    install)
        write_plist
        load_agent
        log_success "Installed LaunchAgent: $LABEL"
        log_info "Managed storage runs every 60s and at login; cleanup sweeps every 15 minutes."
        log_info "It now auto-skips while migration scripts are running."
        ;;
    uninstall)
        unload_agent
        rm -f "$PLIST_PATH"
        log_success "Uninstalled LaunchAgent: $LABEL"
        ;;
    status)
        if launchctl print "gui/$(id -u)/$LABEL" >/dev/null 2>&1; then
            log_success "LaunchAgent is loaded: $LABEL"
        else
            log_warn "LaunchAgent is not loaded: $LABEL"
        fi

        if [ -f "$PLIST_PATH" ]; then
            log_info "Plist: $PLIST_PATH"
        else
            log_warn "Plist not found at $PLIST_PATH"
        fi
        ;;
    *)
        log_error "Invalid action: $ACTION"
        log_info "Usage: ./tools/auto-switch-launchagent.sh [install|uninstall|status]"
        exit 1
        ;;
esac
