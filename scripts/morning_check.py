import json
import os
from datetime import datetime, timedelta, timezone

import requests
from dotenv import load_dotenv

load_dotenv(os.path.expanduser("~/trading-system/.env"))

from alpaca.trading.client import TradingClient
from alpaca.trading.requests import GetOrdersRequest
from alpaca.trading.enums import QueryOrderStatus
from alpaca.data.historical import StockHistoricalDataClient
from alpaca.data.requests import StockLatestTradeRequest

OPENCLAW_CONFIG = "/mnt/c/Users/openc/.openclaw/openclaw.json"
TICKER = "SPY"
ACTIVE_LEG_STATUSES = {"new", "accepted", "held", "pending_new", "partially_filled", "pending_replace"}


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
        print(f"  WARNING: Telegram failed: {e}")


def get_spy_price(dc):
    try:
        trade = dc.get_stock_latest_trade(StockLatestTradeRequest(symbol_or_symbols=TICKER))
        return float(trade[TICKER].price)
    except Exception:
        return None


def leg_status_lines(tc):
    # QueryOrderStatus.OPEN omits bracket stop legs sitting in "held" status,
    # so the stop never showed. Pull ALL recent orders with legs nested,
    # flatten, and filter by status ourselves.
    try:
        orders = tc.get_orders(GetOrdersRequest(
            status=QueryOrderStatus.ALL,
            symbols=[TICKER],
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


def run():
    now = datetime.now().strftime("%Y-%m-%d %H:%M PT")
    print(f"\n-- Morning Trade Check {now} --")

    api_key = os.environ.get("ALPACA_API_KEY")
    secret_key = os.environ.get("ALPACA_SECRET_KEY")
    tc = TradingClient(api_key, secret_key, paper=True)
    dc = StockHistoricalDataClient(api_key, secret_key)

    spy_price = get_spy_price(dc)
    price_str = f"${spy_price:.2f}" if spy_price else "unavailable"

    # Case 1: open position — trade filled and running
    try:
        pos = tc.get_open_position(TICKER)
        entry = float(pos.avg_entry_price)
        pl = float(pos.unrealized_pl)
        pct = float(pos.unrealized_plpc) * 100
        side = str(pos.side).split(".")[-1].upper()
        sign = "+" if pl >= 0 else ""
        legs = leg_status_lines(tc)
        msg = (
            f"Kronos Morning Check — {now}\n"
            f"\n"
            f"Trade: {side} {pos.qty} {TICKER}\n"
            f"Entry:   ${entry:.2f}\n"
            f"Current: {price_str}\n"
            f"P&L:     {sign}${pl:.2f} ({sign}{pct:.2f}%)\n"
            f"\n"
            f"Bracket legs:\n{legs}"
        )
        print(msg)
        send_telegram(msg)
        return
    except Exception:
        pass

    # Case 2: no position — check for unfilled pending orders
    try:
        open_orders = tc.get_orders(GetOrdersRequest(status=QueryOrderStatus.OPEN, symbols=[TICKER]))
        if open_orders:
            o = open_orders[0]
            status = str(o.status).split(".")[-1].upper()
            side = str(o.side).split(".")[-1].upper()
            msg = (
                f"Kronos Morning Check — {now}\n"
                f"\n"
                f"WARNING: Order unfilled\n"
                f"Order: {side} {o.qty} {TICKER}\n"
                f"Status: {status}\n"
                f"Order ID: {o.id}\n"
                f"SPY now: {price_str}\n"
                f"\n"
                f"Check Alpaca — may need manual review."
            )
            print(msg)
            send_telegram(msg)
            return
    except Exception:
        pass

    # Case 3: no position, no open orders
    msg = (
        f"Kronos Morning Check — {now}\n"
        f"\n"
        f"No open {TICKER} position or pending orders.\n"
        f"SPY now: {price_str}\n"
        f"\n"
        f"No active trade — either no signal fired or bracket already closed."
    )
    print(msg)
    send_telegram(msg)


if __name__ == "__main__":
    run()
