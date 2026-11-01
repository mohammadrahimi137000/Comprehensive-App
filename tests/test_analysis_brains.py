from analysis_brains import analyze_brains
from analysis_engine import AnalysisEngine


def sample_candles(count=80):
    rows = []
    price = 2000.0
    for index in range(count):
        close = price + 0.4
        rows.append({
            "timestamp": index, "open": price, "high": close + 0.2,
            "low": price - 0.1, "close": close, "volume": 0,
        })
        price = close
    return rows


def test_independent_brains_return_explainable_scores_and_fixed_weights():
    result = analyze_brains(sample_candles())
    assert set(result["brains"]) == {
        "technical", "price_action", "volatility_statistics", "liquidity_proxy"
    }
    assert result["confluence"]["weights_are_fixed"] is True
    assert abs(sum(result["confluence"]["weights"].values()) - 1.0) < 1e-9
    assert -1 <= result["confluence"]["score"] <= 1
    assert "disagreement" in result["confluence"]


def test_liquidity_brain_explicitly_disclaims_order_book():
    result = analyze_brains(sample_candles())
    assert result["brains"]["liquidity_proxy"]["data_type"] == "OHLC_liquidity_proxy_not_order_book"


def test_technical_ema_and_trend_match_primary_engine():
    rows = sample_candles()
    brain = analyze_brains(rows)["brains"]["technical"]
    primary = AnalysisEngine().analyze(rows)["indicators"]
    assert brain["ema_fast"] == primary["ema_fast"]
    assert brain["ema_slow"] == primary["ema_slow"]
    assert brain["ema_trend"] == primary["trend"]
