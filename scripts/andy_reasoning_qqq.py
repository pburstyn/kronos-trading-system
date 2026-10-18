import csv
import os
import sys

sys.path.insert(0, os.path.expanduser("~/kronos-trading-system/scripts"))
# QQQ equivalent of andy_reasoning.py (added October 18). The prompt, model and
# macro/sentiment/news context are imported from andy_reasoning.py, so Andy
# reasons about QQQ exactly as he does about SPY. ask_andy() reads the ticker off
# the signal row. Only the input and output log files differ.
from andy_reasoning import ask_andy

SIGNAL_LOG = os.path.expanduser("~/kronos-trading-system/logs/signal_log_qqq.csv")
REASONING_LOG = os.path.expanduser("~/kronos-trading-system/logs/reasoning_log_qqq.csv")


def get_latest_signal():
    if not os.path.isfile(SIGNAL_LOG):
        print("No QQQ signal log found. Run signal_logger_qqq.py first.")
        return None

    with open(SIGNAL_LOG, "r") as f:
        rows = list(csv.DictReader(f))

    if not rows:
        print("QQQ signal log is empty.")
        return None

    return rows[-1]

def log_reasoning(signal, reasoning):
    os.makedirs(os.path.dirname(REASONING_LOG), exist_ok=True)

    file_exists = os.path.isfile(REASONING_LOG)
    with open(REASONING_LOG, "a", newline="") as f:
        writer = csv.writer(f)
        if not file_exists:
            writer.writerow([
                "timestamp", "ticker", "direction",
                "confidence_pct", "last_close", "andy_reasoning"
            ])
        writer.writerow([
            signal['timestamp'],
            signal['ticker'],
            signal['direction'],
            signal['confidence_pct'],
            signal['last_close'],
            reasoning.replace("\n", " ")
        ])

    print("\n── Andy's Reasoning (QQQ) ────────────────")
    print(reasoning)
    print("──────────────────────────────────────────")
    print(f"Logged to: {REASONING_LOG}\n")

def run():
    print("Reading latest QQQ signal...")
    signal = get_latest_signal()
    if not signal:
        return
    direction = signal.get("direction", "").strip()
    if direction not in ("UP", "DOWN"):
        print(f"QQQ signal is {direction} — not actionable. Skipping Andy analysis.")
        return

    print(f"Signal: {signal['ticker']} -> "
          f"{signal['direction']} "
          f"({signal['confidence_pct']}% confidence)")
    print("Asking Andy for reasoning...\n")

    reasoning = ask_andy(signal)
    log_reasoning(signal, reasoning)

if __name__ == "__main__":
    run()
