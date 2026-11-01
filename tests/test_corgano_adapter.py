from datetime import datetime, timedelta, timezone

import pytest

from provider_clients import CorganoSpotAdapter


BASE = datetime(2026, 11, 1, 12, 0, tzinfo=timezone.utc)


def payload(as_of="2026-11-01T11:59:00Z"):
    return {
        "data": {"as_of": as_of, "price_usd": {"per_oz": 4000.25}},
        "attribution": {
            "required": True, "text": "Gold price data by Corgano",
            "url": "https://goldprice.corgano.com/",
        },
    }


def test_corgano_returns_fresh_spot_with_required_attribution():
    adapter = CorganoSpotAdapter(
        getter=lambda url, timeout: payload(),
        clock=lambda: BASE,
    )
    result = adapter.get_spot()
    assert result.price == 4000.25
    assert result.attribution_text == "Gold price data by Corgano"
    assert result.attribution_url == "https://goldprice.corgano.com/"
    assert result.is_indicative is True


def test_corgano_enforces_minimum_poll_interval_and_caches():
    calls = []
    now = {"value": BASE}
    adapter = CorganoSpotAdapter(
        getter=lambda url, timeout: (calls.append(url) or payload()),
        clock=lambda: now["value"],
    )
    first = adapter.get_spot()
    now["value"] = BASE + timedelta(seconds=60)
    second = adapter.get_spot()
    assert first is second
    assert len(calls) == 1


def test_corgano_rejects_stale_data_and_missing_attribution_url():
    stale = CorganoSpotAdapter(
        getter=lambda url, timeout: payload("2026-11-01T11:50:00Z"),
        clock=lambda: BASE,
    )
    with pytest.raises(RuntimeError, match="freshness"):
        stale.get_spot()

    missing_credit = payload()
    missing_credit["attribution"]["url"] = ""
    adapter = CorganoSpotAdapter(
        getter=lambda url, timeout: missing_credit,
        clock=lambda: BASE,
    )
    with pytest.raises(RuntimeError, match="attribution"):
        adapter.get_spot()


def test_corgano_cannot_be_configured_to_exceed_safe_poll_rate():
    with pytest.raises(ValueError):
        CorganoSpotAdapter(minimum_interval_seconds=30)


def test_corgano_html_attribution_is_extracted():
    official_shape = {
        "data": {"as_of": "2026-11-01T11:59:00Z", "price_usd": {"per_oz": 4000.25}},
        "attribution": {
            "required": True,
            "html": '<a href="https://goldprice.corgano.com/">Gold price data by Corgano</a>',
        },
    }
    adapter = CorganoSpotAdapter(
        getter=lambda url, timeout: official_shape,
        clock=lambda: BASE,
    )
    result = adapter.get_spot()
    assert result.attribution_url == "https://goldprice.corgano.com/"
    assert result.attribution_text == "Gold price data by Corgano"
