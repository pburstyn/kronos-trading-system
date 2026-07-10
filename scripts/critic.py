import anthropic
import csv
import os
import re
from datetime import datetime
from dotenv import load_dotenv

load_dotenv(os.path.expanduser("~/trading-system/.env"))

REASONING_LOG = os.path.expanduser("~/trading-system/logs/reasoning_log.csv")
HY3_REASONING_LOG = os.path.expanduser("~/trading-system/logs/hy3_reasoning_log.csv")
DECISIONS_LOG = os.path.expanduser("~/trading-system/logs/decisions_log.csv")

today = datetime.now().strftime("%A, %B %d, %Y, %I:%M %p")
CRITIC_SYSTEM_PROMPT = (
    f"You are a skeptical trading risk analyst. Today is {today}. "
    "Your job is to review one or two analysts' reasoning (Andy and possibly Hy3) and find flaws, contradictions, or overconfidence. "
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

def get_hy3_reasoning(timestamp):
    if not os.path.isfile(HY3_REASONING_LOG):
        return None
    with open(HY3_REASONING_LOG, "r") as f:
        rows = list(csv.DictReader(f))
    for row in rows:
        if row["timestamp"] == timestamp:
            return row["hy3_reasoning"]
    return None

def ask_critic(row):
    client = anthropic.Anthropic(api_key=os.environ.get("ANTHROPIC_API_KEY"))
    hy3_reasoning = get_hy3_reasoning(row["timestamp"])
    msg = (
        "Ticker: " + row["ticker"] +
        " Direction: " + row["direction"] +
        " Confidence: " + row["confidence_pct"] + "%" +
        " Last close: " + row["last_close"] +
        " Andy's Reasoning: " + row["andy_reasoning"]
    )
    if hy3_reasoning:
        msg += " Hy3's Reasoning: " + hy3_reasoning
        msg += " Note whether Andy and Hy3 agree or disagree, and weigh that in your verdict."
    else:
        msg += " (Hy3 analysis not available for this signal.)"
    msg += " Issue your verdict now."
    response = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=250,
        system=CRITIC_SYSTEM_PROMPT,
        messages=[{"role": "user", "content": msg}]
    )
    return response.content[0].text

def parse_verdict(critic_response):
    # Claude Haiku sometimes wraps labels/values in markdown bold
    # (e.g. "**VERDICT: FLAG**"), which a plain startswith("VERDICT:")
    # never matches — strip markdown emphasis before line-matching.
    cleaned = critic_response.replace("*", "")
    lines = cleaned.strip().split("\n")
    verdict = "UNKNOWN"
    reason = critic_response
    confidence = "UNKNOWN"
    for line in lines:
        line = line.strip()
        if not line:
            continue
        upper = line.upper()
        if upper.startswith("VERDICT:"):
            match = re.search(r"\b(PASS|FLAG|VETO)\b", line, re.IGNORECASE)
            if match:
                verdict = match.group(1).upper()
        elif upper.startswith("REASON:"):
            reason = line.split(":", 1)[1].strip()
        elif upper.startswith("CONFIDENCE_IN_VERDICT:"):
            match = re.search(r"\b(LOW|MEDIUM|HIGH)\b", line, re.IGNORECASE)
            if match:
                confidence = match.group(1).upper()
    return verdict, reason, confidence

def log_decision(row, verdict, reason, confidence):
    os.makedirs(os.path.dirname(DECISIONS_LOG), exist_ok=True)
    file_exists = os.path.isfile(DECISIONS_LOG)
    hy3_reasoning = get_hy3_reasoning(row["timestamp"]) or "N/A"
    with open(DECISIONS_LOG, "a", newline="") as f:
        writer = csv.writer(f)
        if not file_exists:
            writer.writerow(["timestamp", "ticker", "direction", "signal_confidence_pct", "last_close", "andy_reasoning", "hy3_reasoning", "critic_verdict", "critic_reason", "critic_confidence"])
        writer.writerow([row["timestamp"], row["ticker"], row["direction"], row["confidence_pct"], row["last_close"], row["andy_reasoning"], hy3_reasoning, verdict, reason, confidence])
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