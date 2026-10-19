"""Research data pull: 30-minute SPY and QQQ bars, regular trading hours only.

Read-only. Uses the Alpaca market data API and the trading calendar endpoint.
Places no orders and touches nothing in logs/ or scripts/.

Usage: venv/bin/python research/pull_intraday_data.py
Output: research/data/SPY_30min.csv and research/data/QQQ_30min.csv
"""
import os
import csv
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo
from dotenv import load_dotenv

from alpaca.data.historical import StockHistoricalDataClient
from alpaca.data.requests import StockBarsRequest
from alpaca.data.timeframe import TimeFrame, TimeFrameUnit
from alpaca.data.enums import DataFeed, Adjustment
from alpaca.trading.client import TradingClient
from alpaca.trading.requests import GetCalendarRequest
from alpaca.common.exceptions import APIError

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
load_dotenv(os.path.join(REPO, ".env"))

TICKERS = ["SPY", "QQQ"]
OUT_DIR = os.path.join(REPO, "research", "data")
ET = ZoneInfo("America/New_York")
# Alpaca's historical stock data starts in 2016. Asking from 2016-01-01 returns
# whatever the plan/feed actually has.
START = datetime(2016, 1, 1, tzinfo=timezone.utc)
# Free plans can only query SIP data older than 15 minutes. 20 gives margin.
END = datetime.now(timezone.utc) - timedelta(minutes=20)
BAR_MINUTES = 30


def fetch_bars(client, ticker, feed):
    request = StockBarsRequest(
        symbol_or_symbols=ticker,
        timeframe=TimeFrame(BAR_MINUTES, TimeFrameUnit.Minute),
        start=START,
        end=END,
        feed=feed,
        adjustment=Adjustment.RAW,
    )
    return client.get_stock_bars(request).data.get(ticker, [])


def get_calendar(trading_client, first_day, last_day):
    """Returns {date: (open_dt_et, close_dt_et)} for NYSE sessions in range."""
    days = trading_client.get_calendar(GetCalendarRequest(start=first_day, end=last_day))
    out = {}
    for d in days:
        out[d.date] = (d.open.replace(tzinfo=ET), d.close.replace(tzinfo=ET))
    return out


def in_regular_hours(ts_et, session):
    # A bar's timestamp is its start. Keep bars that start at or after the open
    # and end at or before the close (9:30 to 15:30 starts on a normal day).
    open_et, close_et = session
    return open_et <= ts_et and ts_et + timedelta(minutes=BAR_MINUTES) <= close_et


def expected_bars(session):
    open_et, close_et = session
    return int((close_et - open_et).total_seconds() // (BAR_MINUTES * 60))


def write_csv(path, rows):
    with open(path, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["timestamp", "open", "high", "low", "close", "volume"])
        writer.writerows(rows)


def main():
    api_key = os.environ.get("ALPACA_API_KEY")
    secret_key = os.environ.get("ALPACA_SECRET_KEY")
    data_client = StockHistoricalDataClient(api_key, secret_key)
    trading_client = TradingClient(api_key, secret_key, paper=True)

    feed = DataFeed.SIP
    raw = {}
    for ticker in TICKERS:
        try:
            raw[ticker] = fetch_bars(data_client, ticker, feed)
        except APIError as e:
            if feed != DataFeed.SIP:
                raise
            print(f"SIP feed refused ({e}). Falling back to IEX for all tickers.")
            feed = DataFeed.IEX
            raw = {}
            for t in TICKERS:
                raw[t] = fetch_bars(data_client, t, feed)
            break
    print(f"Feed used: {feed.value.upper()}")
    print(f"Requested range: {START.date()} to {END.astimezone(ET):%Y-%m-%d %H:%M} ET\n")

    os.makedirs(OUT_DIR, exist_ok=True)
    for ticker in TICKERS:
        bars = raw[ticker]
        if not bars:
            print(f"{ticker}: no bars returned.")
            continue
        # Raw bars include extended hours, so the first one can fall on the prior
        # evening in ET. Pad the calendar range, then check only from the first
        # to the last regular-hours session actually returned.
        first_day = bars[0].timestamp.astimezone(ET).date() - timedelta(days=1)
        last_day = bars[-1].timestamp.astimezone(ET).date()
        calendar = get_calendar(trading_client, first_day, last_day)

        rows = []
        per_day = {}
        for b in bars:
            ts_et = b.timestamp.astimezone(ET)
            session = calendar.get(ts_et.date())
            if session is None or not in_regular_hours(ts_et, session):
                continue
            rows.append([ts_et.strftime("%Y-%m-%d %H:%M"), b.open, b.high, b.low, b.close, int(b.volume)])
            per_day[ts_et.date()] = per_day.get(ts_et.date(), 0) + 1

        path = os.path.join(OUT_DIR, f"{ticker}_30min.csv")
        write_csv(path, rows)

        # The last session may still be in progress. Only check it if it has closed.
        now_et = END.astimezone(ET)
        missing_days, short_days = [], []
        for d, session in sorted(calendar.items()):
            if d < min(per_day) or session[1] > now_et:
                continue
            got = per_day.get(d, 0)
            want = expected_bars(session)
            if got == 0:
                missing_days.append(d)
            elif got < want:
                short_days.append((d, got, want))

        print(f"{ticker}: {path}")
        print(f"  First date:   {min(per_day)}")
        print(f"  Last date:    {max(per_day)}")
        print(f"  Trading days: {len(per_day)}")
        print(f"  Total rows:   {len(rows)}")
        print(f"  Calendar sessions with no bars: {len(missing_days)}")
        for d in missing_days:
            print(f"    {d}")
        print(f"  Sessions with fewer bars than expected: {len(short_days)}")
        for d, got, want in short_days:
            print(f"    {d}: {got} of {want}")
        print()


if __name__ == "__main__":
    main()
