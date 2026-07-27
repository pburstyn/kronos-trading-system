import os
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


def run():
    print("\n-- Position Re-confirmation --")

    row = get_latest_decision_row()
    if not row:
        print("  No decision row found.")
        print("------------------------------\n")
        return

    row_date = row["timestamp"].split(" ")[0]
    today_date = datetime.now().strftime("%Y-%m-%d")
    if row_date != today_date:
        print(f"  SKIP: Decision from {row_date} is stale (today is {today_date}).")
        print("------------------------------\n")
        return

    api_key = os.environ.get("ALPACA_API_KEY")
    secret_key = os.environ.get("ALPACA_SECRET_KEY")
    client = TradingClient(api_key, secret_key, paper=True)

    position_direction, position = get_open_position(client)
    if position_direction is None:
        print("  No open position — nothing to reconfirm.")
        print("------------------------------\n")
        return

    signal_direction = row["direction"]

    if signal_direction not in ("UP", "DOWN"):
        print(f"  Open {position_direction} position; today's signal is {signal_direction} — no contradiction check needed.")
        print("------------------------------\n")
        return

    if signal_direction == position_direction:
        print(f"  Open {position_direction} position confirmed by today's {signal_direction} signal.")
        print("------------------------------\n")
        return

    verdict = extract_verdict(row)
    confidence = row.get("signal_confidence_pct", "?")
    print(f"  CONTRADICTION: open {position_direction} position vs. today's {signal_direction} signal ({confidence}%, verdict {verdict}).")

    message = build_contradiction_message(position_direction, position, signal_direction, confidence, verdict, today_date)
    try:
        token, chat_id = get_telegram_config()
        send_telegram(token, chat_id, message)
        print("  Telegram alert sent.")
    except Exception as e:
        print(f"  WARNING: Telegram send failed: {e}")

    print("------------------------------\n")


if __name__ == "__main__":
    run()
