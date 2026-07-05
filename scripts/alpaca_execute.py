import os
import csv
import sys
from datetime import datetime
from dotenv import load_dotenv

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from trade_logic import get_latest_decision_row, make_trade_decision, extract_verdict, calculate_trade_levels
from alpaca_data import get_latest_quote

load_dotenv(os.path.expanduser("~/trading-system/.env"))

from alpaca.trading.client import TradingClient
from alpaca.trading.requests import (
    MarketOrderRequest, TakeProfitRequest, StopLossRequest, GetOrdersRequest
)
from alpaca.trading.enums import OrderSide, TimeInForce, OrderClass, QueryOrderStatus

TICKER = "SPY"
PASS_NOTIONAL = 1000.0
FLAG_NOTIONAL = 500.0
ORDERS_LOG = os.path.expanduser("~/trading-system/logs/alpaca_orders.csv")


def get_notional(verdict):
    return PASS_NOTIONAL if verdict == "PASS" else FLAG_NOTIONAL


def check_existing_exposure(client):
    """Returns (True, reason) if there's already an open position or pending order in TICKER."""
    try:
        client.get_open_position(TICKER)
        return True, "existing open position"
    except Exception:
        pass

    try:
        orders = client.get_orders(GetOrdersRequest(
            status=QueryOrderStatus.OPEN,
            symbols=[TICKER]
        ))
        if orders:
            return True, f"{len(orders)} open order(s)"
    except Exception:
        pass

    return False, None


def log_order(order, decision, notional, qty):
    fieldnames = [
        "timestamp", "order_id", "direction", "notional", "qty",
        "entry_price", "stop_loss", "take_profit_low", "verdict", "status"
    ]
    row = {
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "order_id": str(order.id),
        "direction": decision["direction"],
        "notional": notional,
        "qty": qty,
        "entry_price": decision["entry"],
        "stop_loss": decision["stop_loss"],
        "take_profit_low": decision["take_profit_low"],
        "verdict": decision["verdict"],
        "status": "SUBMITTED"
    }
    file_exists = os.path.isfile(ORDERS_LOG)
    with open(ORDERS_LOG, "a", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        if not file_exists:
            writer.writeheader()
        writer.writerow(row)


def execute_trade(decision, client):
    has_exposure, reason = check_existing_exposure(client)
    if has_exposure:
        print(f"  SKIPPED: Already have {reason} in {TICKER}.")
        return

    # decision["entry"] is last_close from the prior day's decisions_log row — by the time
    # this market order actually fills, price has moved, so stop/take-profit must be
    # recomputed off a live quote or the resulting % from actual fill drifts (e.g. 2.84%
    # stop / 2.21% take-profit instead of the configured 2% / 3%).
    try:
        quote = get_latest_quote()
        live_price = (float(quote.bid_price) + float(quote.ask_price)) / 2
        levels = calculate_trade_levels(decision["direction"], live_price)
    except Exception as e:
        print(f"  WARNING: Could not fetch live quote ({e}); falling back to stale entry ${decision['entry']}.")
        levels = calculate_trade_levels(decision["direction"], decision["entry"])

    notional = get_notional(decision["verdict"])
    qty = max(1, int(notional / levels["entry"]))  # whole shares only — Alpaca requires DAY TIF for fractional, incompatible with GTC bracket
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

    order = client.submit_order(order_request)
    order_decision = {**decision, "entry": levels["entry"], "stop_loss": levels["stop_loss"], "take_profit_low": levels["take_profit_low"]}
    log_order(order, order_decision, notional, qty)

    print(f"  ORDER SUBMITTED: {side.value.upper()} {qty} shares of {TICKER}")
    print(f"  Notional: ${notional:.2f} ({decision['verdict']})")
    print(f"  Entry (approx, live quote): ${levels['entry']}")
    print(f"  Stop-loss: ${levels['stop_loss']}")
    print(f"  Take-profit: ${levels['take_profit_low']}")
    print(f"  Order ID: {order.id}")


def run():
    print("\n-- Alpaca Execute --")

    row = get_latest_decision_row()
    if not row:
        print("  No decision row found.")
        print("--------------------\n")
        return

    row_date = row["timestamp"].split(" ")[0]
    today_date = datetime.now().strftime("%Y-%m-%d")
    if row_date != today_date:
        print(f"  SKIP: Decision from {row_date} is stale (today is {today_date}).")
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
    execute_trade(decision, client)
    print("--------------------\n")


if __name__ == "__main__":
    run()
