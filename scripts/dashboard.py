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
    colors = {
        "PASS": "#1a7a1a",
        "FLAG": "#a67c00",
        "VETO": "#a61a1a"
    }
    return colors.get(verdict, "#333333")

def verdict_bg(verdict):
    colors = {
        "PASS": "#e6f4e6",
        "FLAG": "#fff8e1",
        "VETO": "#fde8e8"
    }
    return colors.get(verdict, "#ffffff")

def verdict_symbol(verdict):
    symbols = {
        "PASS": "✓",
        "FLAG": "⚠",
        "VETO": "✗"
    }
    return symbols.get(verdict, "?")
def build_html(rows):
    rows = list(reversed(rows))
    generated = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    table_rows = ""
    for row in rows:
        verdict = row.get("critic_verdict", "UNKNOWN")
        bg = verdict_bg(verdict)
        color = verdict_color(verdict)
        symbol = verdict_symbol(verdict)

        table_rows += (
            f'<tr style="background:{bg};">'
            f'<td>{row.get("timestamp","")}</td>'
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

    return table_rows, generated, len(rows)

def build_dashboard(rows):
    table_rows, generated, total = build_html(rows)

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
        f"<p class='meta'>Generated: {generated} | Total signals: {total}</p>"
        "<table><thead><tr>"
        "<th>Timestamp</th><th>Ticker</th><th>Direction</th>"
        "<th>Confidence</th><th>Last Close</th>"
        "<th>Andy's Reasoning</th><th>Verdict</th>"
        "<th>Critic's Reason</th><th>Critic Confidence</th>"
        "</tr></thead><tbody>"
        f"{table_rows}"
        "</tbody></table></body></html>"
    )
    return html

def run():
    print("Loading decisions log...")
    rows = load_decisions()

    if not rows:
        print("No decisions found. Run the full pipeline first.")
        return

    print(f"Found {len(rows)} decision(s). Building dashboard...")
    html = build_dashboard(rows)

    with open(DASHBOARD_FILE, "w") as f:
        f.write(html)

    print(f"Dashboard saved to: {DASHBOARD_FILE}")
    print("To view it, run:")
    print(f"  explorer.exe $(wslpath -w {DASHBOARD_FILE})")

if __name__ == "__main__":
    run()
