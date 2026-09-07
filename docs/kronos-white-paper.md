# Kronos: An AI-Powered Systematic Trading Signal Engine
## White Paper — Data Cutoff: September 7, 2026

**Author:** Peter Burstyn  
**Project Start:** April 2026  
**Status:** Phase 2 Complete, Second Validation Window Active (closes September 27, 2026)

---

## Executive Summary

Kronos is a fully automated, AI-powered systematic trading signal engine built from scratch by a single entrepreneur over approximately five months. It uses a three-agent AI council to analyze daily SPY (S&P 500 ETF) price signals, issue trade verdicts, and execute paper orders automatically with no human intervention required at the execution level.

The system is currently in its second paper trading validation window on Alpaca Markets. The historical analysis suggests a hypothesis of positive expectancy that remains unproven out of sample and in forward trading. This white paper documents the architecture, AI stack, methodology, current results, and the full roadmap through Phases 3 through 6.

All performance figures reflect paper trading results and historical backtesting. No real capital has been deployed. Financial projections appear in the appendix as illustrative scenario analysis only.

---

## 1. Origin and Motivation

The project began with a straightforward question: can a disciplined, rules-based AI system identify tradeable signals in SPY without human emotional interference, and can it do so consistently enough to generate meaningful income?

The answer being pursued is yes — but systematically, with proper validation at each step before committing real capital. The approach follows the same principle proven by institutional quant funds: better data and more rigorous validation outperform both intuition and speed.

The long-term goal is to build a compounding, semi-autonomous trading operation that generates meaningful monthly income, operating initially on paper and eventually on MES micro-futures contracts, with potential expansion to individual stocks and options.

---

## 2. Architecture Overview

Kronos runs as a scheduled pipeline on a Windows 11 machine with WSL2/Ubuntu. The codebase is maintained at github.com/pburstyn/kronos-trading-system. Every weekday at 6pm Pacific Time, a master shell script executes the following sequence automatically:

**signal_logger.py** — Pulls SPY's daily OHLCV data via yfinance and computes four technical indicators: RSI, MACD signal line and histogram, 50-day and 200-day moving average structure, and volume relative to average. Each indicator votes bullish or bearish. A minimum of 3 votes in agreement is required. Confidence is computed as a weighted score. Signals below 70% confidence are labeled NEUTRAL rather than directional.

**news_context.py** — Queries Alpaca's news API for the 10 most relevant SPY-related headlines from the past 24 hours, filtered by keywords including Fed, inflation, oil, earnings, and interest rate. Results are cached and made available to both analysts.

**kimi_k3_reasoning.py** — Calls Kimi K3 (moonshotai/kimi-k3), a 2.8-trillion-parameter Mixture of Experts model, via OpenRouter. Kimi reads the signal, indicators, macro data from FRED (Fed Funds Rate, CPI, unemployment), Fear and Greed sentiment from CNN's index, and today's news headlines. It produces an independent written analysis with a credibility rating.

**andy_reasoning.py** — Calls Claude Haiku via the Anthropic API with the same inputs. Andy produces a parallel, independent analysis. Andy and Kimi never see each other's reasoning before producing their own.

**critic.py** — Calls Claude Opus 5 via the Anthropic API. The Critic reads both analyst outputs and the raw signal, then issues one of three verdicts: PASS (full-size position authorized), FLAG (half-size position authorized), or VETO (no trade). It also issues a confidence rating for its own verdict.

**trade_logic.py** — Reads the Critic's verdict and computes the trade decision. Applies a 2% stop-loss and 3-5% take-profit range. Position sizing: PASS equals $1,000 notional, FLAG equals $500 notional. A stale data guard confirms the decisions log entry is from today before acting.

**alpaca_execute.py** — If the decision is ENTER, fetches a live SPY quote, anchors stop-loss and take-profit to the live price (not the prior day's close), and submits a GTC bracket order to Alpaca's paper trading API. Guards against existing open positions to prevent stacking.

**position_reconfirm.py** — Checks whether today's signal direction contradicts any open position. Sends a Telegram alert if so. Does not auto-close; the human reviews manually.

**telegram_notify.py** — Sends an ENTER signal alert when a trade fires and a daily signal summary every day regardless of direction.

**outcome_tracker.py** — Checks all open trades against current SPY price and closes any trade that hit its stop-loss or take-profit, writing exit price, exit reason, and PnL.

**update_claude_md.sh** — Automatically commits an updated project memory file to GitHub after every pipeline run.

In addition to the main pipeline, four standalone cron jobs run independently: a 7am morning trade check, a 7:05am Monday technology news digest, a 1:05pm market-close outcome tracker, and a 30-minute Andy health monitor running 24/7.

---

## 3. The AI Council

The three-agent design is the architectural core of Kronos. It mirrors, at a retail scale, how institutional trading desks use multiple independent analysts before committing capital.

**Andy (Analyst 1)** runs on Claude Haiku, chosen for speed and low cost per call. Andy's role is fundamental and macro analysis: does the technical signal make sense given current interest rates, inflation, unemployment, market sentiment, and today's news?

**Kimi K3 (Analyst 2)** is a 2.8-trillion-parameter Mixture of Experts model from Moonshot AI, accessed via OpenRouter. Kimi provides a second, independent perspective on the same data. Because it is a different model from a different company trained on different data, it may catch blind spots Andy misses.

**Opus 5 (Critic)** is Anthropic's most capable model. The Critic's job is to weigh two analysts who may disagree, identify when confidence is overstated, and issue a calibrated verdict that directly determines whether a trade is placed.

**Important caveat:** Whether the AI council improves risk-adjusted returns versus the raw technical signal alone has not yet been demonstrated. An ablation study is planned as part of the September 27 review to test this directly.

The Critic's three verdicts function as a risk management layer. PASS means both analysts agree and the signal is clean, trade at full size. FLAG means the signal is defensible but uncertain, trade at half size. VETO means the signal is contradictory or analysts identify material risk, no trade placed.

---

## 4. Data Sources

Kronos integrates five live data sources into every signal: Alpaca Markets API for real-time prices and news, FRED API for macroeconomic data updated monthly, CNN Fear and Greed Index for real-time sentiment, yfinance for 250-day SPY historical price data, and Hacker News Algolia API for weekly technology news.

---

## 5. Backtesting and Validation Methodology

Before any live trading, Kronos ran a historical backtest across 325 SPY signals spanning approximately 2.5 years of data. The backtest simulates GTC bracket orders: each signal generates an entry, and the simulation walks forward day by day using daily high/low to determine whether stop-loss or take-profit is hit first.

**Key methodology rule:** When both stop-loss and take-profit fall inside a single day's high-low range (ambiguous same-bar case), the backtest conservatively assumes the stop-loss triggered first. This pessimistic assumption is documented in the code and applies consistently across all runs.

**Backtest results at current settings (2% stop / 3% take-profit):**

- Historical win rate: 45.2% across 325 signals
- Total historical PnL: approximately $847 (paper notional, not real dollars)
- Break-even win rate at this reward-to-risk ratio: 40.0%
- Implied gross expectancy: approximately 0.30% per trade before transaction costs

**Confidence interval:** With 325 signals, the 95% confidence interval for the 45.2% win rate is approximately 39.8% to 50.6%. The apparent positive expectancy is real but narrow enough that realistic trading frictions could erode it.

**Ablation study results (September 2026):** Running the strategy without any confidence filter produces a win rate of 46.7% and approximately $2,000 in historical PnL versus $847 at the current 70% confidence floor. This suggests the 70% confidence filter is removing profitable signals, not noise. The filter will be lowered to 51% at the September 27 review, pending out-of-sample validation.

**Buy-and-hold benchmark:** SPY passive holding over the same period produced approximately $852 in equivalent returns at dramatically lower drawdown than the active strategy. The active strategy has not yet demonstrated superior risk-adjusted performance versus passive holding. This is the primary challenge the remaining validation and Phase 3 regime filter are designed to address.

**Known backtest limitations:** Daily OHLC data cannot reconstruct intraday sequencing. No transaction costs, slippage, or adverse fill assumptions are modeled. FRED data uses current readings rather than vintage release-time data.

---

## 6. Paper Trading Results

**First validation window (June 25 to July 25, 2026):** 0 wins, 4 losses. All four losses occurred under buggy pipeline conditions including CSV header mismatches, bracket geometry errors, and a parse_verdict() mismatch. These bugs were identified and fixed in early July. The results from this window do not represent the corrected system.

**Second validation window (August 3 to September 27, 2026):** 1 clean closed trade as of September 7, 2026. The August 3 LONG was manually closed September 2 at +$1.55 (+0.20%) after five consecutive position reconfirmation alerts. Sample size is too small for statistical conclusions.

**Current status:** No open positions as of September 7, 2026. Validation window continues through September 27, 2026.

---

## 7. Risk Management Framework

Kronos enforces risk at multiple independent layers: indicator voting threshold requiring 3 of 4 indicators to agree, a 70% confidence floor moving to 51% after validation, Critic veto capability, FLAG half-sizing for uncertain signals, a 2% stop-loss bracket order placed automatically at execution, a position guard preventing stacking, a stale data guard preventing action on old decisions, and a position reconfirmation alert when today's signal contradicts an open position.

---

## 8. Infrastructure and Cost

Kronos runs on a home Windows 11 desktop with WSL2/Ubuntu. Monthly API costs are under $0.50 at current once-daily pipeline frequency: Anthropic approximately $0.15/month, Kimi K3 via OpenRouter approximately $0.22/month, all other data sources free.

Developer tooling includes a Claude Pro subscription and eight custom Fable 5 skills: context loader, signal interpreter, code reviewer, Phase 3 planner, pipeline debugger, trade analyzer, schema updater, and Critic evaluator.

---

## 9. Phase 3: Signal Quality and Infrastructure

Phase 3 begins after the September 27 validation review, conditional on results.

**Immediate Phase 3 actions:**

1. Confidence floor alignment: lower signal_logger.py MIN_CONFIDENCE from 70 to 51, re-run the full backtest to confirm the historical improvement holds, then deploy.

2. Ablation study: test whether the AI council adds measurable value versus the raw technical signal alone. If the council does not outperform the baseline after costs, reduce or restructure it.

3. Add QQQ as second instrument: same signal engine, same analyst council, same execution logic pointed at QQQ alongside SPY. Doubles data collection rate. Run bracket grid backtest on QQQ historical data immediately upon adding.

4. Regime filter: build a market regime classifier identifying trending versus choppy market conditions.

5. Edge decay monitor: automated weekly comparison of live win rate against the 45.2% historical baseline.

**Mid-Phase 3 additions:**

6. External signal agents added one at a time, each validated independently: news sentiment, Reddit sentiment via agent-reach MCP, VIX regime, options flow data, and market breadth.

7. Dynamic position sizing replacing the fixed FLAG/PASS multiplier with a continuous function scaled to signal confidence, regime, and account equity.

8. Forward rate expectations replacing the current FRED snapshot with CME FedWatch-style forward rate data.

9. VPS migration from the home Windows machine to a cloud Linux server at approximately $6/month enabling 24/7 uptime and worldwide access.

---

## 10. Critic Self-Learning

At 75 or more closed trades with recorded outcomes, the Critic becomes a candidate for domain-specific fine-tuning using methodology similar to the Bridgewater and Thinking Machines approach published in June 2026, which demonstrated 84.7% accuracy versus 78.2% for a frontier model at 13.8 times lower inference cost by fine-tuning on proprietary expert-labeled data. (Source: "Learning to Replicate Expert Judgment in Financial Tasks," Thinking Machines Lab, June 2026)

Important caveats: 75 trade outcomes is a small dataset. A trade labeled win or loss is a noisy proxy for whether the Critic's reasoning was sound. Fine-tuning carries real overfitting risk at this scale. The appropriate early framework is to store immutable decision snapshots, track explicit analyst hypotheses, score forecasts probabilistically, and analyze which input patterns correlate with positive outcomes.

---

## 11. Phase 4: Live Capital on MES Futures

After Alpaca paper trading demonstrates consistent positive expectancy, Phase 4 moves to live trading on MES micro-futures contracts via Tradovate.

**MES contract economics (current market levels):**

One MES contract represents $5 times the S&P 500 Index. At an index level of approximately 5,500, one MES contract carries roughly $27,500 in notional exposure. CME margin requirements are approximately $2,500 per contract and change with market conditions. A 1% index move generates approximately $275 per contract. A 2% adverse stop generates approximately $550 per contract before slippage and fees.

Margin is not risk capital. The appropriate sizing rule: risk per trade equals a fixed percentage of account equity, calculated using worst-case stop distance plus a slippage buffer. Contract quantity is rounded down to the number that stays within that limit. The PDT rule does not apply to futures.

---

## 12. Phase 5: Scale and Diversification

Phase 5 assumes Phase 4 has produced a consistent track record with real capital. Instruments are added one at a time, each validated independently: QQQ, individual stocks with catalyst signals, and potentially crypto given its 24/7 market structure.

---

## 13. Phase 6: Options Layer

Options require inputs beyond direction: implied volatility, time decay, strike selection, and expiration choice. NEUTRAL signals that produce no trade in the directional system become potentially actionable in an options context since sideways markets with low volatility favor premium-selling strategies.

Prerequisites for Phase 6: established directional track record from Phases 4 and 5, implied volatility data feed, strike selection logic as a separate module, and time decay awareness in position sizing.

---

## 14. Governance Principles

No live capital before paper trading proves the signal. Each phase gate requires validated results before the next phase begins. One instrument at a time, each validated independently. No live MES before paper MES is validated on a futures paper trading simulator. Self-learning blocked until 30 closed trades minimum, fine-tuning until 75 or more. Human checkpoint required on capital deployment above defined thresholds. Per-action approval for all high-stakes automated actions touching financial accounts or sensitive configuration.

---

## Appendix: Illustrative Scenario Analysis (Not a Forecast)

The figures below are mathematical illustrations based on historical backtest win rates and MES contract economics. They are not predictions. Actual results will depend on live win rate, market conditions, transaction costs, slippage, account drawdown, and the pace of capital compounding. Past backtest performance does not guarantee future results.

| Phase | Approximate Timeline | Illustrative Monthly Range |
|-------|---------------------|---------------------------|
| Live MES begins (1-2 contracts) | Q1 2027 | $200-$800 |
| 3-4 MES contracts, stable | Q3 2027 | $600-$2,000 |
| QQQ and individual stocks added | Q4 2027 | $1,500-$4,000 |
| Options layer operational | Q2 2028 | $3,000-$8,000 |
| Semi-autonomous multi-instrument | Q3 2028 | $5,000-$12,000 |

These ranges assume a live win rate near the 45.2% historical baseline, no extended drawdown periods, consistent reinvestment of profits, and correct position sizing relative to account equity at each stage.

---

*This document reflects the state of the Kronos project as of September 7, 2026. The second validation window closes September 27, 2026. Results and conclusions may change materially after that review. This is an internal reference document and a working draft. It is not investment advice and does not constitute a solicitation for capital.*
