import os
import json
from datetime import datetime, timedelta, timezone
from dotenv import load_dotenv

load_dotenv(os.path.expanduser("~/trading-system/.env"))

from alpaca.data.historical import NewsClient
from alpaca.data.requests import NewsRequest

NEWS_CACHE = os.path.expanduser("~/trading-system/logs/news_cache.json")

SYMBOLS = "SPY,QQQ,GLD,USO,TLT"
KEYWORDS = [
    "fed", "inflation", "oil", "iran", "earnings", "s&p", "spy",
    "interest rate", "fomc", "gdp", "recession", "rate hike", "rate cut",
    "market", "economy", "tariff", "treasury"
]


def fetch_news():
    api_key = os.environ.get("ALPACA_API_KEY")
    secret_key = os.environ.get("ALPACA_SECRET_KEY")
    client = NewsClient(api_key, secret_key)

    end = datetime.now(timezone.utc)
    start = end - timedelta(hours=24)

    req = NewsRequest(
        symbols=SYMBOLS,
        start=start,
        end=end,
        limit=50,
        include_content=False
    )
    resp = client.get_news(req)
    articles = resp.data["news"]

    filtered = []
    for a in articles:
        text = (a.headline + " " + (a.summary or "")).lower()
        if any(kw in text for kw in KEYWORDS):
            filtered.append({
                "headline": a.headline,
                "source": a.source,
                "time": a.created_at.strftime("%H:%M ET") if a.created_at else ""
            })

    return filtered[:10]


def get_news_context():
    """Read cached headlines. Returns a formatted string for analyst prompts."""
    if not os.path.isfile(NEWS_CACHE):
        return "Today's headlines: unavailable (run news_context.py first)"

    with open(NEWS_CACHE) as f:
        data = json.load(f)

    if data.get("date") != datetime.now().strftime("%Y-%m-%d"):
        return "Today's headlines: unavailable (cache is stale)"

    articles = data.get("articles", [])
    if not articles:
        return "Today's headlines: none matching financial keywords"

    lines = ["Today's relevant financial headlines:"]
    for a in articles:
        tag = f" [{a['source']}, {a['time']}]" if a.get("source") else ""
        lines.append(f"- {a['headline']}{tag}")

    return "\n".join(lines)


def run():
    print("\n-- News Context --")
    try:
        articles = fetch_news()
        os.makedirs(os.path.dirname(NEWS_CACHE), exist_ok=True)
        with open(NEWS_CACHE, "w") as f:
            json.dump({
                "date": datetime.now().strftime("%Y-%m-%d"),
                "articles": articles
            }, f, indent=2)
        print(f"  {len(articles)} relevant headlines cached.")
        for a in articles:
            print(f"  [{a['time']}] {a['headline']}")
    except Exception as e:
        print(f"  WARNING: News fetch failed: {e}")
    print("------------------\n")


if __name__ == "__main__":
    run()
