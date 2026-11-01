"""Validated live quote -> multi-timeframe candle -> SQLite pipeline."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Callable

from candle_builder import TickCandleBuilder
from feed_router import Quote, QuoteRouter
from market_store import MarketStore


DEFAULT_INTERVALS = {
    "M1": 60, "M5": 300, "M10": 600, "M15": 900, "H1": 3600, "H4": 14400,
}


class LiveMarketPipeline:
    def __init__(
        self, store: MarketStore | None = None, symbol: str = "XAUUSD",
        max_quote_age_seconds: float = 15.0,
        now_provider: Callable[[], datetime] | None = None,
    ):
        self.store = store or MarketStore()
        self.symbol = symbol.strip().upper()
        self.router = QuoteRouter(max_age_seconds=max_quote_age_seconds)
        self.now_provider = now_provider or (lambda: datetime.now(timezone.utc))
        self.builders = {
            name: TickCandleBuilder(seconds) for name, seconds in DEFAULT_INTERVALS.items()
        }

    def on_quote(self, quote: Quote) -> dict:
        if quote.instrument.upper() != self.symbol:
            return {"accepted": False, "reason": "instrument_mismatch", "saved": {}}
        decision = self.router.choose(
            [quote], instrument=self.symbol, market_type="broker",
            now=self.now_provider(),
        )
        if decision.quote is None:
            return {
                "accepted": False, "reason": decision.reason,
                "rejected": list(decision.rejected), "saved": {},
            }

        saved = {}
        for timeframe, builder in self.builders.items():
            completed = builder.update(decision.quote)
            if completed:
                self.store.upsert_candles(
                    source=decision.quote.source, symbol=self.symbol,
                    timeframe=timeframe, values=completed,
                )
                saved[timeframe] = len(completed)
        return {"accepted": True, "reason": "fresh_quote", "saved": saved}
