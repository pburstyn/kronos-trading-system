import yfinance as yf
import pandas_ta as ta
import pandas as pd
import numpy as np
import csv
import os
from datetime import datetime
TICKER = "SPY"
MIN_VOTES = 3
MIN_CONFIDENCE = 70.0
OUTPUT_FILE = os.path.expanduser("~/trading-system/logs/backtest_results.csv")
BRACKET_GRID_OUTPUT_FILE = os.path.expanduser("~/trading-system/logs/backtest_bracket_grid.csv")

# Grid tested against the actual GTC-bracket structure alpaca_execute.py places live:
# market entry at signal close, fixed stop-loss %, fixed take-profit %, held open
# until one leg hits (no time limit) -- this is what's actually being validated,
# not just next-day directional accuracy.
STOP_LOSS_GRID = [1.0, 1.5, 2.0, 2.5, 3.0, 3.5, 4.0]
TAKE_PROFIT_GRID = [2.0, 3.0, 4.0, 5.0, 6.0, 7.0, 8.0]
BRACKET_NOTIONAL = 1000  # matches live PASS-verdict sizing, for dollar PnL reporting

# Confidence-floor / vote-threshold grid: reuses the live stop/TP rather than
# crossing all three axes, since alpaca_execute.py always submits the
# take_profit_low leg as the actual order (take_profit_high is only shown in
# Telegram messaging, never placed) -- this isolates the entry-filter question
# from the exit-level question already covered by the grid above.
CONFIDENCE_GRID = [50.0, 60.0, 70.0, 80.0, 90.0]
MIN_VOTES_GRID = [2, 3, 4]
# Widened from 2.0%/3.0% to 2.5%/4.0% on September 26 2026 (Julius AI-approved --
# see CLAUDE.md Bracket Stop/Take-Profit Widened section). Must stay equal to
# trade_logic.py's STOP_LOSS_PCT/TAKE_PROFIT_PCT_LOW or every "current live
# setting" comparison this file prints silently goes stale.
LIVE_STOP_PCT = 2.5
LIVE_TP_PCT = 4.0
CONFIDENCE_VOTES_GRID_OUTPUT_FILE = os.path.expanduser("~/trading-system/logs/backtest_confidence_votes_grid.csv")

ABLATION_OUTPUT_FILE = os.path.expanduser("~/trading-system/logs/backtest_ablation.csv")
ABLATION_FIELDNAMES = ["version", "description", "trades", "resolved", "win_rate_pct",
                       "total_pnl_pct", "total_pnl_dollars", "profit_factor",
                       "max_drawdown_dollars", "max_drawdown_pct"]

def get_historical_data(ticker):
    df = yf.download(ticker, start="2023-01-01", end=datetime.today().strftime("%Y-%m-%d"), interval="1d", progress=False)
    df.columns = [col[0].lower() if isinstance(col, tuple) else col.lower() for col in df.columns]
    return df

def compute_indicators(df):
    df["rsi"] = ta.rsi(df["close"], length=14)
    macd = ta.macd(df["close"], fast=12, slow=26, signal=9)
    df = pd.concat([df, macd], axis=1)
    df["vol_ma20"] = df["volume"].rolling(20).mean()
    df["ma50"] = df["close"].rolling(50).mean()
    df["ma200"] = df["close"].rolling(200).mean()
    return df

def generate_signal(latest, prev, min_votes=MIN_VOTES):
    rsi = latest["rsi"]
    macd_line = latest["MACD_12_26_9"]
    macd_signal = latest["MACDs_12_26_9"]
    macd_hist = latest["MACDh_12_26_9"]
    macd_hist_prev = prev["MACDh_12_26_9"]
    volume = latest["volume"]
    vol_ma = latest["vol_ma20"]
    ma50 = latest["ma50"]
    ma200 = latest["ma200"]
    price = latest["close"]
    bull_votes = 0
    bear_votes = 0
    vote_log = []
    if price > ma50 and ma50 > ma200:
        bull_votes += 1
        bull_votes += 1
        vote_log.append("bullish structure")
    elif price < ma50 and ma50 < ma200:
        bear_votes += 1
        bear_votes += 1
        vote_log.append("bearish structure")
    else:
        vote_log.append("mixed structure")
    if 50 <= rsi <= 70:
        bull_votes += 1
        vote_log.append(f"RSI {round(rsi,1)}: bullish")
    elif rsi < 50:
        bear_votes += 1
        vote_log.append(f"RSI {round(rsi,1)}: bearish")
    else:
        vote_log.append(f"RSI {round(rsi,1)}: overbought")
    if macd_line > macd_signal:
        bull_votes += 1
        vote_log.append("MACD bullish")
    else:
        bear_votes += 1
        vote_log.append("MACD bearish")
    if macd_hist > 0 and macd_hist > macd_hist_prev:
        bull_votes += 1
        vote_log.append("MACD hist growing")
    elif macd_hist < 0 and macd_hist < macd_hist_prev:
        bear_votes += 1
        vote_log.append("MACD hist falling")
    if bull_votes >= min_votes and bull_votes > bear_votes:
        direction = "UP"
        votes = bull_votes
    elif bear_votes >= min_votes and bear_votes > bull_votes:
        direction = "DOWN"
        votes = bear_votes
    else:
        return "NEUTRAL", 0.0, vote_log
    base = 60 if votes == 3 else 40
    if direction == "UP":
        if 55 <= rsi <= 65: base += 20
        elif 50 <= rsi < 55 or 65 < rsi <= 70: base += 10
        elif rsi > 70: base -= 10
    elif direction == "DOWN":
        if 35 <= rsi <= 45: base += 20
        elif 30 <= rsi < 35 or 45 < rsi <= 50: base += 10
        elif rsi < 30: base -= 10
    if macd_hist > 0 and macd_hist > macd_hist_prev and direction == "UP": base += 10
    elif macd_hist < 0 and macd_hist < macd_hist_prev and direction == "DOWN": base += 10
    if volume > vol_ma * 1.2: base += 10
    elif volume < vol_ma * 0.8: base -= 10
    confidence = round(min(max(base, 0), 99.0), 2)
    return direction, confidence, vote_log

def generate_all_signals(df, min_votes):
    """Every directional (non-NEUTRAL) signal for a given min_votes threshold,
    at any confidence level -- confidence filtering happens downstream so this
    only needs to be recomputed per min_votes value, not per confidence value."""
    signals = []
    for i in range(1, len(df) - 1):
        latest = df.iloc[i]
        prev = df.iloc[i - 1]
        direction, confidence, _ = generate_signal(latest, prev, min_votes=min_votes)
        if direction != "NEUTRAL":
            signals.append((i, direction, confidence))
    return signals

def simulate_bracket_trades(df, signals, stop_pct, tp_pct):
    """Walk forward day-by-day from each signal, using daily high/low to check
    which leg (stop or take-profit) a GTC bracket would hit first -- mirrors
    alpaca_execute.py's actual order structure. If both legs are touched on
    the same day, conservatively assumes stop-loss triggers first (standard
    daily-bar backtest assumption, since intraday sequencing is unknown from
    daily OHLC). Trades that never resolve by the end of the dataset are
    marked OPEN and marked-to-market at the last available close."""
    trades = []
    n = len(df)
    for i, direction, confidence in signals:
        entry = float(df.iloc[i]["close"])
        entry_date = df.iloc[i]["date"]
        if direction == "UP":
            stop_price = entry * (1 - stop_pct / 100)
            tp_price = entry * (1 + tp_pct / 100)
        else:
            stop_price = entry * (1 + stop_pct / 100)
            tp_price = entry * (1 - tp_pct / 100)

        exit_reason = None
        exit_price = None
        holding_days = None
        for j in range(i + 1, n):
            day = df.iloc[j]
            high = float(day["high"])
            low = float(day["low"])
            if direction == "UP":
                hit_stop = low <= stop_price
                hit_tp = high >= tp_price
            else:
                hit_stop = high >= stop_price
                hit_tp = low <= tp_price
            if hit_stop:
                exit_reason = "STOP_LOSS"
                exit_price = stop_price
                holding_days = j - i
                break
            elif hit_tp:
                exit_reason = "TAKE_PROFIT"
                exit_price = tp_price
                holding_days = j - i
                break

        if exit_reason is None:
            exit_reason = "OPEN"
            exit_price = float(df.iloc[n - 1]["close"])
            holding_days = (n - 1) - i

        if direction == "UP":
            pnl_pct = (exit_price - entry) / entry * 100
        else:
            pnl_pct = (entry - exit_price) / entry * 100

        trades.append({
            "entry_date": str(entry_date.date()) if hasattr(entry_date, "date") else str(entry_date),
            "direction": direction,
            "entry": round(entry, 2),
            "exit_reason": exit_reason,
            "exit_price": round(exit_price, 2),
            "holding_days": holding_days,
            "pnl_pct": pnl_pct,
        })
    return trades

def run_bracket_grid(df, signals):
    grid_results = []
    for stop_pct in STOP_LOSS_GRID:
        for tp_pct in TAKE_PROFIT_GRID:
            trades = simulate_bracket_trades(df, signals, stop_pct, tp_pct)
            resolved = [t for t in trades if t["exit_reason"] != "OPEN"]
            wins = [t for t in resolved if t["exit_reason"] == "TAKE_PROFIT"]
            n_trades = len(trades)
            n_resolved = len(resolved)
            win_rate = round(len(wins) / n_resolved * 100, 1) if n_resolved else 0.0
            total_pnl_pct = sum(t["pnl_pct"] for t in trades)
            total_pnl_dollars = sum(t["pnl_pct"] / 100 * BRACKET_NOTIONAL for t in trades)
            avg_holding = round(sum(t["holding_days"] for t in trades) / n_trades, 1) if n_trades else 0.0
            grid_results.append({
                "stop_loss_pct": stop_pct,
                "take_profit_pct": tp_pct,
                "trades": n_trades,
                "resolved": n_resolved,
                "still_open": n_trades - n_resolved,
                "win_rate_pct": win_rate,
                "avg_holding_days": avg_holding,
                "total_pnl_pct": round(total_pnl_pct, 2),
                "total_pnl_dollars": round(total_pnl_dollars, 2),
            })
    return grid_results

def print_and_save_grid(grid_results):
    os.makedirs(os.path.dirname(BRACKET_GRID_OUTPUT_FILE), exist_ok=True)
    fieldnames = ["stop_loss_pct", "take_profit_pct", "trades", "resolved", "still_open",
                  "win_rate_pct", "avg_holding_days", "total_pnl_pct", "total_pnl_dollars"]
    with open(BRACKET_GRID_OUTPUT_FILE, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(grid_results)

    ranked = sorted(grid_results, key=lambda r: r["total_pnl_dollars"], reverse=True)

    print("\n--- BRACKET GRID RESULTS (GTC entry/stop/take-profit, sorted by total PnL $) ---")
    print(f"{'Stop%':>6} {'TP%':>5} {'Trades':>7} {'Open':>5} {'WinRate%':>9} {'AvgDays':>8} {'TotalPnL%':>10} {'TotalPnL$':>10}")
    for r in ranked:
        print(f"{r['stop_loss_pct']:>6.1f} {r['take_profit_pct']:>5.1f} {r['trades']:>7} "
              f"{r['still_open']:>5} {r['win_rate_pct']:>9.1f} {r['avg_holding_days']:>8.1f} "
              f"{r['total_pnl_pct']:>10.2f} {r['total_pnl_dollars']:>10.2f}")

    best = ranked[0]
    print(f"\nBest combo by total PnL: stop={best['stop_loss_pct']}% / TP={best['take_profit_pct']}% "
          f"-> {best['win_rate_pct']}% win rate, ${best['total_pnl_dollars']:.2f} total PnL "
          f"over {best['trades']} trades ({best['still_open']} still open at end of data)")

    # Uses LIVE_STOP_PCT/LIVE_TP_PCT (not hardcoded literals) so this stays correct
    # whenever trade_logic.py's bracket changes -- see LIVE_STOP_PCT's own comment.
    live_rows = [r for r in grid_results if r["stop_loss_pct"] == LIVE_STOP_PCT and r["take_profit_pct"] in (LIVE_TP_PCT, 5.0)]
    for live in sorted(live_rows, key=lambda r: r["take_profit_pct"]):
        rank = ranked.index(live) + 1
        print(f"\nCurrent live setting (stop={LIVE_STOP_PCT:g}%, TP={live['take_profit_pct']:.0f}%, the low/high end of "
              f"trade_logic.py's {LIVE_TP_PCT:.0f}-5% range): rank #{rank} of {len(ranked)} by total PnL "
              f"-> {live['win_rate_pct']}% win rate, ${live['total_pnl_dollars']:.2f} total PnL")

    print(f"\nFull grid saved to: {BRACKET_GRID_OUTPUT_FILE}")
    print("Note: assumes stop-loss triggers first when both legs are touched same day (conservative);")
    print("'still open' trades are marked-to-market at the last available close and included in total PnL,")
    print("but excluded from the win-rate denominator since they haven't actually resolved.")

def run_confidence_votes_grid(df):
    grid_results = []
    for min_votes in MIN_VOTES_GRID:
        all_signals = generate_all_signals(df, min_votes)
        for min_confidence in CONFIDENCE_GRID:
            filtered = [s for s in all_signals if s[2] >= min_confidence]
            trades = simulate_bracket_trades(df, filtered, LIVE_STOP_PCT, LIVE_TP_PCT)
            resolved = [t for t in trades if t["exit_reason"] != "OPEN"]
            wins = [t for t in resolved if t["exit_reason"] == "TAKE_PROFIT"]
            n_trades = len(trades)
            n_resolved = len(resolved)
            win_rate = round(len(wins) / n_resolved * 100, 1) if n_resolved else 0.0
            total_pnl_pct = sum(t["pnl_pct"] for t in trades)
            total_pnl_dollars = sum(t["pnl_pct"] / 100 * BRACKET_NOTIONAL for t in trades)
            avg_holding = round(sum(t["holding_days"] for t in trades) / n_trades, 1) if n_trades else 0.0
            grid_results.append({
                "min_votes": min_votes,
                "min_confidence_pct": min_confidence,
                "trades": n_trades,
                "resolved": n_resolved,
                "still_open": n_trades - n_resolved,
                "win_rate_pct": win_rate,
                "avg_holding_days": avg_holding,
                "total_pnl_pct": round(total_pnl_pct, 2),
                "total_pnl_dollars": round(total_pnl_dollars, 2),
            })
    return grid_results

def print_and_save_confidence_votes_grid(grid_results):
    os.makedirs(os.path.dirname(CONFIDENCE_VOTES_GRID_OUTPUT_FILE), exist_ok=True)
    fieldnames = ["min_votes", "min_confidence_pct", "trades", "resolved", "still_open",
                  "win_rate_pct", "avg_holding_days", "total_pnl_pct", "total_pnl_dollars"]
    with open(CONFIDENCE_VOTES_GRID_OUTPUT_FILE, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(grid_results)

    ranked = sorted(grid_results, key=lambda r: r["total_pnl_dollars"], reverse=True)

    print(f"\n--- CONFIDENCE FLOOR / VOTE THRESHOLD GRID (stop={LIVE_STOP_PCT}%, TP={LIVE_TP_PCT}%, sorted by total PnL $) ---")
    print(f"{'MinVotes':>8} {'MinConf%':>8} {'Trades':>7} {'Open':>5} {'WinRate%':>9} {'AvgDays':>8} {'TotalPnL%':>10} {'TotalPnL$':>10}")
    for r in ranked:
        print(f"{r['min_votes']:>8} {r['min_confidence_pct']:>8.1f} {r['trades']:>7} "
              f"{r['still_open']:>5} {r['win_rate_pct']:>9.1f} {r['avg_holding_days']:>8.1f} "
              f"{r['total_pnl_pct']:>10.2f} {r['total_pnl_dollars']:>10.2f}")

    best = ranked[0]
    print(f"\nBest combo by total PnL: min_votes={best['min_votes']} / min_confidence={best['min_confidence_pct']}% "
          f"-> {best['win_rate_pct']}% win rate, ${best['total_pnl_dollars']:.2f} total PnL "
          f"over {best['trades']} trades ({best['still_open']} still open at end of data)")

    live_rows = [r for r in grid_results if r["min_votes"] == MIN_VOTES and r["min_confidence_pct"] == MIN_CONFIDENCE]
    if live_rows:
        live = live_rows[0]
        rank = ranked.index(live) + 1
        print(f"\nCurrent live setting (min_votes={MIN_VOTES}, min_confidence={MIN_CONFIDENCE}%): "
              f"rank #{rank} of {len(ranked)} by total PnL "
              f"-> {live['win_rate_pct']}% win rate, ${live['total_pnl_dollars']:.2f} total PnL, "
              f"{live['trades']} trades")

    print(f"\nFull grid saved to: {CONFIDENCE_VOTES_GRID_OUTPUT_FILE}")
    print(f"Note: entry filters only (stop/TP fixed at the live {LIVE_STOP_PCT:g}%/{LIVE_TP_PCT:g}% bracket) -- isolates whether raising the")
    print("confidence floor or requiring more indicator agreement would have improved historical results,")
    print("independent of the exit-level question already covered by the stop/TP grid above.")

def compute_trade_metrics(trades):
    """Win rate, PnL, profit factor, and max drawdown for a list of trades from
    simulate_bracket_trades(). Equity curve is built by walking trades in
    chronological entry order and accumulating pnl_dollars -- a reasonable
    stand-in for a real account curve since the live system holds at most one
    position at a time (no-stacking), not a rough approximation. Drawdown %
    is expressed against BRACKET_NOTIONAL (the same $1,000 per-trade notional
    convention used throughout this file), not a modeled running balance."""
    resolved = [t for t in trades if t["exit_reason"] != "OPEN"]
    wins = [t for t in resolved if t["exit_reason"] == "TAKE_PROFIT"]
    n_trades = len(trades)
    n_resolved = len(resolved)
    win_rate = round(len(wins) / n_resolved * 100, 1) if n_resolved else 0.0

    pnl_dollars_by_trade = [(t, t["pnl_pct"] / 100 * BRACKET_NOTIONAL) for t in trades]
    total_pnl_pct = sum(t["pnl_pct"] for t in trades)
    total_pnl_dollars = sum(pnl for _, pnl in pnl_dollars_by_trade)

    gross_profit = sum(pnl for _, pnl in pnl_dollars_by_trade if pnl > 0)
    gross_loss = abs(sum(pnl for _, pnl in pnl_dollars_by_trade if pnl < 0))
    if gross_loss > 0:
        profit_factor = round(gross_profit / gross_loss, 2)
    else:
        profit_factor = float("inf") if gross_profit > 0 else 0.0

    ordered = sorted(pnl_dollars_by_trade, key=lambda tp: tp[0]["entry_date"])
    equity = 0.0
    peak = 0.0
    max_dd_dollars = 0.0
    for _, pnl in ordered:
        equity += pnl
        peak = max(peak, equity)
        max_dd_dollars = max(max_dd_dollars, peak - equity)
    max_dd_pct = round(max_dd_dollars / BRACKET_NOTIONAL * 100, 2) if BRACKET_NOTIONAL else 0.0

    return {
        "trades": n_trades,
        "resolved": n_resolved,
        "win_rate_pct": win_rate,
        "total_pnl_pct": round(total_pnl_pct, 2),
        "total_pnl_dollars": round(total_pnl_dollars, 2),
        "profit_factor": profit_factor,
        "max_drawdown_dollars": round(max_dd_dollars, 2),
        "max_drawdown_pct": max_dd_pct,
    }

def compute_buy_and_hold_metrics(df):
    """Passive buy-and-hold benchmark over the full dataset window. Unlike the
    trade-based versions, this has only one continuous position, so profit
    factor and max drawdown are computed from the daily-return equity curve
    instead of per-trade PnL -- the two methodologies aren't directly
    comparable line-for-line, only the headline win-rate/PnL numbers are."""
    start_close = float(df.iloc[0]["close"])
    end_close = float(df.iloc[-1]["close"])
    total_pnl_pct = (end_close - start_close) / start_close * 100
    total_pnl_dollars = total_pnl_pct / 100 * BRACKET_NOTIONAL
    win_rate = 100.0 if total_pnl_pct > 0 else 0.0

    daily_returns_pct = df["close"].astype(float).pct_change().dropna() * 100
    gross_profit = daily_returns_pct[daily_returns_pct > 0].sum() / 100 * BRACKET_NOTIONAL
    gross_loss = abs(daily_returns_pct[daily_returns_pct < 0].sum()) / 100 * BRACKET_NOTIONAL
    if gross_loss > 0:
        profit_factor = round(gross_profit / gross_loss, 2)
    else:
        profit_factor = float("inf") if gross_profit > 0 else 0.0

    equity_curve = (1 + daily_returns_pct / 100).cumprod() * BRACKET_NOTIONAL
    peak = equity_curve.cummax()
    drawdown_dollars = peak - equity_curve
    drawdown_pct = drawdown_dollars / peak * 100
    max_dd_dollars = float(drawdown_dollars.max()) if len(drawdown_dollars) else 0.0
    max_dd_pct = float(drawdown_pct.max()) if len(drawdown_pct) else 0.0

    return {
        "trades": 1,
        "resolved": 1,
        "win_rate_pct": round(win_rate, 1),
        "total_pnl_pct": round(total_pnl_pct, 2),
        "total_pnl_dollars": round(total_pnl_dollars, 2),
        "profit_factor": profit_factor,
        "max_drawdown_dollars": round(max_dd_dollars, 2),
        "max_drawdown_pct": round(max_dd_pct, 2),
    }

def run_ablation_study(df):
    all_signals = generate_all_signals(df, MIN_VOTES)
    v1_signals = all_signals
    v2_signals = [s for s in all_signals if s[2] >= MIN_CONFIDENCE]
    # v3 "full system as configured" = signal_logger.py's MIN_VOTES/MIN_CONFIDENCE
    # gate + trade_logic.py's own 51% confidence floor. Under current wiring these
    # produce identical entries to v2: trade_logic.py never sees anything below
    # signal_logger.py's stricter 70% gate, so its 51% floor can never bind.
    # (A 50%/50% experiment was tried and reverted after Julius AI review found the
    # risk-adjusted profile worse despite higher total PnL -- see CLAUDE.md.)
    v3_signals = v2_signals

    v1_metrics = compute_trade_metrics(simulate_bracket_trades(df, v1_signals, LIVE_STOP_PCT, LIVE_TP_PCT))
    v2_metrics = compute_trade_metrics(simulate_bracket_trades(df, v2_signals, LIVE_STOP_PCT, LIVE_TP_PCT))
    v3_metrics = compute_trade_metrics(simulate_bracket_trades(df, v3_signals, LIVE_STOP_PCT, LIVE_TP_PCT))
    v4_metrics = compute_buy_and_hold_metrics(df)

    rows = []
    for version, description, metrics in [
        ("v1_technical_only", "Technical signal only, no confidence filter", v1_metrics),
        (f"v2_confidence_{MIN_CONFIDENCE:.0f}", f"Technical signal + {MIN_CONFIDENCE:.0f}% confidence floor", v2_metrics),
        ("v3_full_system", "Full system as currently configured (identical entries to v2 -- "
                            "trade_logic.py's 51% floor never binds beneath signal_logger.py's "
                            "70% gate)", v3_metrics),
        ("v4_buy_and_hold", "Buy-and-hold SPY benchmark (daily-return based, not trade-based)", v4_metrics),
    ]:
        row = {"version": version, "description": description}
        row.update(metrics)
        rows.append(row)
    return rows

def print_and_save_ablation(rows):
    os.makedirs(os.path.dirname(ABLATION_OUTPUT_FILE), exist_ok=True)
    with open(ABLATION_OUTPUT_FILE, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=ABLATION_FIELDNAMES)
        writer.writeheader()
        for r in rows:
            r = dict(r)
            if r["profit_factor"] == float("inf"):
                r["profit_factor"] = "inf"
            writer.writerow(r)

    print(f"\n--- ABLATION STUDY (stop={LIVE_STOP_PCT}%/TP={LIVE_TP_PCT}% bracket except buy-and-hold) ---")
    print(f"{'Version':<20} {'Trades':>7} {'WinRate%':>9} {'TotalPnL%':>10} {'TotalPnL$':>10} "
          f"{'ProfitFactor':>13} {'MaxDD$':>8} {'MaxDD%':>8}")
    for r in rows:
        pf_str = "inf" if r["profit_factor"] == float("inf") else f"{r['profit_factor']:.2f}"
        print(f"{r['version']:<20} {r['trades']:>7} {r['win_rate_pct']:>9.1f} {r['total_pnl_pct']:>10.2f} "
              f"{r['total_pnl_dollars']:>10.2f} {pf_str:>13} {r['max_drawdown_dollars']:>8.2f} "
              f"{r['max_drawdown_pct']:>8.2f}")

    print()
    for r in rows:
        print(f"{r['version']}: {r['description']}")

    print(f"\nFull ablation saved to: {ABLATION_OUTPUT_FILE}")
    print("Note: v3 uses identical entries/exits to v2 under current wiring, not a bug -- see description above.")
    print("v4 (buy-and-hold) computes profit factor and max drawdown from daily returns over the whole")
    print("dataset window, not from discrete trades, since it holds one continuous position throughout;")
    print("only its win-rate/total-PnL figures are directly comparable to v1-v3.")
    print("Max drawdown for v1-v3 is built from a chronological-entry-order equity curve (one position")
    print("at a time, matching live no-stacking behavior) expressed against the $1,000 per-trade notional.")

def run():
    print("Downloading SPY data from 2023-01-01...")
    df = get_historical_data(TICKER)
    df = compute_indicators(df)
    df = df.dropna()
    df["date"] = df.index
    df = df.reset_index(drop=True)
    os.makedirs(os.path.dirname(OUTPUT_FILE), exist_ok=True)
    results = []
    signals = []
    total = 0
    correct = 0
    signals_fired = 0
    for i in range(1, len(df) - 1):
        latest = df.iloc[i]
        prev = df.iloc[i - 1]
        next_day = df.iloc[i + 1]
        direction, confidence, vote_log = generate_signal(latest, prev)
        if direction == "NEUTRAL" or confidence < MIN_CONFIDENCE:
            outcome = "NO_SIGNAL"
        else:
            signals_fired += 1
            total += 1
            signals.append((i, direction, confidence))
            next_return = float(next_day["close"]) - float(latest["close"])
            if direction == "UP" and next_return > 0:
                outcome = "CORRECT"
                correct += 1
            elif direction == "DOWN" and next_return < 0:
                outcome = "CORRECT"
                correct += 1
            else:
                outcome = "WRONG"
        results.append({
            "date": str(latest["date"].date()) if hasattr(latest["date"], "date") else str(latest["date"]),
            "direction": direction,
            "confidence": confidence,
            "close": round(float(latest["close"]), 2),
            "next_day_change": round(float(next_day["close"]) - float(latest["close"]), 2) if direction != "NEUTRAL" else 0,
            "outcome": outcome,
            "votes": " | ".join(vote_log)
        })
    with open(OUTPUT_FILE, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=["date","direction","confidence","close","next_day_change","outcome","votes"])
        writer.writeheader()
        writer.writerows(results)
    print(f"\n--- BACKTEST RESULTS ---")
    print(f"Total trading days analyzed: {len(df)}")
    print(f"Signals fired: {signals_fired}")
    print(f"Correct: {correct}")
    print(f"Wrong: {total - correct}")
    accuracy = round((correct / total) * 100, 1) if total > 0 else 0
    print(f"Accuracy: {accuracy}%")
    print(f"Results saved to: {OUTPUT_FILE}")
    if accuracy >= 55:
        print("EDGE DETECTED. Continue to paper trading.")
    else:
        print("NO EDGE. Revise signals before paper trading.")

    print(f"\nSimulating GTC bracket outcomes for {len(signals)} fired signals across "
          f"{len(STOP_LOSS_GRID)}x{len(TAKE_PROFIT_GRID)} stop/take-profit combinations...")
    grid_results = run_bracket_grid(df, signals)
    print_and_save_grid(grid_results)

    print(f"\nSimulating confidence-floor x vote-threshold grid "
          f"({len(MIN_VOTES_GRID)}x{len(CONFIDENCE_GRID)} combinations) across full history...")
    confidence_votes_grid_results = run_confidence_votes_grid(df)
    print_and_save_confidence_votes_grid(confidence_votes_grid_results)

    print(f"\nRunning ablation study (technical-only, {MIN_CONFIDENCE:.0f}% floor, full system, buy-and-hold)...")
    ablation_rows = run_ablation_study(df)
    print_and_save_ablation(ablation_rows)

if __name__ == "__main__":
    run()
