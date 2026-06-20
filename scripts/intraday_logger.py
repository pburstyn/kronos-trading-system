import os
import csv
from datetime import datetime
import pytz
from dotenv import load_dotenv

load_dotenv(os.path.expanduser("~/trading-system/.env"))

from alpaca.data.historical import StockHistoricalDataClient
from alpaca.data.requests import StockLatestTradeRequest

TICKER = "SPY"
PRICE_LOG = os.path.expanduser("~/trading-system/logs/intraday_price_log.csv")
ET = pytz.timezone("America/New_York")
MARKET_OPEN = (9, 30)
MARKET_CLOSE = (16, 0)


def is_market_hours():
    now_et = datetime.now(ET)
    if now_et.weekday() >= 5:
        return False
    t = (now_et.hour, now_et.minute)
    return MARKET_OPEN <= t < MARKET_CLOSE


def get_spy_price():
    api_key = os.environ.get("ALPACA_API_KEY")
    secret_key = os.environ.get("ALPACA_SECRET_KEY")
    client = StockHistoricalDataClient(api_key, secret_key)
    trade = client.get_stock_latest_trade(StockLatestTradeRequest(symbol_or_symbols=TICKER))
    return float(trade[TICKER].price)


def log_price(price):
    timestamp = datetime.now(ET).strftime("%Y-%m-%d %H:%M:%S")
    file_exists = os.path.isfile(PRICE_LOG)
    with open(PRICE_LOG, "a", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=["timestamp", "price"])
        if not file_exists:
            writer.writeheader()
        writer.writerow({"timestamp": timestamp, "price": price})
    print(f"{timestamp} ET — SPY ${price:.2f} logged")


if __name__ == "__main__":
    if not is_market_hours():
        print("Outside market hours, skipping.")
        exit(0)
    log_price(get_spy_price())
