import os
import csv
import math
from datetime import datetime

# Market regime classifier (October 13). TRENDING when MA50 > MA200 AND the
# 20-day volatility of daily returns is below VOL_THRESHOLD_PCT, otherwise
# CHOPPY. OBSERVE-ONLY for now: signal_logger.py calls classify() and this
# script logs the result to logs/regime_log.csv and the Telegram daily summary,
# but nothing reads it to block a trade. The planned skip belongs in
# trade_logic.py (analysts and Critic still see every signal, the regime only
# blocks execution) with a BLOCKED_REGIME code in decision_ledger.py, and is
# not built until the backtest_regime.py results are reviewed.
#
# The same helpers feed scripts/backtest_regime.py, so the backtest and the
# live classification can't compute volatility differently.

REGIME_LOG = os.path.expanduser("~/kronos-trading-system/logs/regime_log.csv")

VOL_WINDOW = 20
# Placeholder: median 20-day vol since 2023 (0.77% per day). Final value to be
# picked from the backtest_regime.py threshold sweep, not the 7 live trades.
VOL_THRESHOLD_PCT = 0.77

COLUMNS = [
    "timestamp", "ticker", "regime", "last_close", "ma50", "ma200", "ma50_above_ma200",
    "vol20_pct", "vol_threshold_pct", "efficiency_ratio_20", "reason",
]


def vol20_series(close):
    """Rolling standard deviation of daily close-to-close returns, in daily %.
    Each value uses only closes up to and including that day."""
    return close.pct_change().rolling(VOL_WINDOW).std() * 100


def efficiency_ratio_series(close):
    """Net 20-day move divided by the total distance travelled over those 20
    days. Near 1 = straight-line trend, near 0 = back-and-forth chop. Logged and
    backtested for comparison only, it does not affect the classification."""
    net = (close - close.shift(VOL_WINDOW)).abs()
    path = close.diff().abs().rolling(VOL_WINDOW).sum()
    return net / path


def classify_values(ma50, ma200, vol20, threshold=VOL_THRESHOLD_PCT):
    """Returns (regime, reason). UNKNOWN if any input is missing or NaN."""
    values = (ma50, ma200, vol20)
    if any(v is None or (isinstance(v, float) and math.isnan(v)) for v in values):
        return "UNKNOWN", "missing MA50/MA200/vol20 input"
    trend_up = ma50 > ma200
    calm = vol20 < threshold
    if trend_up and calm:
        return "TRENDING", f"MA50 above MA200, vol {vol20:.2f}% < {threshold:.2f}%"
    reasons = []
    if not trend_up:
        reasons.append("MA50 below MA200")
    if not calm:
        reasons.append(f"vol {vol20:.2f}% >= {threshold:.2f}%")
    return "CHOPPY", ", ".join(reasons)


def classify(df, ticker="SPY", threshold=VOL_THRESHOLD_PCT):
    """Classify the latest bar of a dataframe that already has close/ma50/ma200
    columns (signal_logger.compute_indicators() output). Returns a row dict."""
    close = df["close"].astype(float)
    latest = df.iloc[-1]
    vol20 = float(vol20_series(close).iloc[-1])
    er = float(efficiency_ratio_series(close).iloc[-1])
    ma50, ma200 = float(latest["ma50"]), float(latest["ma200"])
    regime, reason = classify_values(ma50, ma200, vol20, threshold)

    def r(v, places):
        return "" if math.isnan(v) else round(v, places)

    return {
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "ticker": ticker,
        "regime": regime,
        "last_close": r(float(latest["close"]), 2),
        "ma50": r(ma50, 2),
        "ma200": r(ma200, 2),
        "ma50_above_ma200": "" if regime == "UNKNOWN" else ("yes" if ma50 > ma200 else "no"),
        "vol20_pct": r(vol20, 3),
        "vol_threshold_pct": threshold,
        "efficiency_ratio_20": r(er, 3),
        "reason": reason,
    }


def log_regime(row):
    """Append-only. Refuses to write on a header mismatch rather than
    misaligning columns (the July 9 decisions_log.csv bug)."""
    os.makedirs(os.path.dirname(REGIME_LOG), exist_ok=True)
    needs_header = not os.path.isfile(REGIME_LOG) or os.path.getsize(REGIME_LOG) == 0
    if not needs_header:
        with open(REGIME_LOG, "r", newline="") as f:
            existing = next(csv.reader(f), [])
        if existing != COLUMNS:
            print("  ERROR: regime_log.csv header does not match current COLUMNS. Row NOT written.")
            return False
    with open(REGIME_LOG, "a", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=COLUMNS)
        if needs_header:
            writer.writeheader()
        writer.writerow(row)
    return True


def get_today_regime(ticker="SPY"):
    """Latest regime_log.csv row for ticker if it is from today, else None."""
    if not os.path.isfile(REGIME_LOG):
        return None
    today = datetime.now().strftime("%Y-%m-%d")
    with open(REGIME_LOG, "r", newline="") as f:
        rows = [r for r in csv.DictReader(f) if r.get("ticker") == ticker]
    if rows and rows[-1]["timestamp"].startswith(today):
        return rows[-1]
    return None


def format_regime_line(row):
    """One line for the Telegram daily summary."""
    if not row:
        return "Regime:      unavailable (no regime_log.csv row for today)"
    return f"Regime:      {row['regime']} ({row['reason']}) [observe-only]"


def run():
    """Manual check: compute and log today's SPY regime from fresh data."""
    from signal_logger import get_market_data, compute_indicators, TICKER, LOOKBACK
    df = compute_indicators(get_market_data(TICKER, LOOKBACK))
    row = classify(df, TICKER)
    print(f"{TICKER} regime: {row['regime']} ({row['reason']}) | ER20 {row['efficiency_ratio_20']}")
    if log_regime(row):
        print("Appended to: " + REGIME_LOG)


if __name__ == "__main__":
    run()
