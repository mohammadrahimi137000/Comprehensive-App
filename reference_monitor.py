"""Poll independent spot references only while the broker stream is live."""
from __future__ import annotations

import threading
import time
from datetime import datetime, timezone
from typing import Callable

from feed_router import Quote
from provider_clients import CorganoSpotAdapter, SpotReference, XausSpotAdapter
from reference_comparator import compare_reference_prices


class SpotReferenceMonitor:
    def __init__(
        self, latest_broker_quote: Callable[[], Quote | None],
        on_result: Callable[[dict], None] | None = None,
        on_status: Callable[[str], None] | None = None,
        xaus: XausSpotAdapter | None = None,
        corgano: CorganoSpotAdapter | None = None,
        xaus_interval_seconds: float = 65.0,
        corgano_interval_seconds: float = 240.0,
        broker_max_age_seconds: float = 15.0,
        clock: Callable[[], datetime] | None = None,
    ):
        self.latest_broker_quote = latest_broker_quote
        self.on_result = on_result
        self.on_status = on_status
        self.xaus = xaus or XausSpotAdapter()
        self.corgano = corgano or CorganoSpotAdapter()
        self.xaus_interval_seconds = max(60.0, xaus_interval_seconds)
        self.corgano_interval_seconds = max(180.0, corgano_interval_seconds)
        self.broker_max_age_seconds = broker_max_age_seconds
        self.clock = clock or (lambda: datetime.now(timezone.utc))
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._last_xaus = 0.0
        self._last_corgano = 0.0
        self._last_report = 0.0
        self._references: dict[str, SpotReference] = {}

    def _status(self, message: str):
        if self.on_status:
            self.on_status(message)

    def start(self):
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, name="SpotReferenceMonitor", daemon=True)
        self._thread.start()

    def stop(self, timeout: float = 3.0):
        self._stop.set()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout)

    def _run(self):
        self._status("مقایسه قیمت مرجع مستقل آماده است؛ تا دریافت تیک زنده هیچ درخواست Spot ارسال نمی‌شود.")
        while not self._stop.wait(1.0):
            if self._stop.is_set():
                break
            now = self.clock()
            quote = self.latest_broker_quote()
            if quote is None or (now - quote.timestamp).total_seconds() > self.broker_max_age_seconds:
                continue
            if (now - quote.timestamp).total_seconds() < -2:
                continue

            monotonic_now = time.monotonic()
            if monotonic_now - self._last_xaus >= self.xaus_interval_seconds:
                self._last_xaus = monotonic_now
                try:
                    self._references["XAUS"] = self.xaus.get_spot()
                except Exception as exc:
                    self._status(f"XAUS reference unavailable: {type(exc).__name__}")
            if monotonic_now - self._last_corgano >= self.corgano_interval_seconds:
                self._last_corgano = monotonic_now
                try:
                    self._references["Corgano"] = self.corgano.get_spot()
                except Exception as exc:
                    self._status(f"Corgano reference unavailable: {type(exc).__name__}")

            if self._stop.is_set():
                break
            if self._references and monotonic_now - self._last_report >= 5.0:
                self._last_report = monotonic_now
                result = compare_reference_prices(quote, list(self._references.values()), now=now)
                if self.on_result:
                    self.on_result(result)
                self._status("قیمت مرجع مستقل با Quote بروکر مقایسه شد؛ Spot در کندل‌ها جایگزین Bid/Ask نمی‌شود.")
