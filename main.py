"""Desktop dashboard for the Comprehensive-App chart detection foundation."""
from __future__ import annotations

import json
import sys
import threading

from PySide6.QtCore import QObject, Qt, Signal
from PySide6.QtWidgets import (
    QApplication, QFrame, QHBoxLayout, QLabel, QMainWindow, QPushButton,
    QStackedWidget, QVBoxLayout, QWidget, QLineEdit, QComboBox, QPlainTextEdit,
    QTableWidget, QTableWidgetItem,
)

from auto_chart_detector import ChartScanner
from analysis_service import AnalysisService
from biquote_stream import BiQuoteSignalRClient
from live_market_pipeline import LiveMarketPipeline
from trade_journal import TradeJournal
from screenshot_capture import capture_window_screenshot


class FeedBridge(QObject):
    status_changed = Signal(str)
    quote_received = Signal(object)


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("برنامه جامع | تحلیل هوشمند بازار")
        self.resize(1400, 850)
        self.setMinimumSize(1050, 680)
        self.scanner = None
        self.analysis_service = AnalysisService()
        self.trade_journal = TradeJournal(self.analysis_service.store.database_path)
        self.current_chart_info = None
        self.market_pipeline = LiveMarketPipeline(store=self.analysis_service.store)
        self.feed_bridge = FeedBridge()
        self.feed_bridge.status_changed.connect(self._on_feed_status)
        self.feed_bridge.quote_received.connect(self._on_feed_quote)
        self.market_feed = BiQuoteSignalRClient(
            symbols=("XAUUSD",),
            on_quote=self._on_market_quote,
            on_status=self.feed_bridge.status_changed.emit,
        )
        self.feed_thread = None
        self._closing = False
        self._build_ui()
        self._start_scanner()
        self._start_market_feed()

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
            "گزارش عملکرد", "تنظیمات", "ژورنال معاملات",
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
        elif index == 2:
            note = QLabel(
                "تحلیل فقط روی کندل‌های ذخیره‌شده و معتبر اجرا می‌شود. "
                "در این نسخه هنوز فید زنده متصل نیست و خروجی، سیگنال آماده معامله نیست."
            )
            note.setWordWrap(True)
            note.setObjectName("muted")
            layout.addWidget(note)
            controls = QHBoxLayout()
            self.analysis_symbol = QLineEdit("XAUUSD")
            self.analysis_symbol.setPlaceholderText("نماد، مانند XAUUSD")
            self.analysis_timeframe = QComboBox()
            self.analysis_timeframe.addItems(["M1", "M5", "M15", "H1"])
            self.analysis_source = QComboBox()
            self.analysis_source.addItems(["همه منابع", "spot", "broker"])
            run_button = QPushButton("تحلیل آخرین کندل‌های ذخیره‌شده")
            run_button.clicked.connect(self._run_analysis)
            controls.addWidget(self.analysis_symbol)
            controls.addWidget(self.analysis_timeframe)
            controls.addWidget(self.analysis_source)
            controls.addWidget(run_button)
            layout.addLayout(controls)
            self.analysis_output = QPlainTextEdit()
            self.analysis_output.setReadOnly(True)
            self.analysis_output.setPlaceholderText("نتیجه تحلیل پس از وجود حداقل ۳۰ کندل نمایش داده می‌شود.")
            layout.addWidget(self.analysis_output, 1)

        elif index == 8:
            note = QLabel("ثبت دستی معاملات برای ژورنال و ارزیابی عملکرد؛ این بخش هیچ سفارشی به کارگزاری ارسال نمی‌کند.")
            note.setWordWrap(True)
            note.setObjectName("muted")
            layout.addWidget(note)
            row1 = QHBoxLayout()
            self.journal_symbol = QLineEdit("XAUUSD")
            self.journal_direction = QComboBox()
            self.journal_direction.addItems(["long", "short"])
            self.journal_entry = QLineEdit()
            self.journal_entry.setPlaceholderText("قیمت ورود")
            self.journal_stop = QLineEdit()
            self.journal_stop.setPlaceholderText("حد ضرر")
            self.journal_target = QLineEdit()
            self.journal_target.setPlaceholderText("حد سود (اختیاری)")
            for widget in (self.journal_symbol, self.journal_direction, self.journal_entry, self.journal_stop, self.journal_target):
                row1.addWidget(widget)
            layout.addLayout(row1)
            row2 = QHBoxLayout()
            self.journal_notes = QLineEdit()
            self.journal_notes.setPlaceholderText("یادداشت معامله")
            self.journal_screenshot = QLineEdit()
            self.journal_screenshot.setReadOnly(True)
            self.journal_screenshot.setPlaceholderText("مسیر تصویر چارت")
            capture_button = QPushButton("ذخیره تصویر پنجره چارت")
            capture_button.clicked.connect(self._capture_journal_screenshot)
            save_button = QPushButton("ثبت معامله")
            save_button.clicked.connect(self._save_journal_trade)
            row2.addWidget(self.journal_notes, 2)
            row2.addWidget(self.journal_screenshot, 2)
            row2.addWidget(capture_button)
            row2.addWidget(save_button)
            layout.addLayout(row2)
            close_row = QHBoxLayout()
            self.journal_exit = QLineEdit()
            self.journal_exit.setPlaceholderText("قیمت خروج برای معامله انتخاب‌شده")
            close_button = QPushButton("بستن معامله انتخاب‌شده")
            close_button.clicked.connect(self._close_journal_trade)
            close_row.addWidget(self.journal_exit)
            close_row.addWidget(close_button)
            layout.addLayout(close_row)
            self.journal_table = QTableWidget(0, 8)
            self.journal_table.setHorizontalHeaderLabels(["ID", "نماد", "جهت", "ورود", "حد ضرر", "حد سود", "وضعیت", "R"])
            self.journal_table.setEditTriggers(self.journal_table.EditTrigger.NoEditTriggers)
            layout.addWidget(self.journal_table, 1)
            self._refresh_journal()
        else:
            note = QLabel(
                "این بخش در نقشه راه قرار دارد. تا اتصال منبع داده معتبر و تکمیل "
                "موتور مربوطه، هیچ خروجی معاملاتی در این صفحه تولید نمی‌شود."
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




    def _refresh_journal(self):
        if not hasattr(self, "journal_table"):
            return
        rows = self.trade_journal.list_trades(limit=200)
        self.journal_table.setRowCount(len(rows))
        for row_index, record in enumerate(rows):
            values = [record["id"], record["symbol"], record["direction"],
                      record["entry_price"], record["stop_loss"],
                      record["take_profit"] if record["take_profit"] is not None else "",
                      record["status"],
                      record["outcome_r"] if record["outcome_r"] is not None else ""]
            for column, value in enumerate(values):
                self.journal_table.setItem(row_index, column, QTableWidgetItem(str(value)))

    def _capture_journal_screenshot(self):
        if not self.current_chart_info:
            self.chart_status.setText("ابتدا باید یک پنجره چارت شناسایی شود.")
            return
        try:
            path = capture_window_screenshot(self.current_chart_info["hwnd"])
            self.journal_screenshot.setText(path)
        except Exception as exc:
            self.journal_screenshot.setText(f"خطای تصویر: {exc}")

    def _save_journal_trade(self):
        try:
            target_text = self.journal_target.text().strip()
            self.trade_journal.create_trade(
                symbol=self.journal_symbol.text(),
                direction=self.journal_direction.currentText(),
                entry_price=float(self.journal_entry.text()),
                stop_loss=float(self.journal_stop.text()),
                take_profit=float(target_text) if target_text else None,
                screenshot_path=self.journal_screenshot.text().strip() or None,
                notes=self.journal_notes.text(),
            )
            self._refresh_journal()
            self.chart_status.setText("معامله در ژورنال محلی ثبت شد.")
        except Exception as exc:
            self.chart_status.setText(f"ثبت معامله ناموفق بود: {exc}")

    def _close_journal_trade(self):
        row = self.journal_table.currentRow()
        if row < 0:
            self.chart_status.setText("ابتدا یک معامله را از جدول انتخاب کنید.")
            return
        try:
            trade_id = int(self.journal_table.item(row, 0).text())
            outcome = self.trade_journal.close_trade(trade_id, float(self.journal_exit.text()))
            self._refresh_journal()
            self.chart_status.setText(f"معامله بسته شد؛ نتیجه: {outcome:+.2f}R")
        except Exception as exc:
            self.chart_status.setText(f"بستن معامله ناموفق بود: {exc}")

    def _start_market_feed(self):
        def connect_feed():
            try:
                self.market_feed.start()
                if self._closing:
                    self.market_feed.stop()
            except Exception as exc:
                self.feed_bridge.status_changed.emit(
                    f"اتصال فید ناموفق بود: {type(exc).__name__}: {exc}"
                )
        self.feed_thread = threading.Thread(
            target=connect_feed, name="BiQuoteSignalR", daemon=True
        )
        self.feed_thread.start()

    def _on_market_quote(self, quote):
        result = self.market_pipeline.on_quote(quote)
        if result.get("accepted"):
            self.feed_bridge.quote_received.emit(quote)
        else:
            self.feed_bridge.status_changed.emit(
                f"تیک رد شد: {result.get('reason', 'نامشخص')}"
            )

    def _on_feed_status(self, message):
        self.footer.setText(message)

    def _on_feed_quote(self, quote):
        self.symbol_value.setText(quote.instrument)
        self.footer.setText(
            f"{quote.source} | Bid: {quote.bid:.3f} | Ask: {quote.ask:.3f} "
            f"| Mid: {quote.mid:.3f} | ذخیره کندل‌های کامل در حال انجام است."
        )

    def _run_analysis(self):
        symbol = self.analysis_symbol.text().strip()
        timeframe = self.analysis_timeframe.currentText()
        source = self.analysis_source.currentText()
        if not symbol:
            self.analysis_output.setPlainText("لطفاً نماد را وارد کنید.")
            return
        if source == "همه منابع":
            source = None
        try:
            result = self.analysis_service.analyze_latest(
                symbol=symbol, timeframe=timeframe, source=source
            )
            self.analysis_output.setPlainText(json.dumps(
                result, ensure_ascii=False, indent=2
            ))
        except Exception as exc:
            self.analysis_output.setPlainText(str(exc))

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
        self.current_chart_info = info
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
        self.current_chart_info = None
        self.frame_value.setText("در انتظار")
        self.chart_status.setText("چارت قبلی دیگر در صفحه قابل شناسایی نیست.")

    def closeEvent(self, event):
        self._closing = True
        if self.scanner is not None:
            self.scanner.stop()
        if self.market_feed is not None:
            try:
                self.market_feed.stop()
            except Exception:
                pass
        if self.feed_thread is not None and self.feed_thread.is_alive():
            self.feed_thread.join(timeout=3.0)
        event.accept()


def main():
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
