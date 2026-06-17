import anthropic
import csv
import os
from datetime import datetime
from dotenv import load_dotenv

load_dotenv(os.path.expanduser("~/trading-system/.env"))

REASONING_LOG = os.path.expanduser("~/trading-system/logs/reasoning_log.csv")
KIMI_REASONING_LOG = os.path.expanduser("~/trading-system/logs/kimi_reasoning_log.csv")
DECISIONS_LOG = os.path.expanduser("~/trading-system/logs/decisions_log.csv")

today = datetime.now().strftime("%A, %B %d, %Y, %I:%M %p")
CRITIC_SYSTEM_PROMPT = (
    f"You are a skeptical trading risk analyst. Today is {today}. "
    "Your job is to review one or two analysts' reasoning (Andy and possibly Kimi) and find flaws, contradictions, or overconfidence. "
    "If both analysts agree, you may weigh that toward PASS. If they disagree, lean toward FLAG and explain which analyst's reasoning is more credible and why. "
    "You must respond in this exact format and nothing else: "
    "VERDICT: [PASS or FLAG or VETO] "
    "REASON: [One or two sentences explaining your verdict] "
    "CONFIDENCE_IN_VERDICT: [LOW or MEDIUM or HIGH] "
    "PASS means reasoning is sound. FLAG means notable weaknesses. VETO means flawed or contradictory. "
    "Be harsh. Your job is to protect against bad trades. If in doubt, FLAG rather than PASS."
)

def get_latest_reasoning():
    if not os.path.isfile(REASONING_LOG):
        print("No reasoning log found. Run andy_reasoning.py first.")
        return None
    with open(REASONING_LOG, "r") as f:
        rows = list(csv.DictReader(f))
    if not rows:
        print("Reasoning log is empty.")
        return None
    return rows[-1]

def get_kimi_reasoning(timestamp):
    if not os.path.isfile(KIMI_REASONING_LOG):
        return None
    with open(KIMI_REASONING_LOG, "r") as f:
        rows = list(csv.DictReader(f))
    for row in rows:
        if row["timestamp"] == timestamp:
            return row["kimi_reasoning"]
    return None

def ask_critic(row):
    client = anthropic.Anthropic(api_key=os.environ.get("ANTHROPIC_API_KEY"))
    kimi_reasoning = get_kimi_reasoning(row["timestamp"])
    msg = (
        "Ticker: " + row["ticker"] +
        " Direction: " + row["direction"] +
        " Confidence: " + row["confidence_pct"] + "%" +
        " Last close: " + row["last_close"] +
        " Andy's Reasoning: " + row["andy_reasoning"]
    )
    if kimi_reasoning:
        msg += " Kimi's Reasoning: " + kimi_reasoning
        msg += " Note whether Andy and Kimi agree or disagree, and weigh that in your verdict."
    else:
        msg += " (Kimi analysis not available for this signal.)"
    msg += " Issue your verdict now."
    response = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=250,
        system=CRITIC_SYSTEM_PROMPT,
        messages=[{"role": "user", "content": msg}]
    )
    return response.content[0].text

def parse_verdict(critic_response):
    lines = critic_response.strip().split("\n")
    verdict = "UNKNOWN"
    reason = critic_response
    confidence = "UNKNOWN"
    for line in lines:
        if line.startswith("VERDICT:"):
            verdict = line.replace("VERDICT:", "").strip()
        elif line.startswith("REASON:"):
            reason = line.replace("REASON:", "").strip()
        elif line.startswith("CONFIDENCE_IN_VERDICT:"):
            confidence = line.replace("CONFIDENCE_IN_VERDICT:", "").strip()
    return verdict, reason, confidence

def log_decision(row, verdict, reason, confidence):
    os.makedirs(os.path.dirname(DECISIONS_LOG), exist_ok=True)
    file_exists = os.path.isfile(DECISIONS_LOG)
    kimi_reasoning = get_kimi_reasoning(row["timestamp"]) or "N/A"
    with open(DECISIONS_LOG, "a", newline="") as f:
        writer = csv.writer(f)
        if not file_exists:
            writer.writerow(["timestamp", "ticker", "direction", "signal_confidence_pct", "last_close", "andy_reasoning", "kimi_reasoning", "critic_verdict", "critic_reason", "critic_confidence"])
        writer.writerow([row["timestamp"], row["ticker"], row["direction"], row["confidence_pct"], row["last_close"], row["andy_reasoning"], kimi_reasoning, verdict, reason, confidence])
    verdict_symbols = {"PASS": "PASS", "FLAG": "FLAG", "VETO": "VETO"}
    symbol = verdict_symbols.get(verdict, "?")
    print("\n-- Critic Verdict --")
    print("  " + symbol + " (Critic confidence: " + confidence + ")")
    print("  " + reason)
    print("Logged to: " + DECISIONS_LOG + "\n")

SIGNAL_LOG = os.path.expanduser("~/trading-system/logs/signal_log.csv")

def get_latest_signal_direction():
    if not os.path.isfile(SIGNAL_LOG):
        return None
    with open(SIGNAL_LOG, "r") as f:
        rows = list(csv.DictReader(f))
    if not rows:
        return None
    return rows[-1].get("direction", "").strip()

def run():
    latest_direction = get_latest_signal_direction()
    if latest_direction not in ("UP", "DOWN"):
        print(f"Latest signal is {latest_direction} — not actionable. Skipping Critic.")
        return
    print("Reading latest reasoning from Andy...")
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