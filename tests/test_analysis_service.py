import math

import pytest

from analysis_service import AnalysisService
from market_store import MarketStore


def rows(count=50):
    price = 2000.0
    result = []
    for index in range(count):
        close = price + 0.1 + math.sin(index / 3) * 0.05
        result.append({
            "timestamp": index, "open": price, "high": max(price, close) + 0.2,
            "low": min(price, close) - 0.2, "close": close, "volume": 1,
        })
        price = close
    return result


def test_service_analyzes_and_persists_latest_candles(tmp_path):
    store = MarketStore(tmp_path / "market.db")
    store.upsert_candles("spot", "XAUUSD", "M1", rows())
    result = AnalysisService(store=store).analyze_latest("XAUUSD", "M1", "spot")
    assert len(result["forecast_points"]) == 15
    saved = store.latest_forecasts("XAUUSD")
    assert saved[0]["payload"]["source"] == "spot"
    assert saved[0]["payload"]["symbol"] == "XAUUSD"


def test_service_explains_missing_history(tmp_path):
    store = MarketStore(tmp_path / "market.db")
    store.upsert_candles("spot", "XAUUSD", "M1", rows(10))
    with pytest.raises(ValueError, match="حداقل ۳۰"):
        AnalysisService(store=store).analyze_latest("XAUUSD", "M1", "spot")


def test_service_selects_one_complete_source_instead_of_mixing_feeds(tmp_path):
    store = MarketStore(tmp_path / "market.db")
    store.upsert_candles("slow_spot", "XAUUSD", "M1", rows(50))
    newer = rows(50)
    newer[-1]["timestamp"] = 999
    store.upsert_candles("broker_live", "XAUUSD", "M1", newer)
    result = AnalysisService(store=store).analyze_latest("XAUUSD", "M1")
    assert result["source"] == "broker_live"
