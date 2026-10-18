import csv
import os
import sys

sys.path.insert(0, os.path.expanduser("~/kronos-trading-system/scripts"))
# QQQ equivalent of kimi_k3_reasoning.py (added October 18). Prompt, model and
# context are imported from kimi_k3_reasoning.py. Only the log files differ.
from kimi_k3_reasoning import ask_kimi_k3

SIGNAL_LOG = os.path.expanduser("~/kronos-trading-system/logs/signal_log_qqq.csv")
KIMI_K3_REASONING_LOG = os.path.expanduser("~/kronos-trading-system/logs/kimi_k3_reasoning_log_qqq.csv")

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
    if not reasoning:
        reasoning = "Kimi K3 returned no reasoning"

    os.makedirs(os.path.dirname(KIMI_K3_REASONING_LOG), exist_ok=True)
    file_exists = os.path.isfile(KIMI_K3_REASONING_LOG)
    with open(KIMI_K3_REASONING_LOG, "a", newline="") as f:
        writer = csv.writer(f)
        if not file_exists:
            writer.writerow([
                "timestamp", "ticker", "direction",
                "confidence_pct", "last_close", "kimi_k3_reasoning"
            ])
        writer.writerow([
            signal['timestamp'],
            signal['ticker'],
            signal['direction'],
            signal['confidence_pct'],
            signal['last_close'],
            reasoning.replace("\n", " ")
        ])
    print("\n-- Kimi K3's Reasoning (QQQ) --")
    print(reasoning)
    print("----------------------")
    print(f"Logged to: {KIMI_K3_REASONING_LOG}\n")

def run():
    print("Reading latest QQQ signal...")
    signal = get_latest_signal()
    if not signal:
        return
    direction = signal.get("direction", "").strip()
    if direction not in ("UP", "DOWN"):
        print(f"QQQ signal is {direction} -- not actionable. Skipping Kimi K3 analysis.")
        return

    print(f"Signal: {signal['ticker']} -> {signal['direction']} ({signal['confidence_pct']}% confidence)")
    print("Asking Kimi K3 for reasoning...\n")

    reasoning = ask_kimi_k3(signal)
    log_reasoning(signal, reasoning)

if __name__ == "__main__":
    run()
