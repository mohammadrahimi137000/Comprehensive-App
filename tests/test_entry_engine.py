from datetime import datetime, timedelta, timezone

from entry_engine import evaluate_entry_readiness


def make_inputs(now=None):
    now = now or datetime.now(timezone.utc)
    candles = [
        {"timestamp": 1, "open": 99.8, "high": 100.2, "low": 99.5, "close": 100.0},
        {"timestamp": 2, "open": 100.0, "high": 102.0, "low": 99.8, "close": 101.8},
    ]
    analysis = {
        "symbol": "XAUUSD", "timeframe_minutes": 1, "directional_bias": "bullish",
        "scenarios": {"bullish": 72.0, "bearish": 18.0, "sideways": 10.0},
        "confluence": {"direction": "bullish", "disagreement": False, "active_brains": 4},
        "analysis_alignment": {"forecast_vs_confluence_conflict": False},
        "market_structure": {
            "atr": 1.0,
            "nearest_support_zone": {"lower": 99.0, "upper": 99.5},
            "nearest_resistance_zone": None,
        },
    }
    quote = {
        "timestamp": now, "instrument": "XAUUSD", "market_type": "broker",
        "bid": 101.8, "ask": 101.9, "is_simulated": False,
    }
    chart = {
        "calibrated": True, "symbol": "XAUUSD", "timeframe_minutes": 1,
        "captured_at": now.isoformat(),
    }
    reference = {"status": "compared", "comparisons": [{"broker_minus_reference_bps": 2.5}]}
    return candles, analysis, quote, chart, reference, now


def evaluate(inputs):
    candles, analysis, quote, chart, reference, now = inputs
    return evaluate_entry_readiness(
        candles, analysis, "BiQuote OHLC", quote, chart, reference, now=now
    )


def test_ready_manual_plan_requires_all_valid_confirmations():
    result = evaluate(make_inputs())
    assert result["status"] == "ready_for_manual_review"
    assert result["entry_allowed"] is True
    assert result["direction"] == "long"
    assert result["plan"]["entry_reference"] == "ask"
    assert result["plan"]["reward_risk"] == 1.5
    assert result["plan"]["execution"] == "manual_only"


def test_missing_live_quote_never_creates_entry():
    inputs = make_inputs()
    inputs = (*inputs[:2], None, *inputs[3:])
    result = evaluate(inputs)
    assert result["entry_allowed"] is False
    assert "fresh_live_broker_quote_missing" in result["blockers"]


def test_stale_quote_is_rejected():
    inputs = make_inputs()
    candles, analysis, quote, chart, reference, now = inputs
    quote["timestamp"] = now - timedelta(seconds=30)
    result = evaluate((candles, analysis, quote, chart, reference, now))
    assert "quote_stale_or_future" in result["blockers"]
    assert result["entry_allowed"] is False


def test_spot_candles_cannot_authorize_broker_entry():
    inputs = make_inputs()
    candles, analysis, quote, chart, reference, now = inputs
    result = evaluate_entry_readiness(
        candles, analysis, "XAUS spot reference", quote, chart, reference, now=now
    )
    assert "analysis_source_is_not_broker_ohlc" in result["blockers"]


def test_missing_independent_reference_blocks_entry():
    inputs = make_inputs()
    candles, analysis, quote, chart, _, now = inputs
    result = evaluate_entry_readiness(
        candles, analysis, "BiQuote OHLC", quote, chart, None, now=now
    )
    assert "independent_spot_reference_not_verified" in result["blockers"]


def test_price_action_confirmation_is_mandatory():
    inputs = make_inputs()
    candles, analysis, quote, chart, reference, now = inputs
    candles[-1]["close"] = 100.1
    result = evaluate((candles, analysis, quote, chart, reference, now))
    assert "completed_candle_breakout_confirmation_missing" in result["blockers"]


def test_reference_divergence_blocks_entry():
    inputs = make_inputs()
    candles, analysis, quote, chart, reference, now = inputs
    reference["comparisons"][0]["broker_minus_reference_bps"] = 60
    result = evaluate((candles, analysis, quote, chart, reference, now))
    assert "broker_spot_deviation_too_large" in result["blockers"]
