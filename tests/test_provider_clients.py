from datetime import datetime, timezone

import pytest

from provider_clients import BiQuoteRestAdapter, XausSpotAdapter


def test_biquote_adapter_normalizes_bid_ask_and_timestamp():
    def getter(url, timeout):
        assert "allowStale=false" in url
        return {
            "symbol": "XAUUSD", "source": "MT5 feed",
            "timestamp": "2026-11-01T10:00:00Z",
            "bid": 3999.8, "ask": 4000.0, "marketState": "open",
            "stale": False,
        }
    quote = BiQuoteRestAdapter(getter=getter).get_quote()
    assert quote.instrument == "XAUUSD"
    assert quote.market_type == "broker"
    assert quote.bid == 3999.8
    assert quote.timestamp.tzinfo == timezone.utc


def test_biquote_rejects_closed_or_stale_market():
    def closed(url, timeout):
        return {"marketState": "closed", "stale": True}
    assert BiQuoteRestAdapter(getter=closed).get_quote() is None


def test_xaus_returns_indicative_spot_without_invented_bid_ask():
    def getter(url, timeout):
        return {
            "spot_usd_oz": 4001.25,
            "price_as_of": "2026-11-01T10:00:00Z",
            "price_source": "upstream-feed",
            "data_state": {"status": "fresh", "age_seconds": 3},
        }
    spot = XausSpotAdapter(getter=getter).get_spot()
    assert spot.price == 4001.25
    assert spot.is_indicative is True
    assert not hasattr(spot, "bid")
    assert not hasattr(spot, "ask")


def test_xaus_rejects_stale_reference_price():
    def getter(url, timeout):
        return {"data_state": {"status": "stale"}}
    with pytest.raises(RuntimeError, match="not fresh"):
        XausSpotAdapter(getter=getter).get_spot()
