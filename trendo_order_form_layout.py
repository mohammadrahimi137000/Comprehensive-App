"""Conservative, read-only layout interpretation for Trendo OCR results.

This module reports geometric candidates only. It never treats OCR text or
coordinates as verified controls and cannot enable order execution.
"""
from __future__ import annotations

import re
from typing import Any

_NUMERIC = re.compile(r"^[+-]?\d+(?:[.,]\d+)?$")
_TOKEN_CLEAN = re.compile(r"[^a-z0-9]+")

_LABELS = {
    "take_profit": ("take profit", "takeprofit", "tp"),
    "stop_loss": ("stop loss", "stoploss", "sl"),
    "volume": ("volume", "size", "lot"),
    "buy": ("buy",),
    "sell": ("sell",),
    "order_type": ("order type", "market execution", "pending"),
}


def _normalise(value: str) -> str:
    """Case-fold OCR text and discard punctuation such as the colon in Size:"""
    return " ".join(_TOKEN_CLEAN.sub(" ", value.casefold()).split())


def _center(bounds: dict[str, int]) -> tuple[float, float]:
    return (
        (bounds["left"] + bounds["right"]) / 2,
        (bounds["top"] + bounds["bottom"]) / 2,
    )


def _merge_bounds(words: list[dict[str, Any]]) -> dict[str, int]:
    boxes = [word["bounds_screen"] for word in words]
    return {
        "left": min(box["left"] for box in boxes),
        "top": min(box["top"] for box in boxes),
        "right": max(box["right"] for box in boxes),
        "bottom": max(box["bottom"] for box in boxes),
    }


def _label_groups(usable: list[dict[str, Any]], key: str) -> list[list[dict[str, Any]]]:
    """Find labels as complete OCR tokens, including labels split over words."""
    groups: list[list[dict[str, Any]]] = []
    normalised = [_normalise(word["text"]) for word in usable]

    if key in {"take_profit", "stop_loss"}:
        first, second = ("take", "profit") if key == "take_profit" else ("stop", "loss")
        for index in range(len(usable) - 1):
            a, b = usable[index], usable[index + 1]
            if normalised[index] != first or normalised[index + 1] != second:
                continue
            ax, ay = _center(a["bounds_screen"])
            bx, by = _center(b["bounds_screen"])
            if abs(ay - by) <= 30 and b["bounds_screen"]["left"] >= a["bounds_screen"]["left"]:
                groups.append([a, b])

    variants = {_normalise(variant) for variant in _LABELS[key]}
    for word, token in zip(usable, normalised):
        if token in variants:
            groups.append([word])

    # De-duplicate the same source word/group while retaining OCR order.
    unique: list[list[dict[str, Any]]] = []
    seen: set[tuple[int, ...]] = set()
    for group in groups:
        marker = tuple(id(word) for word in group)
        if marker not in seen:
            seen.add(marker)
            unique.append(group)
    return unique


def analyze_order_form_layout(ocr_report: dict[str, Any]) -> dict[str, Any]:
    """Return label/value geometry candidates from an OCR report."""
    words = ocr_report.get("words", [])
    usable = [
        word for word in words
        if isinstance(word, dict)
        and isinstance(word.get("text"), str)
        and isinstance(word.get("bounds_screen"), dict)
        and all(k in word["bounds_screen"] for k in ("left", "top", "right", "bottom"))
    ]
    numeric = [
        word for word in usable
        if _NUMERIC.fullmatch(word["text"].strip().replace(",", "."))
    ]

    labels: list[dict[str, Any]] = []
    for key in _LABELS:
        groups = _label_groups(usable, key)
        if not groups:
            continue

        # Keep each distinct label occurrence. For split labels, use the union
        # of both word boxes instead of assuming their order elsewhere in OCR.
        for selected in groups:
            bounds = _merge_bounds(selected)
            lx, ly = _center(bounds)
            nearby = []
            for value in numeric:
                vb = value["bounds_screen"]
                vx, vy = _center(vb)
                dy = abs(vy - ly)
                dx = vx - bounds["right"]
                # Numeric value must be to the right and on the same visual row.
                if dx >= 0 and dy <= max(30, (bounds["bottom"] - bounds["top"]) * 1.5):
                    nearby.append((dy, dx, value))
            nearby.sort(key=lambda item: (item[0], item[1]))
            candidate = nearby[0][2] if nearby else None
            labels.append({
                "field": key,
                "label_text": " ".join(word["text"] for word in selected),
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
