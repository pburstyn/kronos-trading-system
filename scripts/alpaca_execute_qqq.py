import os
import csv
import sys
from datetime import datetime
from dotenv import load_dotenv

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
# QQQ equivalent of alpaca_execute.py (added October 18). Same fail-closed
# position guard, same live-quote bracket recompute, same whole-share GTC
# bracket, same .env credentials. Decision rules and the 2.5%/4% bracket come
# from trade_logic.py via trade_logic_qqq.py. Orders log to their own file so
# nothing SPY-side (telegram_notify.has_order_today, session_init) sees them.
from trade_logic_qqq import (
    get_latest_decision_row, make_trade_decision, extract_verdict,
    calculate_trade_levels, get_spy_entry_direction_today,
)

load_dotenv(os.path.expanduser("~/kronos-trading-system/.env"))

from alpaca.trading.client import TradingClient
from alpaca.trading.requests import (
    MarketOrderRequest, TakeProfitRequest, StopLossRequest, GetOrdersRequest
)
from alpaca.trading.enums import OrderSide, TimeInForce, OrderClass, QueryOrderStatus
from alpaca.common.exceptions import APIError
from alpaca.data.historical import StockHistoricalDataClient
from alpaca.data.requests import StockLatestQuoteRequest

TICKER = "QQQ"
PASS_NOTIONAL = 1000.0
FLAG_NOTIONAL = 500.0
# Overlap rule (October 18): when SPY's own decision today is ENTER in the same
# direction, QQQ trades at half its normal notional. SPY's sizing is untouched.
SPY_OVERLAP_MULTIPLIER = 0.5
# QQQ never holds more than 1 share (Peter, October 18). Without this cap a
# $1,000 PASS would buy 2 shares if QQQ fell below $500.
MAX_QTY = 1
ORDERS_LOG = os.path.expanduser("~/kronos-trading-system/logs/alpaca_orders_qqq.csv")


def get_notional(verdict, spy_overlap=False):
    notional = PASS_NOTIONAL if verdict == "PASS" else FLAG_NOTIONAL
    if spy_overlap:
        notional *= SPY_OVERLAP_MULTIPLIER
    return notional


def get_latest_quote():
    # alpaca_data.get_latest_quote() is hardcoded to SPY, so QQQ fetches its own.
    data_client = StockHistoricalDataClient(os.environ.get("ALPACA_API_KEY"), os.environ.get("ALPACA_SECRET_KEY"))
    quote = data_client.get_stock_latest_quote(StockLatestQuoteRequest(symbol_or_symbols=TICKER))
    return quote[TICKER]


def check_existing_exposure(client):
    """Returns (True, reason) if there's already an open position or pending order in TICKER,
    in either direction. Fails CLOSED, same as alpaca_execute.py's guard (Sept 21 fix): any
    error verifying position/order state blocks the new order."""
    try:
        client.get_open_position(TICKER)
        return True, "existing open position"
    except APIError as e:
        if getattr(e, "status_code", None) != 404:
            return True, f"could not verify position status ({e}) — failing safe"
    except Exception as e:
        return True, f"could not verify position status ({e}) — failing safe"

    try:
        # nested=True so bracket child legs (stop-loss/take-profit) of an already-filled
        # parent are included, not just top-level orders.
        orders = client.get_orders(GetOrdersRequest(
            status=QueryOrderStatus.OPEN,
            symbols=[TICKER],
            nested=True
        ))
        if orders:
            return True, f"{len(orders)} open order(s)"
    except Exception as e:
        return True, f"could not verify order status ({e}) — failing safe"

    return False, None


def log_order(order, decision, notional, qty):
    fieldnames = [
        "timestamp", "order_id", "ticker", "direction", "notional", "qty",
        "entry_price", "stop_loss", "take_profit_low", "verdict", "spy_overlap", "status"
    ]
    row = {
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "order_id": str(order.id),
        "ticker": TICKER,
        "direction": decision["direction"],
        "notional": notional,
        "qty": qty,
        "entry_price": decision["entry"],
        "stop_loss": decision["stop_loss"],
        "take_profit_low": decision["take_profit_low"],
        "verdict": decision["verdict"],
        "spy_overlap": decision["spy_overlap"],
        "status": "SUBMITTED"
    }
    file_exists = os.path.isfile(ORDERS_LOG)
    with open(ORDERS_LOG, "a", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        if not file_exists:
            writer.writeheader()
        writer.writerow(row)


def execute_trade(decision, client, dry_run=False):
    has_exposure, reason = check_existing_exposure(client)
    if has_exposure:
        print(f"  SKIPPED: Already have {reason} in {TICKER}.")
        return

    print(f"  Position guard: no existing {TICKER} exposure, proceeding with order.")

    # Recompute levels off a live quote, same reason as alpaca_execute.py (July 4 drift fix).
    try:
        quote = get_latest_quote()
        live_price = (float(quote.bid_price) + float(quote.ask_price)) / 2
        levels = calculate_trade_levels(decision["direction"], live_price)
    except Exception as e:
        print(f"  WARNING: Could not fetch live quote ({e}); falling back to stale entry ${decision['entry']}.")
        levels = calculate_trade_levels(decision["direction"], decision["entry"])

    spy_direction = get_spy_entry_direction_today()
    spy_overlap = spy_direction == decision["direction"]
    if spy_overlap:
        print(f"  SPY is also ENTER {spy_direction} today: QQQ sized at {SPY_OVERLAP_MULTIPLIER}x.")

    notional = get_notional(decision["verdict"], spy_overlap)
    qty = min(MAX_QTY, max(1, int(notional / levels["entry"])))  # whole shares only — Alpaca requires DAY TIF for fractional, incompatible with GTC bracket
    side = OrderSide.BUY if decision["direction"] == "UP" else OrderSide.SELL

    order_request = MarketOrderRequest(
        symbol=TICKER,
        qty=qty,
        side=side,
        time_in_force=TimeInForce.GTC,
        order_class=OrderClass.BRACKET,
        take_profit=TakeProfitRequest(limit_price=levels["take_profit_low"]),
        stop_loss=StopLossRequest(stop_price=levels["stop_loss"])
    )

    if dry_run:
        print(f"  DRY RUN — order NOT submitted. Would submit:")
        print(f"    {side.value.upper()} {qty} shares of {TICKER}, GTC bracket")
        print(f"    Notional: ${notional:.2f} ({decision['verdict']}{', SPY overlap 0.5x' if spy_overlap else ''})")
        print(f"    Entry (approx, live quote): ${levels['entry']}")
        print(f"    Stop-loss: ${levels['stop_loss']}")
        print(f"    Take-profit: ${levels['take_profit_low']}")
        return

    order = client.submit_order(order_request)
    order_decision = {**decision, "entry": levels["entry"], "stop_loss": levels["stop_loss"],
                      "take_profit_low": levels["take_profit_low"], "spy_overlap": spy_overlap}
    log_order(order, order_decision, notional, qty)

    print(f"  ORDER SUBMITTED: {side.value.upper()} {qty} shares of {TICKER}")
    print(f"  Notional: ${notional:.2f} ({decision['verdict']}{', SPY overlap 0.5x' if spy_overlap else ''})")
    print(f"  Entry (approx, live quote): ${levels['entry']}")
    print(f"  Stop-loss: ${levels['stop_loss']}")
    print(f"  Take-profit: ${levels['take_profit_low']}")
    print(f"  Order ID: {order.id}")


def run(dry_run=False):
    print("\n-- Alpaca Execute (QQQ) --")

    row = get_latest_decision_row()
    if not row:
        print("  No QQQ decision row found.")
        print("--------------------\n")
        return

    row_date = row["timestamp"].split(" ")[0]
    today_date = datetime.now().strftime("%Y-%m-%d")
    if row_date != today_date:
        print(f"  SKIP: QQQ decision from {row_date} is stale (today is {today_date}).")
        print("--------------------\n")
        return

    decision = make_trade_decision(
        row["direction"],
        row["signal_confidence_pct"],
        row["last_close"],
        extract_verdict(row)
    )

    if decision["action"] != "ENTER":
        print(f"  NO ORDER: {decision['reason']}")
        print("--------------------\n")
        return

    api_key = os.environ.get("ALPACA_API_KEY")
    secret_key = os.environ.get("ALPACA_SECRET_KEY")
    client = TradingClient(api_key, secret_key, paper=True)
    execute_trade(decision, client, dry_run)
    print("--------------------\n")


if __name__ == "__main__":
    run(dry_run="--dry-run" in sys.argv)
