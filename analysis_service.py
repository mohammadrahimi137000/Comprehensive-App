"""Application service joining a single trusted candle source to analysis."""
from __future__ import annotations

from analysis_engine import AnalysisEngine
from market_store import MarketStore
from structure_engine import analyze_structure
from analysis_brains import analyze_brains
from ml_engine import WalkForwardDirectionModel


class AnalysisService:
    def __init__(self, store: MarketStore | None = None,
                 engine: AnalysisEngine | None = None):
        self.store = store or MarketStore()
        self.engine = engine or AnalysisEngine(horizon_minutes=15)
        self.ml_model = WalkForwardDirectionModel()
        self.ml_model_path = self.store.database_path.parent / "ml_model.json"
        if self.ml_model_path.exists():
            try:
                self.ml_model.load(self.ml_model_path)
            except Exception:
                self.ml_model = WalkForwardDirectionModel()

    def analyze_latest(self, symbol: str, timeframe: str = "M1",
                       source: str | None = None, candle_limit: int = 500) -> dict:
        selected_source = source
        if selected_source is None:
            available = self.store.list_sources(symbol, timeframe)
            eligible = [item for item in available if item["candle_count"] >= 30]
            if not eligible:
                total = sum(item["candle_count"] for item in available)
                raise ValueError(
                    f"داده کافی از یک منبع مستقل وجود ندارد؛ حداقل ۳۰ کندل از یک منبع لازم است. مجموع منابع: {total}"
                )
            # Select one source only. Never concatenate different brokers/spot references
            # into one synthetic candle sequence.
            selected_source = eligible[0]["source"]

        candles = self.store.get_candles(
            symbol=symbol, timeframe=timeframe, limit=candle_limit,
            source=selected_source,
        )
        if len(candles) < 30:
            raise ValueError(
                f"داده کافی نیست: حداقل ۳۰ کندل کامل لازم است؛ فعلاً {len(candles)} کندل موجود است."
            )
        result = self.engine.analyze(candles)
        result["market_structure"] = analyze_structure(candles)
        result.update(analyze_brains(candles))
        metadata = getattr(self.ml_model, "metadata", {})
        if (self.ml_model.weights is not None
                and metadata.get("symbol") == symbol.strip().upper()
                and metadata.get("timeframe") == timeframe.strip().upper()
                and metadata.get("source") == selected_source):
            result["ml_prediction"] = self.ml_model.predict(candles)
        else:
            result["ml_prediction"] = {
                "status": "not_available",
                "reason": "No trained model matches this symbol, timeframe and data source.",
            }
        result["symbol"] = symbol.strip().upper()
        result["timeframe"] = timeframe.strip().upper()
        result["source"] = selected_source
        self.store.save_forecast(
            source="analysis_engine", symbol=symbol, timeframe=timeframe, payload=result
        )
        return result
