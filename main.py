"""Desktop dashboard for the Comprehensive-App chart detection foundation."""
from __future__ import annotations

import sys

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QApplication, QFrame, QHBoxLayout, QLabel, QMainWindow, QPushButton,
    QStackedWidget, QVBoxLayout, QWidget,
)

from auto_chart_detector import ChartScanner


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("برنامه جامع | تحلیل هوشمند بازار")
        self.resize(1400, 850)
        self.setMinimumSize(1050, 680)
        self.scanner = None
        self._build_ui()
        self._start_scanner()

    def _build_ui(self):
        self.setStyleSheet("""
            QMainWindow, QWidget { background:#0b1120; color:#e5e7eb; font-family:Segoe UI; font-size:13px; }
            QFrame#sidebar { background:#111827; border-right:1px solid #263244; }
            QFrame#panel { background:#151f30; border:1px solid #26364b; border-radius:12px; }
            QLabel#heading { font-size:24px; font-weight:700; color:#fff; }
            QLabel#muted { color:#94a3b8; }
            QPushButton { background:#1e293b; border:0; border-radius:8px; padding:12px; text-align:right; }
            QPushButton:hover, QPushButton[active="true"] { background:#164e63; color:#67e8f9; }
        """)
        root = QWidget()
        self.setCentralWidget(root)
        outer = QHBoxLayout(root)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        sidebar = QFrame()
        sidebar.setObjectName("sidebar")
        sidebar.setFixedWidth(235)
        side = QVBoxLayout(sidebar)
        side.setContentsMargins(15, 25, 15, 20)
        logo = QLabel("برنامه جامع")
        logo.setAlignment(Qt.AlignmentFlag.AlignCenter)
        logo.setStyleSheet("font-size:25px;font-weight:bold;color:#67e8f9;")
        sub = QLabel("SMART MARKET ANALYZER")
        sub.setObjectName("muted")
        sub.setAlignment(Qt.AlignmentFlag.AlignCenter)
        side.addWidget(logo)
        side.addWidget(sub)
        side.addSpacing(28)

        self.pages = QStackedWidget()
        self.nav_buttons = []
        menu = [
            "داشبورد اصلی", "تشخیص خودکار چارت", "پیش‌بینی ۱۵ دقیقه آینده",
            "حمایت و مقاومت", "سناریوهای بازار", "تاریخچه پیش‌بینی‌ها",
            "گزارش عملکرد", "تنظیمات",
        ]
        for index, name in enumerate(menu):
            button = QPushButton(name)
            button.setProperty("active", index == 0)
            button.clicked.connect(lambda checked=False, i=index: self._show_page(i))
            side.addWidget(button)
            self.nav_buttons.append(button)
            self.pages.addWidget(self._make_page(name, index))
        side.addStretch()
        version = QLabel("نسخه پایه توسعه | 1.1")
        version.setObjectName("muted")
        version.setAlignment(Qt.AlignmentFlag.AlignCenter)
        side.addWidget(version)

        content = QWidget()
        content_layout = QVBoxLayout(content)
        content_layout.setContentsMargins(28, 25, 28, 25)
        content_layout.addWidget(self.pages, 1)
        outer.addWidget(sidebar)
        outer.addWidget(content, 1)

    def _make_page(self, name: str, index: int) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        title = QLabel(name)
        title.setObjectName("heading")
        layout.addWidget(title)
        if index == 0:
            description = QLabel(
                "پایش خودکار پنجره‌های معاملاتی و آماده‌سازی زیرساخت تحلیل بازار"
            )
            description.setObjectName("muted")
            layout.addWidget(description)
            cards = QHBoxLayout()
            self.symbol_value = self._card(cards, "نماد معاملاتی", "هنوز تشخیص داده نشده")
            self.frame_value = self._card(cards, "پنجره شناسایی‌شده", "در انتظار")
            self.data_value = self._card(cards, "وضعیت موتور", "در حال راه‌اندازی")
            layout.addLayout(cards)
            panel = QFrame()
            panel.setObjectName("panel")
            panel_layout = QVBoxLayout(panel)
            self.chart_status = QLabel("موتور تشخیص در حال شروع است…")
            self.chart_status.setWordWrap(True)
            self.chart_status.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self.chart_status.setStyleSheet(
                "font-size:17px;color:#94a3b8;padding:30px;"
            )
            panel_layout.addWidget(self.chart_status, 1)
            layout.addWidget(panel, 1)
            self.footer = QLabel(
                "تشخیص بصری چارت فعال می‌شود؛ هنوز داده قیمت یا تحلیل معاملاتی متصل نیست."
            )
            self.footer.setObjectName("muted")
            layout.addWidget(self.footer)
        elif index == 1:
            info = QLabel(
                "این بخش پنجره‌های قابل مشاهده را به‌صورت خودکار پایش می‌کند. "
                "نتیجه فعلی فقط تشخیص بصری احتمالی است."
            )
            info.setWordWrap(True)
            info.setObjectName("muted")
            layout.addWidget(info)
            self.detector_result = QLabel("در انتظار شناسایی پنجره…")
            self.detector_result.setWordWrap(True)
            self.detector_result.setObjectName("panel")
            self.detector_result.setStyleSheet("padding:24px;font-size:16px;")
            layout.addWidget(self.detector_result)
        else:
            note = QLabel(
                "این بخش در نقشه راه قرار دارد و تا اتصال داده بازار و موتور تحلیل، "
                "خروجی معاملاتی تولید نمی‌کند."
            )
            note.setWordWrap(True)
            note.setObjectName("muted")
            layout.addWidget(note)
            layout.addStretch()
        layout.addStretch(1)
        return page

    @staticmethod
    def _card(parent_layout, heading, value):
        card = QFrame()
        card.setObjectName("panel")
        box = QVBoxLayout(card)
        label = QLabel(heading)
        label.setObjectName("muted")
        value_label = QLabel(value)
        value_label.setStyleSheet("font-size:16px;font-weight:bold;color:#67e8f9;")
        value_label.setWordWrap(True)
        box.addWidget(label)
        box.addWidget(value_label)
        parent_layout.addWidget(card)
        return value_label

    def _show_page(self, index):
        self.pages.setCurrentIndex(index)
        for i, button in enumerate(self.nav_buttons):
            button.setProperty("active", i == index)
            button.style().unpolish(button)
            button.style().polish(button)

    def _start_scanner(self):
        # The first positional parameter is the scan interval, not the Qt parent.
        self.scanner = ChartScanner(parent=self)
        self.scanner.status_changed.connect(self._on_status)
        self.scanner.chart_found.connect(self._on_chart_found)
        self.scanner.chart_lost.connect(self._on_chart_lost)
        self.scanner.start()

    def _on_status(self, message):
        self.data_value.setText("فعال" if "خطای" not in message else "دارای خطا")
        self.chart_status.setText(message)

    def _on_chart_found(self, info):
        title = info.get("title", "پنجره ناشناس")
        confidence = info.get("confidence", 0)
        details = (
            f"{title}\nشناسه پنجره: {info.get('hwnd')} | "
            f"PID: {info.get('process_id')}\n"
            f"اعتماد بصری: {confidence:.0%} | "
            f"ستون‌های شبیه کندل: {info.get('candle_columns')}"
        )
        self.frame_value.setText(title)
        self.symbol_value.setText("از روی تصویر قابل تأیید نیست")
        self.chart_status.setText(
            "چارت احتمالی شناسایی شد. این نتیجه هنوز تأیید نماد یا سیگنال نیست."
        )
        self.detector_result.setText(details)
        self.footer.setText(
            "پنجره پیدا شد؛ استخراج قیمت، تایم‌فریم و تولید پیش‌بینی هنوز پیاده‌سازی نشده است."
        )

    def _on_chart_lost(self):
        self.frame_value.setText("در انتظار")
        self.chart_status.setText("چارت قبلی دیگر در صفحه قابل شناسایی نیست.")

    def closeEvent(self, event):
        if self.scanner is not None:
            self.scanner.stop()
        event.accept()


def main():
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
