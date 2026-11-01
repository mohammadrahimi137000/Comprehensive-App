import pytest

from market_store import MarketStore


def candles():
    return [
        {"timestamp": 1, "open": 100, "high": 102, "low": 99, "close": 101, "volume": 4},
        {"timestamp": 2, "open": 101, "high": 103, "low": 100, "close": 102, "volume": 5},
    ]


def test_upsert_is_idempotent_and_updates_existing_candle(tmp_path):
    store = MarketStore(tmp_path / "market.db")
    assert store.upsert_candles("feed-a", "xauusd", "m1", candles()) == 2
    changed = candles()
    changed[1]["close"] = 102.5
    assert store.upsert_candles("feed-a", "XAUUSD", "M1", changed) == 2
    rows = store.get_candles("XAUUSD", "M1")
    assert len(rows) == 2
    assert rows[-1]["close"] == 102.5


def test_sources_are_kept_separate(tmp_path):
    store = MarketStore(tmp_path / "market.db")
    store.upsert_candles("spot", "XAUUSD", "M1", candles())
    store.upsert_candles("broker", "XAUUSD", "M1", candles())
    assert len(store.get_candles("XAUUSD", "M1")) == 4
    assert len(store.get_candles("XAUUSD", "M1", source="spot")) == 2


def test_forecast_history_round_trip(tmp_path):
    store = MarketStore(tmp_path / "market.db")
    forecast_id = store.save_forecast("engine", "XAUUSD", "M1", {"bias": "bullish", "points": [1, 2]})
    rows = store.latest_forecasts("xauusd")
    assert rows[0]["id"] == forecast_id
    assert rows[0]["payload"] == {"bias": "bullish", "points": [1, 2]}


def test_limits_are_validated(tmp_path):
    store = MarketStore(tmp_path / "market.db")
    with pytest.raises(ValueError):
        store.get_candles("XAUUSD", "M1", limit=0)
    with pytest.raises(ValueError):
        store.latest_forecasts("XAUUSD", limit=0)
