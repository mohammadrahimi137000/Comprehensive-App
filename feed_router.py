"""Quality-aware routing for normalized market quotes.

Adapters are intentionally transport-agnostic. Vendor-specific HTTP/WebSocket
clients must implement the adapter contract and be tested against provider docs.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Iterable, Protocol


@dataclass(frozen=True, slots=True)
class Quote:
    source: str
    instrument: str
    market_type: str  # "spot" or "broker"
    timestamp: datetime
    bid: float
    ask: float
    is_simulated: bool = False

    @property
    def mid(self) -> float:
        return (self.bid + self.ask) / 2.0

    @property
    def spread(self) -> float:
        return self.ask - self.bid


class QuoteAdapter(Protocol):
    name: str

    def get_quote(self, instrument: str) -> Quote | None: ...


@dataclass(frozen=True)
class QuoteDecision:
    quote: Quote | None
    rejected: tuple[dict, ...]
    reason: str


class QuoteRouter:
    def __init__(self, max_age_seconds: float = 10.0, max_future_seconds: float = 2.0):
        if max_age_seconds <= 0 or max_future_seconds < 0:
            raise ValueError("Invalid quote age limits")
        self.max_age_seconds = float(max_age_seconds)
        self.max_future_seconds = float(max_future_seconds)

    def choose(
        self, quotes: Iterable[Quote], instrument: str,
        market_type: str = "spot", now: datetime | None = None,
    ) -> QuoteDecision:
        now = now or datetime.now(timezone.utc)
        if now.tzinfo is None:
            raise ValueError("now must be timezone-aware")
        rejected = []
        candidates = []
        for quote in quotes:
            age = (now - quote.timestamp).total_seconds()
            reason = None
            if quote.instrument.upper() != instrument.upper():
                reason = "instrument_mismatch"
            elif quote.market_type != market_type:
                reason = "market_type_mismatch"
            elif quote.is_simulated:
                reason = "simulated_data"
            elif quote.timestamp.tzinfo is None:
                reason = "timestamp_without_timezone"
            elif age > self.max_age_seconds:
                reason = "stale_quote"
            elif age < -self.max_future_seconds:
                reason = "future_timestamp"
            elif quote.bid <= 0 or quote.ask <= 0 or quote.ask < quote.bid:
                reason = "invalid_bid_ask"
            elif quote.spread <= 0:
                reason = "zero_spread"
            if reason:
                rejected.append({"source": quote.source, "reason": reason})
            else:
                # Newer quotes win; tighter relative spread breaks timestamp ties.
                relative_spread = quote.spread / quote.mid
                candidates.append((age, relative_spread, quote))
        if not candidates:
            return QuoteDecision(None, tuple(rejected), "no_eligible_quote")
        candidates.sort(key=lambda item: (item[0], item[1]))
        selected = candidates[0][2]
        return QuoteDecision(selected, tuple(rejected), "best_fresh_quote")

    def choose_from_adapters(
        self, adapters: Iterable[QuoteAdapter], instrument: str,
        market_type: str = "spot", now: datetime | None = None,
    ) -> QuoteDecision:
        quotes = []
        errors = []
        for adapter in adapters:
            try:
                quote = adapter.get_quote(instrument)
                if quote is not None:
                    quotes.append(quote)
            except Exception as exc:
                errors.append({"source": getattr(adapter, "name", type(adapter).__name__),
                               "reason": f"adapter_error: {type(exc).__name__}"})
        decision = self.choose(quotes, instrument, market_type, now)
        return QuoteDecision(decision.quote, decision.rejected + tuple(errors), decision.reason)
