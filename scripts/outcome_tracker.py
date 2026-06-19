import csv
import os
import yfinance as yf
from datetime import datetime

PAPER_TRADES_LOG = os.path.expanduser("~/trading-system/logs/paper_trades.csv")

def get_current_price(ticker):
    df = yf.download(ticker, period="1d", interval="1d", progress=False)
    df.columns = [col[0].lower() if isinstance(col, tuple) else col.lower() for col in df.columns]
    return float(df["close"].iloc[-1])

def check_outcomes():
    if not os.path.isfile(PAPER_TRADES_LOG):
        print("No paper trades log found.")
        return

    with open(PAPER_TRADES_LOG, "r") as f:
        rows = list(csv.DictReader(f))

    if not rows:
        print("No paper trades to check.")
        return

    open_trades = [r for r in rows if r.get("status") == "OPEN"]
    if not open_trades:
        print("No open trades to check.")
        return

    print(f"Checking {len(open_trades)} open trade(s)...")
    current_price = get_current_price("SPY")
    print(f"Current SPY price: ${current_price}")

    updated = False
    for row in rows:
        if row.get("status") != "OPEN":
            continue

        direction = row["direction"]
        entry = float(row["entry_price"])
        stop_loss = float(row["stop_loss"])
        tp_low = float(row["take_profit_low"])
        tp_high = float(row["take_profit_high"])

        exit_price = None
        exit_reason = None

        if direction == "UP":
            if current_price <= stop_loss:
                exit_price = current_price
                exit_reason = "STOP_LOSS"
            elif current_price >= tp_high:
                exit_price = current_price
                exit_reason = "TAKE_PROFIT_HIGH"
            elif current_price >= tp_low:
                exit_price = current_price
                exit_reason = "TAKE_PROFIT_LOW"
        elif direction == "DOWN":
            if current_price >= stop_loss:
                exit_price = current_price
                exit_reason = "STOP_LOSS"
            elif current_price <= tp_high:
                exit_price = current_price
                exit_reason = "TAKE_PROFIT_HIGH"
            elif current_price <= tp_low:
                exit_price = current_price
                exit_reason = "TAKE_PROFIT_LOW"

        if exit_price:
            pnl_dollars = round(exit_price - entry, 2) if direction == "UP" else round(entry - exit_price, 2)
            pnl_pct = round((pnl_dollars / entry) * 100, 2)
            row["exit_price"] = exit_price
            row["exit_reason"] = exit_reason
            row["pnl_dollars"] = pnl_dollars
            row["pnl_pct"] = pnl_pct
            row["status"] = "CLOSED"
            row["notes"] = f"Auto-closed {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
            print(f"  CLOSED: {direction} entered at ${entry} — exited at ${exit_price} ({exit_reason}) — PnL: ${pnl_dollars} ({pnl_pct}%)")
            updated = True
        else:
            unrealized = round(current_price - entry, 2) if direction == "UP" else round(entry - current_price, 2)
            unrealized_pct = round((unrealized / entry) * 100, 2)
            print(f"  OPEN: {direction} entered at ${entry} — current ${current_price} — unrealized PnL: ${unrealized} ({unrealized_pct}%)")

    if updated:
        fieldnames = rows[0].keys()
        with open(PAPER_TRADES_LOG, "w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(rows)
        print(f"Updated: {PAPER_TRADES_LOG}")
    else:
        print("No trades hit targets yet. All still open.")

if __name__ == "__main__":
    check_outcomes()
