import yfinance as yf
import pandas_ta as ta
import pandas as pd

TICKER = "SPY"
LOOKBACK = 60

def get_data():
    df = yf.download(TICKER, period=f"{LOOKBACK}d", interval="1d", progress=False)
    df.columns = [col[0].lower() if isinstance(col, tuple) else col.lower() for col in df.columns]
    return df

def run_ema_rsi_strategy(df):
    df["ema_fast"] = ta.ema(df["close"], length=9)
    df["ema_slow"] = ta.ema(df["close"], length=21)
    df["rsi"] = ta.rsi(df["close"], length=14)

    results = []
    for i in range(1, len(df)):
        prev_fast = df["ema_fast"].iloc[i-1]
        prev_slow = df["ema_slow"].iloc[i-1]
        curr_fast = df["ema_fast"].iloc[i]
        curr_slow = df["ema_slow"].iloc[i]
        rsi = df["rsi"].iloc[i]
        date = df.index[i].strftime("%Y-%m-%d")
        price = df["close"].iloc[i]

        crossover = prev_fast <= prev_slow and curr_fast > curr_slow
        crossunder = prev_fast >= prev_slow and curr_fast < curr_slow

        if crossover and rsi < 70:
            signal = "LONG"
        elif crossunder and rsi > 30:
            signal = "SHORT"
        else:
            signal = "NONE"

        results.append({
            "date": date,
            "price": round(float(price), 2),
            "rsi": round(float(rsi), 1),
            "signal": signal
        })

    return results

def main():
    df = get_data()
    results = run_ema_rsi_strategy(df)

    print(f"{'Date':<12} {'Price':<10} {'RSI':<6} {'Signal'}")
    print("-" * 40)
    for r in results:
        if r["signal"] != "NONE":
            print(f"{r['date']:<12} {r['price']:<10} {r['rsi']:<6} {r['signal']}")

    print("\n--- Full log (last 30 days) ---")
    for r in results[-30:]:
        print(f"{r['date']:<12} {r['price']:<10} {r['rsi']:<6} {r['signal']}")

if __name__ == "__main__":
    main()
