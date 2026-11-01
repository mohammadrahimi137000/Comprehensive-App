"""Evaluate saved research forecasts against later completed candles.

Metrics are descriptive historical hit rates and price errors, not calibrated
probabilities. Overlapping forecast windows may make samples dependent.
"""
from __future__ import annotations

from math import ceil


DIRECTION_FIELDS = (
    ("forecast_bias", "directional_bias"),
    ("technical", "brains.technical.direction"),
    ("price_action", "brains.price_action.direction"),
    ("volatility_statistics", "brains.volatility_statistics.direction"),
    ("liquidity_proxy", "brains.liquidity_proxy.direction"),
    ("multi_brain", "confluence.direction"),
)


def _nested(payload: dict, path: str):
    value = payload
    for key in path.split("."):
        if not isinstance(value, dict):
            return None
        value = value.get(key)
    return value


def evaluate_forecast_history(
    snapshots: list[dict],
    candles: list[dict],
    timeframe_minutes: int,
    source: str,
    timeframe: str,
) -> dict:
    """Return out-of-sample direction hit rates for snapshots now fully matured."""
    if timeframe_minutes < 1:
        raise ValueError("timeframe_minutes must be positive")
    index_by_timestamp = {str(row["timestamp"]): index for index, row in enumerate(candles)}
    stats = {name: {"samples": 0, "correct": 0} for name, _ in DIRECTION_FIELDS}
    price_errors = []
    evaluated = 0

    for snapshot in snapshots:
        payload = snapshot.get("payload") or {}
        if snapshot.get("source") not in {"analysis_engine", source}:
            continue
        if payload.get("source") not in {None, source}:
            continue
        if str(snapshot.get("timeframe", timeframe)).upper() != timeframe.upper():
            continue
        timestamp = payload.get("last_candle_timestamp")
        if timestamp is None:
            continue
        start_index = index_by_timestamp.get(str(timestamp))
        if start_index is None:
            continue
        horizon_minutes = int(payload.get("forecast_horizon_minutes") or 0)
        horizon_candles = max(1, ceil(horizon_minutes / timeframe_minutes))
        target_index = start_index + horizon_candles
        if target_index >= len(candles):
            continue

        start_price = float(candles[start_index]["close"])
        actual_price = float(candles[target_index]["close"])
        actual_direction = "bullish" if actual_price > start_price else (
            "bearish" if actual_price < start_price else "neutral"
        )
        evaluated += 1
        for name, path in DIRECTION_FIELDS:
            predicted = _nested(payload, path)
            if predicted not in {"bullish", "bearish"} or actual_direction == "neutral":
                continue
            stats[name]["samples"] += 1
            stats[name]["correct"] += int(predicted == actual_direction)

        points = payload.get("forecast_points") or []
        if points and isinstance(points[-1], dict) and "mid" in points[-1]:
            price_errors.append(abs(float(points[-1]["mid"]) - actual_price))

    metrics = {}
    for name, item in stats.items():
        samples = item["samples"]
        metrics[name] = {
            "samples": samples,
            "correct": item["correct"],
            "accuracy_pct": round(100.0 * item["correct"] / samples, 2) if samples else None,
        }
    return {
        "status": "available" if evaluated else "insufficient_matured_forecasts",
        "evaluated_forecasts": evaluated,
        "by_brain": metrics,
        "forecast_price_mae": round(sum(price_errors) / len(price_errors), 6) if price_errors else None,
        "price_error_samples": len(price_errors),
        "note": "Descriptive hit rate only; overlapping windows are dependent and this is not probability calibration.",
    }
