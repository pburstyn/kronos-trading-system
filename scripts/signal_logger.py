import yfinance as yf
import pandas_ta as ta
import pandas as pd
import numpy as np
import csv
import os
from datetime import datetime

TICKER = "SPY"
LOOKBACK = 250
MIN_VOTES = 3
MIN_CONFIDENCE = 70.0
LOG_FILE = os.path.expanduser("~/trading-system/logs/signal_log.csv")

def get_market_data(ticker, lookback):
    df = yf.download(ticker, period=f"{lookback}d", interval="1d", progress=False)
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

def generate_signal(df):
    latest = df.iloc[-1]
    prev = df.iloc[-2]
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
    # Moving average context
    if price > ma50 and ma50 > ma200:
        vote_log.append(f"Price ${round(price,2)} above MA50 ${round(ma50,2)} and MA200 ${round(ma200,2)}: bullish structure")
    elif price < ma50 and ma50 < ma200:
        vote_log.append(f"Price ${round(price,2)} below MA50 ${round(ma50,2)} and MA200 ${round(ma200,2)}: bearish structure")
    else:
        vote_log.append(f"MA50 ${round(ma50,2)} MA200 ${round(ma200,2)}: mixed structure")

    if 50 <= rsi <= 70:
        bull_votes += 1
        vote_log.append(f"RSI {round(rsi,1)}: bullish")
    elif rsi < 50:
        bear_votes += 1
        vote_log.append(f"RSI {round(rsi,1)}: bearish")
    else:
        vote_log.append(f"RSI {round(rsi,1)}: overbought, no vote")
    if macd_line > macd_signal:
        bull_votes += 1
        vote_log.append("MACD above signal: bullish")
    else:
        bear_votes += 1
        vote_log.append("MACD below signal: bearish")
    if macd_hist > 0 and macd_hist > macd_hist_prev:
        bull_votes += 1
        vote_log.append("MACD histogram growing: bullish")
    elif macd_hist < 0 and macd_hist < macd_hist_prev:
        bear_votes += 1
        vote_log.append("MACD histogram falling: bearish")
    else:
        vote_log.append("MACD histogram neutral: no vote")
    # Conflict detection: block UP if RSI overbought
    rsi_overbought = rsi > 70
    if bull_votes >= MIN_VOTES and bull_votes > bear_votes:
        if rsi_overbought:
            vote_log.append(f"VERDICT: CONFLICT — RSI {round(rsi,1)} overbought overrides {bull_votes} bull votes — forced NEUTRAL")
            return "NEUTRAL", 0.0, vote_log
        direction = "UP"
        votes = bull_votes
    elif bear_votes >= MIN_VOTES and bear_votes > bull_votes:
        direction = "DOWN"
        votes = bear_votes
    else:
        vote_log.append(f"VERDICT: NEUTRAL — bull_votes={bull_votes} bear_votes={bear_votes} did not meet MIN_VOTES={MIN_VOTES}")
        return "NEUTRAL", 0.0, vote_log
    if votes == 3:
        base = 60
    else:
        base = 40
    if direction == "UP":
        if 55 <= rsi <= 65:
            base += 20
        elif 50 <= rsi < 55 or 65 < rsi <= 70:
            base += 10
        elif rsi > 70:
            base -= 10
    elif direction == "DOWN":
        if 35 <= rsi <= 45:
            base += 20
        elif 30 <= rsi < 35 or 45 < rsi <= 50:
            base += 10
        elif rsi < 30:
            base -= 10
    if macd_hist > 0 and macd_hist > macd_hist_prev and direction == "UP":
        base += 10
    elif macd_hist < 0 and macd_hist < macd_hist_prev and direction == "DOWN":
        base += 10
    if volume > vol_ma * 1.2:
        base += 10
        vote_log.append(f"Volume {round(volume/1e6,1)}M above avg: confirms signal")
    elif volume < vol_ma * 0.8:
        base -= 10
        vote_log.append(f"Volume {round(volume/1e6,1)}M below avg: weakens signal")
    else:
        vote_log.append(f"Volume {round(volume/1e6,1)}M neutral")
    confidence = round(min(max(base, 0), 99.0), 2)
    return direction, confidence, vote_log

def log_signal(ticker, direction, confidence, last_close, vote_log):
    os.makedirs(os.path.dirname(LOG_FILE), exist_ok=True)
    file_exists = os.path.isfile(LOG_FILE)
    with open(LOG_FILE, "a", newline="") as f:
        writer = csv.writer(f)
        if not file_exists:
            writer.writerow(["timestamp", "ticker", "direction", "confidence_pct", "last_close", "votes"])
        writer.writerow([
            datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            ticker, direction, confidence,
            round(float(last_close), 4),
            " | ".join(vote_log)
        ])
    print(f"[{datetime.now().strftime('%H:%M:%S')}] {ticker} -> {direction} ({confidence}% confidence) | Last close: {round(float(last_close), 2)}")
    for vote in vote_log:
        print(f"  {vote}")

def run():
    print(f"Fetching data for {TICKER}...")
    df = get_market_data(TICKER, LOOKBACK)
    if len(df) < 30:
        print("Not enough data. Try again later.")
        return
    df = compute_indicators(df)
    direction, confidence, vote_log = generate_signal(df)
    last_close = df.iloc[-1]["close"]
    if direction == "NEUTRAL":
        print("No clear signal today. Indicators do not agree.")
        log_signal(TICKER, "NEUTRAL", 0.0, last_close, vote_log)
        return
    if confidence < MIN_CONFIDENCE:
        print(f"Confidence {confidence}% below minimum {MIN_CONFIDENCE}%. Logging as WEAK.")
        log_signal(TICKER, "WEAK", confidence, last_close, vote_log)
        return
    log_signal(TICKER, direction, confidence, last_close, vote_log)
    print(f"Logged to: {LOG_FILE}")

if __name__ == "__main__":
    run()
