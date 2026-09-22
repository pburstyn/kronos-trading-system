"""PreToolUse hook: logs every Bash command Claude Code runs, before execution.
Reads the hook input JSON from stdin (see Claude Code hook schema) and appends
one line per command to logs/claude_code_audit.log. Never blocks the tool call —
any error here is swallowed so a logging failure can't take down the session.
"""
import json
import sys
from datetime import datetime

AUDIT_LOG = "/home/pburstyn/trading-system/logs/claude_code_audit.log"


def main():
    try:
        data = json.load(sys.stdin)
        command = data.get("tool_input", {}).get("command", "")
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        with open(AUDIT_LOG, "a") as f:
            f.write(f"{timestamp} | {command}\n")
    except Exception:
        pass


if __name__ == "__main__":
    main()
