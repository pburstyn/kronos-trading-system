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

# QQQ signal, mirroring the SPY signal (same MIN_VOTES/MIN_CONFIDENCE logic,
# separate log file). The rest of the QQQ flow runs after the SPY flow below.
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

# QQQ flow (October 18): analysts, Critic, trade logic and Alpaca execution,
# mirroring SPY with separate _qqq logs. Runs only after the full SPY flow
# above, so it cannot block or delay SPY. Each step is its own process, and
# this script has no `set -e`, so a QQQ failure never stops the pipeline.
echo "$(date) — QQQ flow starting" >> /home/pburstyn/kronos-trading-system/logs/pipeline.log
python3 scripts/andy_reasoning_qqq.py >> /home/pburstyn/kronos-trading-system/logs/pipeline.log 2>&1
python3 scripts/kimi_k3_reasoning_qqq.py >> /home/pburstyn/kronos-trading-system/logs/pipeline.log 2>&1
python3 scripts/critic_qqq.py >> /home/pburstyn/kronos-trading-system/logs/pipeline.log 2>&1
python3 scripts/decision_ledger_qqq.py >> /home/pburstyn/kronos-trading-system/logs/pipeline.log 2>&1
python3 scripts/trade_logic_qqq.py >> /home/pburstyn/kronos-trading-system/logs/pipeline.log 2>&1
python3 scripts/alpaca_execute_qqq.py >> /home/pburstyn/kronos-trading-system/logs/pipeline.log 2>&1
python3 scripts/position_reconfirm_qqq.py >> /home/pburstyn/kronos-trading-system/logs/pipeline.log 2>&1
python3 scripts/telegram_notify_qqq.py >> /home/pburstyn/kronos-trading-system/logs/pipeline.log 2>&1
python3 scripts/trade_ledger_qqq.py >> /home/pburstyn/kronos-trading-system/logs/pipeline.log 2>&1

echo "$(date) — Pipeline complete" >> /home/pburstyn/kronos-trading-system/logs/pipeline.log
bash /home/pburstyn/kronos-trading-system/scripts/update_claude_md.sh >> /home/pburstyn/kronos-trading-system/logs/pipeline.log 2>&1
