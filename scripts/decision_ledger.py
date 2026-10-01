import os
import re
import csv
import sys
import subprocess
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from trade_logic import make_trade_decision, extract_verdict
from news_context import get_news_context

# Append-only audit ledger: one row per pipeline run capturing everything that
# went into the day's decision. Runs right after critic.py in run_pipeline.sh,
# so the trade action recorded here is the action the downstream scripts WILL
# take, computed with the same trade_logic.make_trade_decision() and the same
# read-only alpaca_execute.check_existing_exposure() position guard. This script
# never submits, modifies, or cancels orders.

REPO_DIR = os.path.expanduser("~/trading-system")
SCRIPTS_DIR = os.path.join(REPO_DIR, "scripts")
LOGS_DIR = os.path.join(REPO_DIR, "logs")

SIGNAL_LOG = os.path.join(LOGS_DIR, "signal_log.csv")
ANDY_LOG = os.path.join(LOGS_DIR, "reasoning_log.csv")
KIMI_K3_LOG = os.path.join(LOGS_DIR, "kimi_k3_reasoning_log.csv")
DECISIONS_LOG = os.path.join(LOGS_DIR, "decisions_log.csv")
LEDGER = os.path.join(LOGS_DIR, "decision_ledger.csv")

COLUMNS = [
    "ledger_timestamp", "signal_timestamp", "ticker", "direction", "confidence_pct", "last_close",
    "ma_structure", "ma_structure_vote", "rsi_value", "rsi_vote",
    "macd", "macd_vote", "macd_histogram", "macd_histogram_vote",
    "signal_verdict_note", "raw_votes",
    "news_headlines",
    "andy_model", "andy_reasoning",
    "kimi_k3_model", "kimi_k3_reasoning",
    "critic_model", "critic_verdict", "critic_confidence", "critic_reason",
    "trade_action", "trade_action_reason",
    "commit_hash", "code_dirty",
]

MODEL_RE = re.compile(r"""["']?model["']?\s*[:=]\s*["']([^"']+)["']""")


def read_rows(path):
    if not os.path.isfile(path):
        return []
    with open(path, "r", newline="") as f:
        return list(csv.DictReader(f))


def find_by_timestamp(rows, timestamp):
    for row in reversed(rows):
        if row.get("timestamp") == timestamp:
            return row
    return None


def parse_votes(votes_text):
    """Split signal_log.csv's votes column into the four indicators that
    signal_logger.py evaluates: MA structure, RSI, MACD line vs signal, MACD
    histogram. Each segment is "<value text>: <vote>"."""
    parsed = {
        "ma_structure": "", "ma_structure_vote": "",
        "rsi_value": "", "rsi_vote": "",
        "macd": "", "macd_vote": "",
        "macd_histogram": "", "macd_histogram_vote": "",
        "signal_verdict_note": "",
    }
    for seg in (s.strip() for s in votes_text.split(" | ")):
        if not seg:
            continue
        if seg.startswith("VERDICT:"):
            parsed["signal_verdict_note"] = seg
            continue
        value, _, vote = seg.rpartition(": ")
        if not value:
            value, vote = seg, ""
        if seg.startswith("RSI"):
            m = re.match(r"RSI\s+([\d.]+)", seg)
            parsed["rsi_value"] = m.group(1) if m else value
            parsed["rsi_vote"] = vote
        elif seg.startswith("MACD histogram"):
            parsed["macd_histogram"] = value
            parsed["macd_histogram_vote"] = vote
        elif seg.startswith("MACD"):
            parsed["macd"] = value
            parsed["macd_vote"] = vote
        elif "MA50" in seg:
            parsed["ma_structure"] = value
            parsed["ma_structure_vote"] = vote
    return parsed


def get_model(script_name):
    """Read the model ID straight from the script source, so the ledger always
    reflects what the code at this commit actually calls."""
    try:
        with open(os.path.join(SCRIPTS_DIR, script_name)) as f:
            m = MODEL_RE.search(f.read())
        return m.group(1) if m else "UNKNOWN"
    except OSError:
        return "UNKNOWN"


def get_commit():
    try:
        commit = subprocess.check_output(
            ["git", "-C", REPO_DIR, "rev-parse", "HEAD"], text=True).strip()
        # Only uncommitted changes to code count -- logs/ churns every run.
        dirty = subprocess.check_output(
            ["git", "-C", REPO_DIR, "status", "--porcelain", "--", "scripts"], text=True).strip()
        return commit, "yes" if dirty else "no"
    except Exception as e:
        return f"UNKNOWN ({e})", "unknown"


def determine_action(signal, decision_row):
    """Returns (action, reason) with action in ENTER / SKIP / VETO / BLOCKED."""
    direction = signal["direction"]
    if direction not in ("UP", "DOWN"):
        return "SKIP", f"Signal {direction}, not actionable"
    if not decision_row:
        return "SKIP", "No Critic decision for this signal (critic.py did not log a row)"

    verdict = extract_verdict(decision_row)
    if verdict == "VETO":
        return "VETO", "Critic verdict VETO blocks entry"

    decision = make_trade_decision(
        decision_row["direction"],
        decision_row["signal_confidence_pct"],
        decision_row["last_close"],
        verdict,
    )
    if decision["action"] != "ENTER":
        return "SKIP", decision["reason"]

    # Same read-only guard alpaca_execute.py applies before submitting.
    # Fails closed like alpaca_execute does: unverifiable state counts as blocked.
    try:
        from alpaca_execute import check_existing_exposure
        from alpaca.trading.client import TradingClient
        client = TradingClient(os.environ.get("ALPACA_API_KEY"), os.environ.get("ALPACA_SECRET_KEY"), paper=True)
        exposed, reason = check_existing_exposure(client)
    except Exception as e:
        exposed, reason = True, f"could not run position guard ({e})"
    if exposed:
        return "BLOCKED", f"ENTER {direction} ({verdict}) blocked by position guard: {reason}"
    return "ENTER", f"ENTER {direction}, {verdict} verdict, size {decision['position_size']}"


def append_row(row):
    os.makedirs(LOGS_DIR, exist_ok=True)
    needs_header = not os.path.isfile(LEDGER) or os.path.getsize(LEDGER) == 0
    if not needs_header:
        with open(LEDGER, "r", newline="") as f:
            existing = next(csv.reader(f), [])
        if existing != COLUMNS:
            # Never rewrite the file. A header/row mismatch silently shifted
            # decisions_log.csv columns once (July 9) -- refuse instead.
            print("ERROR: decision_ledger.csv header does not match current COLUMNS. Row NOT written.")
            print("  existing: " + ",".join(existing))
            print("  expected: " + ",".join(COLUMNS))
            return False
    with open(LEDGER, "a", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=COLUMNS)
        if needs_header:
            writer.writeheader()
        writer.writerow(row)
    return True


def run():
    print("\n-- Decision Ledger --")
    signals = read_rows(SIGNAL_LOG)
    if not signals:
        print("  No signal log rows. Nothing to record.")
        print("---------------------\n")
        return
    signal = signals[-1]
    ts = signal["timestamp"]

    andy = find_by_timestamp(read_rows(ANDY_LOG), ts)
    kimi = find_by_timestamp(read_rows(KIMI_K3_LOG), ts)
    decision = find_by_timestamp(read_rows(DECISIONS_LOG), ts)
    commit, dirty = get_commit()
    action, action_reason = determine_action(signal, decision)

    row = {
        "ledger_timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "signal_timestamp": ts,
        "ticker": signal.get("ticker", ""),
        "direction": signal.get("direction", ""),
        "confidence_pct": signal.get("confidence_pct", ""),
        "last_close": signal.get("last_close", ""),
        "raw_votes": signal.get("votes", ""),
        # Exact text the analysts received (headlines plus any seasonal_note).
        "news_headlines": get_news_context(),
        "andy_model": get_model("andy_reasoning.py"),
        "andy_reasoning": andy.get("andy_reasoning", "") if andy else "",
        "kimi_k3_model": get_model("kimi_k3_reasoning.py"),
        "kimi_k3_reasoning": kimi.get("kimi_k3_reasoning", "") if kimi else "",
        "critic_model": get_model("critic.py"),
        "critic_verdict": extract_verdict(decision) if decision else "",
        "critic_confidence": decision.get("critic_confidence", "") if decision else "",
        "critic_reason": decision.get("critic_reason", "") if decision else "",
        "trade_action": action,
        "trade_action_reason": action_reason,
        "commit_hash": commit,
        "code_dirty": dirty,
    }
    row.update(parse_votes(signal.get("votes", "")))

    if append_row(row):
        print(f"  Signal {ts}: {row['direction']} {row['confidence_pct']}% -> {action} ({action_reason})")
        print(f"  Commit {commit[:7]} (dirty={dirty}) | Andy={row['andy_model']} Kimi={row['kimi_k3_model']} Critic={row['critic_model']}")
        print("  Appended to: " + LEDGER)
    print("---------------------\n")


if __name__ == "__main__":
    run()
