import requests

URL = "https://production.dataviz.cnn.io/index/fearandgreed/graphdata"

def get_fear_greed():
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
        "Accept": "application/json",
        "Referer": "https://www.cnn.com/markets/fear-and-greed"
    }
    response = requests.get(URL, headers=headers, timeout=15)
    response.raise_for_status()
    data = response.json()
    fg = data["fear_and_greed"]
    return {
        "score": fg["score"],
        "rating": fg["rating"],
        "previous_close": fg["previous_close"],
        "previous_1_week": fg["previous_1_week"],
        "previous_1_month": fg["previous_1_month"],
        "previous_1_year": fg["previous_1_year"]
    }

def print_fear_greed(fg):
    print("\n-- CNN Fear & Greed Index --")
    print(f"  Current: {fg['score']} ({fg['rating']})")
    print(f"  Previous close: {fg['previous_close']}")
    print(f"  1 week ago: {fg['previous_1_week']}")
    print(f"  1 month ago: {fg['previous_1_month']}")
    print(f"  1 year ago: {fg['previous_1_year']}")
    print("-----------------------------\n")

if __name__ == "__main__":
    print("Fetching CNN Fear & Greed Index...")
    fg = get_fear_greed()
    print_fear_greed(fg)
