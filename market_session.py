from __future__ import annotations

import json
import os
from dataclasses import dataclass
from datetime import date, datetime, timezone
from pathlib import Path


@dataclass(frozen=True)
class SessionState:
    is_open: bool
    reason: str
    checked_at: datetime


class MarketSession:
    """Configurable UTC gold-session guard; broker calendars remain authoritative."""

    def __init__(self, holidays_path="data/market_holidays.json", clock=None,
                 open_hour=None, close_hour=None):
        self.holidays_path = Path(holidays_path)
        self.clock = clock or (lambda: datetime.now(timezone.utc))
        self.open_hour = int(os.getenv("GOLD_SESSION_OPEN_UTC", open_hour if open_hour is not None else 22))
        self.close_hour = int(os.getenv("GOLD_SESSION_CLOSE_UTC", close_hour if close_hour is not None else 21))
        if not 0 <= self.open_hour <= 23 or not 0 <= self.close_hour <= 23:
            raise ValueError("Session hours must be between 0 and 23")

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
        if now.date() in self._holidays():
            return SessionState(False, "تعطیلی ثبت‌شده در تقویم بازار", now)
        weekday = now.weekday()
        minute = now.hour * 60 + now.minute
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
