import csv
import os
from datetime import datetime

DECISIONS_LOG = os.path.expanduser(
    "~/trading-system/logs/decisions_log.csv"
)
DASHBOARD_FILE = os.path.expanduser(
    "~/trading-system/logs/dashboard.html"
)

def load_decisions():
    if not os.path.isfile(DECISIONS_LOG):
        return []
    with open(DECISIONS_LOG, "r") as f:
        return list(csv.DictReader(f))

def verdict_color(verdict):
    colors = {"PASS": "#1a7a1a", "FLAG": "#a67c00", "VETO": "#a61a1a"}
    return colors.get(verdict, "#333333")

def verdict_bg(verdict):
    colors = {"PASS": "#e6f4e6", "FLAG": "#fff8e1", "VETO": "#fde8e8"}
    return colors.get(verdict, "#ffffff")

def verdict_symbol(verdict):
    symbols = {"PASS": "&#10003;", "FLAG": "&#9888;", "VETO": "&#10007;"}
    return symbols.get(verdict, "?")

def trade_calculator(rows):
    if not rows:
        return ""
    latest = rows[-1]
    verdict = latest.get("critic_verdict", "").strip()
    try:
        price = float(latest.get("last_close", 0))
    except:
        return ""
    if price == 0:
        return ""
    stop_loss = round(price * 0.98, 2)
    take_profit = round(price * 1.03, 2)
    shares = int(1000 / price) or 1
    direction = latest.get("direction", "")
    if verdict == "PASS":
        bg = "#e6f4e6"
        border = "#1a7a1a"
        action = "BUY" if direction == "UP" else "SELL"
        action_color = "#1a7a1a" if direction == "UP" else "#a61a1a"
        note = "Place this order on TradingView paper trading now."
        note_color = "#1a7a1a"
    else:
        bg = "#f5f5f5"
        border = "#cccccc"
        action = "NO TRADE"
        action_color = "#666666"
        note = f"Verdict is {verdict} — no trade today."
        note_color = "#666666"
    return (
        f'<div style="margin:20px 0;padding:20px;background:{bg};'
        f'border:2px solid {border};border-radius:6px;max-width:600px;">'
        f'<h2 style="margin:0 0 12px 0;color:#1B2F5E;font-size:1.1em;">Today\'s Trade Calculator</h2>'
        f'<table style="width:100%;border-collapse:collapse;">'
        f'<tr><td style="padding:6px 10px;font-weight:bold;width:50%;">Action</td>'
        f'<td style="padding:6px 10px;color:{action_color};font-weight:bold;font-size:1.1em;">{action}</td></tr>'
        f'<tr style="background:rgba(0,0,0,0.03);">'
        f'<td style="padding:6px 10px;font-weight:bold;">Last Close</td>'
        f'<td style="padding:6px 10px;">${price}</td></tr>'
        f'<tr><td style="padding:6px 10px;font-weight:bold;">Shares (approx $1,000)</td>'
        f'<td style="padding:6px 10px;">{shares} shares</td></tr>'
        f'<tr style="background:rgba(0,0,0,0.03);">'
        f'<td style="padding:6px 10px;font-weight:bold;">Stop Loss (2% below)</td>'
        f'<td style="padding:6px 10px;color:#a61a1a;font-weight:bold;">${stop_loss}</td></tr>'
        f'<tr><td style="padding:6px 10px;font-weight:bold;">Take Profit (3% above)</td>'
        f'<td style="padding:6px 10px;color:#1a7a1a;font-weight:bold;">${take_profit}</td></tr>'
        f'</table>'
        f'<p style="margin:12px 0 0 0;font-size:0.85em;color:{note_color};">{note}</p>'
        f'</div>'
    )

def build_table_rows(rows):
    rows = [r for r in rows if r.get('timestamp','') >= '2026-05-16']
    rows = list(reversed(rows))
    table_rows = ""
    for row in rows:
        verdict = row.get("critic_verdict", "UNKNOWN")
        bg = verdict_bg(verdict)
        color = verdict_color(verdict)
        symbol = verdict_symbol(verdict)
        table_rows += (
            f'<tr style="background:{bg};">'
            f'<td>{datetime.strptime(row.get("timestamp",""), "%Y-%m-%d %H:%M:%S").strftime("%m/%d/%Y %H:%M") if row.get("timestamp") else ""}</td>'
            f'<td><strong>{row.get("ticker","")}</strong></td>'
            f'<td>{row.get("direction","")}</td>'
            f'<td>{row.get("signal_confidence_pct","")}%</td>'
            f'<td>${row.get("last_close","")}</td>'
            f'<td style="font-size:0.85em;">{row.get("andy_reasoning","")[:200]}...</td>'
            f'<td style="color:{color};font-weight:bold;">{symbol} {verdict}</td>'
            f'<td style="font-size:0.85em;">{row.get("critic_reason","")}</td>'
            f'<td>{row.get("critic_confidence","")}</td>'
            f'</tr>'
        )
    return table_rows

def run():
    print("Loading decisions log...")
    rows = load_decisions()
    if not rows:
        print("No decisions found. Run the full pipeline first.")
        return
    print(f"Found {len(rows)} decision(s). Building dashboard...")
    generated = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    calculator = trade_calculator(rows)
    table_rows = build_table_rows(rows)
    html = (
        "<!DOCTYPE html><html><head><meta charset='UTF-8'>"
        "<title>Trading System Dashboard</title><style>"
        "body{font-family:Arial,sans-serif;margin:20px;background:#f5f5f5;}"
        "h1{color:#1B2F5E;}"
        "p.meta{color:#666;font-size:0.85em;}"
        "table{border-collapse:collapse;width:100%;background:white;}"
        "th{background:#1B2F5E;color:white;padding:10px;text-align:left;font-size:0.85em;}"
        "td{padding:8px 10px;border-bottom:1px solid #ddd;vertical-align:top;font-size:0.85em;}"
        "tr:hover{filter:brightness(0.97);}"
        "</style></head><body>"
        "<h1>Trading System Dashboard</h1>"
        f"<p class='meta'>Generated: {generated} | Total signals: {len(rows)}</p>"
        f"{calculator}"
        "<h2 style='color:#1B2F5E;font-size:1em;margin-top:24px;'>Signal History</h2>"
        "<table><thead><tr>"
        "<th>Timestamp</th><th>Ticker</th><th>Direction</th>"
        "<th>Confidence</th><th>Last Close</th>"
        "<th>Andy's Reasoning</th><th>Verdict</th>"
        "<th>Critic's Reason</th><th>Critic Confidence</th>"
        "</tr></thead><tbody>"
        f"{table_rows}"
        "</tbody></table></body></html>"
    )
    with open(DASHBOARD_FILE, "w") as f:
        f.write(html)
    print(f"Dashboard saved to: {DASHBOARD_FILE}")
    print("To view it, run:")
    print(f"  explorer.exe $(wslpath -w {DASHBOARD_FILE})")

if __name__ == "__main__":
    run()
