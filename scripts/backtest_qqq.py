import os
import sys
import csv

# Reuses backtest.py's data/indicator/signal/simulation functions directly rather
# than copy-pasting the RSI/MACD vote logic a third time (SPY signal_logger.py +
# QQQ signal_logger_qqq.py already duplicate it once, on purpose, since those are
# standalone live scripts). This file only differs from backtest.py by ticker and
# output path, so it imports backtest.py as a module instead of forking it --
# whatever MIN_VOTES/MIN_CONFIDENCE/grid backtest.py is set to, this stays in sync
# with it automatically, avoiding the kind of drift the confidence-floor constants
# had before they were unified (see CLAUDE.md, September 26 2026).
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import backtest as bt

TICKER = "QQQ"
OUTPUT_FILE = os.path.expanduser("~/trading-system/logs/backtest_qqq_bracket_grid.csv")

def run():
    print(f"Downloading {TICKER} data from 2023-01-01...")
    df = bt.get_historical_data(TICKER)
    df = bt.compute_indicators(df)
    df = df.dropna()
    df["date"] = df.index
    df = df.reset_index(drop=True)

    # Same live-signal filter backtest.py's own run() applies before feeding its
    # bracket grid: MIN_VOTES/MIN_CONFIDENCE gate, not the unfiltered signal set.
    signals = []
    for i in range(1, len(df) - 1):
        latest = df.iloc[i]
        prev = df.iloc[i - 1]
        direction, confidence, _ = bt.generate_signal(latest, prev)
        if direction != "NEUTRAL" and confidence >= bt.MIN_CONFIDENCE:
            signals.append((i, direction, confidence))

    print(f"{len(df)} trading days analyzed, {len(signals)} signals fired "
          f"(min_votes={bt.MIN_VOTES}, min_confidence={bt.MIN_CONFIDENCE:.0f}% -- same live "
          f"settings as signal_logger.py / signal_logger_qqq.py / backtest.py)")

    print(f"\nSimulating GTC bracket outcomes for {len(signals)} fired signals ({TICKER}) across "
          f"{len(bt.STOP_LOSS_GRID)}x{len(bt.TAKE_PROFIT_GRID)} stop/take-profit combinations...")
    grid_results = bt.run_bracket_grid(df, signals)
    print_and_save_grid(grid_results)

def print_and_save_grid(grid_results):
    os.makedirs(os.path.dirname(OUTPUT_FILE), exist_ok=True)
    fieldnames = ["stop_loss_pct", "take_profit_pct", "trades", "resolved", "still_open",
                  "win_rate_pct", "avg_holding_days", "total_pnl_pct", "total_pnl_dollars"]
    with open(OUTPUT_FILE, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(grid_results)

    ranked = sorted(grid_results, key=lambda r: r["total_pnl_dollars"], reverse=True)

    print(f"\n--- {TICKER} BRACKET GRID RESULTS (GTC entry/stop/take-profit, sorted by total PnL $) ---")
    print(f"{'Stop%':>6} {'TP%':>5} {'Trades':>7} {'Open':>5} {'WinRate%':>9} {'AvgDays':>8} {'TotalPnL%':>10} {'TotalPnL$':>10}")
    for r in ranked:
        print(f"{r['stop_loss_pct']:>6.1f} {r['take_profit_pct']:>5.1f} {r['trades']:>7} "
              f"{r['still_open']:>5} {r['win_rate_pct']:>9.1f} {r['avg_holding_days']:>8.1f} "
              f"{r['total_pnl_pct']:>10.2f} {r['total_pnl_dollars']:>10.2f}")

    best = ranked[0]
    print(f"\nBest combo by total PnL ({TICKER}): stop={best['stop_loss_pct']}% / TP={best['take_profit_pct']}% "
          f"-> {best['win_rate_pct']}% win rate, ${best['total_pnl_dollars']:.2f} total PnL "
          f"over {best['trades']} trades ({best['still_open']} still open at end of data)")

    live_rows = [r for r in grid_results if r["stop_loss_pct"] == bt.LIVE_STOP_PCT and r["take_profit_pct"] in (bt.LIVE_TP_PCT, 5.0)]
    for live in sorted(live_rows, key=lambda r: r["take_profit_pct"]):
        rank = ranked.index(live) + 1
        print(f"\nCurrent live SPY bracket setting applied to {TICKER} (stop={bt.LIVE_STOP_PCT:g}%, TP={live['take_profit_pct']:.0f}%, "
              f"the low/high end of trade_logic.py's {bt.LIVE_TP_PCT:.0f}-5% range): rank #{rank} of {len(ranked)} by total PnL "
              f"-> {live['win_rate_pct']}% win rate, ${live['total_pnl_dollars']:.2f} total PnL")

    print(f"\nFull {TICKER} grid saved to: {OUTPUT_FILE}")
    print(f"Signals generated with backtest.py's own generate_signal()/MIN_VOTES/MIN_CONFIDENCE -- only")
    print(f"the ticker and price history differ from logs/backtest_bracket_grid.csv (SPY).")
    print("Note: assumes stop-loss triggers first when both legs are touched same day (conservative);")
    print("'still open' trades are marked-to-market at the last available close and included in total PnL,")
    print("but excluded from the win-rate denominator since they haven't actually resolved.")
    print(f"QQQ is signal-capture-only in the live pipeline (scripts/signal_logger_qqq.py) -- this grid is")
    print(f"exploratory, not validating a bracket structure that is actually being traded on QQQ yet.")

if __name__ == "__main__":
    run()
