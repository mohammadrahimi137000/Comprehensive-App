"""Build completed OHLC candles from normalized bid/ask ticks."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

from feed_router import Quote


@dataclass
class _WorkingBar:
    bucket: int
    open: float
    high: float
    low: float
    close: float
    last_timestamp: float
    tick_count: int = 1


class TickCandleBuilder:
    def __init__(self, timeframe_seconds: int = 60):
        if timeframe_seconds not in {60, 300, 600, 900, 3600, 14400}:
            raise ValueError("Supported intervals: M1, M5, M10, M15, H1, H4")
        self.timeframe_seconds = int(timeframe_seconds)
        self._bars: dict[tuple[str, str], _WorkingBar] = {}

    def update(self, quote: Quote) -> list[dict]:
        if quote.timestamp.tzinfo is None:
            raise ValueError("Quote timestamp must be timezone-aware")
        if quote.bid <= 0 or quote.ask <= quote.bid:
            raise ValueError("Quote must contain a valid positive bid/ask spread")
        key = (quote.source, quote.instrument.upper())
        timestamp = quote.timestamp.astimezone(timezone.utc).timestamp()
        bucket = int(timestamp) - (int(timestamp) % self.timeframe_seconds)
        price = quote.mid
        current = self._bars.get(key)
        if current is None:
            self._bars[key] = _WorkingBar(bucket, price, price, price, price, timestamp)
            return []
        if timestamp < current.last_timestamp or bucket < current.bucket:
            return []
        if bucket == current.bucket:
            current.high = max(current.high, price)
            current.low = min(current.low, price)
            current.close = price
            current.last_timestamp = timestamp
            current.tick_count += 1
            return []

        gap_buckets = max(0, (bucket - current.bucket) // self.timeframe_seconds - 1)
        completed = {
            "timestamp": current.bucket,
            "open": current.open,
            "high": current.high,
            "low": current.low,
            "close": current.close,
            "volume": 0.0,
            "tick_count": current.tick_count,
            "source": quote.source,
            "symbol": quote.instrument.upper(),
            "timeframe_seconds": self.timeframe_seconds,
            "missing_intervals_after": gap_buckets,
        }
        self._bars[key] = _WorkingBar(bucket, price, price, price, price, timestamp)
        return [completed]

    def current_bar(self, source: str, instrument: str) -> dict | None:
        current = self._bars.get((source, instrument.upper()))
        if current is None:
            return None
        return {
            "timestamp": current.bucket,
            "open": current.open, "high": current.high,
            "low": current.low, "close": current.close,
            "volume": 0.0, "tick_count": current.tick_count,
            "last_timestamp": current.last_timestamp,
        }

    def reset(self) -> None:
        self._bars.clear()
