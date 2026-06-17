import os
import requests
from dotenv import load_dotenv

load_dotenv(os.path.expanduser("~/trading-system/.env"))

API_KEY = os.environ.get("FRED_API_KEY")
BASE_URL = "https://api.stlouisfed.org/fred/series/observations"

SERIES = {
    "fed_funds_rate": "FEDFUNDS",
    "cpi_inflation": "CPIAUCSL",
    "unemployment_rate": "UNRATE"
}

def get_latest_value(series_id):
    params = {
        "series_id": series_id,
        "api_key": API_KEY,
        "file_type": "json",
        "sort_order": "desc",
        "limit": 1
    }
    response = requests.get(BASE_URL, params=params, timeout=15)
    response.raise_for_status()
    data = response.json()
    observation = data["observations"][0]
    return observation["date"], observation["value"]

def get_macro_snapshot():
    snapshot = {}
    for label, series_id in SERIES.items():
        date, value = get_latest_value(series_id)
        snapshot[label] = {"date": date, "value": value}
    return snapshot

def print_snapshot(snapshot):
    print("\n-- Macro Snapshot --")
    print(f"  Fed Funds Rate: {snapshot['fed_funds_rate']['value']}% (as of {snapshot['fed_funds_rate']['date']})")
    print(f"  CPI Index: {snapshot['cpi_inflation']['value']} (as of {snapshot['cpi_inflation']['date']})")
    print(f"  Unemployment Rate: {snapshot['unemployment_rate']['value']}% (as of {snapshot['unemployment_rate']['date']})")
    print("---------------------\n")

if __name__ == "__main__":
    print("Fetching macro snapshot from FRED...")
    snapshot = get_macro_snapshot()
    print_snapshot(snapshot)
