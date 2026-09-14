import os
import subprocess
import sys
import time
from datetime import datetime

from dotenv import load_dotenv

load_dotenv(os.path.expanduser("~/trading-system/.env"))

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from telegram_notify import get_telegram_config, send_telegram
from andy_health import check_andy

LOG_FILE = os.path.expanduser("~/trading-system/logs/startup_check.log")

# Give WSL networking a moment to come up when launched from a Windows logon trigger.
STARTUP_DELAY_SEC = 15


def log(message):
    print(message)
    os.makedirs(os.path.dirname(LOG_FILE), exist_ok=True)
    with open(LOG_FILE, "a") as f:
        f.write(message + "\n")


def check_cron():
    status = subprocess.run(
        ["systemctl", "is-active", "cron"], capture_output=True, text=True
    )
    if status.stdout.strip() == "active":
        return True, "running"

    restart = subprocess.run(
        ["sudo", "-n", "systemctl", "restart", "cron"], capture_output=True, text=True
    )
    if restart.returncode == 0:
        return True, "was down, restarted"
    return False, "down — could not auto-restart (needs manual `sudo systemctl restart cron`)"


def check_alpaca():
    try:
        from alpaca.trading.client import TradingClient

        client = TradingClient(
            os.environ.get("ALPACA_API_KEY"),
            os.environ.get("ALPACA_SECRET_KEY"),
            paper=True,
        )
        account = client.get_account()
        return True, f"connected — status={account.status}, buying power=${account.buying_power}"
    except Exception as e:
        return False, f"connection failed: {e}"


def check_andy_status():
    try:
        return (True, "UP") if check_andy() else (False, "DOWN")
    except Exception as e:
        return False, f"check failed: {e}"


def build_summary(cron, alpaca, andy):
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    def mark(ok):
        return "OK" if ok else "FAIL"

    return (
        f"Kronos Startup Check — {now}\n"
        f"\n"
        f"Cron:   [{mark(cron[0])}] {cron[1]}\n"
        f"Alpaca: [{mark(alpaca[0])}] {alpaca[1]}\n"
        f"Andy:   [{mark(andy[0])}] {andy[1]}\n"
    )


def run(dry_run=False):
    log(f"\n-- Startup Check: {datetime.now()} --")

    time.sleep(STARTUP_DELAY_SEC)

    cron = check_cron()
    log(f"  Cron: {cron[1]}")

    alpaca = check_alpaca()
    log(f"  Alpaca: {alpaca[1]}")

    andy = check_andy_status()
    log(f"  Andy: {andy[1]}")

    message = build_summary(cron, alpaca, andy)

    if dry_run:
        print("  DRY RUN — summary that would be sent:")
        for line in message.splitlines():
            print(f"    {line}")
        return

    try:
        token, chat_id = get_telegram_config()
        send_telegram(token, chat_id, message)
        log("  Telegram summary sent.")
    except Exception as e:
        log(f"  WARNING: Telegram send failed: {e}")


if __name__ == "__main__":
    run(dry_run="--dry-run" in sys.argv)
