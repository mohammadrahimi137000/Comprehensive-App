"""Best-effort chart OCR and pixel-to-OHLC conversion.

OCR is optional and requires the Tesseract executable in addition to pytesseract.
No price mapping is returned unless two plausible, ordered axis labels are found.
"""
from __future__ import annotations

import re
from statistics import median

import cv2
import numpy as np

from chart_vision import _candle_mask, extract_candle_geometry

_SYMBOLS = ("XAUUSD", "GOLD", "EURUSD", "GBPUSD", "USDJPY", "BTCUSD", "ETHUSD")
_TIMEFRAMES = {
    "1M": 1, "1MIN": 1, "M1": 1, "5M": 5, "5MIN": 5, "M5": 5,
    "10M": 10, "10MIN": 10, "M10": 10, "15M": 15, "15MIN": 15, "M15": 15,
    "30M": 30, "30MIN": 30, "M30": 30, "1H": 60, "H1": 60,
    "2H": 120, "H2": 120, "4H": 240, "H4": 240, "1D": 1440, "D1": 1440,
}


def _number(text: str) -> float | None:
    cleaned = text.replace(",", "").replace(" ", "").replace("O", "0")
    match = re.fullmatch(r"[-+]?\d{1,7}(?:\.\d{1,6})?", cleaned)
    if not match:
        return None
    try:
        value = float(cleaned)
        return value if value > 0 else None
    except ValueError:
        return None


def _ocr(image: np.ndarray, tesseract_cmd: str | None = None) -> list[dict]:
    try:
        import pytesseract
        from pytesseract import Output
    except ImportError:
        return []
    if tesseract_cmd:
        pytesseract.pytesseract.tesseract_cmd = tesseract_cmd
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    data = pytesseract.image_to_data(
        gray, output_type=Output.DICT, config="--psm 11"
    )
    words = []
    for index, raw in enumerate(data.get("text", [])):
        text = str(raw).strip()
        if not text:
            continue
        words.append({
            "text": text,
            "x": int(data["left"][index]),
            "y": int(data["top"][index]),
            "width": int(data["width"][index]),
            "height": int(data["height"][index]),
            "confidence": float(data["conf"][index]) if str(data["conf"][index]).replace(".", "", 1).lstrip("-").isdigit() else -1,
        })
    return words


def recognize_chart(
    image: np.ndarray, screen_origin: tuple[int, int] = (0, 0),
    window_title: str = "", tesseract_cmd: str | None = None,
) -> dict:
    geometry = extract_candle_geometry(image)
    empty = {
        "is_chart": geometry["is_chart"], "geometry": geometry,
        "symbol": None, "timeframe": None, "price_axis": None,
        "ohlc": [], "calibrated": False, "ocr_available": False,
        "recognition_warnings": [],
    }
    if not geometry["is_chart"]:
        return empty

    warnings = []
    words = []
    try:
        words = _ocr(image, tesseract_cmd=tesseract_cmd)
    except Exception as exc:
        warnings.append(f"OCR unavailable: {type(exc).__name__}: {exc}")
    empty["ocr_available"] = bool(words)
    text = " ".join([window_title] + [word["text"] for word in words]).upper()
    compact = re.sub(r"[^A-Z0-9]", "", text)
    symbol = next((item for item in _SYMBOLS if item in compact), None)
    timeframe = None
    timeframe_minutes = None
    for raw, minutes in _TIMEFRAMES.items():
        if re.search(rf"(?<![A-Z0-9]){raw}(?![A-Z0-9])", text) or raw in compact:
            timeframe, timeframe_minutes = raw, minutes
            break

    roi = geometry["roi"]
    axis_words = []
    for word in words:
        center_x = word["x"] + word["width"] / 2
        if center_x < roi["right"] or center_x > image.shape[1] * 0.995:
            continue
        value = _number(word["text"])
        if value is not None and word["confidence"] >= 20:
            axis_words.append({"price": value, "y": word["y"] + word["height"] / 2,
                               "confidence": word["confidence"], "text": word["text"]})

    axis = None
    if len(axis_words) >= 2:
        axis_words.sort(key=lambda item: item["y"])
        # Use the most separated pair with a monotonic vertical-price relationship.
        top = axis_words[0]
        bottom = axis_words[-1]
        if top["price"] > bottom["price"] and bottom["y"] - top["y"] >= image.shape[0] * 0.15:
            spread = top["price"] - bottom["price"]
            if spread > 0:
                axis = {
                    "price_at_top": top["price"], "y_at_top": top["y"],
                    "price_at_bottom": bottom["price"], "y_at_bottom": bottom["y"],
                    "source": "tesseract_axis_labels",
                    "confidence": round(min(top["confidence"], bottom["confidence"]) / 100, 2),
                }
        if axis is None:
            warnings.append("Price-axis OCR labels were not sufficiently consistent.")
    else:
        warnings.append("At least two readable right-axis price labels are required.")

    candles = []
    if axis and timeframe_minutes:
        mask = _candle_mask(image)
        top_price, bottom_price = axis["price_at_top"], axis["price_at_bottom"]
        y_top, y_bottom = axis["y_at_top"], axis["y_at_bottom"]

        def price_at(y: float) -> float:
            return top_price + (y - y_top) * (bottom_price - top_price) / (y_bottom - y_top)

        for item in geometry["candles"]:
            left, right = item["left"], item["right"] + 1
            crop = mask[:, left:right]
            row_counts = np.count_nonzero(crop, axis=1)
            threshold = max(3, int((right - left) * 0.55))
            body_rows = np.where(row_counts >= threshold)[0]
            if len(body_rows) < 2:
                continue
            body_top, body_bottom = int(body_rows.min()), int(body_rows.max())
            full_top, full_bottom = item["top"], item["bottom"]
            center = image[max(0, body_top):body_bottom + 1, left:right, :3]
            green = int(np.count_nonzero((center[:, :, 1] > center[:, :, 2] * 1.15) &
                                         (center[:, :, 1] > center[:, :, 0] * 1.15)))
            red = int(np.count_nonzero((center[:, :, 2] > center[:, :, 1] * 1.15) &
                                       (center[:, :, 2] > center[:, :, 0] * 1.15)))
            if green == red:
                continue
            open_y, close_y = (body_bottom, body_top) if green > red else (body_top, body_bottom)
            candles.append({
                "x": item["x"] + screen_origin[0],
                "open": round(price_at(open_y + screen_origin[1]), 6) if False else round(price_at(open_y), 6),
                "high": round(price_at(full_top), 6),
                "low": round(price_at(full_bottom), 6),
                "close": round(price_at(close_y), 6),
                "volume": 0.0,
                "timestamp": None,
                "direction": "bullish" if green > red else "bearish",
                "source": "screen_ocr_estimate",
            })

    spacing = median([b["x"] - a["x"] for a, b in zip(geometry["candles"], geometry["candles"][1:])]) if len(geometry["candles"]) > 1 else None
    px_per_minute = spacing / timeframe_minutes if spacing and timeframe_minutes else None
    roi_screen = {
        "left": roi["left"] + screen_origin[0],
        "top": roi["top"] + screen_origin[1],
        "right": roi["right"] + screen_origin[0],
        "bottom": roi["bottom"] + screen_origin[1],
    }
    result = {
        **empty,
        "symbol": symbol, "timeframe": timeframe,
        "timeframe_minutes": timeframe_minutes,
        "price_axis": axis, "ohlc": candles,
        "calibrated": bool(axis and timeframe_minutes and px_per_minute and len(candles) >= 8),
        "pixels_per_minute": px_per_minute,
        "last_candle_x": geometry["candles"][-1]["x"] + screen_origin[0],
        "chart_roi_screen": roi_screen,
        "recognition_warnings": warnings,
        "ocr_word_count": len(words),
    }
    if not symbol:
        warnings.append("Symbol was not confidently recognized from title/OCR.")
    if not timeframe:
        warnings.append("Timeframe was not confidently recognized from title/OCR.")
    if not candles:
        warnings.append("Pixel candles could not be converted to OHLC; OCR calibration may be absent.")
    result["recognition_warnings"] = warnings
    return result
