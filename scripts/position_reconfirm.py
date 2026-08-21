import csv
import os
import re
import sys
from datetime import datetime

from dotenv import load_dotenv

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from trade_logic import get_latest_decision_row, extract_verdict
from telegram_notify import get_telegram_config, send_telegram

load_dotenv(os.path.expanduser("~/trading-system/.env"))

from alpaca.trading.client import TradingClient
from alpaca.trading.enums import PositionSide

TICKER = "SPY"
SIGNAL_LOG = os.path.expanduser("~/trading-system/logs/signal_log.csv")


def get_open_position(client):
    """Returns (direction, position) for the open TICKER position, or (None, None) if flat.
    direction is 'UP' for a long position, 'DOWN' for a short position."""
    try:
        position = client.get_open_position(TICKER)
    except Exception:
        return None, None
    direction = "UP" if position.side == PositionSide.LONG else "DOWN"
    return direction, position


def build_contradiction_message(position_direction, position, signal_direction, confidence, verdict, today_date):
    qty = abs(float(position.qty))
    qty = int(qty) if qty == int(qty) else qty
    return (
        f"Kronos Position Alert — {today_date}\n"
        f"\n"
        f"Open {position_direction} position ({qty} shares, avg entry ${position.avg_entry_price}) "
        f"CONTRADICTS today's signal: {signal_direction} at {confidence}% confidence (verdict: {verdict}).\n"
        f"\n"
        f"Position was NOT closed automatically — review manually."
    )


def get_latest_signal_row():
    if not os.path.isfile(SIGNAL_LOG):
        return None
    with open(SIGNAL_LOG, "r") as f:
        rows = list(csv.DictReader(f))
    if not rows:
        return None
    return rows[-1]


def get_signal_lean(row):
    """Return (lean, bull_votes, bear_votes) for a signal_log row.
    lean is 'UP'/'DOWN' when the signal (or its NEUTRAL/WEAK vote tally) leans
    that way, or None if bull and bear votes are tied. Handles the vote-count
    format used by both the NEUTRAL 'did not meet MIN_VOTES' line and the
    plain per-indicator vote entries (UP/DOWN/WEAK rows)."""
    direction = row.get("direction", "").strip()
    votes = row.get("votes", "")

    match = re.search(r"bull_votes=(\d+)\s+bear_votes=(\d+)", votes)
    if match:
        bull_votes, bear_votes = int(match.group(1)), int(match.group(2))
    else:
        segments = [seg.strip() for seg in votes.split("|")]
        bull_votes = sum(1 for seg in segments if seg.endswith("bullish"))
        bear_votes = sum(1 for seg in segments if seg.endswith("bearish"))

    if direction == "UP":
        return "UP", bull_votes, bear_votes
    if direction == "DOWN":
        return "DOWN", bull_votes, bear_votes
    if bull_votes > bear_votes:
        return "UP", bull_votes, bear_votes
    if bear_votes > bull_votes:
        return "DOWN", bull_votes, bear_votes
    return None, bull_votes, bear_votes


def build_signal_lean_message(position_direction, position, lean, bull_votes, bear_votes, today_date):
    qty = abs(float(position.qty))
    qty = int(qty) if qty == int(qty) else qty
    lean_label = "bearish" if lean == "DOWN" else "bullish"
    return (
        f"Kronos Position Alert — {today_date}\n"
        f"\n"
        f"Open {position_direction} position ({qty} shares, avg entry ${position.avg_entry_price}) "
        f"CONTRADICTS today's signal lean: {lean_label} (bull_votes={bull_votes}, bear_votes={bear_votes}).\n"
        f"No decisions_log entry for today — this check is based on signal_log only.\n"
        f"\n"
        f"Position was NOT closed automatically — review manually."
    )


def send_alert(message):
    try:
        token, chat_id = get_telegram_config()
        send_telegram(token, chat_id, message)
        print("  Telegram alert sent.")
    except Exception as e:
        print(f"  WARNING: Telegram send failed: {e}")


def reconfirm_from_decision(row, position_direction, position, today_date):
    signal_direction = row["direction"]

    if signal_direction not in ("UP", "DOWN"):
        print(f"  Open {position_direction} position; today's signal is {signal_direction} — no contradiction check needed.")
        return

    if signal_direction == position_direction:
        print(f"  Open {position_direction} position confirmed by today's {signal_direction} signal.")
        return

    verdict = extract_verdict(row)
    confidence = row.get("signal_confidence_pct", "?")
    print(f"  CONTRADICTION: open {position_direction} position vs. today's {signal_direction} signal ({confidence}%, verdict {verdict}).")

    message = build_contradiction_message(position_direction, position, signal_direction, confidence, verdict, today_date)
    send_alert(message)


def reconfirm_from_signal(position_direction, position, today_date):
    row = get_latest_signal_row()
    if not row:
        print("  No signal_log entry found either.")
        return

    row_date = row["timestamp"].split(" ")[0]
    if row_date != today_date:
        print(f"  SKIP: Latest signal_log entry is from {row_date}, not today ({today_date}).")
        return

    lean, bull_votes, bear_votes = get_signal_lean(row)
    if lean is None:
        print(f"  Open {position_direction} position; today's signal has no clear lean (bull_votes={bull_votes}, bear_votes={bear_votes}) — no contradiction check needed.")
        return

    if lean == position_direction:
        print(f"  Open {position_direction} position confirmed by today's signal lean ({lean}, bull_votes={bull_votes}, bear_votes={bear_votes}).")
        return

    print(f"  CONTRADICTION: open {position_direction} position vs. today's signal lean {lean} (bull_votes={bull_votes}, bear_votes={bear_votes}).")
    message = build_signal_lean_message(position_direction, position, lean, bull_votes, bear_votes, today_date)
    send_alert(message)


def run():
    print("\n-- Position Re-confirmation --")

    api_key = os.environ.get("ALPACA_API_KEY")
    secret_key = os.environ.get("ALPACA_SECRET_KEY")
    client = TradingClient(api_key, secret_key, paper=True)

    position_direction, position = get_open_position(client)
    if position_direction is None:
        print("  No open position — nothing to reconfirm.")
        print("------------------------------\n")
        return

    today_date = datetime.now().strftime("%Y-%m-%d")

    row = get_latest_decision_row()
    row_date = row["timestamp"].split(" ")[0] if row else None

    if row and row_date == today_date:
        reconfirm_from_decision(row, position_direction, position, today_date)
    else:
        stale_note = f"from {row_date}" if row else "found"
        print(f"  No decisions_log entry for today (latest {stale_note}) — falling back to signal_log.")
        reconfirm_from_signal(position_direction, position, today_date)

    print("------------------------------\n")


if __name__ == "__main__":
    run()
