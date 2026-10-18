import csv
import os
import sys
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
# QQQ ENTER alert (added October 18), the QQQ equivalent of
# telegram_notify.send_entry_alert(). The QQQ daily signal summary is already
# sent by telegram_notify.py, so this script sends the ENTER alert only.
from telegram_notify import send_message
from trade_logic_qqq import get_latest_decision_row, make_trade_decision, extract_verdict

ALPACA_ORDERS_LOG = os.path.expanduser("~/kronos-trading-system/logs/alpaca_orders_qqq.csv")


def get_order_today(path=ALPACA_ORDERS_LOG):
    """Return today's QQQ order row from alpaca_orders_qqq.csv, or None."""
    if not os.path.isfile(path):
        return None
    today_date = datetime.now().strftime("%Y-%m-%d")
    with open(path, "r") as f:
        rows = [r for r in csv.DictReader(f) if r["timestamp"].startswith(today_date)]
    return rows[-1] if rows else None


def build_message(decision, row, order):
    direction_label = "UP (Long)" if decision["direction"] == "UP" else "DOWN (Short)"
    size_label = "full size" if decision["verdict"] == "PASS" else "half size"
    if order:
        overlap = ", halved: SPY also entering same direction" if order.get("spy_overlap") == "True" else ""
        order_line = f"${float(order['notional']):,.0f} QQQ paper order queued for next market open{overlap}."
    else:
        order_line = "Order BLOCKED, QQQ position already open. No new order placed."

    return (
        f"Kronos QQQ ENTER Signal\n"
        f"\n"
        f"Direction:    {direction_label}\n"
        f"Confidence:   {row['signal_confidence_pct']}%\n"
        f"Entry:        ${decision['entry']}\n"
        f"Stop-loss:    ${decision['stop_loss']}\n"
        f"Take-profit:  ${decision['take_profit_low']} – ${decision['take_profit_high']}\n"
        f"Verdict:      {decision['verdict']} ({size_label})\n"
        f"\n"
        f"{order_line}"
    )


def send_entry_alert(dry_run):
    row = get_latest_decision_row()
    if not row:
        print("  No QQQ decision row found — skipping QQQ ENTER alert.")
        return

    row_date = row["timestamp"].split(" ")[0]
    today_date = datetime.now().strftime("%Y-%m-%d")
    if row_date != today_date:
        print(f"  SKIP QQQ ENTER alert: stale decision ({row_date}), not today.")
        return

    decision = make_trade_decision(
        row["direction"],
        row["signal_confidence_pct"],
        row["last_close"],
        extract_verdict(row)
    )

    if decision["action"] != "ENTER":
        print(f"  NO QQQ ENTER ALERT: {decision['reason']}")
        return

    message = build_message(decision, row, get_order_today())
    send_message(message, dry_run, "QQQ ENTER alert")


def run(dry_run=False):
    print("\n-- Telegram Notify (QQQ) --")
    send_entry_alert(dry_run)
    print("---------------------\n")


if __name__ == "__main__":
    run(dry_run="--dry-run" in sys.argv)
