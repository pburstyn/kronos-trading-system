"""Research backtest: does the first half hour predict the last half hour?

Read-only. Uses research/data/{SPY,QQQ}_30min.csv (from pull_intraday_data.py),
plus Alpaca's trading calendar and corporate actions endpoints. Places no orders
and touches nothing in logs/ or scripts/.

  first half hour return = 9:30 bar close / prior session's 15:30 bar close - 1
  last half hour return  = 15:30 bar close / 15:30 bar open - 1

Strategy: enter at the 15:30 bar open in the direction of the first half hour
return, exit at the 15:30 bar close (16:00). Baseline: long every day over the
same window. Each is run at 0.02% and 0.05% round-trip cost.

Usage: venv/bin/python research/intraday_momentum_backtest.py
Output: research/intraday_momentum_results.csv
"""
import os
from datetime import date, time
import numpy as np
import pandas as pd
from dotenv import load_dotenv

from alpaca.trading.client import TradingClient
from alpaca.trading.requests import GetCalendarRequest
from alpaca.data.historical.corporate_actions import CorporateActionsClient
from alpaca.data.requests import CorporateActionsRequest
from alpaca.data.enums import CorporateActionsType

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
load_dotenv(os.path.join(REPO, ".env"))

TICKERS = ["SPY", "QQQ"]
DATA_DIR = os.path.join(REPO, "research", "data")
RESULTS = os.path.join(REPO, "research", "intraday_momentum_results.csv")
COSTS = [0.0002, 0.0005]
# Known bad QQQ data days (flagged by pull_intraday_data.py on October 19).
DROP_DAYS = {"QQQ": {date(2016, 2, 22), date(2018, 5, 2), date(2018, 5, 3)}}
PERIODS = [("2016-2022", 2016, 2022), ("2023-today", 2023, 9999)]


def load_bars(ticker):
    df = pd.read_csv(os.path.join(DATA_DIR, f"{ticker}_30min.csv"), parse_dates=["timestamp"])
    df["date"] = df["timestamp"].dt.date
    df["time"] = df["timestamp"].dt.strftime("%H:%M")
    return df


def get_sessions(trading_client, start, end):
    """Ordered list of (date, is_early_close) for NYSE sessions in range."""
    days = trading_client.get_calendar(GetCalendarRequest(start=start, end=end))
    return [(d.date, d.close.time() != time(16, 0)) for d in days]


def get_ex_dividend_dates(ca_client, start, end):
    resp = ca_client.get_corporate_actions(CorporateActionsRequest(
        symbols=TICKERS, types=[CorporateActionsType.CASH_DIVIDEND], start=start, end=end))
    out = {t: set() for t in TICKERS}
    for d in resp.data.get("cash_dividends", []):
        out[d.symbol].add(d.ex_date)
    return out


def quarters_without_ex_date(ex_dates, first_day, last_day):
    """SPY and QQQ both pay quarterly, with ex-dates in the quarter's last month.
    A quarter whose last month the data fully covers but has no ex-date from
    Alpaca likely means a gap in Alpaca's corporate actions data."""
    have = {(d.year, (d.month - 1) // 3) for d in ex_dates}
    gaps = []
    y, q = first_day.year, (first_day.month - 1) // 3
    while (y, q) <= (last_day.year, (last_day.month - 1) // 3):
        last_month_start = date(y, 3 * q + 3, 1)
        q_end = date(y + (q == 3), (3 * q + 3) % 12 + 1, 1)
        if last_month_start >= first_day and q_end <= last_day and (y, q) not in have:
            gaps.append(f"{y} Q{q + 1}")
        y, q = (y + 1, 0) if q == 3 else (y, q + 1)
    return gaps


def build_days(ticker, bars, sessions, ex_dates):
    by_day = {d: g.set_index("time") for d, g in bars.groupby("date")}
    drop = DROP_DAYS.get(ticker, set())
    skipped = {"dropped bad data": 0, "early close": 0, "ex-dividend": 0,
               "prior 15:30 close unavailable": 0, "missing 9:30 or 15:30 bar": 0}
    rows = []
    first_bar_day = min(by_day)
    for i, (d, early) in enumerate(sessions):
        if d not in by_day and d < first_bar_day:
            continue
        if i == 0 or d == first_bar_day:
            continue  # no prior session to measure the gap from
        if d in drop:
            skipped["dropped bad data"] += 1
            continue
        if early:
            skipped["early close"] += 1
            continue
        if d in ex_dates:
            skipped["ex-dividend"] += 1
            continue
        prior_day, _ = sessions[i - 1]
        prior = by_day.get(prior_day)
        # A prior session that was dropped or closed early has no usable 15:30 bar.
        if prior_day in drop or prior is None or "15:30" not in prior.index:
            skipped["prior 15:30 close unavailable"] += 1
            continue
        today = by_day.get(d)
        if today is None or "09:30" not in today.index or "15:30" not in today.index:
            skipped["missing 9:30 or 15:30 bar"] += 1
            continue
        rows.append({
            "date": d,
            "first_half_hour": today.at["09:30", "close"] / prior.at["15:30", "close"] - 1,
            "last_half_hour": today.at["15:30", "close"] / today.at["15:30", "open"] - 1,
        })
    days = pd.DataFrame(rows)
    days["year"] = [d.year for d in days["date"]]
    return days, skipped


def trade_stats(net):
    """net: per-trade net returns. Total return and drawdown compound trade by trade."""
    n = len(net)
    if n == 0:
        return dict(trades=0, win_rate=np.nan, profit_factor=np.nan, avg_net_return=np.nan,
                    total_net_return=np.nan, max_drawdown=np.nan)
    gains = net[net > 0].sum()
    losses = -net[net < 0].sum()
    equity = np.cumprod(1 + net.to_numpy())
    peak = np.maximum.accumulate(np.concatenate([[1.0], equity]))[1:]
    return dict(
        trades=n,
        win_rate=(net > 0).mean(),
        profit_factor=gains / losses if losses > 0 else np.inf,
        avg_net_return=net.mean(),
        total_net_return=equity[-1] - 1,
        max_drawdown=(equity / peak - 1).min(),
    )


def signal_stats(days):
    signs = days[(days["first_half_hour"] != 0) & (days["last_half_hour"] != 0)]
    return dict(
        signal_days=len(days),
        correlation=days["first_half_hour"].corr(days["last_half_hour"]),
        hit_rate=(np.sign(signs["first_half_hour"]) == np.sign(signs["last_half_hour"])).mean(),
    )


def evaluate(ticker, scope, days):
    sig = signal_stats(days)
    traded = days[days["first_half_hour"] != 0]
    gross = {
        "momentum": np.sign(traded["first_half_hour"]) * traded["last_half_hour"],
        "long_baseline": days["last_half_hour"],
    }
    out = []
    for strategy, g in gross.items():
        for cost in COSTS:
            out.append({"ticker": ticker, "scope": scope, "strategy": strategy,
                        "cost_pct": cost * 100, **trade_stats(g - cost), **sig})
    return out


def main():
    api_key = os.environ.get("ALPACA_API_KEY")
    secret_key = os.environ.get("ALPACA_SECRET_KEY")
    trading_client = TradingClient(api_key, secret_key, paper=True)
    ca_client = CorporateActionsClient(api_key, secret_key)

    bars = {t: load_bars(t) for t in TICKERS}
    start = min(b["date"].min() for b in bars.values())
    end = max(b["date"].max() for b in bars.values())
    sessions = get_sessions(trading_client, start, end)
    ex_dates = get_ex_dividend_dates(ca_client, start, end)

    results = []
    for ticker in TICKERS:
        days, skipped = build_days(ticker, bars[ticker], sessions, ex_dates[ticker])
        print(f"{ticker}: {len(days)} days used, {days['date'].min()} to {days['date'].max()}")
        print(f"  Ex-dividend dates from Alpaca: {len(ex_dates[ticker])}")
        for reason, n in skipped.items():
            print(f"  Skipped, {reason}: {n}")
        gaps = quarters_without_ex_date(ex_dates[ticker], start, end)
        if gaps:
            print(f"  WARNING: Alpaca has no ex-dividend date for {', '.join(gaps)}. "
                  f"Those ex-dates were not skipped.")

        results += evaluate(ticker, "all", days)
        for year, g in days.groupby("year"):
            results += evaluate(ticker, str(year), g)
        for label, y0, y1 in PERIODS:
            results += evaluate(ticker, label, days[(days["year"] >= y0) & (days["year"] <= y1)])
        print()

    df = pd.DataFrame(results)
    df.to_csv(RESULTS, index=False, float_format="%.6f")
    print(f"Saved {len(df)} rows to {RESULTS}\n")
    print_summary(df)


def pct(x, places=2):
    return f"{x * 100:.{places}f}%"


def print_summary(df):
    print("Summary")
    for ticker in TICKERS:
        t = df[df["ticker"] == ticker]
        row = t[(t["scope"] == "all")].iloc[0]
        print(f"\n{ticker}: correlation {row['correlation']:.3f}, sign hit rate "
              f"{pct(row['hit_rate'], 1)} over {int(row['signal_days'])} days.")
        for scope in ["all", "2016-2022", "2023-today"]:
            s = t[t["scope"] == scope]
            sig = s.iloc[0]
            print(f"  {scope}: correlation {sig['correlation']:.3f}, hit rate {pct(sig['hit_rate'], 1)}")
            for _, r in s.iterrows():
                print(f"    {r['strategy']:<14} cost {r['cost_pct']:.2f}%: {int(r['trades'])} trades, "
                      f"win {pct(r['win_rate'], 1)}, PF {r['profit_factor']:.2f}, "
                      f"avg {pct(r['avg_net_return'], 3)}, total {pct(r['total_net_return'], 1)}, "
                      f"max DD {pct(r['max_drawdown'], 1)}")
        yearly = t[(t["strategy"] == "momentum") & (t["cost_pct"].round(2) == 0.05)
                   & t["scope"].str.fullmatch(r"\d{4}")]
        up = yearly[yearly["total_net_return"] > 0]["scope"].tolist()
        print(f"  Momentum at 0.05% was profitable in {len(up)} of {len(yearly)} years: {', '.join(up) or 'none'}.")


if __name__ == "__main__":
    main()
