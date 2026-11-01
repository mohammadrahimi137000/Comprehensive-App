from forecast_validation import evaluate_forecast_history


def test_matured_forecasts_report_per_brain_hit_rate_and_price_error():
    candles = [
        {"timestamp": str(index), "open": 100 + index, "high": 101 + index,
         "low": 99 + index, "close": 100 + index, "volume": 1}
        for index in range(8)
    ]
    snapshots = [{
        "source": "broker", "timeframe": "M1",
        "payload": {
            "last_candle_timestamp": "0",
            "forecast_horizon_minutes": 2,
            "directional_bias": "bullish",
            "brains": {
                "technical": {"direction": "bullish"},
                "price_action": {"direction": "bearish"},
                "volatility_statistics": {"direction": "neutral"},
                "liquidity_proxy": {"direction": "bullish"},
            },
            "confluence": {"direction": "bullish"},
            "forecast_points": [{"minute": 2, "mid": 101.5}],
        },
    }]
    result = evaluate_forecast_history(snapshots, candles, 1, "broker", "M1")
    assert result["status"] == "available"
    assert result["evaluated_forecasts"] == 1
    assert result["by_brain"]["forecast_bias"]["accuracy_pct"] == 100.0
    assert result["by_brain"]["technical"]["accuracy_pct"] == 100.0
    assert result["by_brain"]["price_action"]["accuracy_pct"] == 0.0
    assert result["by_brain"]["volatility_statistics"]["samples"] == 0
    assert result["forecast_price_mae"] == 0.5


def test_unmatured_or_unmatched_forecasts_are_not_scored():
    candles = [{"timestamp": str(index), "open": 1, "high": 2, "low": 0,
                "close": 1, "volume": 0} for index in range(3)]
    result = evaluate_forecast_history([{
        "source": "other", "timeframe": "M1",
        "payload": {"last_candle_timestamp": "0", "forecast_horizon_minutes": 5},
    }], candles, 1, "broker", "M1")
    assert result["status"] == "insufficient_matured_forecasts"
    assert result["evaluated_forecasts"] == 0
