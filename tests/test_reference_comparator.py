from datetime import datetime, timezone

from feed_router import Quote
from provider_clients import SpotReference
from reference_comparator import compare_reference_prices


def test_compares_broker_mid_to_spot_references_without_substitution():
    now = datetime(2026, 1, 1, tzinfo=timezone.utc)
    quote = Quote("broker", "XAUUSD", "broker", now, 2000, 2000.2)
    refs = [
        SpotReference("XAUS", "XAUUSD", now, 2000.0, "fresh", 1),
        SpotReference("Corgano", "XAUUSD", now, 2000.1, "fresh", 2),
        SpotReference("bad", "XAUUSD", now, 2100.0, "fresh", 1),
    ]
    result = compare_reference_prices(quote, refs, now=now)
    assert result["status"] == "compared"
    assert result["broker_mid"] == 2000.1
    assert result["checked_at"] == now.isoformat()
    assert "bad" in result["outlier_sources"]
    assert all(item["indicative_only"] for item in result["comparisons"])


def test_rejects_stale_and_mismatched_references():
    now = datetime(2026, 1, 1, tzinfo=timezone.utc)
    quote = Quote("broker", "XAUUSD", "broker", now, 2000, 2000.2)
    refs = [
        SpotReference("stale", "XAUUSD", now, 2000, "stale", 1000),
        SpotReference("wrong", "EURUSD", now, 2000, "fresh", 0),
    ]
    result = compare_reference_prices(quote, refs, now=now)
    assert result["status"] == "insufficient_reference_data"
    assert len(result["rejected"]) == 2
