"""Deterministic, explainable market-analysis foundation.

This module consumes trusted OHLC candles. It does not infer market prices from
screenshots, fetch live data, or place orders. Probabilities are heuristic scores,
not statistically calibrated probabilities.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from math import isfinite
from typing import Iterable, Mapping, Sequence


@dataclass(frozen=True, slots=True)
class Candle:
    timestamp: int | float | str
    open: float
    high: float
    low: float
    close: float
    volume: float = 0.0

    @classmethod
    def from_value(cls, value: "Candle | Mapping[str, object] | Sequence[object]") -> "Candle":
        if isinstance(value, cls):
            candle = value
        elif isinstance(value, Mapping):
            candle = cls(
                timestamp=value.get("timestamp", value.get("time", 0)),
                open=float(value["open"]), high=float(value["high"]),
                low=float(value["low"]), close=float(value["close"]),
                volume=float(value.get("volume", 0) or 0),
            )
        else:
            if len(value) < 5:
                raise ValueError("Each candle needs timestamp, open, high, low, close")
            candle = cls(value[0], float(value[1]), float(value[2]),
                         float(value[3]), float(value[4]),
                         float(value[5]) if len(value) > 5 else 0.0)
        numbers = (candle.open, candle.high, candle.low, candle.close, candle.volume)
        if not all(isfinite(float(number)) for number in numbers):
            raise ValueError("OHLCV values must be finite numbers")
        if candle.low > min(candle.open, candle.close) or candle.high < max(candle.open, candle.close):
            raise ValueError("Candle high/low do not contain open and close")
        if candle.high < candle.low or candle.volume < 0:
            raise ValueError("Invalid candle range or volume")
        return candle


def _ema(values: Sequence[float], period: int) -> float:
    alpha = 2.0 / (period + 1)
    result = values[0]
    for value in values[1:]:
        result = alpha * value + (1 - alpha) * result
    return result


def _atr(candles: Sequence[Candle], period: int = 14) -> float:
    ranges = []
    previous = candles[0].close
    for candle in candles[1:]:
        ranges.append(max(candle.high - candle.low,
                          abs(candle.high - previous), abs(candle.low - previous)))
        previous = candle.close
    if not ranges:
        return max(candles[-1].high - candles[-1].low, 1e-9)
    return sum(ranges[-period:]) / min(period, len(ranges))


def _rsi(closes: Sequence[float], period: int = 14) -> float:
    changes = [b - a for a, b in zip(closes, closes[1:])]
    recent = changes[-period:]
    gains = sum(max(change, 0.0) for change in recent) / len(recent)
    losses = sum(max(-change, 0.0) for change in recent) / len(recent)
    if losses == 0:
        return 100.0 if gains else 50.0
    return 100.0 - 100.0 / (1.0 + gains / losses)


def _levels(candles: Sequence[Candle], radius: int = 3) -> dict[str, list[float]]:
    supports: list[float] = []
    resistances: list[float] = []
    for index in range(radius, len(candles) - radius):
        current = candles[index]
        neighbours = candles[index-radius:index] + candles[index+1:index+radius+1]
        if all(current.low <= item.low for item in neighbours):
            supports.append(current.low)
        if all(current.high >= item.high for item in neighbours):
            resistances.append(current.high)

    def cluster(values: list[float], reverse: bool) -> list[float]:
        selected: list[float] = []
        for value in sorted(values, reverse=reverse):
            if all(abs(value - existing) > max(abs(value), 1.0) * 0.0005
                   for existing in selected):
                selected.append(round(value, 6))
            if len(selected) == 5:
                break
        return selected

    return {"support": cluster(supports, True), "resistance": cluster(resistances, False)}


class AnalysisEngine:
    """Explainable baseline forecast for the next N one-minute steps."""

    def __init__(self, horizon_minutes: int = 15):
        if not 1 <= int(horizon_minutes) <= 60:
            raise ValueError("horizon_minutes must be between 1 and 60")
        self.horizon_minutes = int(horizon_minutes)

    def analyze(
        self,
        values: Iterable[Candle | Mapping[str, object] | Sequence[object]],
        timeframe_minutes: int = 1,
    ) -> dict:
        timeframe_minutes = int(timeframe_minutes)
        if timeframe_minutes < 1:
            raise ValueError("timeframe_minutes must be positive")
        candles = [Candle.from_value(value) for value in values]
        if len(candles) < 30:
            raise ValueError("At least 30 completed candles are required")
        closes = [item.close for item in candles]
        last = candles[-1]
        atr = max(_atr(candles), 1e-9)
        ema_fast = _ema(closes[-60:], min(12, len(closes[-60:])))
        ema_slow = _ema(closes[-120:], min(26, len(closes[-120:])))
        rsi = _rsi(closes)
        momentum = (closes[-1] - closes[-6]) / atr
        trend = 1 if ema_fast > ema_slow else -1 if ema_fast < ema_slow else 0
        momentum_score = max(-1.0, min(1.0, momentum / 2.0))
        rsi_score = max(-1.0, min(1.0, (rsi - 50.0) / 25.0))
        score = max(-1.0, min(1.0, 0.50 * trend + 0.30 * momentum_score + 0.20 * rsi_score))

        # Softmax-like mapping keeps all scenarios non-zero. These are heuristic.
        bullish = 1.0 / (1.0 + pow(2.718281828, -2.2 * score))
        bearish = 1.0 - bullish
        sideways = max(0.10, 1.0 - abs(score)) * 0.30
        bullish *= (1.0 - sideways)
        bearish *= (1.0 - sideways)
        total = bullish + bearish + sideways
        probabilities = {
            "bullish": round(100 * bullish / total, 1),
            "bearish": round(100 * bearish / total, 1),
            "sideways": round(100 * sideways / total, 1),
        }

        direction = 1 if probabilities["bullish"] >= probabilities["bearish"] else -1
        points = []
        # Forecast points are spaced by the input candle interval. A 15-minute
        # horizon therefore yields 15 points on M1, 3 on M5 and 1 on M15.
        steps = max(1, (self.horizon_minutes + timeframe_minutes - 1) // timeframe_minutes)
        effective_horizon = steps * timeframe_minutes
        for step in range(1, steps + 1):
            elapsed_minutes = step * timeframe_minutes
            decay = 1.0 - 0.55 * (step / steps)
            recent_drift_per_candle = (closes[-1] - closes[-6]) / 5.0
            drift_per_candle = (
                0.55 * score * atr * 0.10
                + 0.45 * recent_drift_per_candle * 0.20
            )
            drift = drift_per_candle * step * decay
            uncertainty = atr * (0.30 * step ** 0.5)
            points.append({
                "minute": elapsed_minutes,
                "mid": round(last.close + drift, 6),
                "low": round(last.close + drift - uncertainty, 6),
                "high": round(last.close + drift + uncertainty, 6),
            })

        levels = _levels(candles)
        nearest_support = max((level for level in levels["support"] if level <= last.close), default=None)
        nearest_resistance = min((level for level in levels["resistance"] if level >= last.close), default=None)
        invalidation = (nearest_support if direction > 0 else nearest_resistance)
        return {
            "status": "research_only",
            "symbol": None,
            "timeframe": None,
            "last_close": last.close,
            "last_candle_timestamp": str(last.timestamp),
            "input_timeframe_minutes": timeframe_minutes,
            "forecast_horizon_minutes": effective_horizon,
            "indicators": {
                "ema_fast": round(ema_fast, 6), "ema_slow": round(ema_slow, 6),
                "rsi_14": round(rsi, 2), "atr_14": round(atr, 6),
                "momentum_atr": round(momentum, 3), "trend": trend,
            },
            "levels": levels,
            "nearest_support": nearest_support,
            "nearest_resistance": nearest_resistance,
            "scenarios": probabilities,
            "directional_bias": "bullish" if direction > 0 else "bearish",
            "forecast_points": points,
            "forecast_method": "momentum_blended_drift_with_atr_uncertainty_fan",
            "forecast_confidence": "low_unvalidated",
            "risk_reference": {
                "invalidation_level": invalidation,
                "note": "Reference only; confirm spread, execution price, and position risk separately.",
            },
            "limitations": [
                "Heuristic scenario scores are not calibrated probabilities.",
                "Forecast points are model estimates, not guaranteed future prices.",
                "No live feed, chart-price extraction, news, or order execution is included.",
            ],
        }
