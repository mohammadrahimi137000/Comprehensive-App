"""Performance statistics for manually journaled, closed trades (in R multiples)."""
from __future__ import annotations

from math import isfinite


def analyze_performance(trades: list[dict]) -> dict:
    closed = []
    for trade in trades:
        if trade.get("status") != "closed" or trade.get("outcome_r") is None:
            continue
        outcome = float(trade["outcome_r"])
        if isfinite(outcome):
            closed.append((trade.get("closed_at") or "", outcome))
    closed.sort(key=lambda item: item[0])
    values = [item[1] for item in closed]
    if not values:
        return {
            "closed_trades": 0, "wins": 0, "losses": 0, "breakeven": 0,
            "win_rate_pct": 0.0, "average_r": 0.0, "expectancy_r": 0.0,
            "profit_factor": None, "max_drawdown_r": 0.0,
            "equity_curve_r": [],
        }

    wins = [value for value in values if value > 0]
    losses = [value for value in values if value < 0]
    gross_profit = sum(wins)
    gross_loss = abs(sum(losses))
    equity = 0.0
    peak = 0.0
    max_drawdown = 0.0
    curve = []
    for index, value in enumerate(values, start=1):
        equity += value
        peak = max(peak, equity)
        max_drawdown = max(max_drawdown, peak - equity)
        curve.append({"trade": index, "cumulative_r": round(equity, 4)})

    return {
        "closed_trades": len(values),
        "wins": len(wins),
        "losses": len(losses),
        "breakeven": len(values) - len(wins) - len(losses),
        "win_rate_pct": round(len(wins) / len(values) * 100, 2),
        "average_r": round(sum(values) / len(values), 4),
        "expectancy_r": round(sum(values) / len(values), 4),
        "average_win_r": round(gross_profit / len(wins), 4) if wins else None,
        "average_loss_r": round(sum(losses) / len(losses), 4) if losses else None,
        "profit_factor": round(gross_profit / gross_loss, 4) if gross_loss else None,
        "max_drawdown_r": round(max_drawdown, 4),
        "equity_curve_r": curve,
    }
