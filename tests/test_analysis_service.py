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


def test_service_maps_broker_and_spot_aliases_to_real_sources(tmp_path):
    store = MarketStore(tmp_path / "market.db")
    store.upsert_candles("BiQuote OHLC", "XAUUSD", "M1", rows(50))
    spot_rows = rows(50)
    spot_rows[-1]["timestamp"] = 999
    store.upsert_candles("XAUS spot reference", "XAUUSD", "M1", spot_rows)

    broker = AnalysisService(store=store).analyze_latest("XAUUSD", "M1", "broker")
    spot = AnalysisService(store=store).analyze_latest("XAUUSD", "M1", "spot")
    assert broker["source"] == "BiQuote OHLC"
    assert spot["source"] == "XAUS spot reference"


def test_service_uses_timeframe_aware_forecast(tmp_path):
    store = MarketStore(tmp_path / "market.db")
    store.upsert_candles("BiQuote OHLC", "XAUUSD", "M5", rows(50))
    result = AnalysisService(store=store).analyze_latest("XAUUSD", "M5")
    assert [point["minute"] for point in result["forecast_points"]] == [5, 10, 15]


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


def test_service_uses_saved_ml_model_only_for_matching_source(tmp_path):
    from ml_engine import WalkForwardDirectionModel

    store = MarketStore(tmp_path / "market.db")
    history = rows(500)
    store.upsert_candles("broker", "XAUUSD", "M1", history)
    model = WalkForwardDirectionModel(epochs=60)
    model.fit(history, horizon=15)
    model.metadata = {"symbol": "XAUUSD", "timeframe": "M1", "source": "broker"}
    model.save(tmp_path / "ml_model.json", model.metadata)

    result = AnalysisService(store=store).analyze_latest("XAUUSD", "M1")
    assert result["source"] == "broker"
    assert result["ml_prediction"]["model"] == "logistic_regression_walk_forward"
