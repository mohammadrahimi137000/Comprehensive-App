from datetime import datetime, timezone

from market_session import MarketSession


def test_weekend_daily_break_and_open_periods():
    session = MarketSession(holidays_path="/path/that/does/not/exist.json")
    assert not session.state(datetime(2026, 11, 7, 12, tzinfo=timezone.utc)).is_open
    assert not session.state(datetime(2026, 11, 2, 21, 30, tzinfo=timezone.utc)).is_open
    assert session.state(datetime(2026, 11, 2, 12, tzinfo=timezone.utc)).is_open


def test_sunday_open_friday_close():
    session = MarketSession(holidays_path="/path/that/does/not/exist.json")
    assert not session.state(datetime(2026, 11, 1, 21, 30, tzinfo=timezone.utc)).is_open
    assert session.state(datetime(2026, 11, 1, 22, 0, tzinfo=timezone.utc)).is_open
    assert not session.state(datetime(2026, 11, 6, 21, 0, tzinfo=timezone.utc)).is_open


def test_new_york_session_tracks_daylight_saving_time():
    session = MarketSession(holidays_path="/path/that/does/not/exist.json")
    # 17:00 New York is 21:00 UTC during EDT and 22:00 UTC during EST.
    assert session.state(datetime(2026, 7, 5, 21, 0, tzinfo=timezone.utc)).is_open
    assert not session.state(datetime(2026, 7, 5, 20, 30, tzinfo=timezone.utc)).is_open
    assert session.state(datetime(2026, 11, 1, 22, 0, tzinfo=timezone.utc)).is_open
    assert not session.state(datetime(2026, 11, 1, 21, 30, tzinfo=timezone.utc)).is_open


def test_configured_holiday(tmp_path):
    calendar = tmp_path / "holidays.json"
    calendar.write_text('{"closed_dates":["2026-11-02"]}', encoding="utf-8")
    session = MarketSession(holidays_path=calendar)
    assert not session.state(datetime(2026, 11, 2, 12, tzinfo=timezone.utc)).is_open
