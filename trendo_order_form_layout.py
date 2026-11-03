"""Conservative, read-only layout interpretation for Trendo OCR results.

This module reports geometric candidates only. It never treats OCR text or
coordinates as verified controls and cannot enable order execution.
"""
from __future__ import annotations

import re
from typing import Any

_NUMERIC = re.compile(r"^[+-]?\\d+(?:[.,]\\d+)?$")
_LABELS = {
    "take_profit": ("take profit", "takeprofit", "tp"),
    "stop_loss": ("stop loss", "stoploss", "sl"),
    "volume": ("volume", "size", "lot"),
    "buy": ("buy",),
    "sell": ("sell",),
    "order_type": ("order type", "market execution", "pending"),
}


def _center(bounds: dict[str, int]) -> tuple[float, float]:
    return (
        (bounds["left"] + bounds["right"]) / 2,
        (bounds["top"] + bounds["bottom"]) / 2,
    )


def analyze_order_form_layout(ocr_report: dict[str, Any]) -> dict[str, Any]:
    """Return label/value geometry candidates from an OCR report."""
    words = ocr_report.get("words", [])
    usable = [
        word for word in words
        if isinstance(word, dict)
        and isinstance(word.get("text"), str)
        and isinstance(word.get("bounds_screen"), dict)
    ]
    numeric = [
        word for word in usable
        if _NUMERIC.fullmatch(word["text"].strip().replace(",", "."))
    ]

    labels: list[dict[str, Any]] = []
    for key, variants in _LABELS.items():
        matching = [
            word for word in usable
            if word["text"].strip().casefold() in variants
        ]
        if key in {"take_profit", "stop_loss"}:
            # OCR often splits these two-word labels into separate words.
            lines = ocr_report.get("lines", [])
            matching_lines = [
                line for line in lines
                if any(v in str(line.get("text", "")).casefold() for v in variants)
            ]
            for line in matching_lines:
                text = str(line.get("text", "")).casefold()
                if key == "take_profit" and ("take" in text and "profit" in text):
                    matching = [w for w in usable if w["text"].casefold() in {"take", "profit"}]
                if key == "stop_loss" and ("stop" in text and "loss" in text):
                    matching = [w for w in usable if w["text"].casefold() in {"stop", "loss"}]
        if not matching:
            continue
        # Use the first occurrence; retain all source word boxes for auditability.
        selected = matching[:2] if key in {"take_profit", "stop_loss"} else matching[:1]
        boxes = [w["bounds_screen"] for w in selected]
        bounds = {
            "left": min(b["left"] for b in boxes),
            "top": min(b["top"] for b in boxes),
            "right": max(b["right"] for b in boxes),
            "bottom": max(b["bottom"] for b in boxes),
        }
        lx, ly = _center(bounds)
        nearby = []
        for value in numeric:
            vb = value["bounds_screen"]
            vx, vy = _center(vb)
            dy = abs(vy - ly)
            dx = vx - lx
            if dx >= 0 and dy <= 55:
                nearby.append((dy + dx * 0.001, value))
        nearby.sort(key=lambda item: item[0])
        candidate = nearby[0][1] if nearby else None
        labels.append({
            "field": key,
            "label_text": " ".join(w["text"] for w in selected),
            "label_bounds_screen": bounds,
            "value_candidate": candidate["text"] if candidate else None,
            "value_bounds_screen": candidate["bounds_screen"] if candidate else None,
            "value_confidence": candidate.get("confidence") if candidate else None,
            "candidate_verified": False,
            "reason": (
                "nearest_numeric_token_on_same_visual_row"
                if candidate else "no_numeric_token_aligned_with_label"
            ),
        })

    detected_fields = {item["field"] for item in labels}
    return {
        "status": "layout_candidates_only",
        "fields": labels,
        "detected_labels": sorted(detected_fields),
        "missing_labels": sorted(set(_LABELS) - detected_fields),
        "buy_sell": {
            "buy_detected": "buy" in detected_fields,
            "sell_detected": "sell" in detected_fields,
            "verified": False,
        },
        "limitations": [
            "OCR label/value associations are geometric candidates, not verified input controls.",
            "A numeric token may belong to another chart element or display.",
            "No field was focused, changed, clicked, or submitted.",
        ],
        "execution_enabled": False,
        "execution_status": "blocked_unverified_ui",
    }
