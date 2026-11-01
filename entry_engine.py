"""Conservative, read-only entry readiness evaluation.

A candidate requires broker OHLC, a fresh executable quote, calibrated chart
recognition, completed-candle price action and an independent spot comparison.
This module never places orders.
"""
from __future__ import annotations

from datetime import datetime, timezone
from math import isfinite


def _value(item, name, default=None):
    if isinstance(item, dict):
        return item.get(name, default)
    return getattr(item, name, default)


def _blocked(blockers: list[str], details: dict | None = None) -> dict:
    return {
        "status": "no_trade",
        "entry_allowed": False,
        "direction": None,
        "blockers": list(dict.fromkeys(blockers)),
        "plan": None,
        "details": details or {},
        "note": "Research-only assessment. No broker order is sent.",
    }


def evaluate_entry_readiness(
    candles, analysis: dict, source: str, live_quote=None,
    chart_context: dict | None = None, reference_context: dict | None = None,
    now: datetime | None = None, max_quote_age_seconds: float = 10.0,
    max_chart_age_seconds: float = 120.0, max_spread: float = 0.80,
    min_reward_risk: float = 1.5, min_directional_score: float = 60.0,
    max_reference_deviation_bps: float = 35.0,
) -> dict:
    """Return a no-trade explanation or a manual-review candidate plan."""
    now = now or datetime.now(timezone.utc)
    if now.tzinfo is None:
        raise ValueError("now must be timezone-aware")
    now = now.astimezone(timezone.utc)
    blockers: list[str] = []
    details: dict = {}

    if not any(token in str(source or "").lower() for token in ("broker", "biquote")):
        blockers.append("analysis_source_is_not_broker_ohlc")

    quote = live_quote
    bid = ask = 0.0
    if quote is None:
        blockers.append("fresh_live_broker_quote_missing")
    else:
        timestamp = _value(quote, "timestamp")
        if not isinstance(timestamp, datetime) or timestamp.tzinfo is None:
            blockers.append("quote_timestamp_invalid")
        else:
            age = (now - timestamp.astimezone(timezone.utc)).total_seconds()
            details["quote_age_seconds"] = round(age, 3)
            if age < -2 or age > max_quote_age_seconds:
                blockers.append("quote_stale_or_future")
        if str(_value(quote, "instrument", "")).upper() != str(analysis.get("symbol") or "XAUUSD").upper():
            blockers.append("quote_instrument_mismatch")
        if str(_value(quote, "market_type", "")).lower() != "broker":
            blockers.append("quote_is_not_broker_executable")
        if bool(_value(quote, "is_simulated", False)):
            blockers.append("simulated_quote_rejected")
        try:
            bid, ask = float(_value(quote, "bid")), float(_value(quote, "ask"))
            if not all(isfinite(value) for value in (bid, ask)) or bid <= 0 or ask <= bid:
                raise ValueError
        except (TypeError, ValueError):
            bid = ask = 0.0
            blockers.append("quote_bid_ask_invalid")
        spread = ask - bid
        details["spread"] = round(spread, 6)
        if spread <= 0 or spread > max_spread:
            blockers.append("spread_outside_limit")

    if not isinstance(chart_context, dict):
        blockers.append("calibrated_chart_context_missing")
    else:
        if not chart_context.get("calibrated"):
            blockers.append("chart_price_axis_not_calibrated")
        if str(chart_context.get("symbol") or "").upper() != str(analysis.get("symbol") or "XAUUSD").upper():
            blockers.append("chart_symbol_mismatch")
        if chart_context.get("timeframe_minutes") != analysis.get("timeframe_minutes"):
            blockers.append("chart_timeframe_mismatch")
        try:
            captured = datetime.fromisoformat(str(chart_context.get("captured_at")).replace("Z", "+00:00"))
            if captured.tzinfo is None:
                raise ValueError
            chart_age = (now - captured.astimezone(timezone.utc)).total_seconds()
            details["chart_age_seconds"] = round(chart_age, 3)
            if chart_age < -2 or chart_age > max_chart_age_seconds:
                blockers.append("chart_recognition_stale")
        except (TypeError, ValueError):
            blockers.append("chart_capture_timestamp_invalid")

    if not isinstance(reference_context, dict) or reference_context.get("status") != "compared":
        blockers.append("independent_spot_reference_not_verified")
    else:
        comparisons = reference_context.get("comparisons") or []
        deviations = []
        for item in comparisons:
            try:
                deviations.append(abs(float(item["broker_minus_reference_bps"])))
            except (KeyError, TypeError, ValueError):
                continue
        if not deviations:
            blockers.append("independent_spot_comparison_invalid")
        elif max(deviations) > max_reference_deviation_bps:
            blockers.append("broker_spot_deviation_too_large")
        details["max_reference_deviation_bps"] = round(max(deviations), 2) if deviations else None

    if len(candles) < 2:
        return _blocked(blockers + ["insufficient_completed_price_action_candles"], details)
    previous, last = candles[-2], candles[-1]
    try:
        previous_high = float(_value(previous, "high"))
        previous_low = float(_value(previous, "low"))
        open_price = float(_value(last, "open"))
        high = float(_value(last, "high"))
        low = float(_value(last, "low"))
        close = float(_value(last, "close"))
        if not all(isfinite(value) for value in (previous_high, previous_low, open_price, high, low, close)):
            raise ValueError
    except (TypeError, ValueError):
        return _blocked(blockers + ["invalid_completed_candle"], details)

    bias = analysis.get("directional_bias")
    confluence = analysis.get("confluence") or {}
    alignment = analysis.get("analysis_alignment") or {}
    scenarios = analysis.get("scenarios") or {}
    if confluence.get("disagreement"):
        blockers.append("analysis_brains_disagree")
    if confluence.get("active_brains", 0) < 3:
        blockers.append("insufficient_active_analysis_brains")
    if confluence.get("direction") != bias or bias not in {"bullish", "bearish"}:
        blockers.append("forecast_and_confluence_not_aligned")
    if alignment.get("forecast_vs_confluence_conflict"):
        blockers.append("forecast_confluence_conflict")
    try:
        directional_score = float(scenarios.get("bullish" if bias == "bullish" else "bearish", 0))
    except (TypeError, ValueError):
        directional_score = 0.0
    details["directional_score"] = directional_score
    if directional_score < min_directional_score:
        blockers.append("directional_score_below_threshold")

    structure = analysis.get("market_structure") or {}
    if bias == "bullish":
        confirmed, direction = close > open_price and close > previous_high, "long"
        entry = ask
        support = structure.get("nearest_support_zone")
        stop = float(support["lower"]) if support else low
        stop -= max(0.0, float(structure.get("atr") or 0) * 0.10)
    elif bias == "bearish":
        confirmed, direction = close < open_price and close < previous_low, "short"
        entry = bid
        resistance = structure.get("nearest_resistance_zone")
        stop = float(resistance["upper"]) if resistance else high
        stop += max(0.0, float(structure.get("atr") or 0) * 0.10)
    else:
        confirmed, direction, entry, stop = False, None, 0.0, 0.0

    if not confirmed:
        blockers.append("completed_candle_breakout_confirmation_missing")
    if quote is not None and direction == "long" and entry < close:
        blockers.append("live_ask_fell_below_breakout_close")
    if quote is not None and direction == "short" and entry > close:
        blockers.append("live_bid_recovered_above_breakout_close")
    if blockers:
        return _blocked(blockers, details)

    risk = entry - stop if direction == "long" else stop - entry
    if not isfinite(risk) or risk <= 0:
        return _blocked(["invalid_stop_loss_geometry"], details)
    target = entry + risk * min_reward_risk if direction == "long" else entry - risk * min_reward_risk
    if target <= 0:
        return _blocked(["invalid_take_profit_geometry"], details)

    obstacle = structure.get("nearest_resistance_zone") if direction == "long" else structure.get("nearest_support_zone")
    if obstacle:
        obstacle_price = float(obstacle["lower"] if direction == "long" else obstacle["upper"])
        if (direction == "long" and entry < obstacle_price < target) or (
            direction == "short" and target < obstacle_price < entry
        ):
            return _blocked(["nearby_opposing_zone_limits_reward"], details)

    return {
        "status": "ready_for_manual_review",
        "entry_allowed": True,
        "direction": direction,
        "blockers": [],
        "plan": {
            "entry": round(entry, 6), "stop_loss": round(stop, 6),
            "take_profit": round(target, 6), "reward_risk": round(min_reward_risk, 2),
            "entry_reference": "ask" if direction == "long" else "bid",
            "source": source, "execution": "manual_only",
        },
        "details": {
            **details,
            "price_action_confirmation": "bullish_close_above_previous_high" if direction == "long" else "bearish_close_below_previous_low",
            "reference_check": "passed", "chart_calibration": "passed",
        },
        "note": "Candidate passed configured filters. Review risk and execution manually; no order was sent.",
    }
