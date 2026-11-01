"""Startup bootstrap and gap repair for completed historical OHLC bars."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Callable

from market_store import MarketStore
from provider_clients import BiQuoteHistoryAdapter


BOOTSTRAP_TIMEFRAMES = ("M1", "M5", "M15", "H1", "H4")
REFRESH_AFTER_SECONDS = {
    "M1": 300, "M5": 900, "M15": 2700, "H1": 7200, "H4": 28800,
}


class HistoryBootstrapper:
    def __init__(
        self, store: MarketStore | None = None,
        adapter: BiQuoteHistoryAdapter | None = None,
        minimum_existing: int = 100,
        limit: int = 1000,
        on_status: Callable[[str], None] | None = None,
        clock: Callable[[], datetime] | None = None,
    ):
        self.store = store or MarketStore()
        self.adapter = adapter or BiQuoteHistoryAdapter()
        self.minimum_existing = max(30, minimum_existing)
        self.limit = max(100, min(1000, limit))
        self.on_status = on_status
        self.clock = clock or (lambda: datetime.now(timezone.utc))

    def _status(self, message: str):
        if self.on_status:
            self.on_status(message)

    def _needs_refresh(self, timeframe: str, existing: list[dict]) -> bool:
        if len(existing) < self.minimum_existing:
            return True
        try:
            latest = datetime.fromisoformat(str(existing[-1]["timestamp"]).replace("Z", "+00:00"))
            if latest.tzinfo is None:
                return True
            age = (self.clock().astimezone(timezone.utc) - latest.astimezone(timezone.utc)).total_seconds()
            return age < -5 or age > REFRESH_AFTER_SECONDS[timeframe]
        except (KeyError, TypeError, ValueError):
            return True

    def bootstrap_if_needed(self, symbol: str = "XAUUSD") -> dict:
        result = {}
        for timeframe in BOOTSTRAP_TIMEFRAMES:
            existing = self.store.get_candles(
                symbol, timeframe, limit=self.minimum_existing,
                source=self.adapter.name,
            )
            if not self._needs_refresh(timeframe, existing):
                result[timeframe] = {
                    "status": "recent_history_reused", "count": len(existing),
                    "latest_timestamp": existing[-1]["timestamp"],
                }
                continue
            try:
                candles = self.adapter.get_candles(symbol, timeframe, self.limit)
                saved = self.store.upsert_candles(
                    source=self.adapter.name, symbol=symbol,
                    timeframe=timeframe, values=candles,
                )
                result[timeframe] = {"status": "refreshed", "count": saved}
                self._status(f"تاریخچه {timeframe}: {saved} کندل کامل همگام شد.")
            except Exception as exc:
                result[timeframe] = {"status": "unavailable", "error": f"{type(exc).__name__}: {exc}"}
                self._status(f"تاریخچه {timeframe} دریافت نشد: {type(exc).__name__}")
        return result
