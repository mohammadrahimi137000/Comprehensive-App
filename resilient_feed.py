"""Session-aware SignalR feed with stale-safe REST recovery."""
from __future__ import annotations

import threading
import time
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
        market_is_open: Callable[[], bool] | None = None,
        session_check_interval_seconds: float = 2.0,
    ):
        from biquote_stream import BiQuoteSignalRClient
        self.symbols = tuple(dict.fromkeys(s.strip().upper() for s in symbols if s.strip()))
        if not self.symbols:
            raise ValueError("At least one symbol is required")
        self.on_quote = on_quote
        self.on_status = on_status
        self.stream = BiQuoteSignalRClient(
            symbols=self.symbols, on_quote=self._handle_quote,
            on_status=self._status, connection_factory=stream_factory,
        )
        self.rest = rest_adapter or BiQuoteRestAdapter()
        self.stale_after_seconds = max(5.0, stale_after_seconds)
        self.poll_interval_seconds = max(10.0, poll_interval_seconds)
        self.market_is_open = market_is_open or (lambda: True)
        self.session_check_interval_seconds = max(0.5, session_check_interval_seconds)
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._latest: dict[str, Quote] = {}
        self._last_update_monotonic = 0.0
        self._lock = threading.RLock()
        self._stream_active = False

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
        self._thread = threading.Thread(
            target=self._run, name="BiQuoteSessionAwareFeed", daemon=True
        )
        self._thread.start()

    def _run(self):
        next_stream_attempt = 0.0
        next_rest_poll = 0.0
        rest_delay = self.poll_interval_seconds
        was_open = None
        while not self._stop.is_set():
            try:
                is_open = bool(self.market_is_open())
            except Exception as exc:
                is_open = False
                self._status(f"Market calendar unavailable; feed paused: {type(exc).__name__}")

            now_mono = time.monotonic()
            if not is_open:
                if self._stream_active:
                    try:
                        self.stream.stop()
                    except Exception as exc:
                        self._status(f"SignalR stop error: {type(exc).__name__}")
                    self._stream_active = False
                if was_open is not False:
                    self._status("بازار بسته است؛ اتصال و درخواست‌های داده متوقف شدند.")
                was_open = False
                self._stop.wait(self.session_check_interval_seconds)
                continue

            if was_open is not True:
                self._status("بازار باز شد؛ دریافت داده فعال می‌شود.")
                next_stream_attempt = 0.0
                next_rest_poll = 0.0
            was_open = True

            if not self._stream_active and now_mono >= next_stream_attempt:
                try:
                    self.stream.start()
                    self._stream_active = True
                except Exception as exc:
                    self._status(f"SignalR unavailable; retrying: {type(exc).__name__}")
                    next_stream_attempt = now_mono + 15.0

            with self._lock:
                age = (now_mono - self._last_update_monotonic
                       if self._last_update_monotonic else float("inf"))
            if age >= self.stale_after_seconds and now_mono >= next_rest_poll:
                for symbol in self.symbols:
                    if self._stop.is_set() or not self.market_is_open():
                        break
                    try:
                        quote = self.rest.get_quote(symbol)
                        if quote is not None and self._handle_quote(quote):
                            self._status(f"BiQuote REST fallback active for {symbol}; stream is stale.")
                            rest_delay = self.poll_interval_seconds
                        else:
                            rest_delay = min(300.0, max(self.poll_interval_seconds, rest_delay * 2.0))
                    except Exception as exc:
                        self._status(f"BiQuote REST fallback unavailable: {type(exc).__name__}")
                        rest_delay = min(300.0, max(self.poll_interval_seconds, rest_delay * 2.0))
                next_rest_poll = time.monotonic() + rest_delay
            elif age < self.stale_after_seconds:
                next_rest_poll = now_mono + self.poll_interval_seconds
                rest_delay = self.poll_interval_seconds

            self._stop.wait(self.session_check_interval_seconds)

    def stop(self):
        self._stop.set()
        if self._stream_active:
            try:
                self.stream.stop()
            finally:
                self._stream_active = False
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=5.0)
        self._status("BiQuote feed stopped")
