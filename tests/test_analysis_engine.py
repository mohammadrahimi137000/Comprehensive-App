import math

import pytest

from analysis_engine import AnalysisEngine, Candle


def sample_candles(count=180):
    rows = []
    price = 2000.0
    for index in range(count):
        drift = 0.08 if index < count * 0.7 else -0.025
        open_price = price
        close = open_price + drift + math.sin(index / 4) * 0.12
        high = max(open_price, close) + 0.25
        low = min(open_price, close) - 0.25
        rows.append({
            "timestamp": index, "open": open_price, "high": high,
            "low": low, "close": close, "volume": 10,
        })
        price = close
    return rows


def test_forecast_has_15_ordered_points_and_normalized_scenarios():
    result = AnalysisEngine().analyze(sample_candles())
    assert len(result["forecast_points"]) == 15
    assert [p["minute"] for p in result["forecast_points"]] == list(range(1, 16))
    assert sum(result["scenarios"].values()) == pytest.approx(100.0)
    assert all(p["low"] <= p["mid"] <= p["high"] for p in result["forecast_points"])
    assert result["status"] == "research_only"


def test_forecast_points_follow_input_timeframe():
    candles = sample_candles()
    m5 = AnalysisEngine().analyze(candles, timeframe_minutes=5)
    m15 = AnalysisEngine().analyze(candles, timeframe_minutes=15)
    assert [p["minute"] for p in m5["forecast_points"]] == [5, 10, 15]
    assert [p["minute"] for p in m15["forecast_points"]] == [15]
    assert m5["forecast_horizon_minutes"] == 15
    assert m15["input_timeframe_minutes"] == 15


def test_rejects_invalid_timeframe_minutes():
    with pytest.raises(ValueError, match="positive"):
        AnalysisEngine().analyze(sample_candles(), timeframe_minutes=0)


def test_rejects_insufficient_history():
    with pytest.raises(ValueError, match="30"):
        AnalysisEngine().analyze(sample_candles(29))


def test_rejects_invalid_candle_geometry():
    with pytest.raises(ValueError, match="high/low"):
        Candle.from_value({"timestamp": 1, "open": 10, "high": 9,
                           "low": 8, "close": 10})


def test_custom_horizon_is_bounded():
    assert len(AnalysisEngine(5).analyze(sample_candles())["forecast_points"]) == 5
    with pytest.raises(ValueError):
        AnalysisEngine(120)
