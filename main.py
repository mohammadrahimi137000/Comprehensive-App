
import sys
from PySide6.QtWidgets import (
    QApplication,
    QMainWindow,
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QFrame,
)
from PySide6.QtCore import Qt


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()

        self.setWindowTitle("برنامه جامع | تحلیل هوشمند بازار")
        self.resize(1400, 850)
        self.setMinimumSize(1100, 700)

        self.setStyleSheet("""
            QMainWindow {
                background-color: #0b1120;
            }

            QWidget {
                color: #e5e7eb;
                font-family: Segoe UI;
                font-size: 13px;
            }

            QFrame#sidebar {
                background-color: #111827;
                border-right: 1px solid #263244;
            }

            QFrame#panel {
                background-color: #151f30;
                border: 1px solid #26364b;
                border-radius: 12px;
            }

            QLabel#heading {
                font-size: 24px;
                font-weight: bold;
                color: #ffffff;
            }

            QLabel#muted {
                color: #94a3b8;
            }

            QPushButton {
                background-color: #1e293b;
                border: none;
                border-radius: 8px;
                padding: 12px;
                text-align: right;
            }

            QPushButton:hover {
                background-color: #334155;
            }

            QPushButton#active {
                background-color: #164e63;
                color: #67e8f9;
            }
        """)

        root = QWidget()
        self.setCentralWidget(root)

        main_layout = QHBoxLayout(root)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        sidebar = QFrame()
        sidebar.setObjectName("sidebar")
        sidebar.setFixedWidth(230)

        side_layout = QVBoxLayout(sidebar)
        side_layout.setContentsMargins(15, 25, 15, 20)

        logo = QLabel("برنامه جامع")
        logo.setAlignment(Qt.AlignmentFlag.AlignCenter)
        logo.setStyleSheet(
            "font-size: 25px; font-weight: bold; color: #67e8f9;"
        )

        subtitle = QLabel("SMART MARKET ANALYZER")
        subtitle.setAlignment(Qt.AlignmentFlag.AlignCenter)
        subtitle.setObjectName("muted")

        side_layout.addWidget(logo)
        side_layout.addWidget(subtitle)
        side_layout.addSpacing(35)

        menu_items = [
            "داشبورد اصلی",
            "تحلیل هوشمند چارت",
            "پیش‌بینی ۱۵ دقیقه آینده",
            "حمایت و مقاومت",
            "سناریوهای بازار",
            "تاریخچه پیش‌بینی‌ها",
            "گزارش عملکرد",
            "تنظیمات",
        ]

        for index, item in enumerate(menu_items):
            button = QPushButton(item)
            if index == 0:
                button.setObjectName("active")
            side_layout.addWidget(button)

        side_layout.addStretch()

        version = QLabel("نسخه اولیه | 1.0")
        version.setAlignment(Qt.AlignmentFlag.AlignCenter)
        version.setObjectName("muted")
        side_layout.addWidget(version)

        content = QWidget()
        content_layout = QVBoxLayout(content)
        content_layout.setContentsMargins(28, 25, 28, 25)
        content_layout.setSpacing(18)

        header = QHBoxLayout()

        title = QLabel("داشبورد تحلیل بازار")
        title.setObjectName("heading")

        market_status = QLabel("● سیستم آماده اجرا")
        market_status.setStyleSheet("color: #4ade80;")

        header.addWidget(title)
        header.addStretch()
        header.addWidget(market_status)

        content_layout.addLayout(header)

        description = QLabel(
            "تحلیل چندمنبعی بازار، تشخیص چارت و پیش‌بینی هوشمند قیمت"
        )
        description.setObjectName("muted")
        content_layout.addWidget(description)

        cards_layout = QHBoxLayout()
        cards_layout.setSpacing(15)

        card_data = [
            ("نماد معاملاتی", "در انتظار تشخیص"),
            ("تایم‌فریم", "در انتظار تشخیص"),
            ("وضعیت داده", "هنوز متصل نشده"),
        ]

        for heading, value in card_data:
            card = self.create_card(heading, value)
            cards_layout.addWidget(card)

        content_layout.addLayout(cards_layout)

        chart_panel = QFrame()
        chart_panel.setObjectName("panel")

        chart_layout = QVBoxLayout(chart_panel)
        chart_layout.setContentsMargins(20, 20, 20, 20)

        chart_title = QLabel("محیط نمایش نمودار و پیش‌بینی آینده")
        chart_title.setStyleSheet(
            "font-size: 18px; font-weight: bold;"
        )

        chart_placeholder = QLabel(
            "محل نمایش چارت اصلی و مسیر پیش‌بینی ۱۵ دقیقه آینده\n\n"
            "۱۵ نقطه پیش‌بینی | سناریوی صعودی و نزولی\n"
            "اهداف قیمتی | حمایت و مقاومت | محدوده عدم قطعیت"
        )

        chart_placeholder.setAlignment(Qt.AlignmentFlag.AlignCenter)
        chart_placeholder.setStyleSheet(
            "background-color: #0b1424;"
            "border: 1px dashed #475569;"
            "border-radius: 10px;"
            "color: #94a3b8;"
            "font-size: 16px;"
        )

        chart_layout.addWidget(chart_title)
        chart_layout.addSpacing(15)
        chart_layout.addWidget(chart_placeholder, 1)

        content_layout.addWidget(chart_panel, 1)

        footer = QLabel(
            "سیستم هنوز به منبع داده زنده متصل نشده است."
        )
        footer.setObjectName("muted")
        content_layout.addWidget(footer)

        main_layout.addWidget(sidebar)
        main_layout.addWidget(content, 1)

    def create_card(self, heading, value):
        card = QFrame()
        card.setObjectName("panel")

        layout = QVBoxLayout(card)
        layout.setContentsMargins(18, 18, 18, 18)

        title = QLabel(heading)
        title.setObjectName("muted")

        value_label = QLabel(value)
        value_label.setStyleSheet(
            "font-size: 17px; font-weight: bold; color: #67e8f9;"
        )

        layout.addWidget(title)
        layout.addWidget(value_label)

        return card


if __name__ == "__main__":
    app = QApplication(sys.argv)

    window = MainWindow()
    window.show()

    sys.exit(app.exec())
