import os
from datetime import datetime

BASE_POSITION_SIZE = 1
STOP_LOSS_PCT = 0.02
TAKE_PROFIT_PCT_LOW = 0.03
TAKE_PROFIT_PCT_HIGH = 0.05
MIN_CONFIDENCE_FOR_ENTRY = 51.0

def get_position_size(verdict):
    if verdict == "VETO":
        return 0
    elif verdict == "FLAG":
        return BASE_POSITION_SIZE * 0.5
    elif verdict == "PASS":
        return BASE_POSITION_SIZE
    else:
        return 0

def calculate_trade_levels(direction, last_close):
    last_close = float(last_close)
    entry = last_close

    if direction == "UP":
        stop_loss = round(entry * (1 - STOP_LOSS_PCT), 2)
        take_profit_low = round(entry * (1 + TAKE_PROFIT_PCT_LOW), 2)
        take_profit_high = round(entry * (1 + TAKE_PROFIT_PCT_HIGH), 2)
    elif direction == "DOWN":
        stop_loss = round(entry * (1 + STOP_LOSS_PCT), 2)
        take_profit_low = round(entry * (1 - TAKE_PROFIT_PCT_LOW), 2)
        take_profit_high = round(entry * (1 - TAKE_PROFIT_PCT_HIGH), 2)
    else:
        return None

    return {
        "entry": entry,
        "stop_loss": stop_loss,
        "take_profit_low": take_profit_low,
        "take_profit_high": take_profit_high
    }

def make_trade_decision(direction, confidence_pct, last_close, verdict):
    confidence_pct = float(confidence_pct)

    if direction not in ("UP", "DOWN"):
        return {"action": "NO_TRADE", "reason": "Signal not directional"}

    if confidence_pct < MIN_CONFIDENCE_FOR_ENTRY:
        return {"action": "NO_TRADE", "reason": f"Confidence {confidence_pct}% below minimum {MIN_CONFIDENCE_FOR_ENTRY}%"}

    position_size = get_position_size(verdict)
    if position_size == 0:
        return {"action": "NO_TRADE", "reason": f"Critic verdict {verdict} blocks entry"}

    levels = calculate_trade_levels(direction, last_close)
    if not levels:
        return {"action": "NO_TRADE", "reason": "Could not calculate trade levels"}

    return {
        "action": "ENTER",
        "direction": direction,
        "position_size": position_size,
        "entry": levels["entry"],
        "stop_loss": levels["stop_loss"],
        "take_profit_low": levels["take_profit_low"],
        "take_profit_high": levels["take_profit_high"],
        "verdict": verdict
    }

def print_decision(decision):
    print("\n-- Trade Decision --")
    if decision["action"] == "NO_TRADE":
        print(f"  NO TRADE: {decision['reason']}")
    else:
        print(f"  ENTER {decision['direction']}")
        print(f"  Position size: {decision['position_size']} contract(s)")
        print(f"  Entry: ${decision['entry']}")
        print(f"  Stop-loss: ${decision['stop_loss']}")
        print(f"  Take-profit range: ${decision['take_profit_low']} - ${decision['take_profit_high']}")
        print(f"  Critic verdict: {decision['verdict']}")
    print("---------------------\n")

if __name__ == "__main__":
    test_decision = make_trade_decision("DOWN", "90", "725.43", "FLAG")
    print_decision(test_decision)
