"""BiQuote SignalR streaming client with reconnect and freshness-safe callbacks."""
from __future__ import annotations

import threading
from datetime import datetime, timezone
from typing import Callable

from feed_router import Quote
from provider_clients import _parse_timestamp


class BiQuoteSignalRClient:
    HUB_URL = "https://biquote.io/hubs/tick"

    def __init__(
        self, symbols: tuple[str, ...] = ("XAUUSD",),
        on_quote: Callable[[Quote], None] | None = None,
        on_status: Callable[[str], None] | None = None,
        connection_factory=None,
    ):
        normalized = tuple(dict.fromkeys(s.strip().upper() for s in symbols if s.strip()))
        if not normalized:
            raise ValueError("At least one symbol is required")
        self.symbols = normalized
        self.on_quote = on_quote
        self.on_status = on_status
        self.connection_factory = connection_factory
        self.connection = None
        self._lock = threading.RLock()
        self._latest: dict[str, Quote] = {}
        self._started = False

    def _status(self, message: str) -> None:
        if self.on_status:
            self.on_status(message)

    def _handle_tick(self, payload) -> None:
        if isinstance(payload, (list, tuple)):
            if not payload:
                return
            payload = payload[0]
        if not isinstance(payload, dict):
            return
        try:
            symbol = str(payload.get("symbol", "")).upper()
            if symbol not in self.symbols:
                return
            if payload.get("stale") is True:
                return
            timestamp = _parse_timestamp(str(payload["timestamp"]))
            bid, ask = float(payload["bid"]), float(payload["ask"])
            if bid <= 0 or ask <= bid:
                return
            quote = Quote(
                source=str(payload.get("source") or "BiQuote SignalR"),
                instrument=symbol,
                market_type="broker",
                timestamp=timestamp,
                bid=bid,
                ask=ask,
                is_simulated=False,
            )
        except (KeyError, TypeError, ValueError):
            return
        with self._lock:
            self._latest[symbol] = quote
        if self.on_quote:
            self.on_quote(quote)

    def _subscribe(self) -> None:
        if self.connection is not None:
            self.connection.send("Subscribe", [list(self.symbols)])
            self._status("BiQuote: subscribed " + ", ".join(self.symbols))

    def start(self) -> None:
        if self._started:
            return
        factory = self.connection_factory
        if factory is None:
            try:
                from signalrcore.hub_connection_builder import HubConnectionBuilder
            except ImportError as exc:
                raise RuntimeError(
                    "signalrcore is required; install requirements.txt first"
                ) from exc
            builder = (
                HubConnectionBuilder()
                .with_url(self.HUB_URL)
                .with_automatic_reconnect({
                    "type": "raw", "keep_alive_interval": 10,
                    "reconnect_interval": 5, "max_attempts": None,
                })
            )
            factory = builder.build
        self.connection = factory()
        self.connection.on("ReceiveTick", self._handle_tick)
        self.connection.on_open(self._subscribe)
        self.connection.on_close(lambda: self._status("BiQuote: disconnected"))
        self.connection.on_error(lambda error: self._status(f"BiQuote error: {error}"))
        self.connection.start()
        self._started = True
        self._status("BiQuote SignalR connected")

    def get_latest_quote(self, symbol: str = "XAUUSD") -> Quote | None:
        with self._lock:
            return self._latest.get(symbol.strip().upper())

    def stop(self) -> None:
        if self.connection is not None:
            try:
                if self._started:
                    self.connection.send("Unsubscribe", [list(self.symbols)])
            finally:
                self.connection.stop()
        self._started = False
        self._status("BiQuote SignalR stopped")
