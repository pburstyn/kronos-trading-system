import yfinance as yf
import pandas_ta as ta
import pandas as pd
import numpy as np
from datetime import datetime

TICKERS = ["SPY", "QQQ"]
PERIOD = "2y"
MIN_CONFIDENCE = 60.0
MIN_VOTES = 2
POSITION_SIZE = 1000.0
STOP_LOSS_PCT = 0.02
TAKE_PROFIT_PCT = 0.03
MAX_HOLD_DAYS = 10

def get_data(ticker):
    df = yf.download(ticker, period=PERIOD, interval="1d", progress=False)
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
    bull_votes = 0
    bear_votes = 0
    if 50 <= rsi <= 70:
        bull_votes += 1
    elif rsi < 50:
        bear_votes += 1
    if macd_line > macd_signal:
        bull_votes += 1
    else:
        bear_votes += 1
    if macd_hist > 0 and macd_hist > macd_hist_prev:
        bull_votes += 1
    elif macd_hist < 0 and macd_hist < macd_hist_prev:
        bear_votes += 1
    if bull_votes >= MIN_VOTES and bull_votes > bear_votes:
        direction = "UP"
        votes = bull_votes
    elif bear_votes >= MIN_VOTES and bear_votes > bull_votes:
        direction = "DOWN"
        votes = bear_votes
    else:
        return "NEUTRAL", 0.0
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
    elif volume < vol_ma * 0.8:
        base -= 10
    confidence = round(min(max(base, 0), 99.0), 2)
    return direction, confidence

def simulate_trade(df, entry_idx, direction, entry_price):
    shares = POSITION_SIZE / entry_price
    if direction == "UP":
        stop = entry_price * (1 - STOP_LOSS_PCT)
        target = entry_price * (1 + TAKE_PROFIT_PCT)
    else:
        stop = entry_price * (1 + STOP_LOSS_PCT)
        target = entry_price * (1 - TAKE_PROFIT_PCT)
    for j in range(entry_idx, min(entry_idx + MAX_HOLD_DAYS, len(df))):
        day = df.iloc[j]
        high = float(day["high"])
        low = float(day["low"])
        if direction == "UP":
            if low <= stop:
                return (stop - entry_price) * shares, "LOSS", j
            elif high >= target:
                return (target - entry_price) * shares, "WIN", j
        else:
            if high >= stop:
                return (entry_price - stop) * shares, "LOSS", j
            elif low <= target:
                return (entry_price - target) * shares, "WIN", j
    exit_idx = min(entry_idx + MAX_HOLD_DAYS - 1, len(df) - 1)
    close = float(df.iloc[exit_idx]["close"])
    if direction == "UP":
        pnl = (close - entry_price) * shares
    else:
        pnl = (entry_price - close) * shares
    outcome = "WIN" if pnl > 0 else "LOSS"
    return pnl, outcome, exit_idx

def backtest(ticker):
    print(f"Backtesting {ticker}...")
    df = get_data(ticker)
    df = compute_indicators(df)
    df = df.dropna().reset_index()
    trades = []
    balance = 10000.0
    peak_balance = balance
    max_drawdown = 0.0
    i = 1
    while i < len(df) - 1:
        latest = df.iloc[i]
        prev = df.iloc[i - 1]
        result = generate_signal(latest, prev)
        if len(result) != 2:
            i += 1
            continue
        direction, confidence = result
        if direction == "NEUTRAL" or confidence < MIN_CONFIDENCE:
            i += 1
            continue
        entry_price = float(df.iloc[i + 1]["open"])
        pnl, outcome, exit_idx = simulate_trade(df, i + 1, direction, entry_price)
        balance += pnl
        peak_balance = max(peak_balance, balance)
        drawdown = (peak_balance - balance) / peak_balance * 100
        max_drawdown = max(max_drawdown, drawdown)
        trades.append({
            "date": str(df.iloc[i]["Date"])[:10],
            "direction": direction,
            "confidence": confidence,
            "entry": round(entry_price, 2),
            "pnl": round(pnl, 2),
            "outcome": outcome,
            "days_held": exit_idx - i
        })
        i = exit_idx + 1
    return trades, balance, max_drawdown

def print_results(ticker, trades, balance, max_drawdown):
    if not trades:
        print(f"No trades generated for {ticker}")
        return
    wins = [t for t in trades if t["outcome"] == "WIN"]
    losses = [t for t in trades if t["outcome"] == "LOSS"]
    total_gains = sum(t["pnl"] for t in wins)
    total_losses = abs(sum(t["pnl"] for t in losses))
    win_rate = len(wins) / len(trades) * 100 if trades else 0
    profit_factor = total_gains / total_losses if total_losses > 0 else float("inf")
    total_pnl = sum(t["pnl"] for t in trades)
    avg_days = sum(t["days_held"] for t in trades) / len(trades)
    print(f"\n-- {ticker} Backtest Results --")
    print(f"  Period:        {PERIOD}")
    print(f"  Total trades:  {len(trades)}")
    print(f"  Wins:          {len(wins)}")
    print(f"  Losses:        {len(losses)}")
    print(f"  Win rate:      {round(win_rate, 1)}% (target: >50%)")
    print(f"  Profit factor: {round(profit_factor, 2)} (target: >1.2)")
    print(f"  Max drawdown:  {round(max_drawdown, 1)}% (target: <15%)")
    print(f"  Avg hold days: {round(avg_days, 1)}")
    print(f"  Total P&L:     ${round(total_pnl, 2)}")
    print(f"  Final balance: ${round(balance, 2)}")
    passed = win_rate > 50 and profit_factor > 1.2 and max_drawdown < 15
    if passed:
        print(f"  VERDICT: PASS - Ready for paper trading")
    else:
        print(f"  VERDICT: FAIL - Signal engine needs work")
        if win_rate <= 50:
            print(f"  ISSUE: Win rate {round(win_rate,1)}% is below 50%")
        if profit_factor <= 1.2:
            print(f"  ISSUE: Profit factor {round(profit_factor,2)} is below 1.2")
        if max_drawdown >= 15:
            print(f"  ISSUE: Max drawdown {round(max_drawdown,1)}% exceeds 15%")

if __name__ == "__main__":
    print("Starting backtest...")
    for ticker in TICKERS:
        trades, balance, max_drawdown = backtest(ticker)
        print_results(ticker, trades, balance, max_drawdown)
    print("Backtest complete.")
