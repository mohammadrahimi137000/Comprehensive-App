"""Application service joining a single trusted candle source to analysis."""
from __future__ import annotations

from analysis_engine import AnalysisEngine
from market_store import MarketStore
from structure_engine import analyze_structure
from analysis_brains import analyze_brains
from ml_engine import WalkForwardDirectionModel


def _zone_distance(price: float, zone: dict) -> float:
    if zone["lower"] <= price <= zone["upper"]:
        return 0.0
    return min(abs(price - zone["lower"]), abs(price - zone["upper"]))


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
            selected_source = eligible[0]["source"]

        timeframe_key = timeframe.strip().upper()
        timeframe_minutes = {
            "M1": 1, "M2": 2, "M3": 3, "M5": 5, "M10": 10,
            "M15": 15, "M30": 30, "H1": 60, "H2": 120,
            "H4": 240, "D1": 1440,
        }.get(timeframe_key)
        if timeframe_minutes is None:
            raise ValueError(f"تایم‌فریم پشتیبانی نمی‌شود: {timeframe_key}")

        if selected_source:
            source_filter = selected_source.strip().lower()
            if source_filter in {"spot", "broker"}:
                available_sources = self.store.list_sources(symbol, timeframe_key)
                if source_filter == "spot":
                    matches = [item for item in available_sources
                               if any(tag in item["source"].lower()
                                      for tag in ("spot", "xaus", "corgano"))]
                else:
                    matches = [item for item in available_sources
                               if any(tag in item["source"].lower()
                                      for tag in ("biquote", "broker"))]
                if not matches:
                    raise ValueError(
                        f"هیچ منبع {'Spot' if source_filter == 'spot' else 'Broker'} "
                        f"برای {symbol} / {timeframe_key} موجود نیست."
                    )
                selected_source = matches[0]["source"]

        candles = self.store.get_candles(
            symbol=symbol, timeframe=timeframe_key, limit=candle_limit,
            source=selected_source,
        )
        if len(candles) < 30:
            raise ValueError(
                f"داده کافی نیست: حداقل ۳۰ کندل کامل لازم است؛ فعلاً {len(candles)} کندل موجود است."
            )

        result = self.engine.analyze(candles, timeframe_minutes=timeframe_minutes)
        structure = analyze_structure(candles)
        result["market_structure"] = structure
        result.update(analyze_brains(candles))

        # Use support/resistance zones rather than isolated pivot points. A
        # zone containing the latest price is a valid nearest reaction zone.
        price = float(result["last_close"])
        support_zone = structure["nearest_support_zone"]
        resistance_zone = structure["nearest_resistance_zone"]
        result["nearest_support"] = support_zone["center"] if support_zone else None
        result["nearest_resistance"] = resistance_zone["center"] if resistance_zone else None
        result["nearest_support_zone"] = support_zone
        result["nearest_resistance_zone"] = resistance_zone
        result["support_distance"] = round(_zone_distance(price, support_zone), 6) if support_zone else None
        result["resistance_distance"] = round(_zone_distance(price, resistance_zone), 6) if resistance_zone else None
        result["risk_reference"]["invalidation_level"] = (
            resistance_zone["upper"] if result["directional_bias"] == "bearish" and resistance_zone
            else support_zone["lower"] if support_zone else None
        )

        confluence, technical = result["confluence"], result["brains"]["technical"]
        bias = result["directional_bias"]
        result["analysis_alignment"] = {
            "forecast_bias": bias,
            "technical_direction": technical["direction"],
            "multi_brain_direction": confluence["direction"],
            "ema_trend_consistent": technical["ema_trend"] == result["indicators"]["trend"],
            "brains_disagree": confluence["disagreement"],
            "forecast_vs_confluence_conflict": (
                bias != "neutral" and confluence["direction"] != "neutral"
                and bias != confluence["direction"]
            ),
            "note": "Conflicting brains lower confidence; no single brain is an entry trigger.",
        }

        metadata = getattr(self.ml_model, "metadata", {})
        if (self.ml_model.weights is not None
                and metadata.get("symbol") == symbol.strip().upper()
                and metadata.get("timeframe") == timeframe_key
                and metadata.get("source") == selected_source):
            result["ml_prediction"] = self.ml_model.predict(candles)
        else:
            result["ml_prediction"] = {
                "status": "not_available",
                "reason": "No trained model matches this symbol, timeframe and data source.",
            }

        # Historical OHLC cannot prove a fresh quote, chart extraction, spread,
        # execution conditions or order-book confirmation. Never emit a trade.
        blockers = [
            "fresh_live_quote_not_verified",
            "chart_price_extraction_not_verified",
            "spread_and_execution_risk_not_verified",
            "price_action_entry_confirmation_required",
        ]
        if confluence["disagreement"] or result["analysis_alignment"]["forecast_vs_confluence_conflict"]:
            blockers.append("analysis_brains_conflict")
        result["entry_readiness"] = {
            "status": "no_trade", "entry_allowed": False, "blockers": blockers,
            "note": "Research analysis only; this service does not emit a tradable entry signal.",
        }
        result["forecast_quality"] = {
            "status": "heuristic_unvalidated",
            "probabilities_calibrated": False,
            "out_of_sample_calibration_available": False,
            "note": "Track forecasts against later completed candles before treating scores as probabilities.",
        }

        result["symbol"] = symbol.strip().upper()
        result["timeframe"] = timeframe_key
        result["source"] = selected_source
        self.store.save_forecast(
            source="analysis_engine", symbol=symbol, timeframe=timeframe, payload=result
        )
        return result
