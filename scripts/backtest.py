import yfinance as yf
import pandas_ta as ta
import pandas as pd
import numpy as np
import csv
import os
from datetime import datetime
TICKER = "SPY"
MIN_VOTES = 3
MIN_CONFIDENCE = 70.0
OUTPUT_FILE = os.path.expanduser("~/trading-system/logs/backtest_results.csv")

def get_historical_data(ticker):
    df = yf.download(ticker, start="2023-01-01", end=datetime.today().strftime("%Y-%m-%d"), interval="1d", progress=False)
    df.columns = [col[0].lower() if isinstance(col, tuple) else col.lower() for col in df.columns]
    return df

def compute_indicators(df):
    df["rsi"] = ta.rsi(df["close"], length=14)
    macd = ta.macd(df["close"], fast=12, slow=26, signal=9)
    df = pd.concat([df, macd], axis=1)
    df["vol_ma20"] = df["volume"].rolling(20).mean()
    df["ma50"] = df["close"].rolling(50).mean()
    df["ma200"] = df["close"].rolling(200).mean()
    return df

def generate_signal(latest, prev):
    rsi = latest["rsi"]
    macd_line = latest["MACD_12_26_9"]
    macd_signal = latest["MACDs_12_26_9"]
    macd_hist = latest["MACDh_12_26_9"]
    macd_hist_prev = prev["MACDh_12_26_9"]
    volume = latest["volume"]
    vol_ma = latest["vol_ma20"]
    ma50 = latest["ma50"]
    ma200 = latest["ma200"]
    price = latest["close"]
    bull_votes = 0
    bear_votes = 0
    vote_log = []
    if price > ma50 and ma50 > ma200:
        bull_votes += 1
        bull_votes += 1
        vote_log.append("bullish structure")
    elif price < ma50 and ma50 < ma200:
        bear_votes += 1
        bear_votes += 1
        vote_log.append("bearish structure")
    else:
        vote_log.append("mixed structure")
    if 50 <= rsi <= 70:
        bull_votes += 1
        vote_log.append(f"RSI {round(rsi,1)}: bullish")
    elif rsi < 50:
        bear_votes += 1
        vote_log.append(f"RSI {round(rsi,1)}: bearish")
    else:
        vote_log.append(f"RSI {round(rsi,1)}: overbought")
    if macd_line > macd_signal:
        bull_votes += 1
        vote_log.append("MACD bullish")
    else:
        bear_votes += 1
        vote_log.append("MACD bearish")
    if macd_hist > 0 and macd_hist > macd_hist_prev:
        bull_votes += 1
        vote_log.append("MACD hist growing")
    elif macd_hist < 0 and macd_hist < macd_hist_prev:
        bear_votes += 1
        vote_log.append("MACD hist falling")
    if bull_votes >= MIN_VOTES and bull_votes > bear_votes:
        direction = "UP"
        votes = bull_votes
    elif bear_votes >= MIN_VOTES and bear_votes > bull_votes:
        direction = "DOWN"
        votes = bear_votes
    else:
        return "NEUTRAL", 0.0, vote_log
    base = 60 if votes == 3 else 40
    if direction == "UP":
        if 55 <= rsi <= 65: base += 20
        elif 50 <= rsi < 55 or 65 < rsi <= 70: base += 10
        elif rsi > 70: base -= 10
    elif direction == "DOWN":
        if 35 <= rsi <= 45: base += 20
        elif 30 <= rsi < 35 or 45 < rsi <= 50: base += 10
        elif rsi < 30: base -= 10
    if macd_hist > 0 and macd_hist > macd_hist_prev and direction == "UP": base += 10
    elif macd_hist < 0 and macd_hist < macd_hist_prev and direction == "DOWN": base += 10
    if volume > vol_ma * 1.2: base += 10
    elif volume < vol_ma * 0.8: base -= 10
    confidence = round(min(max(base, 0), 99.0), 2)
    return direction, confidence, vote_log

def run():
    print("Downloading SPY data from 2023-01-01...")
    df = get_historical_data(TICKER)
    df = compute_indicators(df)
    df = df.dropna()
    df["date"] = df.index
    df = df.reset_index(drop=True)
    os.makedirs(os.path.dirname(OUTPUT_FILE), exist_ok=True)
    results = []
    total = 0
    correct = 0
    signals_fired = 0
    for i in range(1, len(df) - 1):
        latest = df.iloc[i]
        prev = df.iloc[i - 1]
        next_day = df.iloc[i + 1]
        direction, confidence, vote_log = generate_signal(latest, prev)
        if direction == "NEUTRAL" or confidence < MIN_CONFIDENCE:
            outcome = "NO_SIGNAL"
        else:
            signals_fired += 1
            total += 1
            next_return = float(next_day["close"]) - float(latest["close"])
            if direction == "UP" and next_return > 0:
                outcome = "CORRECT"
                correct += 1
            elif direction == "DOWN" and next_return < 0:
                outcome = "CORRECT"
                correct += 1
            else:
                outcome = "WRONG"
        results.append({
            "date": str(latest["date"].date()) if hasattr(latest["date"], "date") else str(latest["date"]),
            "direction": direction,
            "confidence": confidence,
            "close": round(float(latest["close"]), 2),
            "next_day_change": round(float(next_day["close"]) - float(latest["close"]), 2) if direction != "NEUTRAL" else 0,
            "outcome": outcome,
            "votes": " | ".join(vote_log)
        })
    with open(OUTPUT_FILE, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=["date","direction","confidence","close","next_day_change","outcome","votes"])
        writer.writeheader()
        writer.writerows(results)
    print(f"\n--- BACKTEST RESULTS ---")
    print(f"Total trading days analyzed: {len(df)}")
    print(f"Signals fired: {signals_fired}")
    print(f"Correct: {correct}")
    print(f"Wrong: {total - correct}")
    accuracy = round((correct / total) * 100, 1) if total > 0 else 0
    print(f"Accuracy: {accuracy}%")
    print(f"Results saved to: {OUTPUT_FILE}")
    if accuracy >= 55:
        print("EDGE DETECTED. Continue to paper trading.")
    else:
        print("NO EDGE. Revise signals before paper trading.")

if __name__ == "__main__":
    run()
