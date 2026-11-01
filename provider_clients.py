"""Read-only provider clients for BiQuote executable-style ticks and XAUS spot reference.

The two products are deliberately represented differently: BiQuote exposes bid/ask
quotes; XAUS exposes an indicative spot mid-price and must not be given a fabricated
bid/ask spread.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Callable
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from feed_router import Quote


JsonGetter = Callable[[str, float], dict]


def _get_json(url: str, timeout: float = 8.0) -> dict:
    request = Request(url, headers={"Accept": "application/json", "User-Agent": "Comprehensive-App/0.1"})
    try:
        with urlopen(request, timeout=timeout) as response:
            if response.status != 200:
                raise RuntimeError(f"Provider returned HTTP {response.status}")
            payload = json.loads(response.read().decode("utf-8"))
    except HTTPError as exc:
        raise RuntimeError(f"Provider returned HTTP {exc.code}") from exc
    except URLError as exc:
        raise RuntimeError(f"Provider connection failed: {exc.reason}") from exc
    if not isinstance(payload, dict):
        raise RuntimeError("Provider response must be a JSON object")
    return payload


def _parse_timestamp(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("Provider timestamp must include timezone")
    return parsed.astimezone(timezone.utc)


class BiQuoteRestAdapter:
    """REST fallback adapter. Prefer the provider SignalR stream for production."""

    name = "biquote"

    def __init__(self, getter: JsonGetter = _get_json, timeout: float = 8.0):
        self.getter = getter
        self.timeout = timeout

    def get_quote(self, instrument: str = "XAUUSD") -> Quote | None:
        symbol = instrument.strip().upper()
        payload = self.getter(
            f"https://biquote.io/api/{symbol}?allowStale=false", self.timeout
        )
        if payload.get("stale") is True:
            return None
        state = str(payload.get("marketState", "")).lower()
        if state and state not in {"open", "live", "trading"}:
            return None
        timestamp = _parse_timestamp(str(payload.get("timestamp", "")))
        return Quote(
            source=str(payload.get("source") or self.name),
            instrument=str(payload.get("symbol") or symbol).upper(),
            market_type="broker",
            timestamp=timestamp,
            bid=float(payload["bid"]),
            ask=float(payload["ask"]),
            is_simulated=False,
        )


@dataclass(frozen=True, slots=True)
class SpotReference:
    source: str
    instrument: str
    timestamp: datetime
    price: float
    state: str
    age_seconds: float | None
    is_indicative: bool = True
    attribution_text: str | None = None
    attribution_url: str | None = None


class XausSpotAdapter:
    """XAUS reference-price client; returns a mid-price, never a tradable quote."""

    name = "xaus"

    def __init__(self, getter: JsonGetter = _get_json, timeout: float = 8.0):
        self.getter = getter
        self.timeout = timeout

    def get_spot(self) -> SpotReference:
        payload = self.getter("https://xaus.com/api/v1/spot?compact=1", self.timeout)
        state = payload.get("data_state") or {}
        status = str(state.get("status", "unavailable")).lower()
        if status != "fresh":
            raise RuntimeError(f"XAUS spot is not fresh (state={status})")
        timestamp = _parse_timestamp(str(payload.get("price_as_of") or state.get("as_of") or ""))
        price = float(payload["spot_usd_oz"])
        if price <= 0:
            raise RuntimeError("XAUS returned a non-positive spot price")
        age = state.get("age_seconds")
        return SpotReference(
            source=str(payload.get("price_source") or payload.get("source") or self.name),
            instrument="XAUUSD",
            timestamp=timestamp,
            price=price,
            state=status,
            age_seconds=float(age) if age is not None else None,
        )



class CorganoSpotAdapter:
    """Rate-limited indicative spot reference adapter; never used as bid/ask."""

    name = "corgano"

    def __init__(
        self, getter: JsonGetter = _get_json, timeout: float = 8.0,
        minimum_interval_seconds: float = 240.0, max_age_seconds: float = 180.0,
        clock: Callable[[], datetime] | None = None,
    ):
        if minimum_interval_seconds < 180 or max_age_seconds <= 0:
            raise ValueError("Corgano polling must be at least 180 seconds")
        self.getter = getter
        self.timeout = timeout
        self.minimum_interval_seconds = float(minimum_interval_seconds)
        self.max_age_seconds = float(max_age_seconds)
        self.clock = clock or (lambda: datetime.now(timezone.utc))
        self._last_request: datetime | None = None
        self._cached: SpotReference | None = None

    def get_spot(self) -> SpotReference:
        now = self.clock()
        if now.tzinfo is None:
            raise ValueError("clock must return a timezone-aware datetime")
        if self._cached is not None and self._last_request is not None:
            elapsed = (now - self._last_request).total_seconds()
            if 0 <= elapsed < self.minimum_interval_seconds:
                return self._cached

        payload = self.getter(
            "https://goldprice.corgano.com/api/v1/latest", self.timeout
        )
        data = payload.get("data") or {}
        timestamp = _parse_timestamp(str(data.get("as_of", "")))
        age = (now.astimezone(timezone.utc) - timestamp).total_seconds()
        if age < -2 or age > self.max_age_seconds:
            raise RuntimeError(f"Corgano spot is outside freshness limit (age={age:.1f}s)")
        price = float((data.get("price_usd") or {}).get("per_oz", 0))
        if price <= 0:
            raise RuntimeError("Corgano returned a non-positive spot price")
        attribution = payload.get("attribution") or {}
        if attribution.get("required") and not attribution.get("url"):
            raise RuntimeError("Corgano attribution URL is missing")
        result = SpotReference(
            source="Corgano spot reference",
            instrument="XAUUSD",
            timestamp=timestamp,
            price=price,
            state="fresh",
            age_seconds=age,
            attribution_text=attribution.get("text"),
            attribution_url=attribution.get("url"),
        )
        self._cached = result
        self._last_request = now
        return result
