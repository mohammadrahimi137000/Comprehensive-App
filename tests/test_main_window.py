import os

from PySide6.QtCore import QObject, Signal
from PySide6.QtWidgets import QApplication

import main
from analysis_service import AnalysisService
from market_store import MarketStore


class FakeScanner(QObject):
    chart_found = Signal(dict)
    chart_lost = Signal()
    status_changed = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)

    def start(self):
        pass

    def stop(self):
        pass


class FakeFeed:
    def __init__(self, symbols, on_quote, on_status):
        self.on_status = on_status

    def start(self):
        self.on_status("Fake feed connected")

    def stop(self):
        pass

    def get_latest_quote(self, symbol="XAUUSD"):
        return None


class FakeBootstrapper:
    def __init__(self, **kwargs):
        pass

    def bootstrap_if_needed(self, symbol="XAUUSD"):
        return {}


def test_main_window_builds_all_pages_without_starting_network(monkeypatch, tmp_path):
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    app = QApplication.instance() or QApplication([])
    store = MarketStore(tmp_path / "market.db")
    monkeypatch.setattr(main, "AnalysisService", lambda: AnalysisService(store=store))
    monkeypatch.setattr(main, "ChartScanner", FakeScanner)
    monkeypatch.setattr(main, "ResilientBiQuoteFeed", FakeFeed)
    monkeypatch.setattr(main, "HistoryBootstrapper", FakeBootstrapper)

    window = main.MainWindow()
    assert len(window.nav_buttons) == 9
    assert window.journal_table.columnCount() == 8
    assert hasattr(window, "analysis_output")
    window.close()
    app.processEvents()
