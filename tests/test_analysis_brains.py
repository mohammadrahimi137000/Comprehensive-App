from analysis_brains import analyze_brains


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


def test_liquidity_brain_explicitly_disclaims_order_book():
    result = analyze_brains(sample_candles())
    assert result["brains"]["liquidity_proxy"]["data_type"] == "OHLC_liquidity_proxy_not_order_book"
