import pytest

from performance_engine import analyze_performance


def test_calculates_win_rate_expectancy_profit_factor_and_drawdown():
    result = analyze_performance([
        {"status": "closed", "closed_at": "2026-01-01", "outcome_r": 2.0},
        {"status": "closed", "closed_at": "2026-01-02", "outcome_r": -1.0},
        {"status": "closed", "closed_at": "2026-01-03", "outcome_r": 0.5},
        {"status": "open", "outcome_r": None},
    ])
    assert result["closed_trades"] == 3
    assert result["wins"] == 2
    assert result["losses"] == 1
    assert result["win_rate_pct"] == pytest.approx(66.67)
    assert result["expectancy_r"] == pytest.approx(0.5)
    assert result["profit_factor"] == pytest.approx(2.5)
    assert result["max_drawdown_r"] == pytest.approx(1.0)


def test_handles_empty_journal_and_no_losses():
    empty = analyze_performance([])
    assert empty["closed_trades"] == 0
    assert empty["profit_factor"] is None
    result = analyze_performance([
        {"status": "closed", "closed_at": "2026-01-01", "outcome_r": 1.5},
    ])
    assert result["profit_factor"] is None
    assert result["max_drawdown_r"] == 0
