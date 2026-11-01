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


class ChartScanner(QThread):
    chart_found = Signal(dict)
    chart_lost = Signal()
    status_changed = Signal(str)

    def __init__(self, interval_seconds: float = 2.0, parent=None):
        super().__init__(parent)
        self.interval_seconds = max(0.5, float(interval_seconds))
        self._stop_event = threading.Event()
        self.last_found: tuple[int, str] | None = None
        self._own_pid = os.getpid()

    @staticmethod
    def analyze_image(image: np.ndarray) -> dict[str, Any]:
        """Detect repeated saturated candle-like columns in a BGR screenshot."""
        empty = {"is_chart": False, "confidence": 0.0, "candle_columns": 0}
        if image is None or image.size == 0 or image.ndim != 3:
            return empty

        height, width = image.shape[:2]
        if width < 300 or height < 180 or image.shape[2] < 3:
            return empty

        hsv = cv2.cvtColor(image[:, :, :3], cv2.COLOR_BGR2HSV)

        # Require both saturation and brightness. Without the V floor, some
        # dark neutral UI backgrounds fall into OpenCV's red hue interval.
        green = cv2.inRange(hsv, np.array([35, 65, 65]), np.array([95, 255, 255]))
        red_a = cv2.inRange(hsv, np.array([0, 70, 65]), np.array([12, 255, 255]))
        red_b = cv2.inRange(hsv, np.array([165, 70, 65]), np.array([180, 255, 255]))
        mask = cv2.bitwise_or(green, cv2.bitwise_or(red_a, red_b))
        mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, np.ones((2, 2), np.uint8))

        # Each candle should create a compact run of colored x-columns. A
        # minimum vertical pixel count rejects tiny icons and isolated labels.
        min_vertical_pixels = max(8, int(height * 0.04))
        active = np.count_nonzero(mask, axis=0) >= min_vertical_pixels

        runs: list[tuple[int, int]] = []
        start = None
        for x, is_active in enumerate(active):
            if is_active and start is None:
                start = x
            elif not is_active and start is not None:
                runs.append((start, x - 1))
                start = None
        if start is not None:
            runs.append((start, width - 1))

        max_run_width = max(18, int(width * 0.025))
        candle_runs = [(a, b) for a, b in runs if b - a + 1 <= max_run_width]
        if len(candle_runs) < 8:
            return empty

        centers = [(a + b) // 2 for a, b in candle_runs]
        spread = (centers[-1] - centers[0]) / max(1, width)
        # Repeated candle-like columns should occupy a meaningful horizontal
        # portion of the image, rather than one small colored toolbar cluster.
        if spread < 0.18:
            return empty

        count = len(centers)
        confidence = min(0.90, 0.35 + count / 45.0 + spread * 0.15)
        return {
            "is_chart": True,
            "confidence": round(confidence, 2),
            "candle_columns": count,
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
                found = None
                with mss.MSS() as screen:
                    virtual = screen.monitors[0]
                    for window in self.get_visible_windows():
                        region = self._intersection(window, virtual)
                        if region is None:
                            continue
                        frame = np.asarray(screen.grab(region))
                        frame = cv2.cvtColor(frame, cv2.COLOR_BGRA2BGR)
                        result = self.analyze_image(frame)
                        if result["is_chart"]:
                            found = {
                                **window,
                                "confidence": result["confidence"],
                                "candle_columns": result["candle_columns"],
                            }
                            break

                if found:
                    identity = (found["hwnd"], found["title"])
                    if identity != self.last_found:
                        self.chart_found.emit(found)
                    self.last_found = identity
                    self.status_changed.emit(
                        f"چارت احتمالی شناسایی شد: {found['title']} "
                        f"(اعتماد بصری {found['confidence']:.0%})"
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
