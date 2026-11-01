"""Small pure-Python logistic model for walk-forward candle direction research.

This is intentionally transparent and dependency-light. It reports holdout metrics;
it is not advertised as profitable or calibrated until enough unseen history exists.
"""
from __future__ import annotations

from math import exp, sqrt
from statistics import mean


def _sigmoid(value: float) -> float:
    value = max(-30.0, min(30.0, value))
    return 1.0 / (1.0 + exp(-value))


def _features(candles: list[dict], index: int) -> list[float]:
    window = candles[max(0, index - 20):index + 1]
    closes = [float(row["close"]) for row in window]
    highs = [float(row["high"]) for row in window]
    lows = [float(row["low"]) for row in window]
    returns = [(b - a) / max(abs(a), 1e-9) for a, b in zip(closes, closes[1:])]
    ranges = [(h - l) / max(abs(c), 1e-9) for h, l, c in zip(highs, lows, closes)]
    last = closes[-1]
    mean5 = mean(closes[-5:])
    mean20 = mean(closes[-20:]) if len(closes) >= 20 else mean(closes)
    return [
        1.0,
        (last - mean5) / max(abs(last), 1e-9),
        (last - mean20) / max(abs(last), 1e-9),
        mean(returns[-5:]) if returns else 0.0,
        mean(returns[-15:]) if returns else 0.0,
        mean(ranges[-14:]) if ranges else 0.0,
        (max(highs[-14:]) - min(lows[-14:])) / max(abs(last), 1e-9),
    ]


class WalkForwardDirectionModel:
    def __init__(self, learning_rate: float = 0.15, epochs: int = 500, l2: float = 0.01):
        self.learning_rate = learning_rate
        self.epochs = epochs
        self.l2 = l2
        self.weights: list[float] | None = None
        self.metrics: dict | None = None

    def fit(self, candles: list[dict], horizon: int = 15) -> dict:
        if horizon < 1 or len(candles) < max(180, horizon * 5):
            raise ValueError("At least 180 candles are required for walk-forward training.")
        data = []
        for index in range(25, len(candles) - horizon):
            x = _features(candles, index)
            future = float(candles[index + horizon]["close"])
            current = float(candles[index]["close"])
            data.append((x, 1.0 if future > current else 0.0))
        split = int(len(data) * 0.75)
        train, test = data[:split], data[split:]
        if len(train) < 100 or len(test) < 20:
            raise ValueError("Not enough separated train/holdout samples.")

        weights = [0.0] * len(train[0][0])
        for _ in range(self.epochs):
            gradients = [0.0] * len(weights)
            for features, label in train:
                error = _sigmoid(sum(w * x for w, x in zip(weights, features))) - label
                for j, value in enumerate(features):
                    gradients[j] += error * value
            scale = 1.0 / len(train)
            for j in range(len(weights)):
                regularization = self.l2 * weights[j] if j else 0.0
                weights[j] -= self.learning_rate * (gradients[j] * scale + regularization)

        probabilities = [_sigmoid(sum(w * x for w, x in zip(weights, features))) for features, _ in test]
        labels = [label for _, label in test]
        predictions = [1.0 if probability >= 0.5 else 0.0 for probability in probabilities]
        accuracy = mean(float(a == b) for a, b in zip(predictions, labels))
        brier = mean((p - y) ** 2 for p, y in zip(probabilities, labels))
        baseline = max(mean(labels), 1 - mean(labels))
        self.weights = weights
        self.metrics = {
            "train_samples": len(train), "holdout_samples": len(test),
            "holdout_accuracy": round(accuracy, 4),
            "holdout_brier_score": round(brier, 4),
            "majority_class_baseline": round(baseline, 4),
            "beats_majority_baseline": accuracy > baseline,
            "horizon_candles": horizon,
            "features": ["bias", "return_vs_mean5", "return_vs_mean20",
                         "mean_return5", "mean_return15", "mean_range14", "range14"],
            "warning": "Single chronological holdout; not a guarantee of future performance.",
        }
        return self.metrics

    def predict(self, candles: list[dict]) -> dict:
        if self.weights is None:
            raise RuntimeError("Model has not been trained.")
        probability = _sigmoid(sum(w * x for w, x in zip(self.weights, _features(candles, len(candles) - 1))))
        return {
            "up_probability": round(probability, 4),
            "down_probability": round(1.0 - probability, 4),
            "model": "logistic_regression_walk_forward",
            "metrics": self.metrics,
            "interpretation": "Experimental direction score; not an entry signal.",
        }
