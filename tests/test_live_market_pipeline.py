from datetime import datetime, timedelta, timezone

from feed_router import Quote
from live_market_pipeline import LiveMarketPipeline
from market_store import MarketStore


BASE = datetime(2026, 1, 1, tzinfo=timezone.utc)


def quote(seconds, price):
    return Quote(
        source="biquote", instrument="XAUUSD", market_type="broker",
        timestamp=BASE + timedelta(seconds=seconds),
        bid=price - 0.1, ask=price + 0.1,
    )


def test_pipeline_persists_completed_multi_timeframe_candles(tmp_path):
    store = MarketStore(tmp_path / "market.db")
    clock = {"now": BASE + timedelta(seconds=1)}
    pipeline = LiveMarketPipeline(
        store=store, now_provider=lambda: clock["now"],
    )
    assert pipeline.on_quote(quote(1, 2000))["accepted"] is True
    clock["now"] = BASE + timedelta(seconds=61)
    result = pipeline.on_quote(quote(61, 2001))
    assert result["saved"] == {"M1": 1}
    assert len(store.get_candles("XAUUSD", "M1", source="biquote")) == 1
    assert store.get_candles("XAUUSD", "M5", source="biquote") == []


def test_pipeline_rejects_stale_and_wrong_symbol_quotes(tmp_path):
    store = MarketStore(tmp_path / "market.db")
    clock = {"now": BASE + timedelta(seconds=1)}
    pipeline = LiveMarketPipeline(store=store, now_provider=lambda: clock["now"])
    stale = pipeline.on_quote(quote(-30, 2000))
    assert stale["accepted"] is False
    wrong = Quote("biquote", "EURUSD", "broker", BASE, 1.0, 1.1)
    assert pipeline.on_quote(wrong)["reason"] == "instrument_mismatch"
