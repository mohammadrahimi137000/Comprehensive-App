"""One-time startup bootstrap of completed historical OHLC bars."""
from __future__ import annotations

from typing import Callable

from market_store import MarketStore
from provider_clients import BiQuoteHistoryAdapter


BOOTSTRAP_TIMEFRAMES = ("M1", "M5", "M15", "H1", "H4")


class HistoryBootstrapper:
    def __init__(
        self, store: MarketStore | None = None,
        adapter: BiQuoteHistoryAdapter | None = None,
        minimum_existing: int = 100,
        limit: int = 1000,
        on_status: Callable[[str], None] | None = None,
    ):
        self.store = store or MarketStore()
        self.adapter = adapter or BiQuoteHistoryAdapter()
        self.minimum_existing = max(30, minimum_existing)
        self.limit = max(100, min(1000, limit))
        self.on_status = on_status

    def _status(self, message: str):
        if self.on_status:
            self.on_status(message)

    def bootstrap_if_needed(self, symbol: str = "XAUUSD") -> dict:
        result = {}
        for timeframe in BOOTSTRAP_TIMEFRAMES:
            existing = self.store.get_candles(
                symbol, timeframe, limit=self.minimum_existing,
                source=self.adapter.name,
            )
            if len(existing) >= self.minimum_existing:
                result[timeframe] = {"status": "already_populated", "count": len(existing)}
                continue
            try:
                candles = self.adapter.get_candles(symbol, timeframe, self.limit)
                saved = self.store.upsert_candles(
                    source=self.adapter.name, symbol=symbol,
                    timeframe=timeframe, values=candles,
                )
                result[timeframe] = {"status": "imported", "count": saved}
                self._status(f"تاریخچه {timeframe}: {saved} کندل کامل وارد شد.")
            except Exception as exc:
                result[timeframe] = {"status": "unavailable", "error": f"{type(exc).__name__}: {exc}"}
                self._status(f"تاریخچه {timeframe} دریافت نشد: {type(exc).__name__}")
        return result
