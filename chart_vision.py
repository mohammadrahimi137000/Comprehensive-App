"""Pixel-space chart candidate extraction.

This produces geometry only. It does not convert pixels into OHLC prices;
price-axis calibration/OCR and symbol/timeframe recognition are separate tasks.
"""
from __future__ import annotations

import cv2
import numpy as np


def _candle_mask(image: np.ndarray) -> np.ndarray:
    hsv = cv2.cvtColor(image[:, :, :3], cv2.COLOR_BGR2HSV)
    green = cv2.inRange(hsv, np.array([35, 65, 65]), np.array([95, 255, 255]))
    red_a = cv2.inRange(hsv, np.array([0, 70, 65]), np.array([12, 255, 255]))
    red_b = cv2.inRange(hsv, np.array([165, 70, 65]), np.array([180, 255, 255]))
    mask = cv2.bitwise_or(green, cv2.bitwise_or(red_a, red_b))
    return cv2.morphologyEx(mask, cv2.MORPH_OPEN, np.ones((2, 2), np.uint8))


def extract_candle_geometry(image: np.ndarray) -> dict:
    """Return a candidate plot ROI and candle-like pixel bounds from a BGR image."""
    empty = {"is_chart": False, "roi": None, "candles": [], "confidence": 0.0}
    if image is None or not isinstance(image, np.ndarray) or image.ndim != 3:
        return empty
    height, width = image.shape[:2]
    if height < 180 or width < 300 or image.shape[2] < 3:
        return empty

    mask = _candle_mask(image)
    active = np.count_nonzero(mask, axis=0) >= max(8, int(height * 0.04))
    runs = []
    start = None
    for x, enabled in enumerate(active):
        if enabled and start is None:
            start = x
        elif not enabled and start is not None:
            runs.append((start, x))
            start = None
    if start is not None:
        runs.append((start, width))

    max_width = max(18, int(width * 0.025))
    runs = [(left, right) for left, right in runs if right - left <= max_width]
    if len(runs) < 8 or (runs[-1][0] - runs[0][0]) / width < 0.18:
        return empty

    candles = []
    for left, right in runs:
        crop = mask[:, left:right]
        ys, xs = np.where(crop > 0)
        if len(ys) < max(8, int(height * 0.04)):
            continue
        candles.append({
            "x": int((left + right - 1) / 2),
            "left": int(left), "right": int(right - 1),
            "top": int(ys.min()), "bottom": int(ys.max()),
            "pixel_count": int(len(ys)),
        })
    if len(candles) < 8:
        return empty

    roi = {
        "left": min(item["left"] for item in candles),
        "top": min(item["top"] for item in candles),
        "right": max(item["right"] for item in candles),
        "bottom": max(item["bottom"] for item in candles),
    }
    confidence = min(0.90, 0.35 + len(candles) / 45.0
                     + (roi["right"] - roi["left"]) / width * 0.15)
    return {
        "is_chart": True, "roi": roi, "candles": candles,
        "confidence": round(confidence, 2),
        "coordinate_system": "image_pixels",
    }
