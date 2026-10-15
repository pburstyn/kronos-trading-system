#!/bin/bash

# Master pipeline script for Kronos Trading System
cd /home/pburstyn/kronos-trading-system
source /home/pburstyn/kronos-trading-system/venv/bin/activate

if ! python3 scripts/market_day_check.py >> /home/pburstyn/kronos-trading-system/logs/pipeline.log 2>&1; then
    echo "$(date) — Pipeline skipped (not a market day)" >> /home/pburstyn/kronos-trading-system/logs/pipeline.log
    exit 0
fi

echo "$(date) — Pipeline starting" >> /home/pburstyn/kronos-trading-system/logs/pipeline.log

python3 scripts/signal_logger.py >> /home/pburstyn/kronos-trading-system/logs/pipeline.log 2>&1

# QQQ is a second instrument for signal capture only -- data collection to build
# a QQQ history, mirroring the SPY signal (same MIN_VOTES/MIN_CONFIDENCE logic,
# separate log file). No downstream QQQ analyst reasoning, critic, trade_logic,
# or alpaca_execute exists yet -- QQQ signals are not acted on.
python3 scripts/signal_logger_qqq.py >> /home/pburstyn/kronos-trading-system/logs/pipeline.log 2>&1
python3 scripts/news_context.py >> /home/pburstyn/kronos-trading-system/logs/pipeline.log 2>&1
python3 scripts/andy_reasoning.py >> /home/pburstyn/kronos-trading-system/logs/pipeline.log 2>&1
python3 scripts/kimi_k3_reasoning.py >> /home/pburstyn/kronos-trading-system/logs/pipeline.log 2>&1
python3 scripts/critic.py >> /home/pburstyn/kronos-trading-system/logs/pipeline.log 2>&1
python3 scripts/decision_ledger.py >> /home/pburstyn/kronos-trading-system/logs/pipeline.log 2>&1
# Shadow bracket tracker: old 2%/3% vs current 2.5%/4% on every signal at or
# above the confidence floor, traded or not. Read-only, places no orders.
python3 scripts/shadow_brackets.py >> /home/pburstyn/kronos-trading-system/logs/pipeline.log 2>&1
python3 scripts/trade_logic.py >> /home/pburstyn/kronos-trading-system/logs/pipeline.log 2>&1
python3 scripts/alpaca_execute.py >> /home/pburstyn/kronos-trading-system/logs/pipeline.log 2>&1
python3 scripts/position_reconfirm.py >> /home/pburstyn/kronos-trading-system/logs/pipeline.log 2>&1
python3 scripts/telegram_notify.py >> /home/pburstyn/kronos-trading-system/logs/pipeline.log 2>&1
python3 scripts/dashboard.py >> /home/pburstyn/kronos-trading-system/logs/pipeline.log 2>&1
python3 scripts/auto_logger.py >> /home/pburstyn/kronos-trading-system/logs/pipeline.log 2>&1
python3 scripts/outcome_tracker.py >> /home/pburstyn/kronos-trading-system/logs/pipeline.log 2>&1
python3 scripts/trade_ledger.py >> /home/pburstyn/kronos-trading-system/logs/pipeline.log 2>&1

echo "$(date) — Pipeline complete" >> /home/pburstyn/kronos-trading-system/logs/pipeline.log
bash /home/pburstyn/kronos-trading-system/scripts/update_claude_md.sh >> /home/pburstyn/kronos-trading-system/logs/pipeline.log 2>&1
