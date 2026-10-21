import os
from datetime import datetime, timedelta, timezone

import requests
from dotenv import load_dotenv

load_dotenv(os.path.expanduser("~/kronos-trading-system/.env"))

from alpaca.common.exceptions import APIError
from alpaca.trading.client import TradingClient
from alpaca.trading.requests import GetOrdersRequest
from alpaca.trading.enums import QueryOrderStatus
from alpaca.data.historical import StockHistoricalDataClient
from alpaca.data.requests import StockLatestTradeRequest

TICKERS = ["SPY", "QQQ"]
ACTIVE_LEG_STATUSES = {"new", "accepted", "held", "pending_new", "partially_filled", "pending_replace"}


def get_telegram_config():
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID")
    return token, chat_id


def send_telegram(message):
    try:
        token, chat_id = get_telegram_config()
        url = f"https://api.telegram.org/bot{token}/sendMessage"
        requests.post(url, data={"chat_id": chat_id, "text": message}, timeout=10)
        print("  Telegram sent.")
    except Exception as e:
        print(f"  WARNING: Telegram failed: {e}")


def get_price(dc, ticker):
    try:
        trade = dc.get_stock_latest_trade(StockLatestTradeRequest(symbol_or_symbols=ticker))
        return float(trade[ticker].price)
    except Exception:
        return None


def leg_status_lines(tc, ticker):
    # QueryOrderStatus.OPEN omits bracket stop legs sitting in "held" status,
    # so the stop never showed. Pull ALL recent orders with legs nested,
    # flatten, and filter by status ourselves.
    try:
        orders = tc.get_orders(GetOrdersRequest(
            status=QueryOrderStatus.ALL,
            symbols=[ticker],
            nested=True,
            after=datetime.now(timezone.utc) - timedelta(days=100),
            limit=500,
        ))
        flat = {}
        for order in orders:
            for o in [order] + list(order.legs or []):
                flat.setdefault(str(o.id), o)

        legs = []
        has_stop = False
        for o in flat.values():
            status = getattr(o.status, "value", str(o.status).split(".")[-1]).lower()
            if status not in ACTIVE_LEG_STATUSES:
                continue
            otype = getattr(o.order_type, "value", str(o.order_type).split(".")[-1]).lower()
            if "stop" in otype:
                has_stop = True
                legs.append(f"  STOP LOSS @ ${o.stop_price} ({status})")
            elif "limit" in otype:
                legs.append(f"  TAKE PROFIT @ ${o.limit_price} ({status})")
            else:
                legs.append(f"  {otype} @ ${o.limit_price or o.stop_price} ({status})")
        if not has_stop:
            legs.append("  WARNING: NO STOP LEG FOUND. Check Alpaca now.")
        return "\n".join(legs)
    except Exception:
        return "  (could not fetch leg status)"


def signed_money(x):
    return f"+${x:.2f}" if x >= 0 else f"-${abs(x):.2f}"


def signed_pct(x):
    return f"+{x:.2f}%" if x >= 0 else f"{x:.2f}%"


def ticker_section(tc, dc, ticker):
    price = get_price(dc, ticker)
    price_str = f"${price:.2f}" if price else "unavailable"

    # Case 1: open position — trade filled and running.
    # Only a 404 means flat; any other error is reported, not read as "no position".
    try:
        pos = tc.get_open_position(ticker)
    except APIError as e:
        if getattr(e, "status_code", None) != 404:
            return f"[{ticker}]\nWARNING: could not check {ticker} position: {e}\nCheck Alpaca now."
        pos = None
    except Exception as e:
        return f"[{ticker}]\nWARNING: could not check {ticker} position: {e}\nCheck Alpaca now."

    if pos is not None:
        entry = float(pos.avg_entry_price)
        # unrealized_pl / unrealized_plpc come from Alpaca already signed for the side,
        # so a short that has moved against us shows negative.
        pl = float(pos.unrealized_pl)
        pct = float(pos.unrealized_plpc) * 100
        side = str(pos.side).split(".")[-1].upper()
        qty = abs(float(pos.qty))
        return (
            f"[{ticker}]\n"
            f"Trade: {side} {qty:g} {ticker}\n"
            f"Entry:   ${entry:.2f}\n"
            f"Current: {price_str}\n"
            f"P&L:     {signed_money(pl)} ({signed_pct(pct)})\n"
            f"Bracket legs:\n{leg_status_lines(tc, ticker)}"
        )

    # Case 2: no position — check for unfilled pending orders
    try:
        open_orders = tc.get_orders(GetOrdersRequest(status=QueryOrderStatus.OPEN, symbols=[ticker]))
    except Exception as e:
        return f"[{ticker}]\nWARNING: could not check {ticker} orders: {e}\nCheck Alpaca now."
    if open_orders:
        o = open_orders[0]
        status = str(o.status).split(".")[-1].upper()
        side = str(o.side).split(".")[-1].upper()
        return (
            f"[{ticker}]\n"
            f"WARNING: Order unfilled\n"
            f"Order: {side} {o.qty} {ticker}\n"
            f"Status: {status}\n"
            f"Order ID: {o.id}\n"
            f"{ticker} now: {price_str}\n"
            f"Bracket legs:\n{leg_status_lines(tc, ticker)}\n"
            f"Check Alpaca — may need manual review."
        )

    # Case 3: no position, no open orders
    return f"[{ticker}]\nNo open {ticker} position or pending orders."


def run():
    now = datetime.now().strftime("%Y-%m-%d %H:%M PT")
    print(f"\n-- Morning Trade Check {now} --")

    api_key = os.environ.get("ALPACA_API_KEY")
    secret_key = os.environ.get("ALPACA_SECRET_KEY")
    tc = TradingClient(api_key, secret_key, paper=True)
    dc = StockHistoricalDataClient(api_key, secret_key)

    sections = [ticker_section(tc, dc, t) for t in TICKERS]
    msg = f"Kronos Morning Check — {now}\n\n" + "\n\n".join(sections)
    print(msg)
    send_telegram(msg)


if __name__ == "__main__":
    run()
