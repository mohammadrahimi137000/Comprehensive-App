from datetime import datetime, timezone

from news_engine import assess_event_risk


def test_high_impact_event_within_forecast_horizon_is_flagged():
    now = datetime(2026, 11, 1, 12, 0, tzinfo=timezone.utc)
    events = [{
        "importance": "high", "time_mode": "exact",
        "time": "2026-11-01T12:10:00Z", "name": "US CPI",
        "country": "US", "currency": "USD",
    }]
    result = assess_event_risk(events, now=now)
    assert result["status"] == "high_impact_event_window"
    assert result["events"][0]["name"] == "US CPI"


def test_non_exact_event_time_is_uncertain_not_a_false_blackout():
    now = datetime(2026, 11, 1, 12, 0, tzinfo=timezone.utc)
    result = assess_event_risk([{
        "importance": "high", "time_mode": "date",
        "time": "2026-11-01T00:00:00Z", "name": "Holiday",
    }], now=now)
    assert result["events"] == []
    assert result["uncertain_events"]
