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
