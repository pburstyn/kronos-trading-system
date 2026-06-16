# Kronos Trading System — Claude Memory File
*Auto-updated after every pipeline run. Fetch this file at the start of any session to restore full context.*

## System Overview
- **Goal:** Automated trading signal engine targeting $200-$300/day, scaling to $10,000-$20,000/month
- **Instrument:** SPY (validation), MES futures (live trading target)
- **Machine:** OpenClaw (WSL2/Ubuntu, username: pburstyn, Windows 11, Burbank CA)
- **GitHub:** https://github.com/pburstyn/kronos-trading-system
- **Pipeline runs:** 6pm weekdays via cron

## File Structure
- `scripts/signal_logger.py` — Fetches SPY data, computes indicators, logs signal
- `scripts/andy_reasoning.py` — Claude Haiku reasons about the signal
- `scripts/critic.py` — Issues PASS/FLAG/VETO verdict
- `scripts/dashboard.py` — Generates dashboard.html
- `scripts/auto_logger.py` — Logs paper trades
- `scripts/run_pipeline.sh` — Master pipeline script
- `scripts/backtest.py` — Historical backtest script
- `scripts/compare_ema_rsi.py` — EMA crossover vs Kronos comparison script
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

## Code Changes (June 2026)
- **Conflict detection added (June 13 2026):** RSI overbought (>70) now hard-vetoes any UP signal regardless of other votes. Logs VERDICT: CONFLICT line explaining the override.
- **Granular verdict logging added (June 13 2026):** Every NEUTRAL outcome now logs VERDICT line showing bull_votes, bear_votes, and why MIN_VOTES was not met.
- **Commit:** 02acec3 — "Add conflict detection and granular verdict logging"

## Backtest Results (run May 2026)
- **SPY:** 57.8% accuracy, 282 signals fired, 646 days analyzed (2023-01-01 to present)
- **QQQ:** 57.2% accuracy, 290 signals fired, 646 days analyzed
- **Threshold to beat:** 55% accuracy, under 300 signals
- **Status:** EDGE DETECTED on both instruments

## EMA Crossover Comparison (June 2026)
- Script 2 (EMA 9/21 crossover + RSI filter) produced ZERO signals across same 30-day SPY window
- Kronos fired DOWN at 90% confidence on June 5, 9, 10 during the same period
- Concrete evidence multi-indicator approach beats single-condition strategy using live data
- Script location: scripts/compare_ema_rsi.py
- **Bring this to June 16 Phase 2 session as evidence**

## Live Signal Performance (June 2026)
- **June 5:** DOWN 90% confidence, SPY $737.55 — correct call, sell-off confirmed
- **June 9:** DOWN 90% confidence, SPY $737.05 — confirmed continuation
- **June 10:** DOWN 90% confidence, SPY $725.43 — confirmed continuation
- **June 11:** DOWN 80% confidence, SPY $728.45 — volume below avg weakened signal
- **June 12:** NEUTRAL, SPY $741.75 — RSI recovered to 53, MACD still bearish
- Two market regimes captured: overbought grind (May) and active sell-off (June)

## Phase 2 Architecture Decision (June 16)
- **Andy (Claude Haiku):** Analyst 1
- **Kimi K2 via NVIDIA NIM:** Analyst 2 (free tier, model: moonshotai/kimi-k2)
- **Endpoint:** https://integrate.api.nvidia.com/v1/chat/completions
- **Critic:** Referee — reads both outputs, issues PASS/FLAG/VETO
- Agreement between Andy and Kimi raises confidence
- Disagreement triggers FLAG with Critic explaining which is more credible
- Kimi needs second API call wired into pipeline routing both outputs to Critic

## Entry/Exit Logic (to build June 16)
- Long entry: MACD above signal + RSI < 70 + histogram positive + confidence > 51%
- Short entry: Daily close below key support with MACD bearish + RSI bearish
- Hard confidence floor: 51% minimum for any directional entry
- Stop-loss: 2% below entry or price falls below MA50
- Take-profit: RSI reaches 75+ or +3-5% from entry

## Paper Trading Setup
- **Platform:** Tradovate (sim account, $50,000 simulated equity)
- **Instrument:** MESM6 (expires 06/18/2026), roll to MESU6 after expiry
- **Value per point:** $5.00 USD
- **Margin per contract:** $1,328.50
- **Position sizing:** 1-2 contracts per signal to start

## APIs to Connect on June 16
- **Alpaca Markets:** Free paper trading + real-time data API
- **NVIDIA NIM:** Free API for Kimi K2. Account at build.nvidia.com
- **FRED API:** Free macro data. Account at fred.stlouisfed.org
- **CNN Fear and Greed Index:** No key needed. https://production.dataviz.cnn.io/index/fearandgreed/graphdata

## Architecture Roadmap
1. ✅ Phase 0-3: Signal engine, Andy, Critic, dashboard running
2. ✅ Backtest validated (57.8% SPY, 57.2% QQQ)
3. ✅ Conflict detection and granular logging added
4. 🔄 30-day live signal observation (May 16 - June 16)
5. ⬜ Phase 2: Entry/exit logic, wire Kimi K2, connect APIs (June 16)
6. ⬜ 30-day paper trading on Tradovate sim account
7. ⬜ Live trading with $5,000-$10,000 capital on MES
8. ⬜ Scale up, add QQQ, crypto, FOREX instruments
9. ⬜ Semi-autopilot with Claude Code + Tradovate API executor

## Phase 3 Deferred Tasks
- Add external signal sources one at a time, validate each independently
- Reading list: "Evidence-Based Technical Analysis" by David Aronson
- Reading list: "Advances in Financial Machine Learning" by Marcos Lopez de Prado
- Extract 10-15 rules from each, add to Critic prompt, do not feed raw
- Test Opus 4.8 as Critic on batch of logged signals
- Revisit Hermes Agent (Nous Research) — disable self-modifying behavior first
- Build news sentiment agent, political/macro agent, psychology agent in that order

## Workflow Rules
- **PowerShell:** Andy management only
- **Start Andy:** C:\Users\openc\.openclaw\gateway.cmd
- **WSL terminal:** All Kronos scripts and logs
- **Never close PowerShell gateway window** — closing it kills Andy
- **OpenClaw dashboard:** localhost:18789
- **OpenClaw bash interface mangles commands** — use WSL terminal directly

## Key Commands
```bash
# Run pipeline manually
cd ~/trading-system && bash scripts/run_pipeline.sh

# Run signal logger only
cd ~/trading-system && python3 scripts/signal_logger.py

# Check last signal
tail -3 ~/trading-system/logs/signal_log.csv

# Run EMA comparison
cd ~/trading-system && python3 scripts/compare_ema_rsi.py

# Run SPY backtest
cd ~/trading-system && python3 scripts/backtest.py

# If Ubuntu restarted
cd ~/trading-system && source venv/bin/activate && bash scripts/run_pipeline.sh
```

## Last Updated
2026-06-15 18:00:07
**Last Signal:** 2026-06-15 18:00:04,SPY,NEUTRAL,0.0,754.83,Price $754.83 above MA50 $724.78 and MA200 $684.64: bullish structure | RSI 60.4: bullish | MACD below signal: bearish | MACD histogram neutral: no vote | VERDICT: NEUTRAL — bull_votes=1 bear_votes=1 did not meet MIN_VOTES=3
