from datetime import datetime, timedelta, timezone

import pytest

from candle_builder import TickCandleBuilder
from feed_router import Quote


def quote(seconds, bid, ask, source="feed"):
    return Quote(
        source=source, instrument="XAUUSD", market_type="broker",
        timestamp=datetime(2026, 1, 1, tzinfo=timezone.utc) + timedelta(seconds=seconds),
        bid=bid, ask=ask,
    )


def test_builds_completed_one_minute_candle_from_mid_prices():
    builder = TickCandleBuilder(60)
    assert builder.update(quote(1, 100, 102)) == []
    assert builder.update(quote(20, 102, 104)) == []
    completed = builder.update(quote(61, 99, 101))[0]
    assert completed["open"] == 101
    assert completed["high"] == 103
    assert completed["low"] == 101
    assert completed["close"] == 103
    assert completed["tick_count"] == 2
    assert completed["volume"] == 0


def test_ignores_out_of_order_tick_without_rewriting_bar():
    builder = TickCandleBuilder(60)
    builder.update(quote(61, 100, 102))
    builder.update(quote(121, 102, 104))
    assert builder.update(quote(70, 90, 92)) == []
    assert builder.current_bar("feed", "XAUUSD")["open"] == 103


def test_keeps_provider_sources_separate():
    builder = TickCandleBuilder(60)
    builder.update(quote(1, 100, 102, "feed-a"))
    builder.update(quote(1, 200, 202, "feed-b"))
    assert builder.current_bar("feed-a", "XAUUSD")["open"] == 101
    assert builder.current_bar("feed-b", "XAUUSD")["open"] == 201


def test_rejects_unsupported_timeframe_and_invalid_quote():
    with pytest.raises(ValueError):
        TickCandleBuilder(30)
    builder = TickCandleBuilder(60)
    with pytest.raises(ValueError):
        builder.update(quote(1, 10, 10))
