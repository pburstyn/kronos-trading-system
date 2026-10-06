"""
trade_ledger.py  --  the true closed-trade record for Kronos.

Rebuilds logs/trade_ledger.csv from scratch on every run, using Alpaca as the
only source of truth. Read-only: never submits, cancels, or changes orders.
"""

import csv
import os
import sys
from datetime import datetime, timezone

from dotenv import load_dotenv

load_dotenv(os.path.expanduser("~/trading-system/.env"))

from alpaca.trading.client import TradingClient
from alpaca.trading.requests import GetOrdersRequest
from alpaca.trading.enums import QueryOrderStatus

TICKER = "SPY"
START_DATE = datetime(2026, 6, 1, tzinfo=timezone.utc)
LEDGER_FILE = os.path.expanduser("~/trading-system/logs/trade_ledger.csv")

COLUMNS = [
    "trade_num", "status", "direction", "qty",
    "entry_time_utc", "entry_price", "entry_order_id",
    "exit_time_utc", "exit_price", "exit_order_id", "exit_reason",
    "pnl_dollars", "pnl_pct", "days_held",
]


def _val(x):
    if x is None:
        return ""
    v = getattr(x, "value", x)
    return str(v).split(".")[-1].lower()


def _float(x):
    try:
        return float(x)
    except (TypeError, ValueError):
        return 0.0


def fetch_filled_orders(client):
    req = GetOrdersRequest(
        status=QueryOrderStatus.ALL,
        symbols=[TICKER],
        nested=True,
        after=START_DATE,
        limit=500,
    )
    orders = client.get_orders(req)
    if len(orders) >= 500:
        print("  WARNING: hit the 500-order limit, older orders may be missing.")

    seen = {}
    for o in orders:
        for order in [o] + list(o.legs or []):
            oid = str(order.id)
            if oid in seen:
                continue
            if order.filled_at is None or _float(order.filled_qty) <= 0:
                continue
            seen[oid] = order
    return sorted(seen.values(), key=lambda o: o.filled_at)


def exit_reason_for(order):
    otype = _val(order.order_type)
    if otype in ("stop", "stop_limit", "trailing_stop"):
        return "STOP_LOSS"
    if otype == "limit":
        return "TAKE_PROFIT"
    return "MANUAL_CLOSE"


def build_trades(fills):
    trades = []
    position = 0.0
    current = None

    for f in fills:
        qty = _float(f.filled_qty)
        side = _val(f.side)
        signed = qty if side == "buy" else -qty
        price = _float(f.filled_avg_price)

        if position == 0:
            current = {
                "direction": "LONG" if signed > 0 else "SHORT",
                "qty": qty,
                "entry_time": f.filled_at,
                "entry_price": price,
                "entry_order_id": str(f.id),
            }
            position = signed
            continue

        position += signed
        if abs(position) < 1e-9:
            position = 0.0
            current.update({
                "exit_time": f.filled_at,
                "exit_price": price,
                "exit_order_id": str(f.id),
                "exit_reason": exit_reason_for(f),
            })
            trades.append(current)
            current = None
        elif (position > 0) != (current["direction"] == "LONG"):
            print(f"  WARNING: position flipped on order {f.id}. Check Alpaca manually.")

    if current is not None:
        trades.append(current)
    return trades


def to_rows(trades):
    rows = []
    for i, t in enumerate(trades, start=1):
        row = {
            "trade_num": i,
            "direction": t["direction"],
            "qty": f"{t['qty']:g}",
            "entry_time_utc": t["entry_time"].strftime("%Y-%m-%d %H:%M:%S"),
            "entry_price": f"{t['entry_price']:.2f}",
            "entry_order_id": t["entry_order_id"],
        }
        if "exit_time" in t:
            sign = 1 if t["direction"] == "LONG" else -1
            pnl = (t["exit_price"] - t["entry_price"]) * t["qty"] * sign
            pnl_pct = (t["exit_price"] - t["entry_price"]) / t["entry_price"] * 100 * sign
            row.update({
                "status": "CLOSED",
                "exit_time_utc": t["exit_time"].strftime("%Y-%m-%d %H:%M:%S"),
                "exit_price": f"{t['exit_price']:.2f}",
                "exit_order_id": t["exit_order_id"],
                "exit_reason": t["exit_reason"],
                "pnl_dollars": f"{pnl:.2f}",
                "pnl_pct": f"{pnl_pct:.2f}",
                "days_held": (t["exit_time"].date() - t["entry_time"].date()).days,
            })
        else:
            row.update({
                "status": "OPEN",
                "exit_time_utc": "", "exit_price": "", "exit_order_id": "",
                "exit_reason": "", "pnl_dollars": "", "pnl_pct": "", "days_held": "",
            })
        rows.append(row)
    return rows


def write_ledger(rows):
    tmp = LEDGER_FILE + ".tmp"
    with open(tmp, "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=COLUMNS)
        w.writeheader()
        w.writerows(rows)
    os.replace(tmp, LEDGER_FILE)


def print_summary(rows):
    closed = [r for r in rows if r["status"] == "CLOSED"]
    open_ = [r for r in rows if r["status"] == "OPEN"]
    wins = sum(1 for r in closed if float(r["pnl_dollars"]) > 0)
    losses = sum(1 for r in closed if float(r["pnl_dollars"]) < 0)
    total = sum(float(r["pnl_dollars"]) for r in closed)

    print(f"  {'#':>2}  {'DIR':5} {'ENTRY (UTC)':19} {'ENTRY':>8}  {'EXIT (UTC)':19} {'EXIT':>8}  {'REASON':12} {'P&L':>8}")
    for r in rows:
        print(f"  {r['trade_num']:>2}  {r['direction']:5} {r['entry_time_utc']:19} {r['entry_price']:>8}  "
              f"{r['exit_time_utc'] or '(open)':19} {r['exit_price']:>8}  {r['exit_reason']:12} {r['pnl_dollars']:>8}")
    print(f"\n  Closed: {len(closed)}  |  Wins: {wins}  Losses: {losses}  |  Net P&L: ${total:.2f}  |  Open: {len(open_)}")


def run():
    print(f"\n-- Trade Ledger {datetime.now().strftime('%Y-%m-%d %H:%M')} --")
    api_key = os.environ.get("ALPACA_API_KEY")
    secret_key = os.environ.get("ALPACA_SECRET_KEY")
    if not api_key or not secret_key:
        print("  ERROR: ALPACA_API_KEY / ALPACA_SECRET_KEY missing from .env. Ledger not updated.")
        sys.exit(1)

    try:
        client = TradingClient(api_key, secret_key, paper=True)
        fills = fetch_filled_orders(client)
    except Exception as e:
        print(f"  ERROR: Alpaca fetch failed ({e}). Existing ledger left unchanged.")
        sys.exit(1)

    rows = to_rows(build_trades(fills))
    write_ledger(rows)
    print_summary(rows)
    print(f"  Written to {LEDGER_FILE}")
    print("--------------------\n")


if __name__ == "__main__":
    run()