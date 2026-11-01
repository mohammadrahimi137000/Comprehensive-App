import numpy as np

from chart_vision import extract_candle_geometry


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


def test_extracts_candle_pixel_geometry():
    result = extract_candle_geometry(synthetic_chart())
    assert result["is_chart"] is True
    assert len(result["candles"]) >= 8
    assert result["roi"]["left"] < result["roi"]["right"]
    assert result["coordinate_system"] == "image_pixels"
    assert all(candle["top"] < candle["bottom"] for candle in result["candles"])


def test_rejects_non_chart_image():
    image = np.full((360, 900, 3), (25, 30, 40), dtype=np.uint8)
    result = extract_candle_geometry(image)
    assert result["is_chart"] is False
    assert result["candles"] == []


def test_rejects_invalid_or_small_input():
    assert extract_candle_geometry(None)["is_chart"] is False
    assert extract_candle_geometry(np.zeros((100, 200, 3), dtype=np.uint8))["is_chart"] is False
