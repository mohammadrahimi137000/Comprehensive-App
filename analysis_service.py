"""Application service joining the local candle store and analysis engine."""
from __future__ import annotations

from analysis_engine import AnalysisEngine
from market_store import MarketStore
from structure_engine import analyze_structure


class AnalysisService:
    def __init__(self, store: MarketStore | None = None,
                 engine: AnalysisEngine | None = None):
        self.store = store or MarketStore()
        self.engine = engine or AnalysisEngine(horizon_minutes=15)

    def analyze_latest(self, symbol: str, timeframe: str = "M1",
                       source: str | None = None, candle_limit: int = 500) -> dict:
        candles = self.store.get_candles(
            symbol=symbol, timeframe=timeframe, limit=candle_limit, source=source
        )
        if len(candles) < 30:
            raise ValueError(
                f"داده کافی نیست: حداقل ۳۰ کندل کامل لازم است؛ فعلاً {len(candles)} کندل موجود است."
            )
        result = self.engine.analyze(candles)
        result["market_structure"] = analyze_structure(candles)
        result["symbol"] = symbol.strip().upper()
        result["timeframe"] = timeframe.strip().upper()
        result["source"] = source
        self.store.save_forecast(
            source="analysis_engine", symbol=symbol, timeframe=timeframe, payload=result
        )
        return result
