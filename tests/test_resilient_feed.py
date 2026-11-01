from datetime import datetime, timezone

from feed_router import Quote
from resilient_feed import ResilientBiQuoteFeed


def test_resilient_feed_deduplicates_provider_ticks_and_exposes_latest_quote():
    received = []
    feed = ResilientBiQuoteFeed(
        symbols=("XAUUSD",), on_quote=received.append,
        stream_factory=lambda: None,
    )
    quote = Quote("test", "XAUUSD", "broker", datetime.now(timezone.utc), 2000, 2000.2)
    assert feed._handle_quote(quote) is True
    assert feed._handle_quote(quote) is False
    assert received == [quote]
    assert feed.get_latest_quote("XAUUSD") == quote
