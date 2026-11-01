import math

from ml_engine import WalkForwardDirectionModel


def candles(count=500):
    rows = []
    price = 2000.0
    for i in range(count):
        change = 0.08 + math.sin(i / 8) * 0.02
        close = price + change
        rows.append({
            "open": price, "high": max(price, close) + 0.1,
            "low": min(price, close) - 0.1, "close": close, "volume": 1,
        })
        price = close
    return rows


def test_walk_forward_model_trains_and_reports_holdout_metrics():
    rows = candles()
    model = WalkForwardDirectionModel(epochs=80)
    metrics = model.fit(rows, horizon=5)
    prediction = model.predict(rows)
    assert metrics["train_samples"] > metrics["holdout_samples"]
    assert 0 <= metrics["holdout_brier_score"] <= 1
    assert 0 <= prediction["up_probability"] <= 1
    assert prediction["model"] == "logistic_regression_walk_forward"


def test_ml_model_rejects_short_history():
    import pytest
    with pytest.raises(ValueError, match="180"):
        WalkForwardDirectionModel().fit(candles(100))


def test_model_persistence_round_trip(tmp_path):
    rows = candles()
    model = WalkForwardDirectionModel(epochs=60)
    model.fit(rows, horizon=5)
    model.metadata = {"symbol": "XAUUSD", "timeframe": "M1", "source": "broker"}
    path = tmp_path / "ml_model.json"
    model.save(path, model.metadata)

    restored = WalkForwardDirectionModel()
    metadata = restored.load(path)
    assert metadata == model.metadata
    assert restored.predict(rows)["up_probability"] == model.predict(rows)["up_probability"]
