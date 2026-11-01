from datetime import datetime, timezone

from history_bootstrap import HistoryBootstrapper
from market_store import MarketStore
from provider_clients import BiQuoteHistoryAdapter


def test_history_adapter_skips_open_bar_and_normalizes_closed_ohlc():
    payload = {
        "bars": [
            {"openTime": "2026-11-01T10:00:00Z", "open": 2000, "high": 2002,
             "low": 1999, "close": 2001, "volume": 0, "isOpen": False},
            {"openTime": "2026-11-01T11:00:00Z", "open": 2001, "high": 2003,
             "low": 2000, "close": 2002, "volume": 0, "isOpen": True},
        ]
    }
    adapter = BiQuoteHistoryAdapter(getter=lambda url, timeout: payload)
    result = adapter.get_candles("XAUUSD", "M1", 100)
    assert len(result) == 1
    assert result[0]["close"] == 2001
    assert result[0]["timestamp"].endswith("+00:00")


def test_bootstrap_persists_history_by_source_and_timeframe(tmp_path):
    store = MarketStore(tmp_path / "market.db")

    class FakeAdapter:
        name = "BiQuote OHLC"
        def get_candles(self, symbol, timeframe, limit):
            return [{
                "timestamp": f"2026-11-01T10:{i:02d}:00+00:00",
                "open": 2000, "high": 2001, "low": 1999, "close": 2000.5,
                "volume": 0,
            } for i in range(40)]

    bootstrapper = HistoryBootstrapper(
        store=store, adapter=FakeAdapter(), minimum_existing=30, limit=100
    )
    result = bootstrapper.bootstrap_if_needed()
    assert result["M1"]["status"] == "imported"
    assert len(store.get_candles("XAUUSD", "M1", 100, source="BiQuote OHLC")) == 40
