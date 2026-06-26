import json
import os
import subprocess
import sys
from datetime import datetime

import requests
from dotenv import load_dotenv

load_dotenv(os.path.expanduser("~/trading-system/.env"))

OPENCLAW_CONFIG = "/mnt/c/Users/openc/.openclaw/openclaw.json"
STATUS_FILE = os.path.expanduser("~/trading-system/logs/andy_status.json")
HEALTH_LOG = os.path.expanduser("~/trading-system/logs/andy_health.log")


def check_andy():
    try:
        result = subprocess.run(
            ["powershell.exe", "-Command",
             "Test-NetConnection -ComputerName localhost -Port 18789 -InformationLevel Quiet"],
            capture_output=True, text=True, timeout=15
        )
        return result.stdout.strip().lower() == "true"
    except Exception:
        return False


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
    except Exception as e:
        log(f"  WARNING: Telegram send failed: {e}")


def read_last_status():
    if not os.path.isfile(STATUS_FILE):
        return None
    with open(STATUS_FILE) as f:
        return json.load(f).get("status")


def write_status(status):
    os.makedirs(os.path.dirname(STATUS_FILE), exist_ok=True)
    with open(STATUS_FILE, "w") as f:
        json.dump({
            "status": status,
            "last_checked": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        }, f)


def log(message):
    print(message)
    os.makedirs(os.path.dirname(HEALTH_LOG), exist_ok=True)
    with open(HEALTH_LOG, "a") as f:
        f.write(message + "\n")


def run():
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    is_up = check_andy()
    status = "UP" if is_up else "DOWN"
    last_status = read_last_status()

    log(f"{now} — Andy: {status}")

    if last_status != status:
        if not is_up:
            msg = f"ALERT: Andy (OpenClaw) is DOWN as of {now}.\nStart gateway.cmd in PowerShell to bring him back up."
            send_telegram(msg)
            log("  Alert sent: Andy DOWN")
        elif last_status == "DOWN":
            msg = f"Andy (OpenClaw) is back UP as of {now}."
            send_telegram(msg)
            log("  Alert sent: Andy back UP")

    write_status(status)


if __name__ == "__main__":
    run()
