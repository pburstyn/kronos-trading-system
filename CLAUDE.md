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
- `scripts/hy3_reasoning.py` — Hy3 (via OpenRouter, model `tencent/hy3:free`) reasons about the signal as an optional third analyst. Free tier until July 21 2026. Mirrors kimi_reasoning.py's structure (macro/sentiment/news context, same prompt shape). Logs to logs/hy3_reasoning_log.csv. **Not yet wired into run_pipeline.sh** — built for manually comparing Hy3's reasoning quality against Kimi's before deciding whether to swap.
- `scripts/trade_logic.py` — Entry/exit decision engine: confidence floor, verdict-based position sizing, stop-loss/take-profit calculation
- `scripts/alpaca_execute.py` — Places bracket paper orders on Alpaca when trade_logic.py says ENTER; checks for existing exposure before submitting; logs to logs/alpaca_orders.csv
- `scripts/news_context.py` — Fetches today's top financial headlines via Alpaca News API (no new key needed — uses existing ALPACA_API_KEY). Filters by keywords (Fed, inflation, oil, Iran, earnings, S&P, interest rate, etc.). Caches to logs/news_cache.json. Andy and Kimi call get_news_context() to read from cache — API called once per pipeline run.
- `scripts/telegram_notify.py` — Sends Telegram message to Peter via @Peters_Open_Claw_Bot when pipeline fires an ENTER decision. Skips silently on NEUTRAL/VETO/stale signals. Reads botToken from openclaw.json, chat ID from .env (TELEGRAM_CHAT_ID).
- `scripts/intraday_logger.py` — **Standalone, pipeline-independent.** Pulls SPY's last trade price from Alpaca and appends to logs/intraday_price_log.csv. Runs via cron every 15 min during market hours only (ET check inside script). Does not touch the trading pipeline in any way.
- `scripts/andy_health.py` — **Standalone, pipeline-independent.** Checks if OpenClaw (Andy) is reachable on port 18789 via powershell.exe Test-NetConnection. Sends Telegram alert only on status change (UP→DOWN or DOWN→UP). State tracked in logs/andy_status.json. Runs every 30 min 24/7 via cron. Logs to logs/andy_health.log.
- `scripts/morning_check.py` — **Standalone, pipeline-independent.** Runs at 7 AM PT (10 AM ET) weekdays. Checks Alpaca for open SPY position or pending orders; sends Telegram with filled price, current SPY price, unrealized P&L, and bracket leg status. Alerts if order is unfilled. Logs to logs/morning_check.log.
- `scripts/tech_watch.py` — **Standalone, pipeline-independent.** Runs Mondays at 7:05 AM PT. Queries the HN Algolia search API (`https://hn.algolia.com/api/v1/search`) for stories from the past 7 days matching keywords (LLM, AI trading, Claude Code, MCP, alpaca trading, autonomous agents, trading bot), filters client-side for ≥10 points (the API's `numericFilters` rejects `points` as an unregistered attribute — only `created_at_i` works server-side), dedupes, takes the top 5 by points, and sends a formatted Telegram digest. Sends a "nothing notable this week" message if no story clears the bar. Logs to logs/tech_watch.log.
- `scripts/alpaca_data.py` — Real-time SPY quotes and paper trading account info via Alpaca Markets
- `scripts/fred_data.py` — Macro data (Fed Funds Rate, CPI, unemployment) via FRED API
- `scripts/fear_greed.py` — CNN Fear and Greed Index sentiment data
- `logs/signal_log.csv` — Live signal log
- `logs/decisions_log.csv` — Andy + Critic decisions
- `logs/pipeline.log` — Pipeline run log
- `logs/dashboard.html` — Visual dashboard
- `logs/backtest_results.csv` — SPY backtest results
- `logs/backtest_qqq.csv` — QQQ backtest results
- `logs/news_cache.json` — Daily financial headlines cache written by news_context.py, read by andy and kimi
- `logs/intraday_price_log.csv` — SPY price sampled every 15 min during market hours (standalone, not pipeline)
- `logs/alpaca_orders.csv` — Submitted Alpaca paper orders (order ID, direction, notional, stop/take-profit levels)
- `logs/andy_status.json` — Last known Andy health status (UP/DOWN) and timestamp; used by andy_health.py to suppress duplicate alerts
- `logs/andy_health.log` — Andy health check log (appended by cron every 30 min)
- `logs/morning_check.log` — Morning trade check log (appended by cron at 7 AM PT weekdays)
- `logs/outcome_tracker.log` — Standalone outcome tracker log (appended by cron at 1:05 PM PT weekdays, right after market close)
- `logs/tech_watch.log` — Standalone tech watch log (appended by cron Mondays at 7:05 AM PT)
- `logs/hy3_reasoning_log.csv` — Hy3's per-signal reasoning log, written by hy3_reasoning.py

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
- **Verdict parsing bug fixed (June 24 2026):** decisions_log.csv column format changed — critic_verdict now holds full analysis text; clean FLAG/PASS/VETO keyword moved to critic_reason. All four downstream scripts (trade_logic, auto_logger, alpaca_execute, telegram_notify) were reading the wrong field and doing exact equality checks, silently dropping all signals. Fixed by adding extract_verdict(row) to trade_logic.py that checks both fields in order. auto_logger.py also had a separate bug: hardcoded `verdict == "PASS"` that ignored FLAG entirely — fixed to `verdict not in ("PASS", "FLAG")`. Commit: 61cd97f.

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

## News Context Integration — COMPLETED (June 22)
- **Source:** Alpaca News API (Benzinga articles) — uses existing ALPACA_API_KEY/ALPACA_SECRET_KEY, no new key needed.
- **Script:** `scripts/news_context.py` — fetches last 24h of news tagged to SPY/QQQ/GLD/USO/TLT, filters client-side by keywords (fed, inflation, oil, iran, earnings, s&p, interest rate, fomc, gdp, recession, tariff, treasury), keeps top 10, writes to `logs/news_cache.json`.
- **Cache pattern:** `news_context.py` runs once in pipeline (before andy_reasoning.py) and writes the cache. Both `andy_reasoning.py` and `kimi_reasoning.py` import `get_news_context()` which reads from the cache — Alpaca API called exactly once per pipeline run.
- **Prompt placement:** Added as a separate block after the existing macro/sentiment context in both analysts' prompts.
- **Failure handling:** `run()` in news_context.py wraps fetch in try/except — a failure logs WARNING but never aborts the pipeline. `get_news_context()` returns a graceful "unavailable" string if cache is missing or stale.
- **Pipeline order:** `signal_logger → news_context → andy_reasoning → kimi_reasoning → ...`
- **Tested:** 10 headlines fetched and cached on June 22 including Fed testimony, Iran/Strait of Hormuz, oil drilling, September rate hike warning.

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
- **Position sizing DECIDED (June 19):** PASS = $1,000 notional, FLAG = $500 notional. Whole shares used (qty = max(1, int(notional / last_close))). At SPY ~$734, both PASS and FLAG resolve to 1 share — size distinction reappears naturally when SPY drops below ~$500.
- **Fractional share fix (June 26):** Original code used fractional qty with GTC — Alpaca rejects this with 422 "fractional orders must be DAY orders". Fixed to whole shares (integer qty, min 1) so GTC bracket stays valid. Commit: see below.
- **Bracket stop/take-profit drift fix (July 4):** Code review flagged stops landing at 2.84% and take-profits at 2.21% instead of the configured 2%/3%. Root cause: stop-loss/take-profit were computed as absolute prices off the prior day's stale `last_close` from decisions_log.csv, but the market order actually fills at the live price next session — e.g. June 25's trade was priced off $734.30 but filled at $728.34, so the fixed $748.99/$712.27 legs worked out to the wrong % from the real fill. Fixed by fetching a live quote (bid/ask midpoint via alpaca_data.get_latest_quote) and recomputing levels via trade_logic.calculate_trade_levels immediately before order submission; falls back to the stale entry with a warning if the quote fetch fails. Qty sizing and logged entry_price now use the live-quote-based entry too. Commit: f6a11d5.
- **Order type:** GTC bracket order. Stop-loss and take-profit legs stay active until triggered. Script skips if an existing SPY position or open order is already present (no stacking).
- **Two parallel outcome-tracking systems now exist:** (1) paper_trades.csv via auto_logger + outcome_tracker (simulated, daily-close based), (2) Alpaca bracket orders (actual fills managed by Alpaca). Both run on real SPY price action.
- **30-day paper trading window:** started June 25, 2026.

## Paper Trading Results

| Date | Direction | Entry | Stop | TP | Verdict | Exit | Exit Reason | P&L $ | P&L % | Status |
|------|-----------|-------|------|----|---------|------|-------------|-------|--------|--------|
| 2026-06-25 | DOWN | $734.30 | $748.99 | $712.27 | FLAG | $748.99 | STOP_LOSS | −$20.65 | −2.81% | CLOSED |
| 2026-06-26 | DOWN | $728.99 | $743.57 | $707.12 | FLAG | $746.77 | STOP_LOSS | −$17.78 | −2.44% | CLOSED |

- **Running record:** 0 wins / 2 losses. Both stopped out on SPY rally to ~$750.
- **Note on June 25 P&L:** Alpaca filled the short at $728.34 at Friday open (not the signal's $734.30 last close); Alpaca bracket stop triggered at $748.99. P&L calculated on actual fill price.
- **outcome_tracker.py limitation:** uses daily closing price — does not catch intraday stop hits. June 25 trade showed OPEN until manually corrected on July 2. June 26 trade was caught by outcome_tracker at 6pm close on June 30.

## Telegram Notifications — COMPLETED (June 20)
- **Bot:** @Peters_Open_Claw_Bot (same bot OpenClaw/Andy uses). No new bot needed.
- **Script:** `scripts/telegram_notify.py` — reads botToken from `/mnt/c/Users/openc/.openclaw/openclaw.json` (channels.telegram.botToken), reads Peter's personal chat ID from `.env` (TELEGRAM_CHAT_ID = 8344685831).
- **Trigger:** ENTER decisions only (UP or DOWN with PASS or FLAG verdict, confidence ≥ 51%, today's date). Exits silently on NEUTRAL, VETO, or stale signal — never spams.
- **Message includes:** direction, confidence, entry price, stop-loss, take-profit range, verdict, notional size ($1,000 PASS / $500 FLAG).
- **Pipeline position:** after alpaca_execute.py (order is placed before notification fires): `trade_logic → alpaca_execute → telegram_notify → dashboard`
- **Why chat ID is in .env, not openclaw.json:** openclaw.json's allowFrom field contained a stale group chat ID. Peter's personal Telegram user ID was obtained via @userinfobot and stored in .env so Kronos notifications are independent of OpenClaw's config.
- **.env now holds 6 keys:** ANTHROPIC_API_KEY, NVIDIA_API_KEY, ALPACA_API_KEY, ALPACA_SECRET_KEY, FRED_API_KEY, TELEGRAM_CHAT_ID
- **Tested:** Real message delivered successfully June 20 (message_id: 4).

## APIs Connected — COMPLETED (June 16-17)
- **Alpaca Markets:** Connected (scripts/alpaca_data.py). Paper account confirmed ACTIVE, $100,000 cash, $400,000 buying power. Real-time quotes working.
- **NVIDIA NIM:** Connected (scripts/kimi_reasoning.py). Model moonshotai/kimi-k2.6.
- **FRED API:** Connected (scripts/fred_data.py). Pulling FEDFUNDS, CPIAUCSL, UNRATE.
- **CNN Fear and Greed Index:** Connected (scripts/fear_greed.py). Required full browser-style headers (User-Agent + Accept + Referer) to bypass a 418 bot-blocking error — bare User-Agent alone is not enough.
- **OpenRouter:** Connected (scripts/hy3_reasoning.py). Model tencent/hy3:free. OPENROUTER_API_KEY added to .env to authenticate.
- **.env now holds 7 keys:** ANTHROPIC_API_KEY, NVIDIA_API_KEY, ALPACA_API_KEY, ALPACA_SECRET_KEY, FRED_API_KEY, TELEGRAM_CHAT_ID, OPENROUTER_API_KEY (OpenRouter added July 7 for Hy3 access).
- **SECURITY NOTE:** Anthropic and NVIDIA keys were exposed in full in a Claude.ai chat session on June 16. Peter made an informed decision not to rotate them at the time (low perceived risk, personal project). Alpaca and FRED keys were never exposed (typed directly into nano).
- **NVIDIA_API_KEY rotated (July 7):** the old key started returning 403 "Authorization failed" from NVIDIA's endpoint — confirmed structurally clean (no whitespace/quotes/malformed characters) but revoked/invalid server-side. Rotated to a fresh key generated at build.nvidia.com; verified with a live 200 OK against the NIM endpoint and a successful kimi_reasoning.py run. Unrelated to the June 16 exposure — this was an independent revocation.
- **ANTHROPIC_API_KEY fixed (July 6):** the .env line was corrupted with a literal trailing shell-command fragment (`/' ~/trading-system/.env`), likely from a botched `sed -i` replacement that wrote its own argument text into the file instead of executing. Rewritten as a clean single-line value.

## Outcome Tracking — COMPLETED (June 18)
- **scripts/auto_logger.py rewritten:** now calculates and stores stop_loss, take_profit_low, take_profit_high at the moment a trade is logged (status=OPEN). New paper_trades.csv columns: stop_loss, take_profit_low, take_profit_high, exit_reason, status.
- **scripts/outcome_tracker.py (NEW FILE):** runs daily, checks all OPEN trades against current SPY closing price via yfinance, auto-closes any trade that hit its stop-loss or take-profit, calculates pnl_dollars/pnl_pct, flips status to CLOSED. Leaves unresolved trades OPEN with unrealized PnL printed.
- **LIMITATION:** checks daily closing price only, not intraday — a stop-loss hit and recovered intraday won't be caught. Possible future upgrade via Alpaca intraday data if this proves too loose.
- Wired into run_pipeline.sh immediately after auto_logger.py
- **Standalone cron added (July 1 2026):** also runs at 1:05 PM PT (4:05 PM ET) weekdays — immediately after market close — so paper_trades.csv updates without waiting for the 6pm pipeline. Logs to logs/outcome_tracker.log.
- Commit: a9fd30c

## Andy Health Monitor — COMPLETED (June 25)
- **Script:** `scripts/andy_health.py` — checks if OpenClaw is reachable at localhost:18789 using `powershell.exe Test-NetConnection` (WSL2 cannot reach Windows localhost directly via TCP; must use powershell.exe subprocess).
- **Alert logic:** Sends Telegram alert only on status change — DOWN alert when UP→DOWN, recovery alert when DOWN→UP. Silent on repeated same status (no alert spam every 30 min).
- **First-run fix:** On first run (no status file), `last_status=None`. Only the DOWN alert fires if Andy is down; the "back UP" message is guarded by `elif last_status == "DOWN"` so it never fires falsely when there's no prior state.
- **State file:** `logs/andy_status.json` — stores `{"status": "UP"/"DOWN", "last_checked": "..."}`. Persists across cron runs.
- **Cron:** `*/30 * * * *` — every 30 minutes, all hours, all days (no market-hours restriction; Andy should be up whenever you want to trade). Full absolute path with venv python, stderr+stdout → `logs/andy_health.log`.
- **Telegram config:** Same pattern as telegram_notify.py — botToken from openclaw.json, TELEGRAM_CHAT_ID from .env.
- **DOWN alert message:** `"ALERT: Andy (OpenClaw) is DOWN as of {now}.\nStart gateway.cmd in PowerShell to bring him back up."`
- **Tested:** First run with no prior status file → correctly sent DOWN alert (Andy genuinely down). Second run → no duplicate alert. Fix verified.

## Andy Auto-Restart (Windows Task Scheduler) — COMPLETED (June 25)
- **Problem:** OpenClaw had an existing "OpenClaw Gateway" task (installed by OpenClaw itself) but with `RestartCount: 0` (no restart on crash) and a 72-hour execution time limit that would kill Andy every 3 days.
- **Wrapper script:** `C:\Users\openc\.openclaw\start_andy_loop.bat` — runs a port-check loop: if port 18789 is already LISTENING (Andy is up), waits 30 seconds and checks again. If port is free, starts `gateway.cmd` and monitors it. When gateway.cmd exits, waits 15 seconds and tries again. This handles crashes at the node.exe level.
- **Scheduled task:** `Kronos-Andy-Autostart` in Windows Task Scheduler. Trigger: at login for user `openc`. RestartCount: 10, RestartInterval: 2 min, ExecutionTimeLimit: 0 (unlimited), MultipleInstances: IgnoreNew, StartWhenAvailable: true. This is belt-and-suspenders on top of the wrapper loop — if the CMD process itself is killed, Task Scheduler restarts it after 2 minutes.
- **Coexistence:** The original "OpenClaw Gateway" task could not be disabled without admin privileges (created by OpenClaw installer). The wrapper's port-check prevents both tasks from starting duplicate Andy instances — if Andy is already up (from the original task), the wrapper waits silently. If Andy crashes, the wrapper restarts it within 15 seconds, before Task Scheduler's 2-minute restart policy kicks in.
- **Two-layer restart:** (1) start_andy_loop.bat restarts Andy within 15 seconds of node.exe crashing; (2) Kronos-Andy-Autostart task restarts the wrapper itself within 2 minutes if the CMD process is killed.
- **Tested:** Task state = Running with Andy already up (wrapper correctly waiting, not starting duplicate). Port-check logic verified with netstat.
- **To manage:** `Get-ScheduledTask -TaskName 'Kronos-Andy-Autostart'` to check state. `Stop-ScheduledTask` to stop. `Start-ScheduledTask` to start manually.

## Intraday Price Collection — COMPLETED (June 19)
- **Purpose:** Background data collection for future analysis — specifically, checking whether stop-loss/take-profit levels get hit and recovered intraday, which `outcome_tracker.py` (daily-close-only) cannot see.
- **Script:** `scripts/intraday_logger.py` — pulls SPY last trade price via Alpaca `StockLatestTradeRequest`, appends `timestamp,price` to `logs/intraday_price_log.csv`.
- **Market hours guard:** Script checks current ET time on every invocation; exits silently if outside 9:30 AM–4:00 PM ET or on a weekend.
- **Cron:** `*/15 6-13 * * 1-5` (every 15 min, 6am–1:45pm PT weekdays). PT is always ET−3, so this window covers 9:00 AM–4:45 PM ET; the script's own ET check handles the precise cutoff. Stderr/stdout → `logs/intraday_price.log`.
- **Isolation:** Completely separate from the trading pipeline. Does not read from or write to any pipeline log. Does not trigger any trade action. Safe to disable or delete without affecting signal generation, analyst reasoning, or order execution.
- **Future use:** Once enough intraday data accumulates, can cross-reference against `paper_trades.csv` stop/take-profit levels to audit whether daily-close outcome_tracker.py is over- or under-counting wins/losses.

## Tech Watch — COMPLETED (July 6)
- **Purpose:** Weekly digest of HN discussion relevant to the Kronos stack (LLM tooling, AI trading, Claude Code, MCP, agent frameworks) so Peter doesn't have to monitor HN manually.
- **Script:** `scripts/tech_watch.py` — standalone, pipeline-independent, no state file (unlike andy_health.py, nothing to persist between runs since it's always looking back a fixed 7 days).
- **Source:** HN Algolia search API (`https://hn.algolia.com/api/v1/search`), one query per keyword: LLM, AI trading, Claude Code, MCP, alpaca trading, autonomous agents, trading bot.
- **API quirk discovered during testing:** `numericFilters=points>=10` returns a 400 ("invalid numeric attribute(points), attribute not specified in numericAttributesForFiltering setting") — `points` is not a registered filterable attribute on the public endpoint, only `created_at_i` is. Fixed by filtering the 7-day window server-side via `numericFilters=created_at_i>{timestamp}` and filtering the ≥10-points threshold client-side after fetch.
- **Dedup + ranking:** Merges hits across all 7 keyword queries by `objectID` (a story can match multiple keywords), sorts by points descending, takes top 5.
- **Message:** Sends via the same Telegram bot/config pattern as telegram_notify.py/andy_health.py (botToken from openclaw.json, chat ID from .env). Sends "nothing notable this week" if zero stories clear the 10-point bar in the trailing 7 days.
- **No accuracy vetting:** headlines are surfaced purely by relevance + points, not fact-checked — treat the digest as leads, not confirmed news, especially for any story making claims about Claude/Anthropic itself.
- **Cron:** `5 7 * * 1` — Mondays only, 7:05 AM PT (chosen to land right after morning_check.py's 7:00 AM slot without overlapping). Stderr+stdout → `logs/tech_watch.log`.
- **Tested:** Live run July 6 2026 returned 5 stories (top: 2440 pts) and delivered successfully to Telegram.

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
10. ✅ Telegram notifications built (June 20) — ENTER signals delivered to Peter's phone via @Peters_Open_Claw_Bot
11. ✅ Andy health monitor built (June 25) — scripts/andy_health.py checks port 18789 every 30 min, sends Telegram alert on DOWN/recovery
12. ✅ Andy auto-restart built (June 25) — start_andy_loop.bat + Kronos-Andy-Autostart Task Scheduler task; two-layer restart on crash
13. ✅ **First paper trade placed (June 25)** — DOWN FLAG, SPY $734.30, 1 share short, stop $748.99 / take-profit $712.27. Alpaca order ID: 7aa3c1a7. 30-day window started.
14. ✅ Tech watch built (July 6) — scripts/tech_watch.py sends a weekly Monday HN digest (LLM/AI trading/Claude Code/MCP/agents) via Telegram
15. ✅ Hy3 added as optional third-analyst candidate (July 7) — scripts/hy3_reasoning.py via OpenRouter (tencent/hy3:free, free until July 21 2026), not yet wired into run_pipeline.sh, for manual comparison against Kimi
16. ⬜ Live trading with $5,000-$10,000 capital on MES (after Alpaca validation proves out)
12. ⬜ Live trading with $5,000-$10,000 capital on MES (after Alpaca validation proves out, requires funding live Tradovate)
13. ⬜ Scale up, add QQQ, crypto, FOREX instruments
14. ⬜ Semi-autopilot with Claude Code + broker API executor

## Session Log — June 19, 2026 (First Claude Code Session)

**Context:** Peter upgraded to Claude Pro (which includes Claude Code). This was the first hands-on coding session done entirely inside Claude Code (VS Code/WSL terminal) rather than the claude.ai chat interface. Claude Code reads this CLAUDE.md plus the Google Doc session logs for context at the start of each session. The chat interface remains primary for planning/research/decisions; Claude Code is for direct file editing and running commands in the repo.

**Session goals coming in:** Build the Alpaca execution script (marked as next task in CLAUDE.md and Part 3 Google Doc), then anything else that makes sense.

**What was built:**

1. **scripts/alpaca_execute.py** (commit 58504f2)
   - Reads today's decision from decisions_log.csv (same staleness guard as trade_logic.py)
   - If ENTER: checks Alpaca for existing SPY position or open orders (no stacking), then submits a GTC bracket order — market entry + stop-loss stop order + take-profit limit order
   - Position sizing decided in session: PASS = $1,000 notional, FLAG = $500 notional; fractional shares (qty = notional / last_close)
   - Logs submitted orders to logs/alpaca_orders.csv (order ID, direction, notional, qty, levels, verdict)
   - Wired into run_pipeline.sh immediately after trade_logic.py
   - Stop/take-profit directions verified correct for both long (UP) and short (DOWN): for shorts, stop is above entry, take-profit is below; Alpaca bracket order handles leg sides automatically based on parent order side
   - Tested: with no ENTER signal today (NEUTRAL day, stale decisions_log.csv), correctly prints SKIP and exits without touching Alpaca

2. **scripts/intraday_logger.py** (commit 49a06f3)
   - Completely separate from the trading pipeline — does not read or write any pipeline file
   - Pulls SPY last trade price via Alpaca StockLatestTradeRequest (actual trade price, not bid/ask)
   - Checks current ET time on every invocation; exits silently if outside 9:30 AM–4:00 PM ET or weekend
   - Appends timestamp,price to logs/intraday_price_log.csv
   - Cron: `*/15 6-13 * * 1-5` (every 15 min, 6am–1:45pm PT on weekdays). All paths are absolute in crontab so no cwd dependency.
   - Motivation: outcome_tracker.py only checks daily closing prices; intraday data will let us audit whether stop-losses get hit and recover intraday (i.e., whether the daily-close approximation is too loose). Data collection starts Monday.
   - Tested: market-hours guard fires correctly (correctly skipped at 5pm PT); force-tested CSV write path separately, confirmed SPY $748.46 logged to correct file.

**Decisions made:**
- Position sizing: $1,000 for PASS, $500 for FLAG (Peter chose fixed-dollar over fixed-share-count or pct-of-portfolio)
- Intraday collection: standalone cron, not wired into pipeline, to keep pipeline unchanged and data collection independent

**State at end of session:**
- All Phase 2 + Phase 3 infrastructure is complete
- 30-day paper trading window begins on the next pipeline run that fires an ENTER decision (first directional signal with ≥51% confidence and PASS or FLAG verdict after June 19)
- Intraday price collection begins Monday morning (first weekday market open after June 19)
- Nothing blocking; no open code tasks

**Sofia/AssetAndOak projects placed on hold** — Peter is focusing on Kronos exclusively for now.

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

# Run Hy3 reasoning only (optional third analyst, not wired into pipeline)
cd ~/trading-system && python3 scripts/hy3_reasoning.py

# Run trade logic only (reads latest decisions_log.csv row)
cd ~/trading-system && python3 scripts/trade_logic.py

# Run Alpaca execution only (dry-runs unless today's ENTER decision exists)
cd ~/trading-system && python3 scripts/alpaca_execute.py

# Check intraday price log (last 5 entries)
tail -5 ~/trading-system/logs/intraday_price_log.csv

# Check Alpaca paper orders placed
cat ~/trading-system/logs/alpaca_orders.csv

# Run morning trade check manually
cd ~/trading-system && python3 scripts/morning_check.py

# Run tech watch manually (add --dry-run to skip the Telegram send)
cd ~/trading-system && python3 scripts/tech_watch.py

# View tech watch log
tail -20 ~/trading-system/logs/tech_watch.log

# Check Andy health manually
cd ~/trading-system && python3 scripts/andy_health.py

# View Andy health log (last 20 entries)
tail -20 ~/trading-system/logs/andy_health.log

# Check Andy auto-restart task state (from WSL)
powershell.exe -Command "Get-ScheduledTaskInfo -TaskName 'Kronos-Andy-Autostart' | Select-Object LastRunTime, LastTaskResult, NextRunTime"

# Stop/start Andy auto-restart task manually
powershell.exe -Command "Stop-ScheduledTask -TaskName 'Kronos-Andy-Autostart'"
powershell.exe -Command "Start-ScheduledTask -TaskName 'Kronos-Andy-Autostart'"

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
2026-07-07 18:00:55
**Last Signal:** 2026-07-07 18:00:04,SPY,UP,80,747.71,Price $747.71 above MA50 $737.57 and MA200 $689.71: bullish structure | RSI 55.3: bullish | MACD above signal: bullish | MACD histogram growing: bullish | Volume 40.1M below avg: weakens signal
