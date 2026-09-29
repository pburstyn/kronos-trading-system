import json
import os
import sys
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from difflib import SequenceMatcher
from email.utils import parsedate_to_datetime

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

# Reddit and arXiv share this list -- different phrasing from KEYWORDS above
# (HN's list) by design, per the original request; not consolidated into one
# list since the two sources call for different keyword shapes.
REDDIT_ARXIV_KEYWORDS = [
    "trading",
    "agent",
    "open source",
    "fine-tuning",
    "MCP",
    "quantitative",
    "systematic",
]

# Public JSON endpoint, no OAuth -- but Reddit's own bot-detection can still
# block it outright regardless of headers (see note on fetch_reddit_posts()).
REDDIT_SUBREDDITS = ["MachineLearning", "algotrading", "ArtificialIntelligence"]
REDDIT_MIN_SCORE = 50
REDDIT_TOP_N = 3
REDDIT_HEADERS = {"User-Agent": "kronos-tech-watch/1.0 (by /u/pburstyn)"}

ARXIV_FEEDS = {
    "cs.AI": "https://arxiv.org/rss/cs.AI",
    "q-fin": "https://arxiv.org/rss/q-fin",
}
ARXIV_TOP_N = 3

# difflib.SequenceMatcher ratio -- calibrated against real headline pairs:
# near-identical titles score ~1.0, genuinely different (even same-topic)
# titles topped out at 0.47 in that test, so 0.6 gives comfortable margin
# without being so loose it drops unrelated stories that just share a keyword.
TITLE_SIMILARITY_THRESHOLD = 0.6


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


def fetch_hn_stories(since_ts):
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


def fetch_reddit_posts(since_ts):
    """Returns (posts, any_source_reachable). The second value lets
    build_message() distinguish "checked, nothing matched" from "couldn't
    reach Reddit at all" -- an important distinction here specifically:
    Reddit's public .json endpoints now frequently 403 or redirect
    unauthenticated requests to a login page regardless of User-Agent,
    a change from their 2023 API lockdown that affects many non-residential
    IPs. Confirmed happening in the environment this was developed in
    (403 from www.reddit.com, redirect-to-login from old.reddit.com, 403
    from api.reddit.com, tried with several realistic browser User-Agents) --
    unverified whether the production machine's residential IP fares
    differently. See CLAUDE.md Tech Watch Extended section."""
    seen = {}
    any_ok = False
    for subreddit in REDDIT_SUBREDDITS:
        url = f"https://www.reddit.com/r/{subreddit}/hot.json"
        try:
            resp = requests.get(url, headers=REDDIT_HEADERS, params={"limit": 25}, timeout=10)
            resp.raise_for_status()
            data = resp.json()
        except Exception as e:
            print(f"  WARNING: Reddit fetch failed for r/{subreddit}: {e}")
            continue
        any_ok = True
        for child in data.get("data", {}).get("children", []):
            post = child.get("data", {})
            if (post.get("created_utc") or 0) < since_ts:
                continue
            score = post.get("score") or 0
            if score < REDDIT_MIN_SCORE:
                continue
            title = post.get("title") or ""
            text = (title + " " + (post.get("selftext") or "")).lower()
            if not any(kw.lower() in text for kw in REDDIT_ARXIV_KEYWORDS):
                continue
            post_id = post.get("id")
            if not post_id or post_id in seen:
                continue
            permalink = post.get("permalink", "")
            post_url = f"https://reddit.com{permalink}" if permalink else (post.get("url") or "")
            seen[post_id] = {
                "title": title,
                "url": post_url,
                "score": score,
                "source": f"r/{subreddit}",
            }
    return sorted(seen.values(), key=lambda p: p["score"], reverse=True), any_ok


def fetch_arxiv_entries(since_ts):
    """Returns (entries, any_source_reachable), same shape as
    fetch_reddit_posts() for build_message() to treat uniformly. Unlike HN/
    Reddit, arXiv preprints carry no popularity signal (no points/upvotes) --
    "top" here means most recent by pubDate, which is also how the RSS feed
    itself is already ordered."""
    seen = {}
    any_ok = False
    for category, feed_url in ARXIV_FEEDS.items():
        try:
            resp = requests.get(feed_url, timeout=15)
            resp.raise_for_status()
            root = ET.fromstring(resp.content)
        except Exception as e:
            print(f"  WARNING: arXiv fetch failed for {category}: {e}")
            continue
        any_ok = True
        for item in root.findall(".//item"):
            title = (item.findtext("title") or "").strip()
            link = (item.findtext("link") or "").strip()
            description = (item.findtext("description") or "").strip()
            pub_date_raw = item.findtext("pubDate")
            try:
                pub_dt = parsedate_to_datetime(pub_date_raw) if pub_date_raw else None
            except (TypeError, ValueError):
                pub_dt = None
            if pub_dt is not None and pub_dt.timestamp() < since_ts:
                continue
            text = (title + " " + description).lower()
            if not any(kw.lower() in text for kw in REDDIT_ARXIV_KEYWORDS):
                continue
            if not title or not link or link in seen:
                continue
            seen[link] = {"title": title, "url": link, "source": category, "pub_dt": pub_dt}
    epoch = datetime.min.replace(tzinfo=timezone.utc)
    return sorted(seen.values(), key=lambda e: e["pub_dt"] or epoch, reverse=True), any_ok


def is_similar_to_any(title, other_titles, threshold=TITLE_SIMILARITY_THRESHOLD):
    norm = title.strip().lower()
    for other in other_titles:
        if SequenceMatcher(None, norm, other.strip().lower()).ratio() >= threshold:
            return True
    return False


def build_message(hn_stories, reddit_posts, reddit_ok, arxiv_entries, arxiv_ok):
    now = datetime.now().strftime("%Y-%m-%d")
    if not hn_stories and not reddit_posts and not arxiv_entries:
        return f"Kronos Tech Watch — {now}\n\nNothing notable this week."

    lines = [f"Kronos Tech Watch — {now}", ""]

    lines.append("-- Hacker News --")
    if hn_stories:
        for i, story in enumerate(hn_stories, 1):
            lines.append(f"{i}. {story['title']} ({story['points']} pts)")
            lines.append(f"   {story['url']}")
    else:
        lines.append("Nothing notable this week.")
    lines.append("")

    lines.append("-- Reddit --")
    if reddit_posts:
        for i, post in enumerate(reddit_posts, 1):
            lines.append(f"{i}. [{post['source']}] {post['title']} ({post['score']} upvotes)")
            lines.append(f"   {post['url']}")
    elif not reddit_ok:
        lines.append("(could not reach Reddit this week — see pipeline log)")
    else:
        lines.append("Nothing notable this week.")
    lines.append("")

    lines.append("-- arXiv --")
    if arxiv_entries:
        for i, entry in enumerate(arxiv_entries, 1):
            lines.append(f"{i}. [{entry['source']}] {entry['title']}")
            lines.append(f"   {entry['url']}")
    elif not arxiv_ok:
        lines.append("(could not reach arXiv this week — see pipeline log)")
    else:
        lines.append("Nothing notable this week.")

    return "\n".join(lines)


def run(dry_run=False):
    print("\n-- Tech Watch --")
    since_ts = int((datetime.now(timezone.utc) - timedelta(days=LOOKBACK_DAYS)).timestamp())

    hn_stories = fetch_hn_stories(since_ts)
    reddit_posts, reddit_ok = fetch_reddit_posts(since_ts)
    arxiv_entries, arxiv_ok = fetch_arxiv_entries(since_ts)

    hn_titles = [s["title"] for s in hn_stories]
    reddit_posts = [p for p in reddit_posts if not is_similar_to_any(p["title"], hn_titles)][:REDDIT_TOP_N]
    arxiv_entries = [e for e in arxiv_entries if not is_similar_to_any(e["title"], hn_titles)][:ARXIV_TOP_N]

    message = build_message(hn_stories, reddit_posts, reddit_ok, arxiv_entries, arxiv_ok)
    print(message)
    if dry_run:
        print("  DRY RUN — Telegram send skipped.")
    else:
        send_telegram(message)
    print("---------------------\n")


if __name__ == "__main__":
    run(dry_run="--dry-run" in sys.argv)
