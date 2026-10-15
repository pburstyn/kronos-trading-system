import os
import sys
import csv

import pandas as pd

# Regime filter backtest (October 13). Answers: would skipping CHOPPY-regime
# entries have helped, at what volatility threshold, and which of the real
# Alpaca losses would it have avoided? Read-only, changes no live setting.
#
# Reuses backtest.py's data, signal and bracket simulation (same pattern as
# backtest_qqq.py) and regime_filter.py's own volatility/efficiency helpers, so
# the backtest can't compute the regime differently from the live classifier.
# Every regime input is a trailing rolling value at the signal day's close, the
# same information the 6pm pipeline has. Thresholds are absolute values, not
# percentiles of the full sample, so the sweep itself uses no future data.
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import backtest as bt
import regime_filter as rf

LOGS_DIR = os.path.expanduser("~/kronos-trading-system/logs")
OUTPUT_FILE = os.path.join(LOGS_DIR, "backtest_regime.csv")
TRADE_LEDGER = os.path.join(LOGS_DIR, "trade_ledger.csv")
ALPACA_ORDERS = os.path.join(LOGS_DIR, "alpaca_orders.csv")

VOL_THRESHOLDS = [0.55, 0.65, rf.VOL_THRESHOLD_PCT, 0.85, 0.95, 1.05, 1.15, 1.25]
ER_THRESHOLDS = [0.10, 0.15, 0.20, 0.25, 0.30, 0.35]

FIELDNAMES = [
    "signals", "variant", "threshold", "signal_days_trending_pct",
    "kept_trades", "win_rate_pct", "total_pnl_dollars", "profit_factor", "max_drawdown_dollars",
    "skipped_trades", "skipped_pnl_dollars", "skipped_wins", "skipped_losses",
    "skipped_short_trades", "skipped_short_pnl_dollars",
]


def load_data():
    df = bt.get_historical_data(bt.TICKER)
    df = bt.compute_indicators(df)
    df["vol20"] = rf.vol20_series(df["close"])
    df["er20"] = rf.efficiency_ratio_series(df["close"])
    df = df.dropna()
    df["date"] = df.index
    return df.reset_index(drop=True)


def live_signals(df):
    """Same MIN_VOTES/MIN_CONFIDENCE gate as backtest.py's run() and the live
    signal_logger.py."""
    signals = []
    for i in range(1, len(df) - 1):
        direction, confidence, _ = bt.generate_signal(df.iloc[i], df.iloc[i - 1])
        if direction != "NEUTRAL" and confidence >= bt.MIN_CONFIDENCE:
            signals.append((i, direction, confidence))
    return signals


def dollars(trade):
    return trade["pnl_pct"] / 100 * bt.BRACKET_NOTIONAL


def evaluate(variant, threshold, pairs, is_trending, signals="ALL"):
    """pairs = [(signal_row, trade)]. is_trending(row) -> bool."""
    return evaluate_trades(variant, threshold, pairs, lambda row, t: is_trending(row), signals)


def evaluate_trades(variant, threshold, pairs, keep, signals="ALL"):
    """Like evaluate(), but keep(row, trade) can also look at the trade's direction."""
    kept = [t for row, t in pairs if keep(row, t)]
    skipped = [t for row, t in pairs if not keep(row, t)]
    m = bt.compute_trade_metrics(kept)
    shorts = [t for t in skipped if t["direction"] == "DOWN"]
    return {
        "signals": signals,
        "variant": variant,
        "threshold": threshold,
        "signal_days_trending_pct": round(len(kept) / len(pairs) * 100, 1) if pairs else 0.0,
        "kept_trades": m["trades"],
        "win_rate_pct": m["win_rate_pct"],
        "total_pnl_dollars": m["total_pnl_dollars"],
        "profit_factor": m["profit_factor"],
        "max_drawdown_dollars": m["max_drawdown_dollars"],
        "skipped_trades": len(skipped),
        "skipped_pnl_dollars": round(sum(dollars(t) for t in skipped), 2),
        "skipped_wins": sum(1 for t in skipped if t["exit_reason"] == "TAKE_PROFIT"),
        "skipped_losses": sum(1 for t in skipped if t["exit_reason"] == "STOP_LOSS"),
        "skipped_short_trades": len(shorts),
        "skipped_short_pnl_dollars": round(sum(dollars(t) for t in shorts), 2),
    }


def run_sweeps(pairs, signals="ALL"):
    rows = [evaluate("baseline_no_filter", "", pairs, lambda r: True, signals),
            evaluate("ma_only", "MA50>MA200", pairs, lambda r: r["ma50"] > r["ma200"], signals)]
    for th in VOL_THRESHOLDS:
        rows.append(evaluate("spec_ma_and_vol", th, pairs,
                             lambda r, th=th: rf.classify_values(r["ma50"], r["ma200"], r["vol20"], th)[0] == "TRENDING",
                             signals))
    for th in ER_THRESHOLDS:
        rows.append(evaluate("ma_and_efficiency_ratio", th, pairs,
                             lambda r, th=th: r["ma50"] > r["ma200"] and r["er20"] >= th, signals))
    return rows


def direction_variants(pairs):
    """Direction rules (October 13, follow-on to the regime sweep). Longs are
    always kept. long_only drops every short. shorts_only_in_bear_trend keeps a
    short only when MA50 < MA200 on the signal day."""
    return [
        evaluate_trades("baseline_no_filter", "", pairs, lambda r, t: True, "DIRECTION"),
        evaluate_trades("long_only", "", pairs, lambda r, t: t["direction"] == "UP", "DIRECTION"),
        evaluate_trades("shorts_only_in_bear_trend", "MA50<MA200", pairs,
                        lambda r, t: t["direction"] == "UP" or r["ma50"] < r["ma200"], "DIRECTION"),
    ]


def run_all_sweeps(pairs):
    """Combined, then longs and shorts separately. Shorts lose in every regime
    over 2023-2026, so on the combined set any filter that drops shorts looks
    good. The per-direction rows show whether the regime itself adds anything."""
    rows = run_sweeps(pairs, "ALL")
    for d in ("UP", "DOWN"):
        rows += run_sweeps([p for p in pairs if p[1]["direction"] == d], d)
    return rows + direction_variants(pairs)


def direction_split(pairs):
    out = {}
    for d in ("UP", "DOWN"):
        trades = [t for _, t in pairs if t["direction"] == d]
        out[d] = bt.compute_trade_metrics(trades)
    return out


def real_trades(df):
    """Real Alpaca round trips from trade_ledger.csv, each matched to its signal
    day via the entry order ID in alpaca_orders.csv, with that day's regime inputs."""
    if not (os.path.isfile(TRADE_LEDGER) and os.path.isfile(ALPACA_ORDERS)):
        return []
    with open(ALPACA_ORDERS, newline="") as f:
        order_day = {r["order_id"]: r["timestamp"][:10] for r in csv.DictReader(f)}
    dates = df["date"].dt.strftime("%Y-%m-%d")
    out = []
    with open(TRADE_LEDGER, newline="") as f:
        for t in csv.DictReader(f):
            day = order_day.get(t["entry_order_id"])
            idx = dates[dates <= day].index if day else []
            if not len(idx):
                continue
            row = df.loc[idx[-1]]
            out.append({"trade": t["trade_num"], "signal_day": day, "direction": t["direction"],
                        "pnl": t["pnl_dollars"], "exit": t["exit_reason"] or "OPEN", "row": row})
    return out


def print_report(rows, split, reals, n_signals):
    for label in ("ALL", "UP", "DOWN", "DIRECTION"):
        print_table([r for r in rows if r["signals"] == label], label, n_signals)
    print("  SkipPnL$ = what the skipped trades made. Negative = the filter avoided net losses.")
    print_rest(split, reals)


def print_table(rows, label, n_signals):
    print(f"\n--- REGIME FILTER BACKTEST, {label} SIGNALS ({n_signals} total, live bracket "
          f"{bt.LIVE_STOP_PCT}%/{bt.LIVE_TP_PCT}%, ${bt.BRACKET_NOTIONAL} notional) ---")
    print(f"{'Variant':24} {'Thresh':>10} {'Trend%':>7} {'Kept':>5} {'Win%':>5} {'PnL$':>9} {'PF':>5} "
          f"{'MaxDD$':>8} {'Skip':>5} {'SkipPnL$':>9} {'SkW/L':>6} {'SkShort':>7}")
    for r in rows:
        print(f"{r['variant']:24} {str(r['threshold']):>10} {r['signal_days_trending_pct']:>7} "
              f"{r['kept_trades']:>5} {r['win_rate_pct']:>5} {r['total_pnl_dollars']:>9.2f} "
              f"{r['profit_factor']:>5} {r['max_drawdown_dollars']:>8.2f} {r['skipped_trades']:>5} "
              f"{r['skipped_pnl_dollars']:>9.2f} {r['skipped_wins']:>3}/{r['skipped_losses']:<2} "
              f"{r['skipped_short_trades']:>7}")


def print_rest(split, reals):
    print("\n--- BASELINE BY DIRECTION ---")
    for d, m in split.items():
        print(f"  {d:4} trades {m['trades']:>4}  win {m['win_rate_pct']:>5}%  PnL ${m['total_pnl_dollars']:>9.2f}  PF {m['profit_factor']}")

    if reals:
        print("\n--- REAL ALPACA TRADES: REGIME ON THE SIGNAL DAY ---")
        print(f"{'#':>2} {'Signal day':11} {'Dir':5} {'Exit':12} {'PnL$':>7} {'MA50>200':>8} {'Vol20%':>6} {'ER20':>5}  "
              + " ".join(f"{th:>5}" for th in VOL_THRESHOLDS))
        for t in reals:
            r = t["row"]
            regimes = []
            for th in VOL_THRESHOLDS:
                regime = rf.classify_values(r["ma50"], r["ma200"], r["vol20"], th)[0]
                regimes.append("TREND" if regime == "TRENDING" else "CHOP")
            print(f"{t['trade']:>2} {t['signal_day']:11} {t['direction']:5} {t['exit']:12} {t['pnl'] or '-':>7} "
                  f"{str(bool(r['ma50'] > r['ma200'])):>8} {r['vol20']:>6.2f} {r['er20']:>5.2f}  "
                  + " ".join(f"{x:>5}" for x in regimes))
        print("  Columns on the right = regime under the spec rule at each vol threshold. CHOP = entry skipped.")


def run():
    print(f"Downloading {bt.TICKER} data from 2023-01-01...")
    df = load_data()
    signals = live_signals(df)
    trades = bt.simulate_bracket_trades(df, signals, bt.LIVE_STOP_PCT, bt.LIVE_TP_PCT)
    pairs = [(df.iloc[i], t) for (i, _, _), t in zip(signals, trades)]

    rows = run_all_sweeps(pairs)
    os.makedirs(LOGS_DIR, exist_ok=True)
    with open(OUTPUT_FILE, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDNAMES)
        writer.writeheader()
        writer.writerows(rows)

    print_report(rows, direction_split(pairs), real_trades(df), len(signals))
    print(f"\nSaved to: {OUTPUT_FILE}")


if __name__ == "__main__":
    run()
