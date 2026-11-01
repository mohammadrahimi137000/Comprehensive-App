"""Small pure-Python logistic model for walk-forward candle direction research.

This is intentionally transparent and dependency-light. It reports holdout metrics;
it is not advertised as profitable or calibrated until enough unseen history exists.
"""
from __future__ import annotations

from math import exp
import json
from pathlib import Path
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
        10_000 * (last - mean5) / max(abs(last), 1e-9),
        10_000 * (last - mean20) / max(abs(last), 1e-9),
        10_000 * (mean(returns[-5:]) if returns else 0.0),
        10_000 * (mean(returns[-15:]) if returns else 0.0),
        10_000 * (mean(ranges[-14:]) if ranges else 0.0),
        10_000 * (max(highs[-14:]) - min(lows[-14:])) / max(abs(last), 1e-9),
    ]


class WalkForwardDirectionModel:
    def __init__(self, learning_rate: float = 0.15, epochs: int = 500, l2: float = 0.01):
        self.learning_rate = learning_rate
        self.epochs = epochs
        self.l2 = l2
        self.weights: list[float] | None = None
        self.metrics: dict | None = None
        self.metadata: dict = {}

    def fit(self, candles: list[dict], horizon: int = 15) -> dict:
        minimum_history = max(200, horizon * 5 + 45)
        if horizon < 1 or len(candles) < minimum_history:
            raise ValueError(f"At least {minimum_history} candles are required for walk-forward training.")
        data = []
        for index in range(25, len(candles) - horizon):
            x = _features(candles, index)
            future = float(candles[index + horizon]["close"])
            current = float(candles[index]["close"])
            data.append((x, 1.0 if future > current else 0.0))
        split = int(len(data) * 0.75)
        # Purge the final horizon observations from training so labels cannot
        # overlap the chronological holdout period.
        train, test = data[:max(0, split - horizon)], data[split:]
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
        baseline_brier = mean(labels) * (1.0 - mean(labels))
        self.weights = weights
        self.metrics = {
            "train_samples": len(train), "holdout_samples": len(test),
            "holdout_accuracy": round(accuracy, 4),
            "holdout_brier_score": round(brier, 4),
            "majority_class_baseline": round(baseline, 4),
            "beats_majority_baseline": accuracy > baseline,
            "prevalence_brier_baseline": round(baseline_brier, 4),
            "beats_brier_baseline": brier < baseline_brier,
            "horizon_candles": horizon,
            "features": ["bias", "scaled_return_vs_mean5", "scaled_return_vs_mean20",
                         "mean_return5", "mean_return15", "mean_range14", "range14"],
            "warning": "Single chronological holdout; not a guarantee of future performance.",
        }
        return self.metrics


    def save(self, path: str | Path, metadata: dict | None = None) -> None:
        if self.weights is None or self.metrics is None:
            raise RuntimeError("Cannot save an untrained model.")
        destination = Path(path)
        destination.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "model": "logistic_regression_walk_forward",
            "weights": self.weights,
            "metrics": self.metrics,
            "metadata": metadata or {},
        }
        temporary = destination.with_suffix(destination.suffix + ".tmp")
        temporary.write_text(json.dumps(payload, ensure_ascii=False, allow_nan=False), encoding="utf-8")
        temporary.replace(destination)

    def load(self, path: str | Path) -> dict:
        payload = json.loads(Path(path).read_text(encoding="utf-8"))
        if payload.get("model") != "logistic_regression_walk_forward":
            raise ValueError("Unsupported saved ML model format.")
        weights = payload.get("weights")
        if not isinstance(weights, list) or len(weights) != 7:
            raise ValueError("Saved ML model has invalid weights.")
        self.weights = [float(value) for value in weights]
        self.metrics = payload.get("metrics")
        self.metadata = payload.get("metadata") or {}
        return self.metadata

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
