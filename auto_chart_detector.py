
import sys
import time
import cv2
import mss
import numpy as np
import win32gui
import win32con

from PySide6.QtCore import QThread, Signal
from PySide6.QtWidgets import (
    QApplication,
    QWidget,
    QVBoxLayout,
    QLabel,
)


class ChartScanner(QThread):
    chart_found = Signal(str)
    chart_lost = Signal()
    status_changed = Signal(str)

    def __init__(self):
        super().__init__()
        self.running = True
        self.last_found = None

    def detect_candles(self, image):
        if image is None or image.size == 0:
            return False

        height, width = image.shape[:2]

        if width < 300 or height < 180:
            return False

        hsv = cv2.cvtColor(image, cv2.COLOR_BGR2HSV)

        # شناسایی رنگ‌های رایج کندل صعودی و نزولی
        green_mask = cv2.inRange(
            hsv,
            np.array([35, 35, 35]),
            np.array([95, 255, 255])
        )

        red_mask_1 = cv2.inRange(
            hsv,
            np.array([0, 45, 40]),
            np.array([12, 255, 255])
        )

        red_mask_2 = cv2.inRange(
            hsv,
            np.array([165, 45, 40]),
            np.array([180, 255, 255])
        )

        candle_mask = cv2.bitwise_or(
            green_mask,
            cv2.bitwise_or(red_mask_1, red_mask_2)
        )

        # حذف نویزهای کوچک
        candle_mask = cv2.morphologyEx(
            candle_mask,
            cv2.MORPH_OPEN,
            np.ones((2, 2), np.uint8)
        )

        contours, _ = cv2.findContours(
            candle_mask,
            cv2.RETR_EXTERNAL,
            cv2.CHAIN_APPROX_SIMPLE
        )

        candle_candidates = []

        for contour in contours:
            x, y, w, h = cv2.boundingRect(contour)

            if 2 <= w <= 25 and 5 <= h <= height * 0.7:
                candle_candidates.append((x, y, w, h))

        if len(candle_candidates) < 8:
            return False

        # تعداد نواحی رنگی در ستون‌های مختلف
        x_positions = sorted(
            item[0] + item[2] // 2
            for item in candle_candidates
        )

        distinct_positions = []

        for x in x_positions:
            if (
                not distinct_positions
                or x - distinct_positions[-1] > 3
            ):
                distinct_positions.append(x)

        return len(distinct_positions) >= 8

    def get_visible_windows(self):
        windows = []

        def callback(hwnd, _):
            if not win32gui.IsWindowVisible(hwnd):
                return

            if win32gui.IsIconic(hwnd):
                return

            title = win32gui.GetWindowText(hwnd).strip()

            if not title:
                return

            try:
                left, top, right, bottom = win32gui.GetWindowRect(hwnd)

                if right - left < 300 or bottom - top < 180:
                    return

                windows.append({
                    "hwnd": hwnd,
                    "title": title,
                    "left": left,
                    "top": top,
                    "width": right - left,
                    "height": bottom - top,
                })

            except Exception:
                pass

        win32gui.EnumWindows(callback, None)

        return windows

    def run(self):
        self.status_changed.emit("در حال جست‌وجوی خودکار چارت‌ها...")

        while self.running:
            try:
                found = None

                with mss.mss() as screen:
                    for window in self.get_visible_windows():

                        # پنجره خود برنامه را بررسی نکن
                        if "برنامه جامع" in window["title"]:
                            continue

                        left = max(0, window["left"])
                        top = max(0, window["top"])

                        monitor = {
                            "left": left,
                            "top": top,
                            "width": min(
                                window["width"],
                                screen.monitors[0]["width"] - left
                            ),
                            "height": min(
                                window["height"],
                                screen.monitors[0]["height"] - top
                            ),
                        }

                        if monitor["width"] < 300 or monitor["height"] < 180:
                            continue

                        raw = screen.grab(monitor)

                        image = np.array(raw)
                        image = cv2.cvtColor(
                            image,
                            cv2.COLOR_BGRA2BGR
                        )

                        if self.detect_candles(image):
                            found = window["title"]
                            break

                if found:
                    if found != self.last_found:
                        self.last_found = found
                        self.chart_found.emit(found)

                    self.status_changed.emit(
                        "چارت احتمالی شناسایی شد: " + found
                    )

                else:
                    if self.last_found is not None:
                        self.chart_lost.emit()

                    self.last_found = None
                    self.status_changed.emit(
                        "هنوز چارت معاملاتی شناسایی نشده است."
                    )

            except Exception as error:
                self.status_changed.emit(
                    "خطای تشخیص: " + str(error)
                )

            time.sleep(2)

    def stop(self):
        self.running = False
        self.wait()


class DetectorWindow(QWidget):
    def __init__(self):
        super().__init__()

        self.setWindowTitle("برنامه جامع | تشخیص خودکار چارت")
        self.resize(650, 300)

        self.setStyleSheet("""
            QWidget {
                background: #0b1120;
                color: white;
                font-family: Segoe UI;
            }

            QLabel {
                padding: 12px;
                font-size: 15px;
            }
        """)

        layout = QVBoxLayout(self)

        title = QLabel("موتور تشخیص خودکار چارت")
        title.setStyleSheet(
            "font-size: 23px; font-weight: bold; color: #67e8f9;"
        )

        self.status = QLabel("در حال آماده‌سازی...")
        self.result = QLabel("هنوز چارتی شناسایی نشده است.")

        layout.addWidget(title)
        layout.addWidget(self.status)
        layout.addWidget(self.result)

        self.scanner = ChartScanner()

        self.scanner.status_changed.connect(
            self.status.setText
        )

        self.scanner.chart_found.connect(
            self.on_chart_found
        )

        self.scanner.chart_lost.connect(
            self.on_chart_lost
        )

        self.scanner.start()

    def on_chart_found(self, title):
        self.result.setText(
            "چارت احتمالی شناسایی شد:\n" + title
        )

    def on_chart_lost(self):
        self.result.setText(
            "چارت دیگر شناسایی نمی‌شود."
        )

    def closeEvent(self, event):
        self.scanner.stop()
        event.accept()


if __name__ == "__main__":
    app = QApplication(sys.argv)

    window = DetectorWindow()
    window.show()

    sys.exit(app.exec())
