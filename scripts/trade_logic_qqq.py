import os
import sys
import csv
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
# QQQ equivalent of trade_logic.py (added October 18). The decision rules,
# bracket percentages (2.5% stop / 4% take-profit), confidence floor and
# LONG_ONLY_MODE are imported, not copied, so QQQ can never drift from SPY's
# settings (auto_logger.py and dashboard.py once carried stale duplicate
# bracket constants, see CLAUDE.md). Only the decisions log path differs.
from trade_logic import (
    extract_verdict,
    make_trade_decision,
    calculate_trade_levels,
    print_decision,
    get_latest_decision_row as get_latest_spy_decision_row,
)

TICKER = "QQQ"
DECISIONS_LOG = os.path.expanduser("~/kronos-trading-system/logs/decisions_log_qqq.csv")


def get_latest_decision_row():
    if not os.path.isfile(DECISIONS_LOG):
        print("No QQQ decisions log found. Run critic_qqq.py first.")
        return None
    with open(DECISIONS_LOG, "r") as f:
        rows = list(csv.DictReader(f))
    if not rows:
        print("QQQ decisions log is empty.")
        return None
    return rows[-1]


def get_spy_entry_direction_today():
    """Return 'UP'/'DOWN' if SPY's own trade_logic decision today is ENTER in
    that direction, else None. Read-only: same decisions_log.csv row and same
    make_trade_decision() call that trade_logic.py/alpaca_execute.py use for SPY.
    Used for the QQQ overlap sizing rule in alpaca_execute_qqq.py."""
    row = get_latest_spy_decision_row()
    if not row:
        return None
    today_date = datetime.now().strftime("%Y-%m-%d")
    if row["timestamp"].split(" ")[0] != today_date:
        return None
    decision = make_trade_decision(
        row["direction"],
        row["signal_confidence_pct"],
        row["last_close"],
        extract_verdict(row)
    )
    if decision["action"] != "ENTER":
        return None
    return decision["direction"]


def run():
    row = get_latest_decision_row()
    if not row:
        return

    row_date = row["timestamp"].split(" ")[0]
    today_date = datetime.now().strftime("%Y-%m-%d")
    if row_date != today_date:
        print(f"\n-- QQQ Trade Decision --")
        print(f"  NO TRADE: Latest QQQ decisions log entry is from {row_date}, not today ({today_date}). Stale data, skipping.")
        print("---------------------\n")
        return

    decision = make_trade_decision(
        row["direction"],
        row["signal_confidence_pct"],
        row["last_close"],
        extract_verdict(row)
    )
    print(f"\n[{TICKER}]", end="")
    print_decision(decision)

if __name__ == "__main__":
    run()
