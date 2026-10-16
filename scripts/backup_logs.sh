#!/bin/bash
# Nightly backup of logs/ to Google Drive via rclone. Standalone, run by cron;
# touches nothing in the trading pipeline.
#
#   <remote>/latest/            mirror of logs/ (rclone sync)
#   <remote>/snapshots/DATE/    full dated copy, pruned after KEEP_DAYS
#
# logs/ only: .env never leaves this machine. Setup steps are in docs/backup_setup.md.
# Usage: bash scripts/backup_logs.sh [--dry-run]

set -uo pipefail

REPO="$HOME/kronos-trading-system"
LOGS="$REPO/logs"
REMOTE="${KRONOS_BACKUP_REMOTE:-gdrive:kronos-backup}"
KEEP_DAYS=30
TODAY=$(date +%F)
DRY=()
[ "${1:-}" = "--dry-run" ] && DRY=(--dry-run)

log() { echo "$(date '+%F %T') $*"; }

# Telegram alert on failure, since cron failures are otherwise silent.
# Reads .env with grep rather than sourcing it.
alert() {
    local token chat
    token=$(grep -E '^TELEGRAM_BOT_TOKEN=' "$REPO/.env" 2>/dev/null | tail -n1 | cut -d= -f2- | tr -d '"'"'"'\r')
    chat=$(grep -E '^TELEGRAM_CHAT_ID=' "$REPO/.env" 2>/dev/null | tail -n1 | cut -d= -f2- | tr -d '"'"'"'\r')
    [ -n "$token" ] && [ -n "$chat" ] || return 0
    curl -s -m 20 -o /dev/null "https://api.telegram.org/bot$token/sendMessage" \
        --data-urlencode "chat_id=$chat" \
        --data-urlencode "text=Kronos log backup FAILED on $(hostname) at $(date '+%F %T'): $1. See logs/backup.log." || true
}

die() { log "ERROR: $1"; [ ${#DRY[@]} -eq 0 ] && alert "$1"; exit 1; }

# One run at a time.
exec 9>"$LOGS/.backup.lock"
flock -n 9 || { log "Another backup is running; exiting"; exit 0; }

command -v rclone >/dev/null || die "rclone not installed"
rclone listremotes | grep -qxF "${REMOTE%%:*}:" || die "rclone remote '${REMOTE%%:*}:' not configured"

log "Backup starting: $LOGS -> $REMOTE ${DRY[*]}"

# Mirror. --exclude keeps the lock file out of the backup.
rclone sync "${DRY[@]}" "$LOGS" "$REMOTE/latest" --exclude ".backup.lock" \
    || die "rclone sync to $REMOTE/latest failed"

# Dated snapshot. Server-side copy on Drive, so nothing is uploaded twice.
# A dry run hasn't really synced latest/ (it may not exist yet), so preview from logs/.
snap_src="$REMOTE/latest"
[ ${#DRY[@]} -gt 0 ] && snap_src="$LOGS"
rclone copy "${DRY[@]}" "$snap_src" "$REMOTE/snapshots/$TODAY" --exclude ".backup.lock" \
    || die "snapshot copy to $REMOTE/snapshots/$TODAY failed"

# Prune snapshots older than KEEP_DAYS. Folder names are YYYY-MM-DD, so string
# comparison is date order; anything not shaped like a date is left alone.
cutoff=$(date -d "$KEEP_DAYS days ago" +%F)
pruned=0
while IFS= read -r dir; do
    dir=${dir%/}
    [[ "$dir" =~ ^[0-9]{4}-[0-9]{2}-[0-9]{2}$ ]] || continue
    if [[ "$dir" < "$cutoff" ]]; then
        rclone purge "${DRY[@]}" "$REMOTE/snapshots/$dir" && pruned=$((pruned + 1)) \
            || log "WARNING: could not prune $REMOTE/snapshots/$dir"
    fi
done < <(rclone lsf --dirs-only "$REMOTE/snapshots" 2>/dev/null)

log "Backup complete: latest synced, snapshot $TODAY, pruned $pruned older than $cutoff"
