import os
import csv
import math
import sys
from datetime import datetime, timedelta

import yfinance as yf

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from signal_logger import MIN_CONFIDENCE
from trade_logic import STOP_LOSS_PCT, TAKE_PROFIT_PCT_LOW

# Shadow bracket tracker (Julius AI recommendation, October 12). For every SPY
# signal that passes the confidence floor, whether or not a real order was
# placed, tracks two hypothetical GTC brackets in parallel on the same price
# path: the old 2%/3% bracket and the current 2.5%/4% bracket. Runs after
# decision_ledger.py in run_pipeline.sh. Read-only: no orders, no Alpaca calls.
#
# Simulation rules (match backtest.simulate_bracket_trades() where possible):
#   - Entry at the next session's open after the signal date, which is when
#     alpaca_execute.py's market order actually fills. Not the stale last_close.
#   - Each completed daily bar from the entry day on is checked against both legs.
#     If one bar touches both legs, stop-loss is assumed first (daily bars can't
#     show intraday order, same conservative rule as backtest.py).
#   - A gap open past a leg exits at the open, not the leg price.
#   - No time limit, like the live GTC bracket. Unresolved trades stay OPEN and
#     are marked to the last close.
#   - PnL is per share (live sizing resolves to 1 share at current SPY prices).
#
# logs/shadow_brackets.csv is derived state, rebuilt in full from signal_log.csv
# and daily bars on every run (written via a temp file + os.replace), so a row
# moves OPEN -> STOP_LOSS / TAKE_PROFIT as the price path resolves.

REPO_DIR = os.path.expanduser("~/trading-system")
LOGS_DIR = os.path.join(REPO_DIR, "logs")
SIGNAL_LOG = os.path.join(LOGS_DIR, "signal_log.csv")
LEDGER = os.path.join(LOGS_DIR, "decision_ledger.csv")
OUTPUT = os.path.join(LOGS_DIR, "shadow_brackets.csv")

TICKER = "SPY"
# First signal date tracked: the day the live bracket moved 2%/3% -> 2.5%/4%.
SHADOW_START_DATE = "2026-09-26"
# Daily bars are only trusted once the session has closed (1pm PT) plus a buffer.
BAR_COMPLETE_HOUR = 14

# Fixed experiment arms, hardcoded on purpose. If trade_logic.py's live bracket
# changes again, these rows must not silently shift with it (see the warning in
# run()). (name, stop_pct, take_profit_pct)
BRACKETS = [
    ("OLD_2.0_3.0", 0.020, 0.030),
    ("CURRENT_2.5_4.0", 0.025, 0.040),
]

COLUMNS = [
    "signal_timestamp", "signal_date", "direction", "confidence_pct", "signal_close",
    "real_trade_action", "raw_signal_action",
    "bracket", "stop_pct", "take_profit_pct",
    "entry_date", "entry_price", "stop_price", "take_profit_price",
    "status", "exit_date", "exit_price", "holding_days",
    "pnl_per_share", "pnl_pct", "mark_price", "updated_at",
]


def read_rows(path):
    if not os.path.isfile(path):
        return []
    with open(path, "r", newline="") as f:
        return list(csv.DictReader(f))


def eligible_signals():
    """Last signal of each date since SHADOW_START_DATE (the 6pm pipeline run,
    or a later manual rerun), kept only if it is UP/DOWN at or above the floor."""
    by_date = {}
    for row in read_rows(SIGNAL_LOG):
        date = row.get("timestamp", "")[:10]
        if date >= SHADOW_START_DATE:
            by_date[date] = row
    signals = []
    for date in sorted(by_date):
        row = by_date[date]
        try:
            confidence = float(row["confidence_pct"])
        except (KeyError, ValueError):
            continue
        if row.get("direction") in ("UP", "DOWN") and confidence >= MIN_CONFIDENCE:
            signals.append(row)
    return signals


def raw_signal_action(sig):
    """What the technical signal alone would do, ignoring the analysts and the
    Critic: ENTER if the direction is UP/DOWN and confidence meets the floor,
    otherwise SKIP. Compare against real_trade_action (the full council path)."""
    try:
        confidence = float(sig.get("confidence_pct", ""))
    except ValueError:
        return "SKIP"
    if sig.get("direction") in ("UP", "DOWN") and confidence >= MIN_CONFIDENCE:
        return "ENTER"
    return "SKIP"


def ledger_actions():
    """signal_timestamp -> trade_action, last row wins."""
    return {r["signal_timestamp"]: r.get("trade_action", "") for r in read_rows(LEDGER)}


def get_daily_bars(start_date):
    """Completed raw (unadjusted) daily bars from start_date on, as a list of
    dicts. Unadjusted so dividend adjustments can't rewrite old entry prices."""
    start = (datetime.strptime(start_date, "%Y-%m-%d") - timedelta(days=5)).strftime("%Y-%m-%d")
    df = yf.download(TICKER, start=start, interval="1d", auto_adjust=False, progress=False)
    df.columns = [col[0].lower() if isinstance(col, tuple) else col.lower() for col in df.columns]
    now = datetime.now()
    today = now.strftime("%Y-%m-%d")
    bars = []
    for idx, r in df.iterrows():
        date = idx.strftime("%Y-%m-%d")
        if date > today or (date == today and now.hour < BAR_COMPLETE_HOUR):
            continue
        bar = {"date": date, "open": float(r["open"]), "high": float(r["high"]),
               "low": float(r["low"]), "close": float(r["close"])}
        # yfinance can return the current day's bar with a NaN field (seen
        # October 12: close=NaN at 5pm PT). A NaN high/low compares False and
        # would silently miss a leg hit, so drop the bar until it's complete.
        if any(math.isnan(bar[k]) for k in ("open", "high", "low", "close")):
            continue
        bars.append(bar)
    return bars


def simulate(direction, bars_after_signal, stop_pct, tp_pct):
    """Returns a dict of entry/exit fields for one bracket on one signal."""
    if not bars_after_signal:
        return {"status": "PENDING_ENTRY"}
    entry_bar = bars_after_signal[0]
    entry = entry_bar["open"]
    sign = 1 if direction == "UP" else -1
    stop = entry * (1 - sign * stop_pct)
    tp = entry * (1 + sign * tp_pct)
    result = {"entry_date": entry_bar["date"], "entry_price": entry,
              "stop_price": stop, "take_profit_price": tp}

    for n, bar in enumerate(bars_after_signal, start=1):
        # Gap check on the open (skipped on the entry bar, which opens AT entry).
        if n > 1:
            gapped_stop = bar["open"] <= stop if direction == "UP" else bar["open"] >= stop
            gapped_tp = bar["open"] >= tp if direction == "UP" else bar["open"] <= tp
            if gapped_stop or gapped_tp:
                status = "STOP_LOSS" if gapped_stop else "TAKE_PROFIT"
                return finish(result, status, bar["date"], bar["open"], n, sign)
        if direction == "UP":
            hit_stop, hit_tp = bar["low"] <= stop, bar["high"] >= tp
        else:
            hit_stop, hit_tp = bar["high"] >= stop, bar["low"] <= tp
        if hit_stop:
            return finish(result, "STOP_LOSS", bar["date"], stop, n, sign)
        if hit_tp:
            return finish(result, "TAKE_PROFIT", bar["date"], tp, n, sign)

    last = bars_after_signal[-1]
    result.update({"status": "OPEN", "holding_days": len(bars_after_signal),
                   "mark_price": last["close"]})
    pnl = sign * (last["close"] - entry)
    result.update({"pnl_per_share": pnl, "pnl_pct": pnl / entry * 100})
    return result


def finish(result, status, date, price, holding_days, sign):
    pnl = sign * (price - result["entry_price"])
    result.update({"status": status, "exit_date": date, "exit_price": price,
                   "holding_days": holding_days, "pnl_per_share": pnl,
                   "pnl_pct": pnl / result["entry_price"] * 100})
    return result


def fmt(value):
    return f"{value:.2f}" if isinstance(value, float) else value


def build_rows(signals, bars, actions):
    updated_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    rows = []
    for sig in signals:
        signal_date = sig["timestamp"][:10]
        after = [b for b in bars if b["date"] > signal_date]
        for name, stop_pct, tp_pct in BRACKETS:
            outcome = simulate(sig["direction"], after, stop_pct, tp_pct)
            row = {c: "" for c in COLUMNS}
            row.update({
                "signal_timestamp": sig["timestamp"], "signal_date": signal_date,
                "direction": sig["direction"], "confidence_pct": sig["confidence_pct"],
                "signal_close": sig["last_close"],
                "real_trade_action": actions.get(sig["timestamp"], ""),
                "raw_signal_action": raw_signal_action(sig),
                "bracket": name, "stop_pct": f"{stop_pct * 100:g}", "take_profit_pct": f"{tp_pct * 100:g}",
                "updated_at": updated_at,
            })
            row.update({k: fmt(v) for k, v in outcome.items()})
            rows.append(row)
    return rows


def write_rows(rows):
    os.makedirs(LOGS_DIR, exist_ok=True)
    tmp = OUTPUT + ".tmp"
    with open(tmp, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=COLUMNS)
        writer.writeheader()
        writer.writerows(rows)
    os.replace(tmp, OUTPUT)


def matched_comparison(rows):
    """Pair the two brackets per signal. Matched = both brackets CLOSED (stop or
    take-profit hit), so PnL is compared on the identical set of signals."""
    old_name, cur_name = BRACKETS[0][0], BRACKETS[1][0]
    by_signal = {}
    for r in rows:
        by_signal.setdefault(r["signal_timestamp"], {})[r["bracket"]] = r
    closed = ("STOP_LOSS", "TAKE_PROFIT")
    matched, open_pairs = [], []
    for pair in by_signal.values():
        old, cur = pair.get(old_name), pair.get(cur_name)
        if not old or not cur:
            continue
        if old["status"] in closed and cur["status"] in closed:
            matched.append((old, cur))
        elif old["status"] != "PENDING_ENTRY":
            open_pairs.append((old, cur))
    return matched, open_pairs


def weekly_summary_lines(lookback_days=7):
    """Lines for the Monday Telegram health check. Reads the CSV the pipeline
    already wrote, so the 7:10am check makes no market data calls."""
    rows = read_rows(OUTPUT)
    if not rows:
        return ["Shadow brackets: no data yet (logs/shadow_brackets.csv missing or empty)."]
    old_name, cur_name = BRACKETS[0][0], BRACKETS[1][0]
    matched, open_pairs = matched_comparison(rows)
    cutoff = (datetime.now().date() - timedelta(days=lookback_days)).strftime("%Y-%m-%d")

    def stats(pairs, i):
        legs = [p[i] for p in pairs]
        pnl = sum(float(r["pnl_per_share"]) for r in legs)
        wins = sum(1 for r in legs if r["status"] == "TAKE_PROFIT")
        return pnl, wins

    lines = [f"Shadow brackets (old 2%/3% vs current 2.5%/4%, per share, since {SHADOW_START_DATE}):"]
    if matched:
        o_pnl, o_w = stats(matched, 0)
        c_pnl, c_w = stats(matched, 1)
        n = len(matched)
        lines.append(f"  Matched closed signals: {n}")
        lines.append(f"  Old:     ${o_pnl:+.2f}, {o_w}/{n} take-profit")
        lines.append(f"  Current: ${c_pnl:+.2f}, {c_w}/{n} take-profit")
        lines.append(f"  Current minus old: ${c_pnl - o_pnl:+.2f}")
    else:
        lines.append("  Matched closed signals: 0 (no signal has resolved under both brackets yet)")

    # A signal counts toward this week once its later-closing leg closed this week.
    this_week = [p for p in matched if max(p[0]["exit_date"], p[1]["exit_date"]) >= cutoff]
    if this_week:
        o_pnl, _ = stats(this_week, 0)
        c_pnl, _ = stats(this_week, 1)
        lines.append(f"  Fully resolved this week: {len(this_week)} (old ${o_pnl:+.2f}, current ${c_pnl:+.2f})")

    if open_pairs:
        o_pnl, _ = stats(open_pairs, 0)
        c_pnl, _ = stats(open_pairs, 1)
        lines.append(f"  Not yet resolved under both: {len(open_pairs)} "
                     f"(old ${o_pnl:+.2f}, current ${c_pnl:+.2f}, open legs marked to last close)")
    return lines + [""] + council_summary_lines(rows)


def council_bucket(action):
    """Collapse real_trade_action to ENTER / VETO / BLOCKED / SKIP / NO_LEDGER_ROW.
    Pre-October 12 ledger rows carry a bare BLOCKED, later ones BLOCKED_<code>."""
    if not action:
        return "NO_LEDGER_ROW"
    if action.startswith("BLOCKED"):
        return "BLOCKED"
    return action


def council_summary_lines(rows):
    """Raw technical signal vs full council, both on the CURRENT bracket (the one
    live orders use). Raw = enter every signal with raw_signal_action ENTER.
    Council = enter only where real_trade_action is ENTER, $0 elsewhere. Matched
    = signals whose CURRENT leg has closed, so both sides cover the same signals.
    Both sides are shadow simulations, so council PnL here is not the real
    Alpaca fill (that lives in trade_ledger.csv)."""
    cur_name = BRACKETS[1][0]
    cur = [r for r in rows if r["bracket"] == cur_name]
    raw_enter = sum(1 for r in cur if r.get("raw_signal_action") == "ENTER")

    counts, blocked_codes = {}, {}
    for r in cur:
        bucket = council_bucket(r.get("real_trade_action", ""))
        counts[bucket] = counts.get(bucket, 0) + 1
        if bucket == "BLOCKED":
            code = r["real_trade_action"]
            if code == "BLOCKED":
                code = "BLOCKED (pre-Oct 12, no code)"
            blocked_codes[code] = blocked_codes.get(code, 0) + 1

    lines = ["Raw signal vs council (current 2.5%/4% bracket, per share):",
             f"  Signals tracked: {len(cur)}",
             f"  Raw signal would enter: {raw_enter}"]
    order = ["ENTER", "VETO", "BLOCKED", "SKIP", "NO_LEDGER_ROW"]
    parts = [f"{b.lower().replace('_', ' ')} {counts[b]}" for b in order if counts.get(b)]
    lines.append("  Council: " + ", ".join(parts))
    if blocked_codes:
        detail = ", ".join(f"{c} {n}" for c, n in sorted(blocked_codes.items()))
        lines.append(f"    Blocked by reason: {detail}")

    closed = [r for r in cur if r["status"] in ("STOP_LOSS", "TAKE_PROFIT")]
    if not closed:
        lines.append("  Matched closed signals: 0 (no signal has closed under the current bracket yet)")
        return lines

    def pnl(subset):
        return sum(float(r["pnl_per_share"]) for r in subset)

    raw_taken = [r for r in closed if r.get("raw_signal_action") == "ENTER"]
    council_taken = [r for r in closed if council_bucket(r.get("real_trade_action", "")) == "ENTER"]
    raw_pnl, council_pnl = pnl(raw_taken), pnl(council_taken)
    lines.append(f"  Matched closed signals: {len(closed)}")
    lines.append(f"  Raw signal: ${raw_pnl:+.2f} on {len(raw_taken)} trade(s)")
    lines.append(f"  Council:    ${council_pnl:+.2f} on {len(council_taken)} trade(s)")
    lines.append(f"  Council minus raw: ${council_pnl - raw_pnl:+.2f}")
    # What each filter removed. Negative = the filter skipped losers and helped.
    for bucket in ("VETO", "BLOCKED"):
        skipped = [r for r in raw_taken if council_bucket(r.get("real_trade_action", "")) == bucket]
        if skipped:
            lines.append(f"    {bucket.title()} signals would have made ${pnl(skipped):+.2f} on {len(skipped)}")
    return lines


def run():
    print("\n-- Shadow Brackets --")
    if (STOP_LOSS_PCT, TAKE_PROFIT_PCT_LOW) != (BRACKETS[1][1], BRACKETS[1][2]):
        print(f"  WARNING: live bracket in trade_logic.py is now {STOP_LOSS_PCT * 100:g}%/"
              f"{TAKE_PROFIT_PCT_LOW * 100:g}%, not the {BRACKETS[1][0]} arm tracked here.")

    signals = eligible_signals()
    if not signals:
        print(f"  No signals at or above {MIN_CONFIDENCE}% since {SHADOW_START_DATE}. Nothing to track.")
        print("---------------------\n")
        return

    try:
        bars = get_daily_bars(signals[0]["timestamp"][:10])
    except Exception as e:
        # Leave the previous CSV in place rather than overwrite it with nothing.
        print(f"  WARNING: could not fetch {TICKER} daily bars ({e}). Shadow CSV not updated.")
        print("---------------------\n")
        return
    if not bars:
        print(f"  WARNING: no {TICKER} daily bars returned. Shadow CSV not updated.")
        print("---------------------\n")
        return

    rows = build_rows(signals, bars, ledger_actions())
    write_rows(rows)

    status_counts = {}
    for r in rows:
        key = (r["bracket"], r["status"])
        status_counts[key] = status_counts.get(key, 0) + 1
    print(f"  {len(signals)} signal(s) tracked, bars through {bars[-1]['date']}")
    for name, _, _ in BRACKETS:
        parts = [f"{s}={c}" for (b, s), c in sorted(status_counts.items()) if b == name]
        print(f"  {name}: " + ", ".join(parts))
    for line in weekly_summary_lines()[1:]:
        print(line)
    print("  Wrote: " + OUTPUT)
    print("---------------------\n")


if __name__ == "__main__":
    run()
