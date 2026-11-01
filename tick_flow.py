"""Tick-direction pressure proxy; this is not exchange order-book data."""
from __future__ import annotations

from collections import deque
from datetime import datetime, timezone
from statistics import mean

from feed_router import Quote


class TickPressure:
    def __init__(self, capacity: int = 500):
        if capacity < 20:
            raise ValueError("capacity must be at least 20")
        self.samples = deque(maxlen=capacity)
        self.last_mid: float | None = None

    def update(self, quote: Quote) -> dict:
        mid = quote.mid
        if self.last_mid is None or mid == self.last_mid:
            direction = 0
        else:
            direction = 1 if mid > self.last_mid else -1
        self.last_mid = mid
        self.samples.append({
            "timestamp": quote.timestamp.astimezone(timezone.utc).isoformat(),
            "mid": mid, "spread": quote.spread, "direction": direction,
        })
        return self.snapshot()

    def snapshot(self) -> dict:
        values = list(self.samples)
        buy = sum(1 for item in values if item["direction"] > 0)
        sell = sum(1 for item in values if item["direction"] < 0)
        total = buy + sell
        imbalance = (buy - sell) / total if total else 0.0
        return {
            "samples": len(values), "upticks": buy, "downticks": sell,
            "tick_imbalance": round(imbalance, 4),
            "average_spread": round(mean(item["spread"] for item in values), 6) if values else None,
            "classification": "buy_pressure_proxy" if imbalance > 0.15 else
                              "sell_pressure_proxy" if imbalance < -0.15 else "balanced_or_insufficient",
            "data_type": "tick_direction_proxy",
            "limitations": [
                "No Level-2 order book, exchange aggressor flags, or real traded volume is available.",
                "Quote upticks/downticks are only a directional pressure proxy.",
            ],
        }
