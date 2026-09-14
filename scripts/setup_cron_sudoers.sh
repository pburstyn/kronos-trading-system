#!/bin/bash
# One-time setup: lets startup_check.py restart cron via `sudo -n systemctl restart cron`
# without a password prompt. Scope is exactly that one command — nothing broader.
set -euo pipefail

RULE='pburstyn ALL=(root) NOPASSWD: /usr/bin/systemctl restart cron'
TARGET=/etc/sudoers.d/pburstyn-cron-restart
TMP=$(mktemp)
trap 'rm -f "$TMP"' EXIT

echo "$RULE" > "$TMP"
visudo -cf "$TMP"
sudo install -o root -g root -m 0440 "$TMP" "$TARGET"
sudo visudo -c

echo "Installed $TARGET:"
cat "$TARGET"
