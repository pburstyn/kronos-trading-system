import anthropic
import csv
import os
import sys
from dotenv import load_dotenv

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
# QQQ equivalent of critic.py (added October 18). System prompt and verdict
# parsing are imported from critic.py. ask_critic() is a copy rather than an
# import because critic.ask_critic() reads Kimi K3's reasoning from the SPY log
# via a module-level path. Keep its model and message shape in sync with
# critic.py by hand.
from critic import CRITIC_SYSTEM_PROMPT, parse_verdict

load_dotenv(os.path.expanduser("~/kronos-trading-system/.env"))

SIGNAL_LOG = os.path.expanduser("~/kronos-trading-system/logs/signal_log_qqq.csv")
REASONING_LOG = os.path.expanduser("~/kronos-trading-system/logs/reasoning_log_qqq.csv")
KIMI_K3_REASONING_LOG = os.path.expanduser("~/kronos-trading-system/logs/kimi_k3_reasoning_log_qqq.csv")
DECISIONS_LOG = os.path.expanduser("~/kronos-trading-system/logs/decisions_log_qqq.csv")

def get_latest_reasoning():
    if not os.path.isfile(REASONING_LOG):
        print("No QQQ reasoning log found. Run andy_reasoning_qqq.py first.")
        return None
    with open(REASONING_LOG, "r") as f:
        rows = list(csv.DictReader(f))
    if not rows:
        print("QQQ reasoning log is empty.")
        return None
    return rows[-1]

def get_kimi_k3_reasoning(timestamp):
    if not os.path.isfile(KIMI_K3_REASONING_LOG):
        return None
    with open(KIMI_K3_REASONING_LOG, "r") as f:
        rows = list(csv.DictReader(f))
    for row in rows:
        if row["timestamp"] == timestamp:
            return row["kimi_k3_reasoning"]
    return None

def ask_critic(row):
    client = anthropic.Anthropic(api_key=os.environ.get("ANTHROPIC_API_KEY"))
    kimi_k3_reasoning = get_kimi_k3_reasoning(row["timestamp"])
    msg = (
        "Ticker: " + row["ticker"] +
        " Direction: " + row["direction"] +
        " Confidence: " + row["confidence_pct"] + "%" +
        " Last close: " + row["last_close"] +
        " Andy's Reasoning: " + row["andy_reasoning"]
    )
    if kimi_k3_reasoning:
        msg += " Kimi K3's Reasoning: " + kimi_k3_reasoning
        msg += " Note whether Andy and Kimi K3 agree or disagree, and weigh that in your verdict."
    else:
        msg += " (Kimi K3 analysis not available for this signal.)"
    msg += " Issue your verdict now."
    response = client.messages.create(
        model="claude-opus-5",
        max_tokens=2000,
        system=CRITIC_SYSTEM_PROMPT,
        messages=[{"role": "user", "content": msg}]
    )
    # Opus 5 has thinking on by default, so content[0] is a ThinkingBlock, not
    # TextBlock -- find the text block instead of assuming position 0.
    for block in response.content:
        if block.type == "text":
            return block.text
    return ""

def log_decision(row, verdict, reason, confidence):
    os.makedirs(os.path.dirname(DECISIONS_LOG), exist_ok=True)
    file_exists = os.path.isfile(DECISIONS_LOG)
    kimi_k3_reasoning = get_kimi_k3_reasoning(row["timestamp"]) or "N/A"
    with open(DECISIONS_LOG, "a", newline="") as f:
        writer = csv.writer(f)
        if not file_exists:
            writer.writerow(["timestamp", "ticker", "direction", "signal_confidence_pct", "last_close", "andy_reasoning", "kimi_k3_reasoning", "critic_verdict", "critic_reason", "critic_confidence"])
        writer.writerow([row["timestamp"], row["ticker"], row["direction"], row["confidence_pct"], row["last_close"], row["andy_reasoning"], kimi_k3_reasoning, verdict, reason, confidence])
    print("\n-- Critic Verdict (QQQ) --")
    print("  " + verdict + " (Critic confidence: " + confidence + ")")
    print("  " + reason)
    print("Logged to: " + DECISIONS_LOG + "\n")

def get_latest_signal():
    if not os.path.isfile(SIGNAL_LOG):
        return None
    with open(SIGNAL_LOG, "r") as f:
        rows = list(csv.DictReader(f))
    if not rows:
        return None
    return rows[-1]

def run():
    signal = get_latest_signal()
    latest_direction = signal.get("direction", "").strip() if signal else None
    if latest_direction not in ("UP", "DOWN"):
        print(f"Latest QQQ signal is {latest_direction} — not actionable. Skipping Critic.")
        return
    print("Reading latest QQQ reasoning from Andy...")
    row = get_latest_reasoning()
    if not row:
        return
    print("Signal: " + row["ticker"] + " -> " + row["direction"] + " (" + row["confidence_pct"] + "% confidence)")
    print("Asking Critic to evaluate Andy's reasoning...\n")
    critic_response = ask_critic(row)
    verdict, reason, confidence = parse_verdict(critic_response)
    log_decision(row, verdict, reason, confidence)

if __name__ == "__main__":
    run()
