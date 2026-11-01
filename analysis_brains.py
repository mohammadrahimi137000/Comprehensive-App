"""Independent, explainable OHLC analysis brains with explicit evidence and fixed weights."""
from __future__ import annotations

from statistics import mean, pstdev

from analysis_engine import Candle


def _clamp(value: float) -> float:
    return max(-1.0, min(1.0, value))


def _ema(values: list[float], period: int) -> float:
    alpha = 2.0 / (period + 1)
    value = values[0]
    for item in values[1:]:
        value = alpha * item + (1 - alpha) * value
    return value


def _direction(score: float) -> str:
    return "bullish" if score > 0.15 else "bearish" if score < -0.15 else "neutral"


def analyze_brains(values: list[dict]) -> dict:
    candles = [Candle.from_value(item) for item in values]
    if len(candles) < 30:
        raise ValueError("At least 30 candles are required for independent analysis brains.")
    last, previous = candles[-1], candles[-2]
    prior = candles[-21:-1]
    prior_high = max(item.high for item in prior)
    prior_low = min(item.low for item in prior)
    candle_range = max(last.high - last.low, 1e-9)
    body = last.close - last.open
    body_ratio = abs(body) / candle_range

    pa_score = 0.0
    pa_evidence = []
    if body > 0:
        pa_score += 0.35 * body_ratio
        pa_evidence.append("last_candle_bullish")
    elif body < 0:
        pa_score -= 0.35 * body_ratio
        pa_evidence.append("last_candle_bearish")
    if last.close > previous.high and last.open < previous.close:
        pa_score += 0.45
        pa_evidence.append("bullish_engulfing_or_break")
    elif last.close < previous.low and last.open > previous.close:
        pa_score -= 0.45
        pa_evidence.append("bearish_engulfing_or_break")
    if last.close > prior_high:
        pa_score += 0.35
        pa_evidence.append("20_candle_high_breakout")
    elif last.close < prior_low:
        pa_score -= 0.35
        pa_evidence.append("20_candle_low_breakdown")
    price_action = {"score": round(_clamp(pa_score), 4),
                    "direction": _direction(pa_score), "evidence": pa_evidence}

    closes = [item.close for item in candles[-21:]]
    returns = [(b - a) / max(abs(a), 1e-9) for a, b in zip(closes, closes[1:])]
    volatility = pstdev(returns) if len(returns) > 1 else 0.0
    avg_return = mean(returns) if returns else 0.0
    zscore = avg_return / max(volatility, 1e-9)
    stat_score = _clamp(zscore / 2.5)
    ranges = [(item.high - item.low) / max(abs(item.close), 1e-9) for item in candles[-20:]]
    volatility_brain = {
        "score": round(stat_score, 4), "direction": _direction(stat_score),
        "mean_return": avg_return, "return_volatility": volatility,
        "current_range_pct": ranges[-1],
        "volatility_regime": "expanding" if ranges[-1] > mean(ranges) * 1.25 else
                             "contracting" if ranges[-1] < mean(ranges) * 0.75 else "normal",
        "sample_size": len(returns),
    }

    liquidity_score = 0.0
    liquidity_evidence = []
    if last.high > prior_high and last.close < prior_high:
        liquidity_score -= 0.8
        liquidity_evidence.append("possible_buy_side_liquidity_sweep")
    if last.low < prior_low and last.close > prior_low:
        liquidity_score += 0.8
        liquidity_evidence.append("possible_sell_side_liquidity_sweep")
    tolerance = max(abs(last.close) * 0.00015, candle_range * 0.15)
    equal_highs = sum(abs(item.high - prior_high) <= tolerance for item in prior)
    equal_lows = sum(abs(item.low - prior_low) <= tolerance for item in prior)
    if equal_highs >= 2:
        liquidity_evidence.append("clustered_equal_highs")
    if equal_lows >= 2:
        liquidity_evidence.append("clustered_equal_lows")
    liquidity_brain = {
        "score": round(_clamp(liquidity_score), 4),
        "direction": _direction(liquidity_score),
        "evidence": liquidity_evidence,
        "equal_high_cluster_count": equal_highs,
        "equal_low_cluster_count": equal_lows,
        "data_type": "OHLC_liquidity_proxy_not_order_book",
    }

    closes_for_ema = [item.close for item in candles]
    fast = _ema(closes_for_ema[-30:], 8)
    slow = _ema(closes_for_ema[-60:], 24)
    rsi_gain = mean([max(b.close - a.close, 0) for a, b in zip(candles[-15:], candles[-14:])])
    rsi_loss = mean([max(a.close - b.close, 0) for a, b in zip(candles[-15:], candles[-14:])])
    rsi = 100 - 100 / (1 + rsi_gain / max(rsi_loss, 1e-9))
    technical_score = _clamp((1 if fast > slow else -1 if fast < slow else 0) * 0.65
                             + _clamp((rsi - 50) / 40) * 0.35)
    technical = {
        "score": round(technical_score, 4), "direction": _direction(technical_score),
        "ema_fast": fast, "ema_slow": slow, "rsi_proxy": round(rsi, 2),
    }

    weights = {
        "technical": 0.35, "price_action": 0.25,
        "volatility_statistics": 0.20, "liquidity_proxy": 0.20,
    }
    combined = (
        technical_score * weights["technical"]
        + pa_score * weights["price_action"]
        + stat_score * weights["volatility_statistics"]
        + liquidity_score * weights["liquidity_proxy"]
    )
    return {
        "brains": {
            "technical": technical, "price_action": price_action,
            "volatility_statistics": volatility_brain,
            "liquidity_proxy": liquidity_brain,
        },
        "confluence": {
            "score": round(combined, 4), "direction": _direction(combined),
            "weights": weights, "weights_are_fixed": True,
            "weighting_note": "Weights are transparent starting values; not yet learned from live out-of-sample engine performance.",
        },
    }
