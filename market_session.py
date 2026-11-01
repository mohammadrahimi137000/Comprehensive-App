from __future__ import annotations

import json
import os
from dataclasses import dataclass
from datetime import date, datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError


@dataclass(frozen=True)
class SessionState:
    is_open: bool
    reason: str
    checked_at: datetime


class MarketSession:
    """DST-aware gold session guard using New York market time by default.

    The default weekly session is Sunday 17:00 through Friday 16:00 New York
    time, with a daily 16:00-17:00 maintenance break. Broker calendars remain
    authoritative; explicit closed dates can be added to market_holidays.json.
    """

    def __init__(self, holidays_path="data/market_holidays.json", clock=None,
                 open_hour=None, close_hour=None, timezone_name=None):
        self.holidays_path = Path(holidays_path)
        self.clock = clock or (lambda: datetime.now(timezone.utc))
        legacy_open = os.getenv("GOLD_SESSION_OPEN_UTC")
        legacy_close = os.getenv("GOLD_SESSION_CLOSE_UTC")
        if legacy_open is not None or legacy_close is not None:
            timezone_name = "UTC"
        self.timezone_name = timezone_name or os.getenv(
            "GOLD_SESSION_TIMEZONE", "America/New_York"
        )
        try:
            self.session_timezone = ZoneInfo(self.timezone_name)
        except ZoneInfoNotFoundError as exc:
            raise ValueError(f"Unknown market timezone: {self.timezone_name}") from exc
        self.open_hour = int(
            legacy_open if legacy_open is not None else
            os.getenv("GOLD_SESSION_OPEN_HOUR", open_hour if open_hour is not None else 17)
        )
        self.close_hour = int(
            legacy_close if legacy_close is not None else
            os.getenv("GOLD_SESSION_CLOSE_HOUR", close_hour if close_hour is not None else 16)
        )
        if not 0 <= self.open_hour <= 23 or not 0 <= self.close_hour <= 23:
            raise ValueError("Session hours must be between 0 and 23")
        if self.open_hour == self.close_hour:
            raise ValueError("Session open and close hours must differ")

    def _holidays(self):
        try:
            payload = json.loads(self.holidays_path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            return set()
        except (OSError, json.JSONDecodeError) as exc:
            raise RuntimeError(f"Invalid market holiday calendar: {exc}") from exc
        dates = payload.get("closed_dates", []) if isinstance(payload, dict) else None
        if not isinstance(dates, list):
            raise ValueError("market_holidays.json must contain a closed_dates list")
        return {date.fromisoformat(str(value)) for value in dates}

    def state(self, at=None):
        now = at or self.clock()
        if now.tzinfo is None:
            raise ValueError("Market session clock must be timezone-aware")
        now = now.astimezone(timezone.utc)
        local_now = now.astimezone(self.session_timezone)
        if local_now.date() in self._holidays():
            return SessionState(False, "تعطیلی ثبت‌شده در تقویم بازار", now)
        weekday = local_now.weekday()
        minute = local_now.hour * 60 + local_now.minute
        opening = self.open_hour * 60
        closing = self.close_hour * 60
        if weekday == 5:
            return SessionState(False, "تعطیلی آخر هفته", now)
        if weekday == 6 and minute < opening:
            return SessionState(False, "بازار تا ساعت شروع یکشنبه بسته است", now)
        if weekday == 4 and minute >= closing:
            return SessionState(False, "تعطیلی آخر هفته از جمعه", now)
        if closing <= minute < opening:
            return SessionState(False, "وقفه روزانه بازار", now)
        return SessionState(True, "بازار باز است", now)

    def is_open(self):
        return self.state().is_open
