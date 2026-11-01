"""Transparent, mouse-through forecast overlay for calibrated chart coordinates."""
from __future__ import annotations

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QPainter, QPainterPath, QPen, QPolygonF
from PySide6.QtWidgets import QApplication, QWidget

from chart_projection import ChartProjection


class ForecastOverlay(QWidget):
    def __init__(self):
        flags = (
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
            | Qt.WindowType.WindowTransparentForInput
        )
        super().__init__(None, flags)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating, True)
        self.projection: ChartProjection | None = None
        self.forecast_points: list[dict] = []
        self._sync_virtual_geometry()

    def _sync_virtual_geometry(self):
        screen = QApplication.primaryScreen()
        if screen is not None:
            self.setGeometry(screen.virtualGeometry())

    def set_forecast(self, projection: ChartProjection, points: list[dict]):
        # Validate and project before making the overlay visible.
        projection.project_forecast(points)
        self.projection = projection
        self.forecast_points = list(points)
        self._sync_virtual_geometry()
        self.update()
        if self.forecast_points:
            self.show()

    def clear(self):
        self.forecast_points = []
        self.projection = None
        self.hide()

    def paintEvent(self, _event):
        if self.projection is None or not self.forecast_points:
            return
        projected = self.projection.project_forecast(self.forecast_points)
        origin = self.geometry()
        mid_path = QPainterPath()
        band_points = []
        for index, item in enumerate(projected):
            x = item["x"] - origin.left()
            y = item["y"] - origin.top()
            top = item["band_top"] - origin.top()
            bottom = item["band_bottom"] - origin.top()
            if index == 0:
                mid_path.moveTo(x, y)
            else:
                mid_path.lineTo(x, y)
            band_points.append((x, top))
        for item in reversed(projected):
            band_points.append((
                item["x"] - origin.left(),
                item["band_bottom"] - origin.top(),
            ))

        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.setClipRect(QRectF(
            self.projection.chart_left - origin.left(),
            self.projection.chart_top - origin.top(),
            self.projection.chart_right - self.projection.chart_left,
            self.projection.chart_bottom - self.projection.chart_top,
        ))
        polygon = QPolygonF()
        for x, y in band_points:
            polygon.append(QPointF(x, y))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(34, 211, 238, 38))
        painter.drawPolygon(polygon)
        painter.setPen(QPen(QColor(34, 211, 238, 230), 2.2))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawPath(mid_path)
        painter.setBrush(QColor(34, 211, 238, 230))
        for item in projected:
            painter.drawEllipse(
                item["x"] - origin.left() - 3,
                item["y"] - origin.top() - 3, 6, 6,
            )
        painter.end()
