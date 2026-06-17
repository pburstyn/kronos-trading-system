import requests
import csv
import os
from datetime import datetime
from dotenv import load_dotenv

load_dotenv(os.path.expanduser("~/trading-system/.env"))

SIGNAL_LOG = os.path.expanduser("~/trading-system/logs/signal_log.csv")
KIMI_REASONING_LOG = os.path.expanduser("~/trading-system/logs/kimi_reasoning_log.csv")

NIM_URL = "https://integrate.api.nvidia.com/v1/chat/completions"

today = datetime.now().strftime("%A, %B %d, %Y, %I:%M %p")
KIMI_SYSTEM_PROMPT = f"""You are Kimi, an expert trading analyst assistant. Today is {today}. You receive a signal from a quantitative model and provide a short, honest reasoning analysis.

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

def ask_kimi(signal):
    api_key = os.environ.get("NVIDIA_API_KEY")
    votes = signal.get("votes", "No indicator data available")
    user_message = (
        "Here is the latest signal from the indicator model:\n\n"
        f"- Ticker:     {signal['ticker']}\n"
        f"- Direction:  {signal['direction']}\n"
        f"- Confidence: {signal['confidence_pct']}%\n"
        f"- Last close: ${signal['last_close']}\n"
        f"- Timestamp:  {signal['timestamp']}\n\n"
        "Indicator breakdown:\n"
        f"{votes}\n\n"
        "Please provide your reasoning analysis based on these specific indicators."
    )

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }
    payload = {
        "model": "moonshotai/kimi-k2.6",
        "messages": [
            {"role": "system", "content": KIMI_SYSTEM_PROMPT},
            {"role": "user", "content": user_message}
        ],
        "max_tokens": 300
    }

    response = requests.post(NIM_URL, headers=headers, json=payload, timeout=30)
    response.raise_for_status()
    result = response.json()
    return result["choices"][0]["message"]["content"]

def log_reasoning(signal, reasoning):
    os.makedirs(os.path.dirname(KIMI_REASONING_LOG), exist_ok=True)
    file_exists = os.path.isfile(KIMI_REASONING_LOG)
    with open(KIMI_REASONING_LOG, "a", newline="") as f:
        writer = csv.writer(f)
        if not file_exists:
            writer.writerow([
                "timestamp", "ticker", "direction",
                "confidence_pct", "last_close", "kimi_reasoning"
            ])
        writer.writerow([
            signal['timestamp'],
            signal['ticker'],
            signal['direction'],
            signal['confidence_pct'],
            signal['last_close'],
            reasoning.replace("\n", " ")
        ])
    print("\n-- Kimi's Reasoning --")
    print(reasoning)
    print("----------------------")
    print(f"Logged to: {KIMI_REASONING_LOG}\n")

def run():
    print("Reading latest signal...")
    signal = get_latest_signal()
    if not signal:
        return
    direction = signal.get("direction", "").strip()
    if direction not in ("UP", "DOWN"):
        print(f"Signal is {direction} -- not actionable. Skipping Kimi analysis.")
        return

    print(f"Signal: {signal['ticker']} -> {signal['direction']} ({signal['confidence_pct']}% confidence)")
    print("Asking Kimi for reasoning...\n")

    reasoning = ask_kimi(signal)
    log_reasoning(signal, reasoning)

if __name__ == "__main__":
    run()
