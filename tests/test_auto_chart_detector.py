import numpy as np

from auto_chart_detector import ChartScanner


def make_candlestick_chart():
    image = np.zeros((360, 900, 3), dtype=np.uint8)
    image[:] = (24, 30, 42)
    for index in range(24):
        x = 35 + index * 34
        top = 65 + (index % 6) * 12
        bottom = top + 75 + (index % 4) * 8
        color = (40, 220, 70) if index % 2 else (30, 40, 230)
        # wick and body in BGR
        image[max(20, top - 25):bottom + 25, x + 4:x + 7] = color
        image[top:bottom, x:x + 12] = color
    return image


def test_detects_synthetic_candlestick_chart():
    result = ChartScanner.analyze_image(make_candlestick_chart())
    assert result["is_chart"] is True
    assert result["candle_columns"] >= 8
    assert 0 < result["confidence"] <= 1


def test_rejects_empty_and_small_images():
    assert ChartScanner.analyze_image(np.zeros((0, 0, 3), dtype=np.uint8))["is_chart"] is False
    assert ChartScanner.analyze_image(np.zeros((100, 200, 3), dtype=np.uint8))["is_chart"] is False


def test_rejects_plain_background():
    image = np.full((360, 900, 3), (25, 30, 40), dtype=np.uint8)
    assert ChartScanner.analyze_image(image)["is_chart"] is False



def test_rejects_microsoft_store_even_when_pixels_look_colorful():
    image = make_candlestick_chart()
    result = ChartScanner.analyze_image(image, window_title="Microsoft Store")
    assert result["is_chart"] is False
    assert result["reason"] == "excluded_non_trading_window"


def test_rejects_sparse_colorful_ui_elements():
    image = np.full((360, 900, 3), (24, 30, 42), dtype=np.uint8)
    # A small number of colorful product-tile-like columns must not qualify.
    for index in range(9):
        x = 30 + index * 90
        color = (40, 220, 70) if index % 2 else (30, 40, 230)
        image[70:280, x:x + 14] = color
    assert ChartScanner.analyze_image(image)["is_chart"] is False


def test_rejects_irregular_colored_columns():
    image = np.full((360, 900, 3), (24, 30, 42), dtype=np.uint8)
    positions = [20, 45, 110, 145, 260, 290, 470, 510, 720, 760, 850]
    for index, x in enumerate(positions):
        color = (40, 220, 70) if index % 2 else (30, 40, 230)
        image[65 + (index % 3) * 8:285, x:x + 8] = color
    assert ChartScanner.analyze_image(image)["is_chart"] is False



def make_alternate_palette_chart():
    image = np.full((360, 900, 3), (24, 30, 42), dtype=np.uint8)
    # Blue/orange palette used by some chart themes; deliberately not the
    # green/red palette from the original unit test.
    for index in range(16):
        x = 35 + index * 48
        top = 55 + (index % 5) * 13
        bottom = top + 90 + (index % 3) * 9
        color = (230, 150, 35) if index % 2 else (35, 180, 230)
        image[max(15, top - 22):bottom + 22, x + 4:x + 7] = color
        image[top:bottom, x:x + 12] = color
    return image


def test_detects_alternate_blue_orange_candle_palette():
    result = ChartScanner.analyze_image(make_alternate_palette_chart())
    assert result["is_chart"] is True
    assert result["candle_columns"] >= 8
