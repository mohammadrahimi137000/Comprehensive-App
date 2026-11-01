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


def test_returns_separate_static_and_dynamic_structure():
    result = analyze_structure(sample())
    assert "static_support_zones" in result
    assert "static_resistance_zones" in result
    assert result["dynamic_support"] is not None
    assert result["dynamic_resistance"] is not None
    assert result["dynamic_support"]["points"] >= 2


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
