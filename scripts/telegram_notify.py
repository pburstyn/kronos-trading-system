import csv
import json
import os
import re
import sys
from datetime import datetime

import requests
from dotenv import load_dotenv

load_dotenv(os.path.expanduser("~/trading-system/.env"))

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from trade_logic import get_latest_decision_row, make_trade_decision, extract_verdict

OPENCLAW_CONFIG = "/mnt/c/Users/openc/.openclaw/openclaw.json"
SIGNAL_LOG = os.path.expanduser("~/trading-system/logs/signal_log.csv")


def get_telegram_config():
    with open(OPENCLAW_CONFIG) as f:
        cfg = json.load(f)
    token = cfg["channels"]["telegram"]["botToken"]
    chat_id = os.environ.get("TELEGRAM_CHAT_ID")
    return token, chat_id


def build_message(decision, row):
    direction_label = "UP (Long)" if decision["direction"] == "UP" else "DOWN (Short)"
    notional = "$1,000" if decision["verdict"] == "PASS" else "$500"
    size_label = "full size" if decision["verdict"] == "PASS" else "half size"

    return (
        f"Kronos ENTER Signal\n"
        f"\n"
        f"Direction:    {direction_label}\n"
        f"Confidence:   {row['signal_confidence_pct']}%\n"
        f"Entry:        ${decision['entry']}\n"
        f"Stop-loss:    ${decision['stop_loss']}\n"
        f"Take-profit:  ${decision['take_profit_low']} – ${decision['take_profit_high']}\n"
        f"Verdict:      {decision['verdict']} ({size_label})\n"
        f"\n"
        f"{notional} paper order queued for next market open."
    )


def send_telegram(token, chat_id, text):
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    resp = requests.post(url, data={"chat_id": chat_id, "text": text}, timeout=10)
    resp.raise_for_status()
    return resp.json()


def get_latest_signal_row():
    if not os.path.isfile(SIGNAL_LOG):
        return None
    with open(SIGNAL_LOG, "r") as f:
        rows = list(csv.DictReader(f))
    if not rows:
        return None
    return rows[-1]


def plain_english_verdict(row):
    direction = row["direction"]
    confidence = row["confidence_pct"]
    votes = row.get("votes", "")

    if "VERDICT: CONFLICT" in votes:
        return "No trade — RSI overbought conflicted with bullish votes, signal forced to neutral."

    if "VERDICT: NEUTRAL" in votes:
        match = re.search(r"bull_votes=(\d+)\s+bear_votes=(\d+).*MIN_VOTES=(\d+)", votes)
        if match:
            bull, bear, min_votes = match.groups()
            return f"No trade — {bull} bullish vs {bear} bearish votes, needed {min_votes} to act."
        return "No trade — not enough votes to confirm a direction."

    if direction == "UP":
        return f"Bullish signal — {confidence}% confidence to go long."
    if direction == "DOWN":
        return f"Bearish signal — {confidence}% confidence to go short."

    return "No directional signal."


def build_daily_summary_message(row):
    date = row["timestamp"].split(" ")[0]
    return (
        f"Kronos Daily Signal — {date}\n"
        f"\n"
        f"Ticker:      {row['ticker']}\n"
        f"Direction:   {row['direction']}\n"
        f"Confidence:  {row['confidence_pct']}%\n"
        f"Close:       ${row['last_close']}\n"
        f"\n"
        f"{plain_english_verdict(row)}"
    )


def send_message(message, dry_run, label):
    if dry_run:
        print(f"  DRY RUN — {label} that would be sent:")
        print()
        for line in message.splitlines():
            print(f"    {line}")
        print()
        return

    try:
        token, chat_id = get_telegram_config()
        send_telegram(token, chat_id, message)
        print(f"  {label} sent.")
    except Exception as e:
        print(f"  WARNING: {label} send failed: {e}")


def send_entry_alert(dry_run):
    row = get_latest_decision_row()
    if not row:
        print("  No decision row found — skipping ENTER alert.")
        return

    row_date = row["timestamp"].split(" ")[0]
    today_date = datetime.now().strftime("%Y-%m-%d")
    if row_date != today_date:
        print(f"  SKIP ENTER alert: stale decision ({row_date}), not today.")
        return

    decision = make_trade_decision(
        row["direction"],
        row["signal_confidence_pct"],
        row["last_close"],
        extract_verdict(row)
    )

    if decision["action"] != "ENTER":
        print(f"  NO ENTER ALERT: {decision['reason']}")
        return

    message = build_message(decision, row)
    send_message(message, dry_run, "ENTER alert")


def send_daily_summary(dry_run):
    row = get_latest_signal_row()
    if not row:
        print("  No signal row found — skipping daily summary.")
        return

    row_date = row["timestamp"].split(" ")[0]
    today_date = datetime.now().strftime("%Y-%m-%d")
    if row_date != today_date:
        print(f"  SKIP daily summary: stale signal ({row_date}), not today.")
        return

    message = build_daily_summary_message(row)
    send_message(message, dry_run, "Daily summary")


def run(dry_run=False):
    print("\n-- Telegram Notify --")
    send_entry_alert(dry_run)
    send_daily_summary(dry_run)
    print("---------------------\n")


if __name__ == "__main__":
    run(dry_run="--dry-run" in sys.argv)
