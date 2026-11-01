"""SignalR-first BiQuote feed with a conservative REST recovery path."""
from __future__ import annotations

import threading
import time
from datetime import datetime, timezone
from typing import Callable

from feed_router import Quote
from provider_clients import BiQuoteRestAdapter


class ResilientBiQuoteFeed:
    def __init__(
        self, symbols: tuple[str, ...] = ("XAUUSD",),
        on_quote: Callable[[Quote], None] | None = None,
        on_status: Callable[[str], None] | None = None,
        stream_factory=None, rest_adapter: BiQuoteRestAdapter | None = None,
        stale_after_seconds: float = 15.0, poll_interval_seconds: float = 30.0,
    ):
        from biquote_stream import BiQuoteSignalRClient
        self.symbols = tuple(s.strip().upper() for s in symbols)
        self.on_quote = on_quote
        self.on_status = on_status
        self.stream = BiQuoteSignalRClient(
            symbols=self.symbols, on_quote=self._handle_quote,
            on_status=self._status, connection_factory=stream_factory,
        )
        self.rest = rest_adapter or BiQuoteRestAdapter()
        self.stale_after_seconds = max(5.0, stale_after_seconds)
        self.poll_interval_seconds = max(10.0, poll_interval_seconds)
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._latest: dict[str, Quote] = {}
        self._last_update_monotonic = 0.0
        self._lock = threading.RLock()

    def _status(self, message: str):
        if self.on_status:
            self.on_status(message)

    def _handle_quote(self, quote: Quote) -> bool:
        if self._stop.is_set():
            return False
        with self._lock:
            current = self._latest.get(quote.instrument)
            if current and quote.timestamp <= current.timestamp:
                return False
            self._latest[quote.instrument] = quote
            self._last_update_monotonic = time.monotonic()
        if self.on_quote:
            self.on_quote(quote)
        return True

    def get_latest_quote(self, symbol: str = "XAUUSD") -> Quote | None:
        with self._lock:
            return self._latest.get(symbol.strip().upper())

    def start(self):
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        try:
            self.stream.start()
        except Exception as exc:
            self._status(f"SignalR unavailable; REST fallback will be used: {type(exc).__name__}")
        self._thread = threading.Thread(target=self._fallback_loop, name="BiQuoteFallback", daemon=True)
        self._thread.start()

    def _fallback_loop(self):
        delay = self.poll_interval_seconds
        while not self._stop.wait(delay):
            with self._lock:
                age = time.monotonic() - self._last_update_monotonic if self._last_update_monotonic else float("inf")
            if age < self.stale_after_seconds:
                delay = self.poll_interval_seconds
                continue
            recovered = False
            for symbol in self.symbols:
                try:
                    quote = self.rest.get_quote(symbol)
                    if quote is not None and self._handle_quote(quote):
                        recovered = True
                        self._status(f"BiQuote REST fallback active for {symbol}; SignalR stream is stale.")
                except Exception as exc:
                    self._status(f"BiQuote REST fallback unavailable: {type(exc).__name__}")
            delay = self.poll_interval_seconds if recovered else min(300.0, delay * 2.0)

    def stop(self):
        self._stop.set()
        try:
            self.stream.stop()
        finally:
            if self._thread and self._thread.is_alive():
                self._thread.join(timeout=3.0)
            self._status("BiQuote feed stopped")
