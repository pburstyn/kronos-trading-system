import anthropic
import csv
import os
import json
from datetime import datetime
from dotenv import load_dotenv

# Load API key from .env file
load_dotenv(os.path.expanduser("~/trading-system/.env"))

# ── SETTINGS ──────────────────────────────────────
SIGNAL_LOG   = os.path.expanduser(
    "~/trading-system/logs/signal_log.csv"
)
REASONING_LOG = os.path.expanduser(
    "~/trading-system/logs/reasoning_log.csv"
)
# ──────────────────────────────────────────────────

ANDY_SYSTEM_PROMPT = """You are Andy, an expert trading analyst assistant. You receive a signal from a quantitative model and provide a short, honest reasoning analysis.

Your job is NOT to blindly agree with the signal. Your job is to:
1. Assess whether the signal makes sense given general market context
2. Identify one or two reasons it could be right
3. Identify one or two reasons it could be wrong
4. Give an overall credibility rating: LOW / MEDIUM / HIGH

Keep your response under 150 words. Be direct and critical.
Do not recommend actual trades. This is analysis only."""
def get_latest_signal():
    if not os.path.isfile(SIGNAL_LOG):
        print("No signal log found. Run signal_logger.py first.")
        return None

    with open(SIGNAL_LOG, "r") as f:
        rows = list(csv.DictReader(f))

    if not rows:
        print("Signal log is empty.")
        return None

    return rows[-1]

def ask_andy(signal):
    client = anthropic.Anthropic(
        api_key=os.environ.get("ANTHROPIC_API_KEY")
    )

    user_message = (
        "Here is the latest signal from the Kronos model:\n\n"
        f"- Ticker:     {signal['ticker']}\n"
        f"- Direction:  {signal['direction']}\n"
        f"- Confidence: {signal['confidence_pct']}%\n"
        f"- Last close: ${signal['last_close']}\n"
        f"- Timestamp:  {signal['timestamp']}\n\n"
        "Please provide your reasoning analysis."
    )

    message = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=300,
        system=ANDY_SYSTEM_PROMPT,
        messages=[
            {"role": "user", "content": user_message}
        ]
    )

    return message.content[0].text
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

    print("\n── Andy's Reasoning ──────────────────────")
    print(reasoning)
    print("──────────────────────────────────────────")
    print(f"Logged to: {REASONING_LOG}\n")

def run():
    print("Reading latest signal...")
    signal = get_latest_signal()
    if not signal:
        return

    print(f"Signal: {signal['ticker']} -> "
          f"{signal['direction']} "
          f"({signal['confidence_pct']}% confidence)")
    print("Asking Andy for reasoning...\n")

    reasoning = ask_andy(signal)
    log_reasoning(signal, reasoning)

if __name__ == "__main__":
    run()
