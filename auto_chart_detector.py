"""Automatic chart-window scanner for Windows.

This is a visual candidate detector, not a market-data or trading-signal engine.
Only visible desktop pixels can be inspected; covered/minimized windows and
hardware-accelerated surfaces may not be capturable in every application.
"""
from __future__ import annotations

import os
import sys
import threading
from typing import Any

import cv2
import mss
import numpy as np
import win32gui
import win32process
from PySide6.QtCore import QCoreApplication, QThread, Signal
from chart_vision import extract_candle_geometry


class ChartScanner(QThread):
    chart_found = Signal(dict)
    charts_updated = Signal(list)
    chart_lost = Signal()
    status_changed = Signal(str)

    def __init__(self, interval_seconds: float = 2.0, parent=None):
        super().__init__(parent)
        self.interval_seconds = max(0.5, float(interval_seconds))
        self._stop_event = threading.Event()
        self.last_found: tuple[int, str] | None = None
        self._own_pid = os.getpid()

    @staticmethod
    def analyze_image(
        image: np.ndarray, window_title: str = ""
    ) -> dict[str, Any]:
        """Conservative visual validation of a candlestick chart candidate."""
        empty = {
            "is_chart": False, "confidence": 0.0, "candle_columns": 0,
            "reason": "insufficient_chart_structure",
        }
        if image is None or not isinstance(image, np.ndarray) or image.size == 0:
            return empty
        if image.ndim != 3 or image.shape[2] < 3:
            return empty

        height, width = image.shape[:2]
        if width < 300 or height < 180:
            return empty

        # Shell/store windows are common false positives: colorful tiles and
        # product artwork can resemble candle columns at pixel level.
        normalized_title = " ".join(window_title.casefold().replace("_", " ").split())
        blocked_titles = (
            "microsoft store", "windows store", "start menu",
            "search", "windows widgets",
        )
        if any(token in normalized_title for token in blocked_titles):
            return {**empty, "reason": "excluded_non_trading_window"}

        # Use the shared geometry extractor, then validate candle spacing.
        # A handful of colored UI icons is not enough to qualify as a chart.
        geometry = extract_candle_geometry(image[:, :, :3])
        candles = geometry.get("candles", [])
        count = len(candles)
        if not geometry.get("is_chart") or count < 12:
            return {**empty, "candle_columns": count}

        centers = np.asarray([item["x"] for item in candles], dtype=float)
        gaps = np.diff(centers)
        if len(gaps) < 11 or np.any(gaps <= 0):
            return {**empty, "candle_columns": count}

        median_gap = float(np.median(gaps))
        if median_gap < max(3.0, width * 0.004) or median_gap > width * 0.12:
            return {**empty, "candle_columns": count}

        gap_cv = float(np.std(gaps) / max(1.0, np.mean(gaps)))
        spread = float((centers[-1] - centers[0]) / width)
        if gap_cv > 0.70 or spread < 0.25:
            return {**empty, "candle_columns": count}

        # Require repeated, reasonably evenly spaced price marks distributed
        # across the plot. Keep confidence conservative rather than promoting
        # weak candidates into the chart selector.
        regularity = max(0.0, 1.0 - gap_cv)
        confidence = min(
            0.96,
            0.45 + min(count, 30) / 100.0 + spread * 0.12
            + regularity * 0.12,
        )
        if confidence < 0.68:
            return {
                **empty, "candle_columns": count,
                "confidence": round(confidence, 2),
                "reason": "low_structural_confidence",
            }

        return {
            "is_chart": True,
            "confidence": round(confidence, 2),
            "candle_columns": count,
            "reason": "repeated_candle_geometry",
            "gap_cv": round(gap_cv, 3),
        }

    def detect_candles(self, image: np.ndarray) -> bool:
        return bool(self.analyze_image(image)["is_chart"])

    def get_visible_windows(self) -> list[dict[str, Any]]:
        windows: list[dict[str, Any]] = []

        def callback(hwnd, _):
            if not win32gui.IsWindowVisible(hwnd) or win32gui.IsIconic(hwnd):
                return
            title = win32gui.GetWindowText(hwnd).strip()
            if not title:
                return
            normalized_title = " ".join(title.casefold().split())
            if any(token in normalized_title for token in (
                "microsoft store", "windows store", "start menu",
                "windows widgets",
            )):
                return
            try:
                _, pid = win32process.GetWindowThreadProcessId(hwnd)
                if pid == self._own_pid:
                    return
                left, top, right, bottom = win32gui.GetWindowRect(hwnd)
                if right - left < 300 or bottom - top < 180:
                    return
                windows.append({
                    "hwnd": int(hwnd), "title": title, "process_id": int(pid),
                    "left": left, "top": top, "right": right, "bottom": bottom,
                    "width": right - left, "height": bottom - top,
                })
            except Exception:
                return

        win32gui.EnumWindows(callback, None)
        return windows

    @staticmethod
    def _intersection(window: dict, virtual: dict) -> dict | None:
        left = max(window["left"], virtual["left"])
        top = max(window["top"], virtual["top"])
        right = min(window["right"], virtual["left"] + virtual["width"])
        bottom = min(window["bottom"], virtual["top"] + virtual["height"])
        if right - left < 300 or bottom - top < 180:
            return None
        return {"left": left, "top": top, "width": right - left, "height": bottom - top}

    def run(self):
        self.status_changed.emit("در حال پایش پنجره‌های قابل مشاهده ویندوز…")
        while not self._stop_event.is_set():
            try:
                found = []
                seen_hwnds = set()
                with mss.MSS() as screen:
                    virtual = screen.monitors[0]
                    for window in self.get_visible_windows():
                        if window["hwnd"] in seen_hwnds:
                            continue
                        seen_hwnds.add(window["hwnd"])
                        region = self._intersection(window, virtual)
                        if region is None:
                            continue
                        frame = np.asarray(screen.grab(region))
                        frame = cv2.cvtColor(frame, cv2.COLOR_BGRA2BGR)
                        result = self.analyze_image(frame, window_title=window["title"])
                        if result["is_chart"]:
                            geometry = extract_candle_geometry(frame)
                            roi = geometry.get("roi")
                            chart_roi_screen = None
                            if roi:
                                chart_roi_screen = {
                                    "left": region["left"] + roi["left"],
                                    "top": region["top"] + roi["top"],
                                    "right": region["left"] + roi["right"],
                                    "bottom": region["top"] + roi["bottom"],
                                }
                            found.append({
                                **window,
                                "confidence": result["confidence"],
                                "candle_columns": result["candle_columns"],
                                "chart_roi_pixels": roi,
                                "chart_roi_screen": chart_roi_screen,
                            })

                self.charts_updated.emit(found)
                if found:
                    # EnumWindows returns topmost windows first. Keep that as the
                    # default selection while exposing every detected candidate.
                    primary = found[0]
                    identity = (primary["hwnd"], primary["title"])
                    if identity != self.last_found:
                        self.chart_found.emit(primary)
                    self.last_found = identity
                    names = "، ".join(item["title"] for item in found[:5])
                    self.status_changed.emit(
                        f"{len(found)} چارت احتمالی شناسایی شد: {names}"
                    )
                else:
                    if self.last_found is not None:
                        self.chart_lost.emit()
                    self.last_found = None
                    self.status_changed.emit("در حال جست‌وجو؛ هنوز چارت معتبری پیدا نشده است.")
            except Exception as exc:
                self.status_changed.emit(f"خطای پایش چارت: {exc}")
            self._stop_event.wait(self.interval_seconds)

    def stop(self, timeout_ms: int = 5000):
        self._stop_event.set()
        if self.isRunning():
            self.wait(timeout_ms)


def main() -> int:
    app = QCoreApplication(sys.argv)
    scanner = ChartScanner(interval_seconds=2.0)
    scanner.status_changed.connect(lambda message: print(message, flush=True))
    scanner.chart_found.connect(
        lambda info: print(
            f"CHART FOUND: {info.get('title')} | "
            f"confidence={info.get('confidence', 0):.0%} | "
            f"candle-like columns={info.get('candle_columns')}",
            flush=True,
        )
    )
    scanner.chart_lost.connect(
        lambda: print("CHART LOST: no chart candidate currently visible.", flush=True)
    )
    app.aboutToQuit.connect(scanner.stop)
    scanner.start()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
