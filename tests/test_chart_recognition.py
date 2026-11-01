import numpy as np

import chart_recognition
from tests.test_chart_vision import synthetic_chart


def test_ocr_axis_and_timeframe_enable_estimated_ohlc(monkeypatch):
    monkeypatch.setattr(chart_recognition, "_ocr", lambda image, tesseract_cmd=None: [
        {"text": "2010.0", "x": 860, "y": 25, "width": 35, "height": 12, "confidence": 90},
        {"text": "1990.0", "x": 860, "y": 320, "width": 35, "height": 12, "confidence": 90},
    ])
    result = chart_recognition.recognize_chart(
        synthetic_chart(), screen_origin=(100, 50), window_title="TradingView XAUUSD 1m"
    )
    assert result["symbol"] == "XAUUSD"
    assert result["timeframe_minutes"] == 1
    assert result["price_axis"]["price_at_top"] == 2010
    assert result["calibrated"] is True
    assert len(result["ohlc"]) >= 8
    assert all(row["high"] >= max(row["open"], row["close"]) for row in result["ohlc"])


def test_never_claims_calibration_without_axis_labels(monkeypatch):
    monkeypatch.setattr(chart_recognition, "_ocr", lambda image, tesseract_cmd=None: [])
    result = chart_recognition.recognize_chart(
        synthetic_chart(), window_title="TradingView XAUUSD 1m"
    )
    assert result["symbol"] == "XAUUSD"
    assert result["calibrated"] is False
    assert result["price_axis"] is None
