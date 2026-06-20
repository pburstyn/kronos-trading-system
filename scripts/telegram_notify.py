import json
import os
import sys
from datetime import datetime

import requests
from dotenv import load_dotenv

load_dotenv(os.path.expanduser("~/trading-system/.env"))

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from trade_logic import get_latest_decision_row, make_trade_decision

OPENCLAW_CONFIG = "/mnt/c/Users/openc/.openclaw/openclaw.json"


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


def run(dry_run=False):
    print("\n-- Telegram Notify --")

    row = get_latest_decision_row()
    if not row:
        print("  No decision row found.")
        print("---------------------\n")
        return

    row_date = row["timestamp"].split(" ")[0]
    today_date = datetime.now().strftime("%Y-%m-%d")
    if row_date != today_date:
        print(f"  SKIP: Stale decision ({row_date}), not today.")
        print("---------------------\n")
        return

    decision = make_trade_decision(
        row["direction"],
        row["signal_confidence_pct"],
        row["last_close"],
        row["critic_verdict"]
    )

    if decision["action"] != "ENTER":
        print(f"  NO MESSAGE: {decision['reason']}")
        print("---------------------\n")
        return

    message = build_message(decision, row)

    if dry_run:
        print("  DRY RUN — message that would be sent:")
        print()
        for line in message.splitlines():
            print(f"    {line}")
        print()
        print("---------------------\n")
        return

    try:
        token, chat_id = get_telegram_config()
        send_telegram(token, chat_id, message)
        print(f"  Message sent.")
    except Exception as e:
        print(f"  WARNING: Telegram send failed: {e}")
    print("---------------------\n")


if __name__ == "__main__":
    run(dry_run="--dry-run" in sys.argv)
