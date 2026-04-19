import csv
import os
from datetime import datetime
from dotenv import load_dotenv

load_dotenv(os.path.expanduser("~/trading-system/.env"))

DECISIONS_LOG = os.path.expanduser(
    "~/trading-system/logs/decisions_log.csv"
)
PAPER_TRADES_LOG = os.path.expanduser(
    "~/trading-system/logs/paper_trades.csv"
)

def get_latest_decision():
    if not os.path.isfile(DECISIONS_LOG):
        print("No decisions log found. Run critic.py first.")
        return None

    with open(DECISIONS_LOG, "r") as f:
        rows = list(csv.DictReader(f))

    if not rows:
        print("Decisions log is empty.")
        return None

    return rows[-1]

def already_logged(timestamp):
    if not os.path.isfile(PAPER_TRADES_LOG):
        return False

    with open(PAPER_TRADES_LOG, "r") as f:
        rows = list(csv.DictReader(f))

    for row in rows:
        if row.get("signal_timestamp") == timestamp:
            return True

    return False

def log_paper_trade(decision):
    os.makedirs(os.path.dirname(PAPER_TRADES_LOG), exist_ok=True)

    file_exists = os.path.isfile(PAPER_TRADES_LOG)
    with open(PAPER_TRADES_LOG, "a", newline="") as f:
        writer = csv.writer(f)
        if not file_exists:
            writer.writerow([
                "signal_timestamp", "date_logged", "ticker",
                "direction", "signal_confidence_pct",
                "critic_verdict", "entry_price",
                "exit_price", "shares", "pnl_dollars",
                "pnl_pct", "notes"
            ])
        writer.writerow([
            decision["timestamp"],
            datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            decision["ticker"],
            decision["direction"],
            decision["signal_confidence_pct"],
            decision["critic_verdict"],
            decision["last_close"],
            "",
            "",
            "",
            "",
            "Auto-logged. Fill in exit price when trade closes."
        ])

    print(f"Paper trade logged: {decision['ticker']} "
          f"{decision['direction']} at ${decision['last_close']}")
    print(f"Saved to: {PAPER_TRADES_LOG}")
    print("Fill in exit price manually when you close the trade.")

def run():
    print("Checking latest Critic decision...")
    decision = get_latest_decision()
    if not decision:
        return

    verdict = decision.get("critic_verdict", "").strip()
    print(f"Verdict: {verdict}")

    if verdict != "PASS":
        print(f"Verdict is {verdict} — no paper trade logged.")
        return

    if already_logged(decision["timestamp"]):
        print("This signal was already logged. Skipping.")
        return

    log_paper_trade(decision)

if __name__ == "__main__":
    run()

