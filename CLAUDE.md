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
- `scripts/kimi_reasoning.py` — Kimi K2 (via NVIDIA NIM) reasons about the signal as Analyst 2
- `scripts/trade_logic.py` — Entry/exit decision engine: confidence floor, verdict-based position sizing, stop-loss/take-profit calculation
- `scripts/alpaca_execute.py` — Places bracket paper orders on Alpaca when trade_logic.py says ENTER; checks for existing exposure before submitting; logs to logs/alpaca_orders.csv
- `scripts/alpaca_data.py` — Real-time SPY quotes and paper trading account info via Alpaca Markets
- `scripts/fred_data.py` — Macro data (Fed Funds Rate, CPI, unemployment) via FRED API
- `scripts/fear_greed.py` — CNN Fear and Greed Index sentiment data
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
- Used as opening evidence in the June 16 Phase 2 session

## Live Signal Performance (June 2026)
- **June 5:** DOWN 90% confidence, SPY $737.55 — correct call, sell-off confirmed
- **June 9:** DOWN 90% confidence, SPY $737.05 — confirmed continuation
- **June 10:** DOWN 90% confidence, SPY $725.43 — confirmed continuation
- **June 11:** DOWN 80% confidence, SPY $728.45 — volume below avg weakened signal
- **June 12:** NEUTRAL, SPY $741.75 — RSI recovered to 53, MACD still bearish
- Two market regimes captured: overbought grind (May) and active sell-off (June)

## Phase 2 Architecture — COMPLETED (June 16-17)
- **Andy (Claude Haiku):** Analyst 1
- **Kimi K2 via NVIDIA NIM:** Analyst 2 (free tier, model: moonshotai/kimi-k2.6)
- **Endpoint:** https://integrate.api.nvidia.com/v1/chat/completions
- **Critic:** Referee — reads both outputs, issues PASS/FLAG/VETO, logs both reasonings to decisions_log.csv
- Agreement between Andy and Kimi raises confidence toward PASS
- Disagreement triggers FLAG with Critic explaining which analyst is more credible
- Validated against June 10 historical signal: both analysts independently flagged the same 90%-confidence-vs-bullish-structure contradiction; Critic correctly synthesized into FLAG, HIGH confidence
- Commits: cb82783 (Kimi wired in), aea8077 (trade_logic wired into pipeline)

## Entry/Exit Logic — COMPLETED (scripts/trade_logic.py)
- Long entry: MACD above signal + RSI < 70 + histogram positive + confidence > 51%
- Short entry: Daily close below key support with MACD bearish + RSI bearish
- Hard confidence floor: 51% minimum for any directional entry (checked independently of verdict)
- Position sizing: VETO blocks entirely, FLAG = 0.5x size, PASS = 1x size
- Stop-loss: 2% from entry (above for shorts, below for longs)
- Take-profit: 3-5% from entry
- **Stale-data protection added (commit aea8077):** checks latest decisions_log.csv timestamp matches today's date before acting; if signal is NEUTRAL or stale, reports NO TRADE instead of silently re-acting on an old decision
- Tested against VETO, FLAG, and confidence-floor-block scenarios — all behave correctly

## Macro and Sentiment Integration — COMPLETED (June 17)
- Both andy_reasoning.py and kimi_reasoning.py now call get_macro_context() before building their prompts
- Pulls Fed Funds Rate, CPI, unemployment from fred_data.py and CNN Fear & Greed score/rating from fear_greed.py
- Wrapped in try/except per source so a FRED or CNN outage does not break the analyst's reasoning, just logs "data unavailable" for that piece
- Commits: 10ba5f0 (Andy), fbe7e26 (Kimi)
- Verified live: Fed Funds 3.63%, CPI 333.979, Unemployment 4.3% (all as of 2026-05-01), Fear & Greed 32.7 (fear) as of June 17

## Paper Trading Setup — REVISED (June 18-19)
- **DECISION: Using Alpaca, not Tradovate, for the 30-day paper trading validation.**
- **Why Tradovate was ruled out:** API access requires a LIVE, funded account ($1,000+ minimum) plus a paid $25/month API Access Add-on. Sim/demo accounts get NO API access at all — confirmed via Tradovate's own docs and forum. The existing $50,000 sim account (MESM6 contract) cannot be connected to via API in any form.
- **Why TradingView was also ruled out:** No public data/execution API. Trades aren't executed by TradingView natively — would require rewriting signal logic in Pine Script plus a paid third-party bridge (TradersPost/PickMyTrade), which still needs a connected broker underneath, putting us back at square one.
- **Platform:** Alpaca Markets (already connected, free, paper account confirmed ACTIVE — see APIs Connected section)
- **Instrument:** SPY shares (not MES futures)
- **Accuracy tradeoff accepted:** signal generation, entry/stop/take-profit price levels, and win/loss outcomes will all be equally valid on Alpaca since they're based on real SPY price action. What will NOT be tested: futures leverage (~10:1 vs SPY's 1:1/4:1), overnight/weekend gap behavior, and contract rolling (MESM6→MESU6). Revisit funding live Tradovate ONLY after Kronos proves out on Alpaca.
- **Execution script BUILT (June 19):** scripts/alpaca_execute.py — places bracket orders (market entry + stop-loss stop + take-profit limit) via alpaca-py. Wired into run_pipeline.sh after trade_logic.py.
- **Position sizing DECIDED (June 19):** PASS = $1,000 notional, FLAG = $500 notional. Fractional shares used (qty = notional / last_close). Alpaca handles fractional share execution.
- **Order type:** GTC bracket order. Stop-loss and take-profit legs stay active until triggered. Script skips if an existing SPY position or open order is already present (no stacking).
- **Two parallel outcome-tracking systems now exist:** (1) paper_trades.csv via auto_logger + outcome_tracker (simulated, daily-close based), (2) Alpaca bracket orders (actual fills managed by Alpaca). Both run on real SPY price action.
- **30-day paper trading window:** begins on the next pipeline run that produces an ENTER decision.

## APIs Connected — COMPLETED (June 16-17)
- **Alpaca Markets:** Connected (scripts/alpaca_data.py). Paper account confirmed ACTIVE, $100,000 cash, $400,000 buying power. Real-time quotes working.
- **NVIDIA NIM:** Connected (scripts/kimi_reasoning.py). Model moonshotai/kimi-k2.6.
- **FRED API:** Connected (scripts/fred_data.py). Pulling FEDFUNDS, CPIAUCSL, UNRATE.
- **CNN Fear and Greed Index:** Connected (scripts/fear_greed.py). Required full browser-style headers (User-Agent + Accept + Referer) to bypass a 418 bot-blocking error — bare User-Agent alone is not enough.
- **.env now holds 5 keys:** ANTHROPIC_API_KEY, NVIDIA_API_KEY, ALPACA_API_KEY, ALPACA_SECRET_KEY, FRED_API_KEY
- **SECURITY NOTE:** Anthropic and NVIDIA keys were exposed in full in a Claude.ai chat session on June 16. Peter made an informed decision not to rotate them (low perceived risk, personal project). Alpaca and FRED keys were never exposed (typed directly into nano).

## Outcome Tracking — COMPLETED (June 18)
- **scripts/auto_logger.py rewritten:** now calculates and stores stop_loss, take_profit_low, take_profit_high at the moment a trade is logged (status=OPEN). New paper_trades.csv columns: stop_loss, take_profit_low, take_profit_high, exit_reason, status.
- **scripts/outcome_tracker.py (NEW FILE):** runs daily, checks all OPEN trades against current SPY closing price via yfinance, auto-closes any trade that hit its stop-loss or take-profit, calculates pnl_dollars/pnl_pct, flips status to CLOSED. Leaves unresolved trades OPEN with unrealized PnL printed.
- **LIMITATION:** checks daily closing price only, not intraday — a stop-loss hit and recovered intraday won't be caught. Possible future upgrade via Alpaca intraday data if this proves too loose.
- Wired into run_pipeline.sh immediately after auto_logger.py
- Commit: a9fd30c

## Architecture Roadmap
1. ✅ Phase 0-3: Signal engine, Andy, Critic, dashboard running
2. ✅ Backtest validated (57.8% SPY, 57.2% QQQ)
3. ✅ Conflict detection and granular logging added
4. ✅ 30-day live signal observation (May 16 - June 16) — captured two market regimes (overbought grind in May, active sell-off in June)
5. ✅ Phase 2: Three-agent architecture, entry/exit logic, all four APIs connected, macro/sentiment feeding into both analysts (June 16-17)
6. ✅ Outcome tracking built (June 18) — paper trades now auto-resolve win/loss instead of requiring manual exit-price entry
7. ✅ Tradovate ruled out, Alpaca confirmed as paper trading platform (June 18) — see Paper Trading Setup section
8. ✅ Alpaca execution script built (June 19) — scripts/alpaca_execute.py places bracket paper orders; wired into pipeline
9. ✅ Position sizing decided (June 19) — PASS = $1,000 notional, FLAG = $500 notional, fractional shares
10. ⬜ **NEXT: 30-day paper trading window** — begins on first ENTER signal after June 19; track start date when it fires
11. ⬜ Live trading with $5,000-$10,000 capital on MES (after Alpaca validation proves out, requires funding live Tradovate)
12. ⬜ Scale up, add QQQ, crypto, FOREX instruments
13. ⬜ Semi-autopilot with Claude Code + broker API executor

## Account Note (June 19)
- Peter upgraded to Claude Pro. Plan to use Claude Code (now included) for hands-on coding sessions on this repo going forward, pointing it at this CLAUDE.md file plus the Google Doc session logs (Parts 1-3, in Drive folder linked from CLAUDE.md context) for full context at the start of any session. This chat interface remains primary for planning/research/decisions; Claude Code is for direct file editing and running commands in this repo.
- Sofia/AssetAndOak projects placed on hold — Peter is focusing on Kronos exclusively for now.

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

# Run Kimi reasoning only (Analyst 2)
cd ~/trading-system && python3 scripts/kimi_reasoning.py

# Run trade logic only (reads latest decisions_log.csv row)
cd ~/trading-system && python3 scripts/trade_logic.py

# Run Alpaca execution only (dry-runs unless today's ENTER decision exists)
cd ~/trading-system && python3 scripts/alpaca_execute.py

# Check Alpaca account and live quote
cd ~/trading-system && python3 scripts/alpaca_data.py

# Check macro snapshot (FRED)
cd ~/trading-system && python3 scripts/fred_data.py

# Check Fear and Greed Index
cd ~/trading-system && python3 scripts/fear_greed.py

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
2026-06-19 18:00:08
**Last Signal:** 2026-06-19 18:00:04,SPY,NEUTRAL,0.0,746.74,Price $746.74 above MA50 $727.82 and MA200 $684.49: bullish structure | RSI 55.1: bullish | MACD below signal: bearish | MACD histogram neutral: no vote | VERDICT: NEUTRAL — bull_votes=1 bear_votes=1 did not meet MIN_VOTES=3
