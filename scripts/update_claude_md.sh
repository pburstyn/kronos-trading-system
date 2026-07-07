#!/bin/bash
cd /home/pburstyn/trading-system
LAST_SIGNAL=$(tail -1 logs/signal_log.csv)
sed -i '/^## Last Updated/,$d' CLAUDE.md
echo "## Last Updated" >> CLAUDE.md
echo "$(date '+%Y-%m-%d %H:%M:%S')" >> CLAUDE.md
echo "**Last Signal:** $LAST_SIGNAL" >> CLAUDE.md
git add CLAUDE.md && git commit -m "auto-update CLAUDE.md $(date '+%Y-%m-%d')" && git push
