"""Desktop dashboard for the Comprehensive-App chart detection foundation."""
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
import threading

import win32gui

from PySide6.QtCore import QObject, Qt, Signal, QTimer
from PySide6.QtWidgets import (
    QApplication, QFrame, QHBoxLayout, QLabel, QMainWindow, QPushButton,
    QStackedWidget, QVBoxLayout, QWidget, QLineEdit, QComboBox, QPlainTextEdit,
    QTableWidget, QTableWidgetItem,
)

from auto_chart_detector import ChartScanner
from analysis_service import AnalysisService
from resilient_feed import ResilientBiQuoteFeed
from live_market_pipeline import LiveMarketPipeline
from trade_journal import TradeJournal
from screenshot_capture import capture_window_screenshot, capture_window_frame
from performance_engine import analyze_performance
from chart_recognition import recognize_chart
from chart_projection import ChartProjection
from forecast_overlay import ForecastOverlay
from tick_flow import TickPressure
from news_engine import RssNewsClient, BiQuoteContextClient
from reference_monitor import SpotReferenceMonitor
from history_bootstrap import HistoryBootstrapper
from trendo_connector import (
    discover_trendo_windows, connection_report, inspect_trendo_controls,
    parse_trendo_positions,
)
from trendo_uia_inspector import inspect_trendo_window_detailed
from trendo_visual_inspector import inspect_trendo_visual_ocr
from trendo_order_form_layout import analyze_order_form_layout

from trendo_order_bridge import inspect_order_form_controls

class FeedBridge(QObject):
    status_changed = Signal(str)
    quote_received = Signal(object)
    reference_received = Signal(object)


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("برنامه جامع | تحلیل هوشمند بازار")
        self.resize(1400, 850)
        self.setMinimumSize(1050, 680)
        self.scanner = None
        self.analysis_service = AnalysisService()
        self.trade_journal = TradeJournal(self.analysis_service.store.database_path)
        self.feed_bridge = FeedBridge()
        self.feed_bridge.status_changed.connect(self._on_feed_status)
        self.feed_bridge.quote_received.connect(self._on_feed_quote)
        self.feed_bridge.reference_received.connect(self._on_reference_result)
        self.current_chart_info = None
        self.detected_charts = {}
        self.latest_accepted_quote = None
        self.latest_reference_result = None
        self.market_pipeline = LiveMarketPipeline(store=self.analysis_service.store)
        self.history_bootstrapper = HistoryBootstrapper(
            store=self.analysis_service.store,
            on_status=self.feed_bridge.status_changed.emit,
        )
        self.ml_model = self.analysis_service.ml_model
        self.tick_pressure = TickPressure()
        self.latest_tick_pressure = self.tick_pressure.snapshot()
        self.news_client = RssNewsClient()
        self.biquote_context = BiQuoteContextClient()
        self.overlay = ForecastOverlay()
        self.ocr_tesseract_path = ""
        self.market_feed = ResilientBiQuoteFeed(
            symbols=("XAUUSD",),
            on_quote=self._on_market_quote,
            on_status=self.feed_bridge.status_changed.emit,
        )
        self.reference_monitor = SpotReferenceMonitor(
            latest_broker_quote=lambda: self.latest_accepted_quote,
            on_result=self.feed_bridge.reference_received.emit,
            on_status=self.feed_bridge.status_changed.emit,
        )
        self.feed_thread = None
        self._closing = False
        self._build_ui()
        self._start_scanner()
        self._start_market_feed()
        self.overlay_timer = QTimer(self)
        self.overlay_timer.timeout.connect(self._refresh_current_overlay)
        self.overlay_timer.start(60_000)

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
            "گزارش عملکرد", "تنظیمات", "ژورنال معاملات", "اتصال Trendo",
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
            self.chart_selector = QComboBox()
            self.chart_selector.setPlaceholderText("انتخاب چارت شناسایی‌شده")
            self.chart_selector.currentIndexChanged.connect(self._select_detected_chart)
            layout.addWidget(self.chart_selector)
            self.footer = QLabel(
                "تشخیص بصری چارت فعال است؛ داده قیمت مستقل و تحلیل پژوهشی جداگانه بررسی می‌شوند."
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
                "تحلیل روی کندل‌های کامل ذخیره‌شده اجرا می‌شود؛ فید زنده و مرجع‌های مستقل "
                "به‌صورت جداگانه پایش می‌شوند. خروجی پژوهشی است و سیگنال آماده معامله نیست."
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



        elif index == 3:
            note = QLabel("زون‌های استاتیک و خطوط داینامیک از کندل‌های ذخیره‌شده محاسبه می‌شوند؛ تأیید قیمت برای ورود لازم است.")
            note.setWordWrap(True)
            note.setObjectName("muted")
            layout.addWidget(note)
            button = QPushButton("محاسبه حمایت، مقاومت و خطوط داینامیک")
            button.clicked.connect(self._refresh_structure)
            layout.addWidget(button)
            self.structure_output = QPlainTextEdit()
            self.structure_output.setReadOnly(True)
            layout.addWidget(self.structure_output, 1)
        elif index == 4:
            note = QLabel("سناریوها و مسیر ۱۵ دقیقه‌ای، برآوردهای الگوریتمی غیرکالیبره هستند و تضمین حرکت بازار نیستند.")
            note.setWordWrap(True)
            note.setObjectName("muted")
            layout.addWidget(note)
            button = QPushButton("ساخت سناریوهای تازه")
            button.clicked.connect(self._refresh_scenarios)
            layout.addWidget(button)
            self.scenario_output = QPlainTextEdit()
            self.scenario_output.setReadOnly(True)
            layout.addWidget(self.scenario_output, 1)
        elif index == 5:
            note = QLabel("آخرین snapshotهای تحلیل ذخیره‌شده در دیتابیس محلی.")
            note.setObjectName("muted")
            layout.addWidget(note)
            button = QPushButton("بارگذاری تاریخچه پیش‌بینی‌ها")
            button.clicked.connect(self._refresh_forecast_history)
            layout.addWidget(button)
            self.forecast_history_output = QPlainTextEdit()
            self.forecast_history_output.setReadOnly(True)
            layout.addWidget(self.forecast_history_output, 1)
        elif index == 6:
            note = QLabel("گزارش فقط بر اساس معاملات بسته‌شده‌ای محاسبه می‌شود که در ژورنال دستی ثبت شده‌اند؛ معیارها بر حسب R هستند.")
            note.setWordWrap(True)
            note.setObjectName("muted")
            layout.addWidget(note)
            refresh_button = QPushButton("به‌روزرسانی گزارش عملکرد")
            refresh_button.clicked.connect(self._refresh_performance)
            layout.addWidget(refresh_button)
            self.performance_output = QPlainTextEdit()
            self.performance_output.setReadOnly(True)
            layout.addWidget(self.performance_output, 1)
            self._refresh_performance()

        elif index == 9:
            note = QLabel(
                "شناسایی پنجره Trendo در نسخه ویندوز و Chrome. این نسخه فقط وضعیت اتصال "
                "را می‌خواند؛ تا زمان اعتبارسنجی کنترل‌ها و تأیید سفارش، اجرای خودکار غیرفعال است."
            )
            note.setWordWrap(True)
            note.setObjectName("muted")
            layout.addWidget(note)
            refresh = QPushButton("بررسی دوباره پنجره‌های Trendo")
            refresh.clicked.connect(self._refresh_trendo_status)
            layout.addWidget(refresh)
            inspect = QPushButton("بررسی کنترل‌های قابل‌دسترسی (فقط خواندنی)")
            inspect.clicked.connect(self._inspect_trendo_ui)
            inspect_detailed = QPushButton("بررسی کامل و بازگشتی کنترل‌ها (فقط خواندنی)")
            inspect_detailed.clicked.connect(self._inspect_trendo_ui_detailed)
            inspect_ocr = QPushButton("بررسی تصویری فرم با OCR (فقط خواندنی)")
            inspect_ocr.clicked.connect(self._inspect_trendo_visual_ocr)
            layout.addWidget(inspect_ocr)
            layout.addWidget(inspect_detailed)
            inspect_order = QPushButton("شناسایی کاندیداهای فرم سفارش (فقط خواندنی)")
            inspect_order.clicked.connect(self._inspect_trendo_order_form)
            layout.addWidget(inspect_order)
            layout.addWidget(inspect)
            self.trendo_output = QPlainTextEdit()
            self.trendo_output.setReadOnly(True)
            self.trendo_output.setPlaceholderText("وضعیت نسخه ویندوز و مرورگر Trendo")
            layout.addWidget(self.trendo_output, 1)
            self._refresh_trendo_status()
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

        elif index == 7:
            note = QLabel("ابزارهای تشخیص متن، یادگیری ماشین، خبر و فشار تیک. برای OCR باید Tesseract روی ویندوز نصب باشد؛ مسیر اجرایی آن را در صورت نیاز وارد کنید.")
            note.setWordWrap(True)
            note.setObjectName("muted")
            layout.addWidget(note)
            self.tesseract_path_input = QLineEdit()
            self.tesseract_path_input.setPlaceholderText(r"مسیر اختیاری tesseract.exe")
            self.tesseract_path_input.setText(self.ocr_tesseract_path)
            layout.addWidget(self.tesseract_path_input)
            ml_button = QPushButton("آموزش و ارزیابی مدل ML روی کندل‌های محلی")
            ml_button.clicked.connect(self._train_ml_model)
            layout.addWidget(ml_button)
            self.ml_output = QPlainTextEdit()
            self.ml_output.setReadOnly(True)
            self.ml_output.setPlaceholderText("نتیجه آموزش walk-forward اینجا نمایش داده می‌شود.")
            layout.addWidget(self.ml_output, 1)
            self.news_url_input = QLineEdit("https://feeds.finance.yahoo.com/rss/2.0/headline?s=GC%3DF&region=US&lang=en-US")
            self.news_url_input.setPlaceholderText("آدرس HTTPS منبع RSS")
            layout.addWidget(self.news_url_input)
            news_button = QPushButton("دریافت خبر بازار و تقویم اقتصادی رسمی BiQuote")
            news_button.clicked.connect(self._refresh_biquote_context)
            layout.addWidget(news_button)
            self.biquote_news_output = QPlainTextEdit()
            self.biquote_news_output.setReadOnly(True)
            self.biquote_news_output.setPlaceholderText("خبرهای بازار و رویدادهای اقتصادی بااهمیت")
            layout.addWidget(self.biquote_news_output, 1)
            rss_button = QPushButton("دریافت تیترها از منبع RSS دلخواه")
            rss_button.clicked.connect(self._refresh_news)
            layout.addWidget(rss_button)
            self.news_output = QPlainTextEdit()
            self.news_output.setReadOnly(True)
            layout.addWidget(self.news_output, 1)
            self.flow_output = QPlainTextEdit()
            self.flow_output.setReadOnly(True)
            self.flow_output.setMaximumHeight(130)
            self.flow_output.setPlainText(json.dumps(self.latest_tick_pressure, ensure_ascii=False, indent=2))
            layout.addWidget(self.flow_output)
            self.reference_output = QPlainTextEdit()
            self.reference_output.setReadOnly(True)
            self.reference_output.setMaximumHeight(180)
            self.reference_output.setPlaceholderText("اختلاف قیمت Spot مستقل با Mid بروکر؛ با attribution منبع")
            layout.addWidget(self.reference_output)
            self.corgano_credit = QLabel('<a href="https://goldprice.corgano.com/">Gold price data by Corgano</a>')
            self.corgano_credit.setOpenExternalLinks(True)
            layout.addWidget(self.corgano_credit)
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








    def _refresh_trendo_status(self):
        """Read-only discovery; no clicks or order submission are performed."""
        try:
            windows = discover_trendo_windows()
            report = connection_report(windows)
            self.trendo_output.setPlainText(json.dumps(
                report, ensure_ascii=False, indent=2
            ))
        except Exception as exc:
            self.trendo_output.setPlainText(
                f"بررسی Trendo ناموفق بود: {type(exc).__name__}: {exc}"
            )

    def _inspect_trendo_ui(self):
        """Inventory accessible Trendo controls without interacting with them."""
        try:
            windows = discover_trendo_windows()
            if not windows:
                raise RuntimeError("پنجره Trendo شناسایی نشد؛ ابتدا صفحه یا برنامه Trendo را باز کنید.")
            reports = []
            for window in windows:
                report = inspect_trendo_controls(int(window["hwnd"]))
                report["window_title"] = window.get("title", "")
                report["window_kind"] = window.get("kind", "")
                report["parsed_positions"] = parse_trendo_positions(report.get("controls", []))
                reports.append(report)
            self.trendo_output.setPlainText(json.dumps({
                "inspection": "read_only",
                "execution_enabled": False,
                "windows": reports,
                "next_step": "پوزیشن‌ها و PnL خالص ساختاریافته‌اند؛ کنترل‌های معتبر ثبت/بستن سفارش هنوز باید شناسایی و راستی‌آزمایی شوند."
            }, ensure_ascii=False, indent=2))
        except Exception as exc:
            self.trendo_output.setPlainText(
                f"بررسی کنترل‌های Trendo ناموفق بود: {type(exc).__name__}: {exc}"
            )

    def _inspect_trendo_ui_detailed(self):
        """Export a detailed recursive UIA inventory; never interact with Trendo."""
        try:
            windows = discover_trendo_windows()
            if not windows:
                raise RuntimeError("پنجره Trendo شناسایی نشد؛ ابتدا Trendo را باز کنید.")
            reports = []
            for window in windows:
                report = inspect_trendo_window_detailed(int(window["hwnd"]))
                report["window_title"] = window.get("title", "")
                report["window_kind"] = window.get("kind", "")
                report["window_bounds"] = window.get("bounds")
                reports.append(report)
            self.trendo_output.setPlainText(json.dumps({
                "inspection": "read_only_detailed_recursive",
                "execution_enabled": False,
                "execution_status": "blocked_unverified_ui",
                "windows": reports,
                "next_step": (
                    "فهرست کنترل‌ها و کاندیداهای فرم سفارش را بررسی کنید. "
                    "اگر فیلدهای ORDER در فهرست نیستند، احتمالاً Flutter آنها را "
                    "به‌صورت Canvas رسم کرده و باید مسیر OCR تصویریِ فقط‌خواندنی بررسی شود."
                )
            }, ensure_ascii=False, indent=2))
        except Exception as exc:
            self.trendo_output.setPlainText(
                f"بررسی کامل کنترل‌های Trendo ناموفق بود: {type(exc).__name__}: {exc}"
            )

    def _inspect_trendo_visual_ocr(self):
        """OCR the visible Trendo window in memory; never interacts with its UI."""
        try:
            windows = discover_trendo_windows()
            if not windows:
                raise RuntimeError("پنجره Trendo شناسایی نشد؛ ابتدا Trendo را باز کنید.")
            reports = []
            tesseract_path = ""
            if hasattr(self, "tesseract_path_input"):
                tesseract_path = self.tesseract_path_input.text().strip()
            for window in windows:
                report = inspect_trendo_visual_ocr(
                    int(window["hwnd"]),
                    tesseract_path=tesseract_path or None,
                    languages="eng",
                    min_confidence=20,
                )
                report["window_title"] = window.get("title", "")
                report["window_kind"] = window.get("kind", "")
                report["order_form_layout"] = analyze_order_form_layout(report)
                reports.append(report)
            self.trendo_output.setPlainText(json.dumps({
                "inspection": "read_only_visual_ocr",
                "execution_enabled": False,
                "execution_status": "blocked_unverified_ui",
                "windows": reports,
                "next_step": (
                    "گزارش OCR و کاندیداهای هندسی فیلدهای فرم اضافه شدند. "
                    "برچسب و عدد نزدیک فقط کاندیدا هستند؛ برای اعتبارسنجی بعدی "
                    "خروجی OCR و UI Automation را با هم مقایسه کنید. هیچ کلیک یا سفارشی انجام نشده است."
                )
            }, ensure_ascii=False, indent=2))
        except Exception as exc:
            self.trendo_output.setPlainText(
                f"OCR تصویری Trendo ناموفق بود: {type(exc).__name__}: {exc}"
            )

    def _inspect_trendo_order_form(self):
        """Read-only scan for possible order-form controls; never submits orders."""
        try:
            windows = discover_trendo_windows()
            if not windows:
                raise RuntimeError("پنجره Trendo شناسایی نشد؛ ابتدا Trendo را باز کنید.")
            reports = []
            for window in windows:
                report = inspect_order_form_controls(int(window["hwnd"]))
                report["window_title"] = window.get("title", "")
                report["window_kind"] = window.get("kind", "")
                reports.append(report)
            self.trendo_output.setPlainText(json.dumps({
                "inspection": "read_only_order_form_candidates",
                "execution_enabled": False,
                "windows": reports,
                "next_step": "کاندیداها باید با فرم واقعی و بدون ثبت سفارش بررسی شوند؛ هیچ کلیک یا تغییری انجام نشده است."
            }, ensure_ascii=False, indent=2))
        except Exception as exc:
            self.trendo_output.setPlainText(
                f"شناسایی فرم سفارش ناموفق بود: {type(exc).__name__}: {exc}"
            )

    def _train_ml_model(self):
        try:
            sources = self.analysis_service.store.list_sources("XAUUSD", "M1")
            source = next((item["source"] for item in sources if item["candle_count"] >= 200), None)
            if source is None:
                raise ValueError("حداقل ۲۰۰ کندل از یک منبع مستقل برای آموزش ML لازم است.")
            rows = self.analysis_service.store.get_candles(
                "XAUUSD", "M1", limit=10000, source=source
            )
            metrics = self.ml_model.fit(rows, horizon=15)
            self.ml_model.metadata = {
                "symbol": "XAUUSD", "timeframe": "M1", "source": source,
            }
            self.ml_model.save(self.analysis_service.ml_model_path, self.ml_model.metadata)
            prediction = self.ml_model.predict(rows)
            self.ml_output.setPlainText(json.dumps(
                {"evaluation": metrics, "latest_prediction": prediction},
                ensure_ascii=False, indent=2
            ))
        except Exception as exc:
            self.ml_output.setPlainText(f"آموزش انجام نشد: {exc}")

    def _refresh_biquote_context(self):
        try:
            result = self.biquote_context.fetch(symbol="XAUUSD", countries=("US", "EU", "GB"), importance="high")
            self.biquote_news_output.setPlainText(json.dumps(result, ensure_ascii=False, indent=2))
        except Exception as exc:
            self.biquote_news_output.setPlainText(f"دریافت خبر/تقویم ناموفق بود: {exc}")

    def _refresh_news(self):
        url = self.news_url_input.text().strip()
        result = self.news_client.fetch([url] if url else None)
        self.news_output.setPlainText(json.dumps(result, ensure_ascii=False, indent=2))

    def _refresh_current_overlay(self):
        if not self.current_chart_info:
            self.overlay.clear()
            return
        try:
            info = self.current_chart_info
            left, top, right, bottom = win32gui.GetWindowRect(info["hwnd"])
            info.update({"left": left, "top": top, "right": right, "bottom": bottom})
            image, capture_origin = capture_window_frame(info["hwnd"])
            recognition = recognize_chart(
                image, screen_origin=capture_origin, window_title=info.get("title", ""),
                tesseract_cmd=self.tesseract_path_input.text().strip(),
            )
            recognition["captured_at"] = datetime.now(timezone.utc).isoformat()
            info["recognition"] = recognition
            self._try_show_forecast_overlay(recognition)
        except Exception:
            self.overlay.clear()

    def _try_show_forecast_overlay(self, recognition: dict):
        self.overlay.clear()
        if not recognition.get("calibrated") or recognition.get("symbol") != "XAUUSD":
            return
        if recognition.get("timeframe_minutes") != 1:
            return
        axis = recognition["price_axis"]
        roi = recognition["chart_roi_screen"]
        origin_y = recognition.get("screen_origin", [
            self.current_chart_info["left"], self.current_chart_info["top"]
        ])[1]
        try:
            result = self.analysis_service.analyze_latest(
                "XAUUSD", "M1", source="broker", live_quote=self.latest_accepted_quote,
                chart_context=recognition, reference_context=self.latest_reference_result,
            )
            projection = ChartProjection(
                chart_left=roi["left"], chart_top=axis["y_at_top"] + origin_y,
                chart_right=self.current_chart_info["right"] - 70,
                chart_bottom=axis["y_at_bottom"] + origin_y,
                price_at_top=axis["price_at_top"],
                y_at_top=axis["y_at_top"] + origin_y,
                price_at_bottom=axis["price_at_bottom"],
                y_at_bottom=axis["y_at_bottom"] + origin_y,
                last_candle_x=recognition["last_candle_x"],
                pixels_per_minute=recognition["pixels_per_minute"],
            )
            projection.project_forecast(result["forecast_points"])
            self.overlay.set_forecast(projection, result["forecast_points"])
        except Exception:
            self.overlay.clear()

    def _run_latest_analysis(self):
        chart_context = (self.current_chart_info or {}).get("recognition")
        return self.analysis_service.analyze_latest(
            "XAUUSD", "M1", source="broker", live_quote=self.latest_accepted_quote,
            chart_context=chart_context, reference_context=self.latest_reference_result,
        )

    def _refresh_structure(self):
        try:
            result = self._run_latest_analysis()
            self.structure_output.setPlainText(json.dumps(
                result["market_structure"], ensure_ascii=False, indent=2
            ))
        except Exception as exc:
            self.structure_output.setPlainText(str(exc))

    def _refresh_scenarios(self):
        try:
            result = self._run_latest_analysis()
            output = {
                "scenarios": result["scenarios"],
                "directional_bias": result["directional_bias"],
                "forecast_points": result["forecast_points"],
                "limitations": result["limitations"],
                "brains": result.get("brains", {}),
                "confluence": result.get("confluence", {}),
            }
            self.scenario_output.setPlainText(json.dumps(
                output, ensure_ascii=False, indent=2
            ))
        except Exception as exc:
            self.scenario_output.setPlainText(str(exc))

    def _refresh_forecast_history(self):
        if not hasattr(self, "forecast_history_output"):
            return
        rows = self.analysis_service.store.latest_forecasts("XAUUSD", limit=50)
        self.forecast_history_output.setPlainText(json.dumps(
            rows, ensure_ascii=False, indent=2
        ))

    def _refresh_performance(self):
        if not hasattr(self, "performance_output"):
            return
        result = analyze_performance(self.trade_journal.list_trades(limit=10000))
        self.performance_output.setPlainText(json.dumps(
            result, ensure_ascii=False, indent=2
        ))

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
                bootstrap = self.history_bootstrapper.bootstrap_if_needed("XAUUSD")
                self.feed_bridge.status_changed.emit(
                    "تاریخچه اولیه آماده شد: " + json.dumps(bootstrap, ensure_ascii=False)
                )
                self.market_feed.start()
                if self._closing:
                    self.market_feed.stop()
                else:
                    self.reference_monitor.start()
                    if self._closing:
                        self.reference_monitor.stop()
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
            self.latest_accepted_quote = quote
            self.latest_tick_pressure = self.tick_pressure.update(quote)
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
        if hasattr(self, "flow_output"):
            self.flow_output.setPlainText(json.dumps(
                self.latest_tick_pressure, ensure_ascii=False, indent=2
            ))

    def _on_reference_result(self, result):
        self.latest_reference_result = result
        if hasattr(self, "reference_output"): 
            self.reference_output.setPlainText(json.dumps(result, ensure_ascii=False, indent=2))

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
            chart_context = (self.current_chart_info or {}).get("recognition")
            result = self.analysis_service.analyze_latest(
                symbol=symbol, timeframe=timeframe, source=source,
                live_quote=self.latest_accepted_quote, chart_context=chart_context,
                reference_context=self.latest_reference_result,
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
        # Keep compatibility with lightweight scanner doubles used by tests.
        if hasattr(self.scanner, "charts_updated"):
            self.scanner.charts_updated.connect(self._on_charts_updated)
        self.scanner.chart_lost.connect(self._on_chart_lost)
        self.scanner.start()

    def _on_charts_updated(self, charts):
        self.detected_charts = {int(item["hwnd"]): item for item in charts}
        if not hasattr(self, "chart_selector"):
            return
        selected = self.chart_selector.currentData()
        target = selected if selected in self.detected_charts else None
        if target is None and self.current_chart_info:
            current_hwnd = self.current_chart_info.get("hwnd")
            if current_hwnd in self.detected_charts:
                target = current_hwnd
        if target is None and self.detected_charts:
            target = next(iter(self.detected_charts))
        self.chart_selector.blockSignals(True)
        self.chart_selector.clear()
        for hwnd, info in self.detected_charts.items():
            self.chart_selector.addItem(
                f"{info.get('title', 'پنجره ناشناس')} | اعتماد {info.get('confidence', 0):.0%}",
                hwnd,
            )
        if target is not None:
            index = self.chart_selector.findData(target)
            if index >= 0:
                self.chart_selector.setCurrentIndex(index)
        self.chart_selector.blockSignals(False)
        if target is not None and (
            not self.current_chart_info
            or self.current_chart_info.get("hwnd") != target
        ):
            self._on_chart_found(self.detected_charts[target])

    def _select_detected_chart(self, index):
        if index < 0 or not hasattr(self, "chart_selector"):
            return
        hwnd = self.chart_selector.itemData(index)
        info = self.detected_charts.get(hwnd)
        if info and (
            not self.current_chart_info
            or self.current_chart_info.get("hwnd") != hwnd
        ):
            self._on_chart_found(info)

    def _on_status(self, message):
        self.data_value.setText("فعال" if "خطای" not in message else "دارای خطا")
        self.chart_status.setText(message)

    def _on_chart_found(self, info):
        self.current_chart_info = info
        title = info.get("title", "پنجره ناشناس")
        confidence = info.get("confidence", 0)
        recognition = {}
        try:
            image, capture_origin = capture_window_frame(info["hwnd"])
            recognition = recognize_chart(
                image, screen_origin=capture_origin,
                window_title=title,
                tesseract_cmd=self.tesseract_path_input.text().strip() if hasattr(self, "tesseract_path_input") else self.ocr_tesseract_path,
            )
        except Exception as exc:
            recognition = {"recognition_warnings": [str(exc)], "symbol": None, "timeframe": None, "calibrated": False}
        recognition["captured_at"] = datetime.now(timezone.utc).isoformat()
        info["recognition"] = recognition
        symbol = recognition.get("symbol") or "نامشخص"
        timeframe = recognition.get("timeframe") or "نامشخص"
        self.frame_value.setText(title)
        self.symbol_value.setText(symbol)
        details = (
            f"{title}\nشناسه پنجره: {info.get('hwnd')} | PID: {info.get('process_id')}\n"
            f"اعتماد تشخیص بصری: {confidence:.0%}\n"
            f"نماد OCR: {symbol} | تایم‌فریم OCR: {timeframe}\n"
            f"کالیبراسیون محور: {'تأیید اولیه' if recognition.get('calibrated') else 'نامعتبر/ناکافی'}\n"
            f"کندل‌های OHLC تخمینی: {len(recognition.get('ohlc', []))}\n"
            + "\n".join(recognition.get("recognition_warnings", []))
        )
        self.chart_status.setText(
            "چارت احتمالی شناسایی شد؛ مقادیر OCR تخمینی‌اند و فقط با داده بازار مستقل مقایسه می‌شوند."
        )
        self.detector_result.setText(details)
        self.footer.setText(
            "تشخیص پنجره فعال است؛ Overlay فقط در صورت شناسایی XAUUSD/M1 و کالیبراسیون معتبر روشن می‌شود."
        )
        self._try_show_forecast_overlay(recognition)

    def _on_chart_lost(self):
        self.current_chart_info = None
        self.overlay.clear()
        self.frame_value.setText("در انتظار")
        self.chart_status.setText("هیچ چارت قابل شناسایی در پنجره‌های قابل مشاهده پیدا نشد.")

    def closeEvent(self, event):
        self._closing = True
        if hasattr(self, "overlay_timer"):
            self.overlay_timer.stop()
        self.reference_monitor.stop()
        if self.scanner is not None:
            self.scanner.stop()
        self.overlay.clear()
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
