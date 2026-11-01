from datetime import datetime, timedelta, timezone

from feed_router import Quote, QuoteRouter


def test_router_selects_fresh_quote_and_keeps_market_types_separate():
    now = datetime(2026, 1, 1, tzinfo=timezone.utc)
    quotes = [
        Quote("old", "XAUUSD", "spot", now - timedelta(seconds=30), 2000, 2000.5),
        Quote("broker", "XAUUSD", "broker", now, 2000, 2000.1),
        Quote("fresh", "XAUUSD", "spot", now - timedelta(seconds=1), 2000, 2000.2),
    ]
    result = QuoteRouter(max_age_seconds=10).choose(quotes, "XAUUSD", "spot", now)
    assert result.quote.source == "fresh"
    assert {"source": "old", "reason": "stale_quote"} in result.rejected
    assert {"source": "broker", "reason": "market_type_mismatch"} in result.rejected


def test_router_rejects_simulated_invalid_and_future_quotes():
    now = datetime(2026, 1, 1, tzinfo=timezone.utc)
    quotes = [
        Quote("sim", "XAUUSD", "spot", now, 10, 11, True),
        Quote("bad", "XAUUSD", "spot", now, 12, 11),
        Quote("future", "XAUUSD", "spot", now + timedelta(seconds=9), 10, 11),
    ]
    result = QuoteRouter().choose(quotes, "XAUUSD", "spot", now)
    assert result.quote is None
    assert {item["reason"] for item in result.rejected} == {
        "simulated_data", "invalid_bid_ask", "future_timestamp"
    }


def test_router_handles_timezone_naive_timestamp_without_crashing():
    now = datetime(2026, 1, 1, tzinfo=timezone.utc)
    quote = Quote("naive", "XAUUSD", "spot", datetime(2026, 1, 1), 10, 11)
    result = QuoteRouter().choose([quote], "XAUUSD", "spot", now)
    assert result.quote is None
    assert result.rejected[0]["reason"] == "timestamp_without_timezone"


def test_router_returns_none_when_every_source_is_unavailable():
    result = QuoteRouter().choose([], "XAUUSD", "spot")
    assert result.quote is None
    assert result.reason == "no_eligible_quote"
