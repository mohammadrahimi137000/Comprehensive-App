import numpy as np

import chart_recognition


def synthetic_chart():
    image = np.zeros((360, 900, 3), dtype=np.uint8)
    image[:] = (24, 30, 42)
    for index in range(24):
        x = 35 + index * 34
        top = 65 + (index % 6) * 12
        bottom = top + 75 + (index % 4) * 8
        color = (40, 220, 70) if index % 2 else (30, 40, 230)
        image[max(20, top - 25):bottom + 25, x + 4:x + 7] = color
        image[top:bottom, x:x + 12] = color
    return image


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


def test_timeframe_detection_does_not_misread_15m_as_5m(monkeypatch):
    monkeypatch.setattr(chart_recognition, "_ocr", lambda image, tesseract_cmd=None: [])
    result = chart_recognition.recognize_chart(
        synthetic_chart(), window_title="TradingView XAUUSD 15m"
    )
    assert result["timeframe_minutes"] == 15


def test_never_claims_calibration_without_axis_labels(monkeypatch):
    monkeypatch.setattr(chart_recognition, "_ocr", lambda image, tesseract_cmd=None: [])
    result = chart_recognition.recognize_chart(
        synthetic_chart(), window_title="TradingView XAUUSD 1m"
    )
    assert result["symbol"] == "XAUUSD"
    assert result["calibrated"] is False
    assert result["price_axis"] is None
