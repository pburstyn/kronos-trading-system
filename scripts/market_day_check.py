import os
import sys
from datetime import date

from dotenv import load_dotenv

load_dotenv(os.path.expanduser("~/trading-system/.env"))

from alpaca.trading.client import TradingClient
from alpaca.trading.requests import GetCalendarRequest

API_KEY = os.environ.get("ALPACA_API_KEY")
SECRET_KEY = os.environ.get("ALPACA_SECRET_KEY")


def is_market_day(day: date) -> bool:
    tc = TradingClient(API_KEY, SECRET_KEY, paper=True)
    sessions = tc.get_calendar(GetCalendarRequest(start=day, end=day))
    return len(sessions) > 0


if __name__ == "__main__":
    today = date.today()
    try:
        market_day = is_market_day(today)
    except Exception as e:
        # Fail open: an API hiccup shouldn't silently skip a real trading day.
        print(f"WARNING: calendar check failed ({e}) — assuming market day, proceeding.")
        sys.exit(0)

    if market_day:
        print(f"{today} is a market day — proceeding.")
        sys.exit(0)
    else:
        print(f"{today} is not a market day (weekend or holiday) — skipping pipeline.")
        sys.exit(1)
