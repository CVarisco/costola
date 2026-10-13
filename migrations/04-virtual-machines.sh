#!/bin/bash
# ============================================================
# 4. Virtual Machines → External SSD
# Moves UTM and Parallels VM files.
# ============================================================

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
source "$SCRIPT_DIR/../core/00-common.sh"

log_header "Virtual Machines Migration"
check_ssd

VM_DIR="$SSD_VOLUME/Volumes/VMs"
mkdir -p "$VM_DIR"

MOVED_COUNT=0

# --- UTM ---
UTM_DIR="$HOME/Library/Containers/com.utmapp.UTM/Data/Documents"
UTM_ALT="$HOME/Documents/UTM"

UTM_SOURCE=""
if [ -d "$UTM_DIR" ] && [ ! -L "$UTM_DIR" ]; then
    UTM_SOURCE="$UTM_DIR"
elif [ -d "$UTM_ALT" ] && [ ! -L "$UTM_ALT" ]; then
    UTM_SOURCE="$UTM_ALT"
fi

if [ -n "$UTM_SOURCE" ]; then
    UTM_COUNT=$(find "$UTM_SOURCE" -name "*.utm" -maxdepth 1 2>/dev/null | wc -l | tr -d ' ')
    if [ "$UTM_COUNT" -gt 0 ]; then
        UTM_SIZE=$(du -sh "$UTM_SOURCE" 2>/dev/null | awk '{print $1}')
        log_info "Found $UTM_COUNT UTM VM(s) at $UTM_SOURCE ($UTM_SIZE)"

        mkdir -p "$VM_DIR/UTM"
        for vm in "$UTM_SOURCE"/*.utm; do
            [ -e "$vm" ] || continue
            VM_NAME=$(basename "$vm")
            if [ -e "$VM_DIR/UTM/$VM_NAME" ]; then
                log_skip "$VM_NAME already on SSD"
            else
                VM_SIZE=$(du -sh "$vm" 2>/dev/null | awk '{print $1}')
                log_info "Moving $VM_NAME ($VM_SIZE)..."
                move_and_link "$vm" "$VM_DIR/UTM/$VM_NAME" || {
                    log_error "Failed to move $VM_NAME"
                    continue
                }
                ((MOVED_COUNT++))
                log_success "Moved $VM_NAME"
            fi
        done

        log_info ""
        log_info "To use VMs from SSD in UTM:"
        log_info "  1. Open UTM"
        log_info "  2. File → Open → navigate to $VM_DIR/UTM/"
        log_info "  3. Select the .utm file(s)"
    else
        log_skip "No .utm files found in $UTM_SOURCE"
    fi
else
    log_skip "UTM not found or already migrated"
fi

# --- Parallels ---
PARALLELS_DIR="$HOME/Parallels"
if [ -d "$PARALLELS_DIR" ] && [ ! -L "$PARALLELS_DIR" ]; then
    PVM_COUNT=$(find "$PARALLELS_DIR" -name "*.pvm" -maxdepth 1 2>/dev/null | wc -l | tr -d ' ')
    if [ "$PVM_COUNT" -gt 0 ]; then
        PVM_SIZE=$(du -sh "$PARALLELS_DIR" 2>/dev/null | awk '{print $1}')
        log_info "Found $PVM_COUNT Parallels VM(s) ($PVM_SIZE)"

        mkdir -p "$VM_DIR/Parallels"
        for vm in "$PARALLELS_DIR"/*.pvm; do
            [ -e "$vm" ] || continue
            VM_NAME=$(basename "$vm")
            if [ -e "$VM_DIR/Parallels/$VM_NAME" ]; then
                log_skip "$VM_NAME already on SSD"
            else
                VM_SIZE=$(du -sh "$vm" 2>/dev/null | awk '{print $1}')
                log_info "Moving $VM_NAME ($VM_SIZE)..."
                move_and_link "$vm" "$VM_DIR/Parallels/$VM_NAME" || {
                    log_error "Failed to move $VM_NAME"
                    continue
                }
                ((MOVED_COUNT++))
                log_success "Moved $VM_NAME"
            fi
        done

        log_info ""
        log_info "To re-register in Parallels:"
        log_info "  prlctl register '$VM_DIR/Parallels/<name>.pvm'"
    else
        log_skip "No .pvm files found"
    fi
else
    log_skip "Parallels VMs not found or already migrated"
fi

# --- VMware Fusion ---
VMWARE_DIR="$HOME/Virtual Machines.localized"
if [ -d "$VMWARE_DIR" ] && [ ! -L "$VMWARE_DIR" ]; then
    VMX_COUNT=$(find "$VMWARE_DIR" -name "*.vmwarevm" -maxdepth 1 2>/dev/null | wc -l | tr -d ' ')
    if [ "$VMX_COUNT" -gt 0 ]; then
        VMX_SIZE=$(du -sh "$VMWARE_DIR" 2>/dev/null | awk '{print $1}')
        log_info "Found $VMX_COUNT VMware VM(s) ($VMX_SIZE)"

        mkdir -p "$VM_DIR/VMware"
        for vm in "$VMWARE_DIR"/*.vmwarevm; do
            [ -e "$vm" ] || continue
            VM_NAME=$(basename "$vm")
            if [ -e "$VM_DIR/VMware/$VM_NAME" ]; then
                log_skip "$VM_NAME already on SSD"
            else
                VM_SIZE=$(du -sh "$vm" 2>/dev/null | awk '{print $1}')
                log_info "Moving $VM_NAME ($VM_SIZE)..."
                move_and_link "$vm" "$VM_DIR/VMware/$VM_NAME" || {
                    log_error "Failed to move $VM_NAME"
                    continue
                }
                ((MOVED_COUNT++))
                log_success "Moved $VM_NAME"
            fi
        done

        log_info "Reopen VMs from $VM_DIR/VMware/ in VMware Fusion"
    else
        log_skip "No VMware VMs found"
    fi
else
    log_skip "VMware Fusion VMs not found or already migrated"
fi

if [ "$MOVED_COUNT" -eq 0 ]; then
    log_info "No VMs were moved. Nothing to do."
fi

show_disk_usage
log_header "Virtual Machines Migration Complete"
