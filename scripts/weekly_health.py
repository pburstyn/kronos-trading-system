import json
import os
import sys
from datetime import datetime, timedelta

import requests
from dotenv import load_dotenv

load_dotenv(os.path.expanduser("~/trading-system/.env"))

OPENCLAW_CONFIG = "/mnt/c/Users/openc/.openclaw/openclaw.json"
PIPELINE_LOG = os.path.expanduser("~/trading-system/logs/pipeline.log")
LOOKBACK_DAYS = 7

# Marker strings unique enough to tell whether a given script ran in a day's
# pipeline.log block. andy_reasoning.py and kimi_k3_reasoning.py both print an
# identical "Reading latest signal..." first line, so each script's markers
# use the distinctive text that follows instead. signal_logger_qqq.py's own
# first line already differs from signal_logger.py's ("...QQQ..." vs.
# "...SPY..."), so no disambiguation trick is needed there.
EXPECTED_SCRIPTS = {
    "signal_logger": ["Fetching data for SPY..."],
    "signal_logger_qqq": ["Fetching data for QQQ..."],
    "andy_reasoning": ["Skipping Andy analysis.", "Asking Andy for reasoning", "Andy's Reasoning"],
    "kimi_k3_reasoning": ["Skipping Kimi K3 analysis.", "Asking Kimi K3 for reasoning", "Kimi K3's Reasoning"],
    "critic": ["Skipping Critic.", "Reading latest reasoning from Andy", "Critic Verdict"],
    "trade_logic": ["-- Trade Decision --"],
    "alpaca_execute": ["-- Alpaca Execute --"],
}

FLAG_KEYWORDS = ["ERROR", "Traceback", "SKIP"]
MAX_FLAG_LINES_PER_DAY = 10


def get_telegram_config():
    with open(OPENCLAW_CONFIG) as f:
        cfg = json.load(f)
    token = cfg["channels"]["telegram"]["botToken"]
    chat_id = os.environ.get("TELEGRAM_CHAT_ID")
    return token, chat_id


def send_telegram(message):
    try:
        token, chat_id = get_telegram_config()
        url = f"https://api.telegram.org/bot{token}/sendMessage"
        requests.post(url, data={"chat_id": chat_id, "text": message}, timeout=10)
        print("  Telegram sent.")
    except Exception as e:
        print(f"  WARNING: Telegram send failed: {e}")


def parse_run_date(line):
    """Parse the date out of a 'Pipeline starting' line, e.g.
    'Wed Sep  4 18:00:01 PDT 2026 — Pipeline starting'. str.split() collapses
    the double space that appears before single-digit days."""
    parts = line.split()
    try:
        return datetime.strptime(f"{parts[1]} {parts[2]} {parts[5]}", "%b %d %Y").date()
    except (IndexError, ValueError):
        return None


def split_into_daily_blocks(lines):
    """Return {date: block_text} for each 'Pipeline starting' .. next
    'Pipeline starting' (or end of file) span, so a run that crashed before
    ever printing 'Pipeline complete' is still captured on its own day
    instead of being silently swallowed into the following day's block."""
    blocks = {}
    current_date = None
    current_lines = []
    for line in lines:
        if "— Pipeline starting" in line:
            if current_date is not None:
                blocks[current_date] = "\n".join(current_lines)
            current_date = parse_run_date(line)
            current_lines = [line]
        elif current_date is not None:
            current_lines.append(line)
    if current_date is not None:
        blocks[current_date] = "\n".join(current_lines)
    return blocks


def expected_weekdays(lookback_days):
    """Mon-Fri calendar dates in the trailing window, excluding today (today's
    pipeline run hasn't happened yet at 7:10am when this check fires)."""
    today = datetime.now().date()
    days = [today - timedelta(days=offset) for offset in range(1, lookback_days + 1)]
    return sorted(d for d in days if d.weekday() < 5)


def check_day(block):
    """Return (missing_scripts, flag_lines) for one day's pipeline block."""
    missing_scripts = [
        script for script, markers in EXPECTED_SCRIPTS.items()
        if not any(marker in block for marker in markers)
    ]
    flag_lines = [
        line.strip() for line in block.splitlines()
        if any(keyword in line for keyword in FLAG_KEYWORDS)
    ]
    return missing_scripts, flag_lines


def build_message(findings, missing_days):
    now = datetime.now().strftime("%Y-%m-%d")
    if not findings and not missing_days:
        # Built from EXPECTED_SCRIPTS.keys() rather than a hand-maintained list so
        # adding a new checked script (e.g. signal_logger_qqq) can't leave this
        # message silently stale, the way the SPY-only script list did before.
        script_list = ", ".join(EXPECTED_SCRIPTS.keys())
        return (
            f"Kronos Weekly Health Check — {now}\n\n"
            f"All clear. Every weekday pipeline run in the last {LOOKBACK_DAYS} days completed "
            f"with no errors, tracebacks, or skips, and all expected scripts "
            f"({script_list}) ran."
        )

    lines = [f"Kronos Weekly Health Check — {now}", ""]

    if missing_days:
        lines.append("No pipeline run found for:")
        for d in missing_days:
            lines.append(f"  - {d.strftime('%a %Y-%m-%d')}")
        lines.append("")

    for date, missing, flags in findings:
        lines.append(f"{date.strftime('%a %Y-%m-%d')}:")
        if missing:
            lines.append(f"  Missing/failed scripts: {', '.join(missing)}")
        for flag in flags[:MAX_FLAG_LINES_PER_DAY]:
            lines.append(f"  {flag}")
        if len(flags) > MAX_FLAG_LINES_PER_DAY:
            lines.append(f"  ... and {len(flags) - MAX_FLAG_LINES_PER_DAY} more flagged line(s)")
        lines.append("")

    return "\n".join(lines).rstrip()


def run(dry_run=False):
    print("\n-- Weekly Pipeline Health Check --")

    if not os.path.isfile(PIPELINE_LOG):
        message = "Kronos Weekly Health Check\n\nWARNING: pipeline.log not found."
        print(message)
        if not dry_run:
            send_telegram(message)
        print("----------------------------------\n")
        return

    with open(PIPELINE_LOG) as f:
        lines = f.readlines()

    cutoff = datetime.now().date() - timedelta(days=LOOKBACK_DAYS)
    blocks = {d: b for d, b in split_into_daily_blocks(lines).items() if d and d >= cutoff}

    findings = []
    for date in sorted(blocks):
        missing, flags = check_day(blocks[date])
        if missing or flags:
            findings.append((date, missing, flags))

    missing_days = [d for d in expected_weekdays(LOOKBACK_DAYS) if d not in blocks]

    message = build_message(findings, missing_days)
    print(message)

    if dry_run:
        print("  DRY RUN — Telegram send skipped.")
    else:
        send_telegram(message)
    print("----------------------------------\n")


if __name__ == "__main__":
    run(dry_run="--dry-run" in sys.argv)
