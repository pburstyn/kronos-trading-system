import os
import csv
import sys
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from trade_logic_qqq import make_trade_decision, extract_verdict
from news_context import get_news_context
# Column set, vote parsing, model lookup and commit lookup are imported from
# decision_ledger.py so both ledgers share one schema.
from decision_ledger import COLUMNS, read_rows, find_by_timestamp, parse_votes, get_model, get_commit

# QQQ equivalent of decision_ledger.py (added October 18). Append-only audit
# ledger, one row per pipeline run, written to its own file. Runs right after
# critic_qqq.py. The trade action is computed with the same make_trade_decision()
# and the QQQ copy of the fail-closed position guard. Never submits orders.

REPO_DIR = os.path.expanduser("~/kronos-trading-system")
LOGS_DIR = os.path.join(REPO_DIR, "logs")

SIGNAL_LOG = os.path.join(LOGS_DIR, "signal_log_qqq.csv")
ANDY_LOG = os.path.join(LOGS_DIR, "reasoning_log_qqq.csv")
KIMI_K3_LOG = os.path.join(LOGS_DIR, "kimi_k3_reasoning_log_qqq.csv")
DECISIONS_LOG = os.path.join(LOGS_DIR, "decisions_log_qqq.csv")
LEDGER = os.path.join(LOGS_DIR, "decision_ledger_qqq.csv")


def determine_action(signal, decision_row, latest_decision_row):
    """Same rules and trade_action codes as decision_ledger.determine_action(),
    against the QQQ logs and the QQQ position guard."""
    direction = signal["direction"]
    if direction == "NEUTRAL":
        return "BLOCKED_NEUTRAL", "Signal NEUTRAL, not actionable"
    if direction not in ("UP", "DOWN"):
        return "SKIP", f"Signal {direction}, not actionable"

    today = datetime.now().strftime("%Y-%m-%d")
    signal_date = signal["timestamp"].split(" ")[0]
    if signal_date != today:
        return "BLOCKED_STALE_DATA", f"Latest signal is from {signal_date}, not today ({today})"
    if latest_decision_row:
        decision_date = latest_decision_row["timestamp"].split(" ")[0]
        if decision_date != today:
            return "BLOCKED_STALE_DATA", f"Latest decisions log entry is from {decision_date}, not today ({today})"

    if not decision_row:
        return "SKIP", "No Critic decision for this signal (critic_qqq.py did not log a row)"

    verdict = extract_verdict(decision_row)
    if verdict == "VETO":
        return "VETO", "Critic verdict VETO blocks entry"

    decision = make_trade_decision(
        decision_row["direction"],
        decision_row["signal_confidence_pct"],
        decision_row["last_close"],
        verdict,
    )
    if decision.get("block_code") == "BLOCKED_SHORT":
        return "BLOCKED_SHORT", decision["reason"]
    if decision["action"] != "ENTER":
        return "SKIP", decision["reason"]

    try:
        from alpaca_execute_qqq import check_existing_exposure
        from alpaca.trading.client import TradingClient
        client = TradingClient(os.environ.get("ALPACA_API_KEY"), os.environ.get("ALPACA_SECRET_KEY"), paper=True)
        exposed, reason = check_existing_exposure(client)
    except Exception as e:
        return "BLOCKED_API_ERROR", f"ENTER {direction} ({verdict}) blocked, could not run position guard ({e})"
    if exposed:
        if reason.startswith("could not verify"):
            return "BLOCKED_API_ERROR", f"ENTER {direction} ({verdict}) blocked by position guard: {reason}"
        return "BLOCKED_EXISTING_POSITION", f"ENTER {direction} ({verdict}) blocked by position guard: {reason}"
    return "ENTER", f"ENTER {direction}, {verdict} verdict, size {decision['position_size']}"


def append_row(row):
    os.makedirs(LOGS_DIR, exist_ok=True)
    needs_header = not os.path.isfile(LEDGER) or os.path.getsize(LEDGER) == 0
    if not needs_header:
        with open(LEDGER, "r", newline="") as f:
            existing = next(csv.reader(f), [])
        if existing != COLUMNS:
            print("ERROR: decision_ledger_qqq.csv header does not match current COLUMNS. Row NOT written.")
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
    print("\n-- Decision Ledger (QQQ) --")
    signals = read_rows(SIGNAL_LOG)
    if not signals:
        print("  No QQQ signal log rows. Nothing to record.")
        print("---------------------\n")
        return
    signal = signals[-1]
    ts = signal["timestamp"]

    andy = find_by_timestamp(read_rows(ANDY_LOG), ts)
    kimi = find_by_timestamp(read_rows(KIMI_K3_LOG), ts)
    decisions = read_rows(DECISIONS_LOG)
    decision = find_by_timestamp(decisions, ts)
    commit, dirty = get_commit()
    action, action_reason = determine_action(signal, decision, decisions[-1] if decisions else None)

    row = {
        "ledger_timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "signal_timestamp": ts,
        "ticker": signal.get("ticker", ""),
        "direction": signal.get("direction", ""),
        "confidence_pct": signal.get("confidence_pct", ""),
        "last_close": signal.get("last_close", ""),
        "raw_votes": signal.get("votes", ""),
        "news_headlines": get_news_context(),
        # andy_reasoning_qqq.py / kimi_k3_reasoning_qqq.py import their model
        # calls from the SPY scripts, so the model ID lives there.
        "andy_model": get_model("andy_reasoning.py"),
        "andy_reasoning": andy.get("andy_reasoning", "") if andy else "",
        "kimi_k3_model": get_model("kimi_k3_reasoning.py"),
        "kimi_k3_reasoning": kimi.get("kimi_k3_reasoning", "") if kimi else "",
        "critic_model": get_model("critic_qqq.py"),
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
