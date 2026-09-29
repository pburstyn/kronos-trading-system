import csv
import os
import subprocess
from datetime import datetime

import requests

# Fetches the live GitHub copy rather than the local file, so the briefing
# reflects what's actually pushed -- not uncommitted local edits sitting in
# the working tree. Falls back to the local file (clearly labeled) if the
# fetch fails, rather than dropping CLAUDE.md from the briefing entirely.
CLAUDE_MD_URL = "https://raw.githubusercontent.com/pburstyn/kronos-trading-system/main/CLAUDE.md"
LOCAL_CLAUDE_MD = os.path.expanduser("~/trading-system/CLAUDE.md")

SIGNAL_LOG = os.path.expanduser("~/trading-system/logs/signal_log.csv")
QQQ_SIGNAL_LOG = os.path.expanduser("~/trading-system/logs/signal_log_qqq.csv")
ALPACA_ORDERS_LOG = os.path.expanduser("~/trading-system/logs/alpaca_orders.csv")


def fetch_claude_md():
    try:
        resp = requests.get(CLAUDE_MD_URL, timeout=15)
        resp.raise_for_status()
        return resp.text
    except Exception as e:
        print(f"  WARNING: Could not fetch CLAUDE.md from GitHub ({e}); falling back to local file.")
        try:
            with open(LOCAL_CLAUDE_MD) as f:
                return f.read() + "\n\n[NOTE: this is the local copy -- GitHub fetch failed, may not match what's pushed.]"
        except Exception as e2:
            return f"[CLAUDE.md unavailable -- GitHub fetch failed ({e}) and local read failed ({e2})]"


def read_last_rows(path, n):
    """None means the file doesn't exist yet; [] means it exists but is empty --
    kept distinct so the briefing can say which one happened."""
    if not os.path.isfile(path):
        return None
    with open(path, "r", newline="") as f:
        rows = list(csv.DictReader(f))
    return rows[-n:]


def _money(val):
    """Some historical alpaca_orders.csv rows carry float-precision artifacts
    (e.g. "739.3399999999999") from an old computation, stored as plain text in
    the CSV -- round for display only, without touching the source file. Falls
    back to the raw value if it isn't parseable as a number."""
    try:
        return f"{float(val):.2f}"
    except (TypeError, ValueError):
        return val


def format_signal_rows(rows, none_label="no rows yet"):
    if rows is None:
        return "  (file not found)"
    if not rows:
        return f"  ({none_label})"
    lines = []
    for r in rows:
        lines.append(
            f"  {r.get('timestamp', '')} | {r.get('ticker', '')} | {r.get('direction', '')} "
            f"| conf={r.get('confidence_pct', '')}% | close=${_money(r.get('last_close', ''))}"
        )
        votes = r.get("votes", "")
        if votes:
            lines.append(f"      {votes}")
    return "\n".join(lines)


def format_order_rows(rows):
    if rows is None:
        return "  (file not found)"
    if not rows:
        return "  (no orders yet)"
    lines = []
    for r in rows:
        lines.append(
            f"  {r.get('timestamp', '')} | {r.get('direction', '')} | notional=${_money(r.get('notional', ''))} "
            f"qty={r.get('qty', '')} entry=${_money(r.get('entry_price', ''))} stop=${_money(r.get('stop_loss', ''))} "
            f"tp=${_money(r.get('take_profit_low', ''))} | verdict={r.get('verdict', '')} | status={r.get('status', '')}"
        )
    return "\n".join(lines)


def build_briefing():
    spy_rows = read_last_rows(SIGNAL_LOG, 5)
    qqq_rows = read_last_rows(QQQ_SIGNAL_LOG, 3)
    order_rows = read_last_rows(ALPACA_ORDERS_LOG, 5)
    claude_md = fetch_claude_md()
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    parts = [
        f"KRONOS SESSION BRIEFING -- generated {now}",
        "Context briefing for the Kronos Trading System project (paste this at the",
        "start of a new Claude session). Live status first, full CLAUDE.md reference below.",
        "=" * 70,
        "",
        "## Last 5 SPY Signals (logs/signal_log.csv)",
        format_signal_rows(spy_rows),
        "",
        "## Last 3 QQQ Signals (logs/signal_log_qqq.csv) -- signal-capture-only, not traded",
        format_signal_rows(qqq_rows),
        "",
        "## Last 5 Alpaca Paper Orders (logs/alpaca_orders.csv)",
        format_order_rows(order_rows),
        "",
        "=" * 70,
        "## Full CLAUDE.md (fetched live from GitHub main branch)",
        "=" * 70,
        claude_md,
    ]
    return "\n".join(parts)


def copy_to_clipboard(text):
    """WSL2-specific: pipes to Windows' clip.exe via interop. Verified UTF-8
    round-trips correctly through clip.exe in this environment (em dashes,
    curly quotes, accented characters all survive intact) -- no iconv/UTF-16LE
    conversion needed here, unlike some WSL setups."""
    try:
        subprocess.run(["clip.exe"], input=text.encode("utf-8"), check=True)
        return True
    except Exception as e:
        print(f"  WARNING: Could not copy to clipboard ({e}).")
        return False


def run():
    print("\n-- Kronos Session Init --")
    briefing = build_briefing()
    print(f"  Briefing built ({len(briefing)} characters).")
    if copy_to_clipboard(briefing):
        print("  Copied to clipboard. Paste into a new Claude chat session.")
    else:
        print("  Clipboard copy failed -- printing briefing instead:\n")
        print(briefing)
    print("--------------------------\n")


if __name__ == "__main__":
    run()
