import requests
import csv
import os
import sys
from datetime import datetime
from dotenv import load_dotenv

sys.path.insert(0, os.path.expanduser("~/trading-system/scripts"))
from fred_data import get_macro_snapshot
from fear_greed import get_fear_greed
from news_context import get_news_context

load_dotenv(os.path.expanduser("~/trading-system/.env"))

SIGNAL_LOG = os.path.expanduser("~/trading-system/logs/signal_log.csv")
HY3_REASONING_LOG = os.path.expanduser("~/trading-system/logs/hy3_reasoning_log.csv")

OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"

today = datetime.now().strftime("%A, %B %d, %Y, %I:%M %p")
HY3_SYSTEM_PROMPT = f"""You are Hy3, an expert trading analyst assistant. Today is {today}. You receive a signal from a quantitative model and provide a short, honest reasoning analysis.

Your job is NOT to blindly agree with the signal. Your job is to:
1. Assess whether the signal makes sense given general market context
2. Identify one or two reasons it could be right
3. Identify one or two reasons it could be wrong
4. Give an overall credibility rating: LOW / MEDIUM / HIGH

Keep your response under 150 words. Be direct and critical.
Do not recommend actual trades. This is analysis only."""

def get_macro_context():
    context_lines = []
    try:
        macro = get_macro_snapshot()
        context_lines.append(f"Fed Funds Rate: {macro['fed_funds_rate']['value']}% (as of {macro['fed_funds_rate']['date']})")
        context_lines.append(f"CPI Index: {macro['cpi_inflation']['value']} (as of {macro['cpi_inflation']['date']})")
        context_lines.append(f"Unemployment Rate: {macro['unemployment_rate']['value']}% (as of {macro['unemployment_rate']['date']})")
    except Exception as e:
        context_lines.append(f"Macro data unavailable: {e}")

    try:
        fg = get_fear_greed()
        context_lines.append(f"CNN Fear & Greed Index: {round(fg['score'], 1)} ({fg['rating']})")
    except Exception as e:
        context_lines.append(f"Fear & Greed data unavailable: {e}")

    return "\n".join(context_lines)

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

def ask_hy3(signal):
    api_key = os.environ.get("OPENROUTER_API_KEY")
    votes = signal.get("votes", "No indicator data available")
    macro_context = get_macro_context()
    user_message = (
        "Here is the latest signal from the indicator model:\n\n"
        f"- Ticker:     {signal['ticker']}\n"
        f"- Direction:  {signal['direction']}\n"
        f"- Confidence: {signal['confidence_pct']}%\n"
        f"- Last close: ${signal['last_close']}\n"
        f"- Timestamp:  {signal['timestamp']}\n\n"
        "Indicator breakdown:\n"
        f"{votes}\n\n"
        "Macro and sentiment context:\n"
        f"{macro_context}\n\n"
        f"{get_news_context()}\n\n"
        "Please provide your reasoning analysis based on these specific indicators, factoring in the macro context, sentiment, and today's news where relevant."
    )

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }
    payload = {
        "model": "tencent/hy3:free",
        "messages": [
            {"role": "system", "content": HY3_SYSTEM_PROMPT},
            {"role": "user", "content": user_message}
        ],
        "max_tokens": 300
    }

    response = requests.post(OPENROUTER_URL, headers=headers, json=payload, timeout=30)
    response.raise_for_status()
    result = response.json()

    choices = result.get("choices")
    if not choices:
        print(f"WARNING: Hy3 response had no choices: {result}")
        return None

    content = choices[0].get("message", {}).get("content")
    if not content:
        print(f"WARNING: Hy3 response had no message content: {result}")
        return None

    return content

def log_reasoning(signal, reasoning):
    if not reasoning:
        reasoning = "Hy3 returned no reasoning"

    os.makedirs(os.path.dirname(HY3_REASONING_LOG), exist_ok=True)
    file_exists = os.path.isfile(HY3_REASONING_LOG)
    with open(HY3_REASONING_LOG, "a", newline="") as f:
        writer = csv.writer(f)
        if not file_exists:
            writer.writerow([
                "timestamp", "ticker", "direction",
                "confidence_pct", "last_close", "hy3_reasoning"
            ])
        writer.writerow([
            signal['timestamp'],
            signal['ticker'],
            signal['direction'],
            signal['confidence_pct'],
            signal['last_close'],
            reasoning.replace("\n", " ")
        ])
    print("\n-- Hy3's Reasoning --")
    print(reasoning)
    print("----------------------")
    print(f"Logged to: {HY3_REASONING_LOG}\n")

def run():
    print("Reading latest signal...")
    signal = get_latest_signal()
    if not signal:
        return
    direction = signal.get("direction", "").strip()
    if direction not in ("UP", "DOWN"):
        print(f"Signal is {direction} -- not actionable. Skipping Hy3 analysis.")
        return

    print(f"Signal: {signal['ticker']} -> {signal['direction']} ({signal['confidence_pct']}% confidence)")
    print("Asking Hy3 for reasoning...\n")

    reasoning = ask_hy3(signal)
    log_reasoning(signal, reasoning)

if __name__ == "__main__":
    run()
