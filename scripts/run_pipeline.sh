#!/bin/bash

# Master pipeline script for Kronos Trading System
cd /home/pburstyn/trading-system
source /home/pburstyn/trading-system/venv/bin/activate

echo "$(date) — Pipeline starting" >> /home/pburstyn/trading-system/logs/pipeline.log

python3 scripts/signal_logger.py >> /home/pburstyn/trading-system/logs/pipeline.log 2>&1
python3 scripts/andy_reasoning.py >> /home/pburstyn/trading-system/logs/pipeline.log 2>&1
python3 scripts/critic.py >> /home/pburstyn/trading-system/logs/pipeline.log 2>&1
python3 scripts/dashboard.py >> /home/pburstyn/trading-system/logs/pipeline.log 2>&1
python3 scripts/auto_logger.py >> /home/pburstyn/trading-system/logs/pipeline.log 2>&1

echo "$(date) — Pipeline complete" >> /home/pburstyn/trading-system/logs/pipeline.log
