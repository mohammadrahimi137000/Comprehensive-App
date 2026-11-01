"""Static zones and dynamic trendline structure from completed OHLC candles."""
from __future__ import annotations

from analysis_engine import Candle


def _regression(points: list[tuple[int, float]]) -> dict | None:
    if len(points) < 2:
        return None
    xs = [float(item[0]) for item in points]
    ys = [float(item[1]) for item in points]
    x_mean = sum(xs) / len(xs)
    y_mean = sum(ys) / len(ys)
    denominator = sum((x - x_mean) ** 2 for x in xs)
    if denominator == 0:
        return None
    slope = sum((x - x_mean) * (y - y_mean) for x, y in zip(xs, ys)) / denominator
    intercept = y_mean - slope * x_mean
    x_now = max(xs)
    return {
        "slope_per_candle": round(slope, 8),
        "current_value": round(intercept + slope * x_now, 6),
        "points": len(points),
    }


def _atr(candles: list[Candle], period: int = 14) -> float:
    ranges = []
    previous = candles[0].close
    for candle in candles[1:]:
        ranges.append(max(candle.high - candle.low,
                          abs(candle.high - previous), abs(candle.low - previous)))
        previous = candle.close
    return sum(ranges[-period:]) / max(1, min(period, len(ranges)))


def analyze_structure(values, pivot_radius: int = 3) -> dict:
    candles = [Candle.from_value(value) for value in values]
    if len(candles) < pivot_radius * 2 + 5:
        raise ValueError("Not enough candles to analyze market structure")
    if pivot_radius < 1:
        raise ValueError("pivot_radius must be positive")

    lows: list[tuple[int, float]] = []
    highs: list[tuple[int, float]] = []
    for index in range(pivot_radius, len(candles) - pivot_radius):
        candle = candles[index]
        before = candles[index - pivot_radius:index]
        after = candles[index + 1:index + pivot_radius + 1]
        if all(candle.low <= item.low for item in before + after):
            lows.append((index, candle.low))
        if all(candle.high >= item.high for item in before + after):
            highs.append((index, candle.high))

    atr = max(_atr(candles), 1e-9)
    tolerance = max(atr * 0.20, abs(candles[-1].close) * 0.0001)

    def zones(points: list[tuple[int, float]], kind: str) -> list[dict]:
        groups: list[list[tuple[int, float]]] = []
        for point in sorted(points, key=lambda item: item[1]):
            if not groups or abs(point[1] - sum(p[1] for p in groups[-1]) / len(groups[-1])) > tolerance:
                groups.append([point])
            else:
                groups[-1].append(point)
        output = []
        for group in groups:
            prices = [point[1] for point in group]
            center = sum(prices) / len(prices)
            output.append({
                "kind": kind,
                "lower": round(min(prices) - tolerance / 2, 6),
                "upper": round(max(prices) + tolerance / 2, 6),
                "center": round(center, 6),
                "touches": len(group),
                "strength": round(min(100, 35 + len(group) * 12), 1),
            })
        return sorted(output, key=lambda item: item["center"])

    support_zones = zones(lows, "support")
    resistance_zones = zones(highs, "resistance")
    overlaps = []
    for support in support_zones:
        for resistance in resistance_zones:
            lower = max(support["lower"], resistance["lower"])
            upper = min(support["upper"], resistance["upper"])
            if lower <= upper:
                overlaps.append({
                    "lower": round(lower, 6), "upper": round(upper, 6),
                    "priority": "high", "role": "reaction_confluence",
                    "standalone_signal": False,
                    "requires_confirmation": True,
                })

    return {
        "last_close": candles[-1].close,
        "atr": round(atr, 6),
        "static_support_zones": support_zones,
        "static_resistance_zones": resistance_zones,
        "dynamic_support": _regression(lows[-8:]),
        "dynamic_resistance": _regression(highs[-8:]),
        "overlap_reaction_zones": overlaps,
        "note": "Dynamic lines and static zones are independent structure signals; confluence zones require price-action confirmation.",
    }
