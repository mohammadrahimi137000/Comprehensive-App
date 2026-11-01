"""Automatic chart-window scanner for Windows.

The scanner detects likely chart windows from visible desktop content. It does not
read OHLC data, identify symbols/timeframes, or generate trading signals.
Run this file directly for a console-based detection monitor, or import
ChartScanner from the main desktop application.
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
        """Return a conservative visual-candle heuristic result."""
        empty = {"is_chart": False, "confidence": 0.0, "candle_columns": 0}
        if image is None or image.size == 0 or image.ndim != 3:
            return empty

        height, width = image.shape[:2]
        if width < 300 or height < 180:
            return empty

        hsv = cv2.cvtColor(image, cv2.COLOR_BGR2HSV)
        green = cv2.inRange(hsv, np.array([35, 35, 35]), np.array([95, 255, 255]))
        red_a = cv2.inRange(hsv, np.array([0, 45, 40]), np.array([12, 255, 255]))
        red_b = cv2.inRange(hsv, np.array([165, 45, 40]), np.array([180, 255, 255]))
        mask = cv2.bitwise_or(green, cv2.bitwise_or(red_a, red_b))
        mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, np.ones((2, 2), np.uint8))

        # Project colored pixels onto the x-axis. This is less sensitive than
        # contour boxes to a candle body touching its own wick.
        active = np.count_nonzero(mask, axis=0) >= max(5, int(height * 0.025))
        columns = []
        run_start = None
        previous = None
        for x, is_active in enumerate(active):
            if is_active:
                if run_start is None:
                    run_start = x
                previous = x
            elif run_start is not None:
                if previous - run_start + 1 <= max(30, int(width * 0.035)):
                    columns.append((run_start + previous) // 2)
                run_start = None
                previous = None
        if run_start is not None and previous is not None:
            if previous - run_start + 1 <= max(30, int(width * 0.035)):
                columns.append((run_start + previous) // 2)

        if len(columns) < 8:
            return empty

        count = len(columns)
        spread = (columns[-1] - columns[0]) / max(1, width)
        is_chart = count >= 8 and spread >= 0.18
        confidence = min(0.95, 0.35 + count / 35) if is_chart else 0.0
        return {
            "is_chart": is_chart,
            "confidence": round(confidence, 2),
            "candle_columns": count,
        }

    def detect_candles(self, image: np.ndarray) -> bool:
        """Backward-compatible boolean detector API."""
        return bool(self.analyze_image(image)["is_chart"])

    def get_visible_windows(self) -> list[dict[str, Any]]:
        windows = []

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
                    "hwnd": int(hwnd),
                    "title": title,
                    "process_id": int(pid),
                    "left": left,
                    "top": top,
                    "right": right,
                    "bottom": bottom,
                    "width": right - left,
                    "height": bottom - top,
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
        return {
            "left": left,
            "top": top,
            "width": right - left,
            "height": bottom - top,
        }

    def run(self):
        self.status_changed.emit("در حال پایش پنجره‌های قابل مشاهده ویندوز…")
        while not self._stop_event.is_set():
            try:
                found = None
                # MSS 10+ exposes the supported context manager as MSS().
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
                    self.status_changed.emit(
                        "در حال جست‌وجو؛ هنوز چارت معتبری پیدا نشده است."
                    )
            except Exception as exc:
                self.status_changed.emit(f"خطای پایش چارت: {exc}")
            self._stop_event.wait(self.interval_seconds)

    def stop(self, timeout_ms: int = 5000):
        self._stop_event.set()
        if self.isRunning():
            self.wait(timeout_ms)


def main() -> int:
    """Run the detector independently and print status to the terminal."""
    app = QCoreApplication(sys.argv)
    scanner = ChartScanner(interval_seconds=2.0)
    scanner.status_changed.connect(lambda message: print(message, flush=True))
    scanner.chart_found.connect(
        lambda info: print(
            "CHART FOUND: "
            f"{info.get('title')} | confidence={info.get('confidence', 0):.0%} | "
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
