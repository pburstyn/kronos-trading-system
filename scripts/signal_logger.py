import yfinance as yf
import numpy as np
import torch
import csv
import os
from datetime import datetime

# ── SETTINGS ──────────────────────────────────────
TICKER   = "SPY"       # What to watch (SPY = S&P 500 ETF)
LOOKBACK = 30          # How many candles to feed Kronos
LOG_FILE = os.path.expanduser(
    "~/trading-system/logs/signal_log.csv"
)
# ──────────────────────────────────────────────────

def get_price_data(ticker, lookback):
    """Download recent daily candles from Yahoo Finance."""
    df = yf.download(ticker, period="60d", interval="1d",
                     progress=False)
    df = df.tail(lookback)
    closes = df["Close"].values.flatten().astype(float)
    return closes

def simple_kronos_signal(prices):
    if len(prices) < 5:
        return "INSUFFICIENT_DATA", 0.0

    mean  = np.mean(prices)
    std   = np.std(prices) + 1e-9
    norm  = (prices - mean) / std

    short_mom = float(np.mean(np.diff(norm[-5:])))
    long_mom  = float(np.mean(np.diff(norm)))

    signal_score = (short_mom * 0.6) + (long_mom * 0.4)

    direction  = "UP" if signal_score > 0 else "DOWN"
    confidence = round(min(abs(signal_score) * 100, 99.0), 2)

    return direction, confidence

def log_signal(ticker, direction, confidence, prices):
    os.makedirs(os.path.dirname(LOG_FILE), exist_ok=True)

    file_exists = os.path.isfile(LOG_FILE)
    with open(LOG_FILE, "a", newline="") as f:
        writer = csv.writer(f)
        if not file_exists:
            writer.writerow([
                "timestamp", "ticker", "direction",
                "confidence_pct", "last_close"
            ])
        writer.writerow([
            datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            ticker,
            direction,
            confidence,
            round(float(prices[-1]), 4)
        ])
    print(f"[{datetime.now().strftime('%H:%M:%S')}] "
          f"{ticker} → {direction} "
          f"({confidence}% confidence) "
          f"| Last close: {round(float(prices[-1]),2)}")

def run():
    print(f"Fetching data for {TICKER}...")
    prices = get_price_data(TICKER, LOOKBACK)

    if len(prices) < 5:
        print("Not enough data. Try again later.")
        return

    direction, confidence = simple_kronos_signal(prices)
    log_signal(TICKER, direction, confidence, prices)
    print(f"Logged to: {LOG_FILE}")

if __name__ == "__main__":
    run()
