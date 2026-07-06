import json
import os
import sys
from datetime import datetime, timedelta, timezone

import requests
from dotenv import load_dotenv

load_dotenv(os.path.expanduser("~/trading-system/.env"))

OPENCLAW_CONFIG = "/mnt/c/Users/openc/.openclaw/openclaw.json"
HN_SEARCH_URL = "https://hn.algolia.com/api/v1/search"
KEYWORDS = [
    "LLM",
    "AI trading",
    "Claude Code",
    "MCP",
    "alpaca trading",
    "autonomous agents",
    "trading bot",
]
MIN_POINTS = 10
LOOKBACK_DAYS = 7
TOP_N = 5


def get_telegram_config():
    with open(OPENCLAW_CONFIG) as f:
        cfg = json.load(f)
    token = cfg["channels"]["telegram"]["botToken"]
    chat_id = os.environ.get("TELEGRAM_CHAT_ID")
    return token, chat_id


def send_telegram(message):
    try:
        token, chat_id = get_telegram_config()
        url = f"https://api.telegram.org/bot{token}/sendMessage"
        requests.post(url, data={"chat_id": chat_id, "text": message}, timeout=10)
        print("  Telegram sent.")
    except Exception as e:
        print(f"  WARNING: Telegram send failed: {e}")


def search_keyword(keyword, since_ts):
    # Note: "points" is not registered as a filterable numeric attribute on
    # the public HN Algolia API (returns 400) — only created_at_i works
    # server-side, so points must be filtered client-side after the fetch.
    params = {
        "query": keyword,
        "tags": "story",
        "numericFilters": f"created_at_i>{since_ts}",
        "hitsPerPage": 20,
    }
    try:
        resp = requests.get(HN_SEARCH_URL, params=params, timeout=10)
        resp.raise_for_status()
        return resp.json().get("hits", [])
    except Exception as e:
        print(f"  WARNING: search failed for '{keyword}': {e}")
        return []


def fetch_stories():
    since_ts = int((datetime.now(timezone.utc) - timedelta(days=LOOKBACK_DAYS)).timestamp())
    seen = {}
    for keyword in KEYWORDS:
        for hit in search_keyword(keyword, since_ts):
            points = hit.get("points") or 0
            if points < MIN_POINTS:
                continue
            object_id = hit.get("objectID")
            if object_id in seen:
                continue
            title = hit.get("title") or hit.get("story_title")
            if not title:
                continue
            url = hit.get("url") or hit.get("story_url") or f"https://news.ycombinator.com/item?id={object_id}"
            seen[object_id] = {"title": title, "url": url, "points": points}
    return sorted(seen.values(), key=lambda s: s["points"], reverse=True)[:TOP_N]


def build_message(stories):
    now = datetime.now().strftime("%Y-%m-%d")
    if not stories:
        return f"Kronos Tech Watch — {now}\n\nNothing notable this week."
    lines = [f"Kronos Tech Watch — {now}", ""]
    for i, story in enumerate(stories, 1):
        lines.append(f"{i}. {story['title']} ({story['points']} pts)")
        lines.append(f"   {story['url']}")
    return "\n".join(lines)


def run(dry_run=False):
    print("\n-- Tech Watch --")
    stories = fetch_stories()
    message = build_message(stories)
    print(message)
    if dry_run:
        print("  DRY RUN — Telegram send skipped.")
    else:
        send_telegram(message)
    print("---------------------\n")


if __name__ == "__main__":
    run(dry_run="--dry-run" in sys.argv)
