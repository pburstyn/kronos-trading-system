# Kronos Trading System — Claude Memory File
*Auto-updated after every pipeline run. Fetch this file at the start of any session to restore full context.*

## System Overview
- **Goal:** Automated trading signal engine targeting $200-$300/day, scaling to $10,000-$20,000/month
- **Instrument:** SPY (validation), MES futures (live trading target)
- **Machine:** OpenClaw (WSL2/Ubuntu, username: pburstyn, Windows 11, Burbank CA)
- **GitHub:** https://github.com/pburstyn/kronos-trading-system
- **Pipeline runs:** 6pm weekdays via cron

## File Structure
## File Structure
- `scripts/signal_logger.py` — Fetches SPY data, computes indicators, logs signal
- `scripts/andy_reasoning.py` — Claude Haiku reasons about the signal
- `scripts/critic.py` — Issues PASS/FLAG/VETO verdict
- `scripts/dashboard.py` — Generates dashboard.html
- `scripts/auto_logger.py` — Logs paper trades
- `scripts/run_pipeline.sh` — Master pipeline script
- `scripts/backtest.py` — Historical backtest script
- `logs/signal_log.csv` — Live signal log
- `logs/decisions_log.csv` — Andy + Critic decisions
- `logs/pipeline.log` — Pipeline run log
- `logs/dashboard.html` — Visual dashboard
- `logs/backtest_results.csv` — SPY backtest results
- `logs/backtest_qqq.csv` — QQQ backtest results

## Signal Engine Settings
- **Ticker:** SPY
- **Lookback:** 250 days
- **MIN_VOTES:** 3
- **MIN_CONFIDENCE:** 70.0
- **Indicators:** RSI(14), MACD(12,26,9), MA50, MA200, Volume MA20
- **MA structure:** Casts bull/bear vote (fixed May 16 2026)
## Backtest Results (run May 2026)
- **SPY:** 57.8% accuracy, 282 signals fired, 646 days analyzed (2023-01-01 to present)
- **QQQ:** 57.2% accuracy, 290 signals fired, 646 days analyzed
- **Threshold to beat:** 55% accuracy, under 300 signals
- **Status:** EDGE DETECTED on both instruments

## Validation Timeline
- **May 16 2026:** 30-day live observation period started
- **June 5 2026:** Return to build entry/exit/take-profit/stop-loss logic
- **June 16 2026:** Review 30-day signal log, connect new APIs, move to paper trading

## Paper Trading Setup
- **Platform:** Tradovate (sim account, $50,000 simulated equity)
- **Instrument:** MESM6 (expires 06/18/2026), roll to MESU6 after expiry
- **Value per point:** $5.00 USD
- **Margin per contract:** $1,328.50
- **Position sizing:** 1-2 contracts per signal to start

## APIs to Connect on June 16
- **Alpaca Markets:** Free paper trading + real-time data API. Account created, keys saved.
- **FRED API:** Free macro data (rates, inflation, GDP). Account needed at fred.stlouisfed.org
- **CNN Fear and Greed Index:** Free, no key needed. Endpoint: https://production.dataviz.cnn.io/index/fearandgreed/graphdata (verify still live before integrating)
## Architecture Roadmap
1. ✅ Phase 0-3: Signal engine, Andy, Critic, dashboard running
2. ✅ Backtest validated (57.8% SPY, 57.2% QQQ)
3. 🔄 30-day live signal observation (May 16 - June 16)
4. ⬜ Entry/exit/take-profit/stop-loss logic
5. ⬜ Connect CNN Fear & Greed, FRED, Alpaca APIs
6. ⬜ 30-day paper trading on Tradovate sim account
7. ⬜ Live trading with $5,000-$10,000 capital on MES
8. ⬜ Scale up, add QQQ, crypto, FOREX instruments
9. ⬜ Semi-autopilot with Claude Code + Tradovate API executor
10. ⬜ Council as watchdog on high confidence signals only

## Key Commands
```bash
# Run pipeline manually
cd ~/trading-system && bash scripts/run_pipeline.sh

# Check last signal
tail -3 ~/trading-system/logs/signal_log.csv

# Check pipeline log
tail -10 ~/trading-system/logs/pipeline.log

# Open dashboard
explorer.exe $(wslpath -w ~/trading-system/logs/dashboard.html)

# Run SPY backtest
cd ~/trading-system && python3 scripts/backtest.py

# If Ubuntu restarted
cd ~/trading-system && source venv/bin/activate && bash scripts/run_pipeline.sh
\`\`\`
## Architecture Roadmap
1. ✅ Phase 0-3: Signal engine, Andy, Critic, dashboard running
2. ✅ Backtest validated (57.8% SPY, 57.2% QQQ)
3. 🔄 30-day live signal observation (May 16 - June 16)
4. ⬜ Entry/exit/take-profit/stop-loss logic
5. ⬜ Connect CNN Fear & Greed, FRED, Alpaca APIs
6. ⬜ 30-day paper trading on Tradovate sim account
7. ⬜ Live trading with $5,000-$10,000 capital on MES
8. ⬜ Scale up, add QQQ, crypto, FOREX instruments
9. ⬜ Semi-autopilot with Claude Code + Tradovate API executor
10. ⬜ Council as watchdog on high confidence signals only

## Key Commands
```bash
# Run pipeline manually
cd ~/trading-system && bash scripts/run_pipeline.sh

# Check last signal
tail -3 ~/trading-system/logs/signal_log.csv

# Check pipeline log
tail -10 ~/trading-system/logs/pipeline.log

# Open dashboard
explorer.exe $(wslpath -w ~/trading-system/logs/dashboard.html)

# Run SPY backtest
cd ~/trading-system && python3 scripts/backtest.py

# If Ubuntu restarted
cd ~/trading-system && source venv/bin/activate && bash scripts/run_pipeline.sh
\`\`\`

## Deferred Tasks
- Test Opus 4.8 as Critic on batch of logged signals
- Verify Claude dynamic workflow routing at API level
- Evaluate Kimi K2 via OpenRouter as cost-saving swap for Andy and Critic
- Build news sentiment agent, political/macro agent, psychology agent (in that order)
- Scope Kronos done-for-you guide on Gumroad ($37-$67) once system generates income

## Last Updated
2026-06-02 18:00:09
**Last Signal:** 2026-06-02 18:00:05,SPY,NEUTRAL,0.0,759.57,"Price $759.57 above MA50 $707.84 and MA200 $679.87: bullish structure | RSI 75.7: overbought, no vote | MACD below signal: bearish | MACD histogram neutral: no vote"
