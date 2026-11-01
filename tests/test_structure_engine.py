import math

import pytest

from structure_engine import analyze_structure


def sample():
    rows = []
    for index in range(100):
        close = 2000 + math.sin(index / 3) * 0.03
        rows.append({
            "timestamp": index, "open": close,
            "high": close + 0.01, "low": close - 0.01,
            "close": close, "volume": 0,
        })
    return rows


def test_returns_separate_static_dynamic_and_swing_structure():
    result = analyze_structure(sample())
    assert "static_support_zones" in result
    assert "static_resistance_zones" in result
    assert result["dynamic_support"] is not None
    assert result["dynamic_resistance"] is not None
    assert result["dynamic_support"]["points"] >= 2
    assert result["swing_structure"]["trend"] in {"bullish", "bearish", "range_or_transition"}
    assert result["structure_break"]["type"] in {"BOS", "CHoCH", "none"}
    assert isinstance(result["liquidity_sweeps"], list)


def test_nearest_support_is_not_above_price_and_resistance_not_below():
    result = analyze_structure(sample())
    price = result["last_close"]
    support = result["nearest_support_zone"]
    resistance = result["nearest_resistance_zone"]
    if support:
        assert support["lower"] <= price
    if resistance:
        assert resistance["upper"] >= price


def test_overlap_zone_is_high_priority_but_not_standalone_signal():
    result = analyze_structure(sample())
    assert result["overlap_reaction_zones"]
    zone = result["overlap_reaction_zones"][0]
    assert zone["priority"] == "high"
    assert zone["standalone_signal"] is False
    assert zone["requires_confirmation"] is True


def test_rejects_insufficient_history_and_invalid_radius():
    with pytest.raises(ValueError, match="Not enough"):
        analyze_structure(sample()[:8])
    with pytest.raises(ValueError, match="positive"):
        analyze_structure(sample(), pivot_radius=0)
