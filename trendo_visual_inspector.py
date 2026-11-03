"""Read-only visual OCR inspection of the visible Trendo window.

Captures pixels in memory only. It does not save screenshots, click, type, alter
fields, or submit orders. OCR findings are unverified visual candidates.
"""
from __future__ import annotations

import re
import sys
from collections import defaultdict
from typing import Any


ORDER_TERMS = (
    "order", "buy", "sell", "price", "volume", "lot", "stop", "loss",
    "take", "profit", "sl", "tp", "ثبت", "خرید", "فروش", "حد", "ضرر",
    "سود", "قیمت", "حجم",
)


def inspect_trendo_visual_ocr(
    hwnd: int,
    tesseract_path: str | None = None,
    languages: str = "eng",
    min_confidence: float = 20.0,
) -> dict[str, Any]:
    """OCR a visible Trendo window and return word boxes in screen coordinates."""
    if sys.platform != "win32":
        return {
            "status": "unsupported_platform", "hwnd": hwnd,
            "words": [], "order_related_words": [],
            "execution_enabled": False,
        }
    if not isinstance(hwnd, int) or hwnd <= 0:
        raise ValueError("A valid positive HWND is required")
    if not 0 <= float(min_confidence) <= 100:
        raise ValueError("min_confidence must be between 0 and 100")

    try:
        import pytesseract
        from screenshot_capture import capture_window_frame
    except ImportError as exc:
        return {
            "status": "dependency_missing", "hwnd": hwnd,
            "error": str(exc), "words": [],
            "order_related_words": [], "execution_enabled": False,
        }

    try:
        if tesseract_path:
            pytesseract.pytesseract.tesseract_cmd = str(tesseract_path)
        frame, (screen_left, screen_top) = capture_window_frame(hwnd)
        data = pytesseract.image_to_data(
            frame, lang=languages, output_type=pytesseract.Output.DICT,
            config="--oem 3 --psm 11",
        )
        words: list[dict[str, Any]] = []
        lines: dict[tuple[int, int, int], list[str]] = defaultdict(list)
        for i, raw_text in enumerate(data.get("text", [])):
            value = str(raw_text).strip()
            if not value:
                continue
            try:
                confidence = float(data["conf"][i])
            except (TypeError, ValueError, KeyError):
                confidence = -1.0
            if confidence < min_confidence:
                continue
            x, y = int(data["left"][i]), int(data["top"][i])
            width, height = int(data["width"][i]), int(data["height"][i])
            word = {
                "text": value[:160],
                "confidence": round(confidence, 1),
                "bounds_screen": {
                    "left": screen_left + x, "top": screen_top + y,
                    "right": screen_left + x + width,
                    "bottom": screen_top + y + height,
                },
                "bounds_window": {
                    "left": x, "top": y,
                    "right": x + width, "bottom": y + height,
                },
                "block_num": int(data.get("block_num", [0])[i]),
                "par_num": int(data.get("par_num", [0])[i]),
                "line_num": int(data.get("line_num", [0])[i]),
            }
            words.append(word)
            key = (word["block_num"], word["par_num"], word["line_num"])
            lines[key].append(value)

        line_items = [
            {"text": " ".join(parts), "candidate": any(
                term in " ".join(parts).casefold() for term in ORDER_TERMS
            )}
            for parts in lines.values()
        ]
        candidates = [
            word for word in words
            if any(term in word["text"].casefold() for term in ORDER_TERMS)
            or re.fullmatch(r"(?:\\d{1,6}(?:[.,]\\d{1,5})?|\\d+\\.\\d+)", word["text"])
        ]
        return {
            "status": "ocr_completed",
            "hwnd": hwnd,
            "capture": "visible_window_in_memory",
            "image_saved": False,
            "languages": languages,
            "min_confidence": min_confidence,
            "word_count": len(words),
            "words": words,
            "lines": line_items,
            "order_related_words": candidates,
            "interpretation_warning": (
                "OCR فقط متن احتمالی روی تصویر را استخراج می‌کند. هر نتیجه یک کاندیدای "
                "تأییدنشده است؛ مختصات یا متن OCR به‌تنهایی مجوز تعامل با فرم یا ثبت سفارش نیست."
            ),
            "execution_enabled": False,
            "execution_status": "blocked_unverified_ui",
            "message": (
                "تصویر فقط در حافظه پردازش شد؛ هیچ فایلی ذخیره نشد و هیچ کلیک، "
                "تغییر مقدار یا سفارش ارسالی انجام نشد."
            ),
        }
    except Exception as exc:
        return {
            "status": "ocr_error", "hwnd": hwnd,
            "error": f"{type(exc).__name__}: {exc}",
            "words": [], "order_related_words": [],
            "execution_enabled": False,
            "execution_status": "blocked_unverified_ui",
        }
