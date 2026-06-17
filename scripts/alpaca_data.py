import os
from datetime import datetime
from dotenv import load_dotenv
from alpaca.trading.client import TradingClient
from alpaca.data.historical import StockHistoricalDataClient
from alpaca.data.requests import StockLatestQuoteRequest

load_dotenv(os.path.expanduser("~/trading-system/.env"))

API_KEY = os.environ.get("ALPACA_API_KEY")
SECRET_KEY = os.environ.get("ALPACA_SECRET_KEY")
TICKER = "SPY"

def check_account():
    trading_client = TradingClient(API_KEY, SECRET_KEY, paper=True)
    account = trading_client.get_account()
    print(f"Account status: {account.status}")
    print(f"Buying power: ${account.buying_power}")
    print(f"Cash: ${account.cash}")
    print(f"Portfolio value: ${account.portfolio_value}")
    return account

def get_latest_quote():
    data_client = StockHistoricalDataClient(API_KEY, SECRET_KEY)
    request = StockLatestQuoteRequest(symbol_or_symbols=TICKER)
    quote = data_client.get_stock_latest_quote(request)
    spy_quote = quote[TICKER]
    print(f"\n{TICKER} Latest Quote:")
    print(f"  Bid: ${spy_quote.bid_price} x {spy_quote.bid_size}")
    print(f"  Ask: ${spy_quote.ask_price} x {spy_quote.ask_size}")
    print(f"  Timestamp: {spy_quote.timestamp}")
    return spy_quote

if __name__ == "__main__":
    print("Testing Alpaca connection...\n")
    check_account()
    get_latest_quote()
