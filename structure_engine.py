"""Static/dynamic market structure, swing sequence, BOS/CHoCH and liquidity sweeps.

All structure is inferred from completed OHLC candles; liquidity is only an OHLC
proxy and must never be described as order-book liquidity.
"""
from __future__ import annotations

from analysis_engine import Candle


def _regression(points: list[tuple[int, float]]) -> dict | None:
    if len(points) < 2:
        return None
    xs = [float(item[0]) for item in points]
    ys = [float(item[1]) for item in points]
    x_mean, y_mean = sum(xs) / len(xs), sum(ys) / len(ys)
    denominator = sum((x - x_mean) ** 2 for x in xs)
    if denominator == 0:
        return None
    slope = sum((x - x_mean) * (y - y_mean) for x, y in zip(xs, ys)) / denominator
    intercept = y_mean - slope * x_mean
    return {"slope_per_candle": round(slope, 8),
            "current_value": round(intercept + slope * max(xs), 6),
            "points": len(points)}


def _atr(candles: list[Candle], period: int = 14) -> float:
    ranges, previous = [], candles[0].close
    for candle in candles[1:]:
        ranges.append(max(candle.high - candle.low,
                          abs(candle.high - previous), abs(candle.low - previous)))
        previous = candle.close
    return sum(ranges[-period:]) / max(1, min(period, len(ranges)))


def _pivot_points(candles: list[Candle], radius: int):
    lows, highs = [], []
    for index in range(radius, len(candles) - radius):
        candle = candles[index]
        neighbours = candles[index-radius:index] + candles[index+1:index+radius+1]
        if all(candle.low <= item.low for item in neighbours):
            lows.append((index, candle.low))
        if all(candle.high >= item.high for item in neighbours):
            highs.append((index, candle.high))
    return lows, highs


def _swing_labels(points: list[tuple[int, float]], kind: str) -> list[dict]:
    result = []
    for previous, current in zip(points, points[1:]):
        delta = current[1] - previous[1]
        tolerance = max(abs(current[1]), 1.0) * 0.00005
        if kind == "high":
            label = "HH" if delta > tolerance else "LH" if delta < -tolerance else "EH"
        else:
            label = "HL" if delta > tolerance else "LL" if delta < -tolerance else "EL"
        result.append({"index": current[0], "price": round(current[1], 6), "label": label})
    if points and not result:
        result.append({"index": points[-1][0], "price": round(points[-1][1], 6), "label": "initial"})
    return result


def _zone_distance(price: float, zone: dict) -> float:
    if zone["lower"] <= price <= zone["upper"]:
        return 0.0
    return min(abs(price - zone["lower"]), abs(price - zone["upper"]))


def analyze_structure(values, pivot_radius: int = 3) -> dict:
    candles = [Candle.from_value(value) for value in values]
    if pivot_radius < 1:
        raise ValueError("pivot_radius must be positive")
    if len(candles) < pivot_radius * 2 + 5:
        raise ValueError("Not enough candles to analyze market structure")

    lows, highs = _pivot_points(candles, pivot_radius)
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
            output.append({
                "kind": kind, "lower": round(min(prices) - tolerance / 2, 6),
                "upper": round(max(prices) + tolerance / 2, 6),
                "center": round(sum(prices) / len(prices), 6),
                "touches": len(group),
                "strength": round(min(100, 35 + len(group) * 12), 1),
            })
        return sorted(output, key=lambda item: item["center"])

    support_zones, resistance_zones = zones(lows, "support"), zones(highs, "resistance")
    price = candles[-1].close
    support_candidates = [zone for zone in support_zones if zone["lower"] <= price]
    resistance_candidates = [zone for zone in resistance_zones if zone["upper"] >= price]
    nearest_support = min(support_candidates, key=lambda z: _zone_distance(price, z), default=None)
    nearest_resistance = min(resistance_candidates, key=lambda z: _zone_distance(price, z), default=None)

    high_labels, low_labels = _swing_labels(highs, "high"), _swing_labels(lows, "low")
    high_sequence = [item["label"] for item in high_labels[-2:]]
    low_sequence = [item["label"] for item in low_labels[-2:]]
    bullish = (len(high_sequence) == 2 and high_sequence[-1] == "HH"
               and len(low_sequence) == 2 and low_sequence[-1] == "HL")
    bearish = (len(high_sequence) == 2 and high_sequence[-1] == "LH"
               and len(low_sequence) == 2 and low_sequence[-1] == "LL")
    structural_trend = "bullish" if bullish else "bearish" if bearish else "range_or_transition"

    last_high = highs[-1] if highs else None
    last_low = lows[-1] if lows else None
    bullish_break = bool(last_high and price > last_high[1])
    bearish_break = bool(last_low and price < last_low[1])
    previous_trend = "bearish" if bearish else "bullish" if bullish else "unknown"
    if bullish_break:
        break_direction = "bullish"
        break_type = "CHoCH" if previous_trend == "bearish" else "BOS"
        broken_level = last_high[1]
    elif bearish_break:
        break_direction = "bearish"
        break_type = "CHoCH" if previous_trend == "bullish" else "BOS"
        broken_level = last_low[1]
    else:
        break_direction, break_type, broken_level = "none", "none", None

    last = candles[-1]
    sweeps = []
    if last_high and last.high > last_high[1] and price < last_high[1]:
        sweeps.append({"side": "buy_side", "level": round(last_high[1], 6),
                       "confirmation": "close_back_below"})
    if last_low and last.low < last_low[1] and price > last_low[1]:
        sweeps.append({"side": "sell_side", "level": round(last_low[1], 6),
                       "confirmation": "close_back_above"})

    overlaps = []
    for support in support_zones:
        for resistance in resistance_zones:
            lower, upper = max(support["lower"], resistance["lower"]), min(support["upper"], resistance["upper"])
            if lower <= upper:
                overlaps.append({"lower": round(lower, 6), "upper": round(upper, 6),
                                 "priority": "high", "role": "reaction_confluence",
                                 "standalone_signal": False, "requires_confirmation": True})

    return {
        "last_close": price, "atr": round(atr, 6),
        "static_support_zones": support_zones, "static_resistance_zones": resistance_zones,
        "nearest_support_zone": nearest_support, "nearest_resistance_zone": nearest_resistance,
        "nearest_support": nearest_support["center"] if nearest_support else None,
        "nearest_resistance": nearest_resistance["center"] if nearest_resistance else None,
        "dynamic_support": _regression(lows[-8:]), "dynamic_resistance": _regression(highs[-8:]),
        "swing_structure": {"highs": high_labels[-8:], "lows": low_labels[-8:],
                            "trend": structural_trend},
        "structure_break": {"type": break_type, "direction": break_direction,
                            "level": round(broken_level, 6) if broken_level is not None else None,
                            "confirmed_by_close": break_direction != "none"},
        "liquidity_sweeps": sweeps,
        "overlap_reaction_zones": overlaps,
        "note": "BOS/CHoCH and liquidity sweeps are OHLC swing proxies; validate with context. Confluence zones require price-action confirmation.",
    }
