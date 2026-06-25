import csv
import os
import sys
from datetime import datetime
from dotenv import load_dotenv

load_dotenv(os.path.expanduser("~/trading-system/.env"))

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from trade_logic import extract_verdict

DECISIONS_LOG = os.path.expanduser("~/trading-system/logs/decisions_log.csv")
PAPER_TRADES_LOG = os.path.expanduser("~/trading-system/logs/paper_trades.csv")
SIGNAL_LOG_PATH = os.path.expanduser("~/trading-system/logs/signal_log.csv")

STOP_LOSS_PCT = 0.02
TAKE_PROFIT_LOW_PCT = 0.03
TAKE_PROFIT_HIGH_PCT = 0.05

def calculate_levels(direction, entry_price):
    entry = float(entry_price)
    if direction == "UP":
        stop_loss = round(entry * (1 - STOP_LOSS_PCT), 2)
        take_profit_low = round(entry * (1 + TAKE_PROFIT_LOW_PCT), 2)
        take_profit_high = round(entry * (1 + TAKE_PROFIT_HIGH_PCT), 2)
    else:
        stop_loss = round(entry * (1 + STOP_LOSS_PCT), 2)
        take_profit_low = round(entry * (1 - TAKE_PROFIT_LOW_PCT), 2)
        take_profit_high = round(entry * (1 - TAKE_PROFIT_HIGH_PCT), 2)
    return stop_loss, take_profit_low, take_profit_high

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
    stop_loss, tp_low, tp_high = calculate_levels(
        decision["direction"], decision["last_close"]
    )
    with open(PAPER_TRADES_LOG, "a", newline="") as f:
        writer = csv.writer(f)
        if not file_exists:
            writer.writerow([
                "signal_timestamp", "date_logged", "ticker",
                "direction", "signal_confidence_pct",
                "critic_verdict", "entry_price", "stop_loss",
                "take_profit_low", "take_profit_high",
                "exit_price", "exit_reason", "pnl_dollars",
                "pnl_pct", "status", "notes"
            ])
        writer.writerow([
            decision["timestamp"],
            datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            decision["ticker"],
            decision["direction"],
            decision["signal_confidence_pct"],
            decision["critic_verdict"],
            decision["last_close"],
            stop_loss, tp_low, tp_high,
            "", "", "", "",
            "OPEN",
            "Auto-logged."
        ])
    print(f"Paper trade logged: {decision['ticker']} {decision['direction']} at ${decision['last_close']}")
    print(f"  Stop-loss: ${stop_loss}")
    print(f"  Take-profit: ${tp_low} - ${tp_high}")
    print(f"  Status: OPEN")
    print(f"Saved to: {PAPER_TRADES_LOG}")

def get_latest_signal_direction():
    if not os.path.isfile(SIGNAL_LOG_PATH):
        return None
    with open(SIGNAL_LOG_PATH, "r") as f:
        rows = list(csv.DictReader(f))
    if not rows:
        return None
    return rows[-1].get("direction", "").strip()

def run():
    latest_direction = get_latest_signal_direction()
    if latest_direction not in ("UP", "DOWN"):
        print(f"Latest signal is {latest_direction} — no paper trade logged.")
        return
    print("Checking latest Critic decision...")
    decision = get_latest_decision()
    if not decision:
        return
    verdict = extract_verdict(decision)
    print(f"Verdict: {verdict}")
    if verdict not in ("PASS", "FLAG"):
        print(f"Verdict is '{verdict}' — no paper trade logged.")
        return
    if already_logged(decision["timestamp"]):
        print("This signal was already logged. Skipping.")
        return
    log_paper_trade(decision)

if __name__ == "__main__":
    run()
