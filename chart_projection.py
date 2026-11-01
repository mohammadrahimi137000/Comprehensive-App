"""Map forecast prices to desktop pixels using two verified price-axis anchors."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ChartProjection:
    chart_left: int
    chart_top: int
    chart_right: int
    chart_bottom: int
    price_at_top: float
    y_at_top: float
    price_at_bottom: float
    y_at_bottom: float
    last_candle_x: float
    pixels_per_minute: float

    def __post_init__(self):
        if self.chart_right <= self.chart_left or self.chart_bottom <= self.chart_top:
            raise ValueError("Chart ROI must have positive width and height")
        if self.price_at_top == self.price_at_bottom:
            raise ValueError("Price-axis anchors must have different prices")
        if self.y_at_top == self.y_at_bottom:
            raise ValueError("Price-axis anchors must have different y coordinates")
        if self.pixels_per_minute <= 0:
            raise ValueError("pixels_per_minute must be positive")

    def price_to_y(self, price: float) -> float:
        ratio = (float(price) - self.price_at_top) / (
            self.price_at_bottom - self.price_at_top
        )
        return self.y_at_top + ratio * (self.y_at_bottom - self.y_at_top)

    def minute_to_x(self, minute: float) -> float:
        return self.last_candle_x + float(minute) * self.pixels_per_minute

    def project_point(self, minute: float, price: float) -> tuple[float, float]:
        return self.minute_to_x(minute), self.price_to_y(price)

    def project_forecast(self, points: list[dict]) -> list[dict]:
        projected = []
        previous_minute = 0
        for point in points:
            minute = int(point["minute"])
            if minute <= previous_minute:
                raise ValueError("Forecast minutes must be strictly increasing")
            previous_minute = minute
            x, y = self.project_point(minute, point["mid"])
            _, y_low = self.project_point(minute, point["low"])
            _, y_high = self.project_point(minute, point["high"])
            projected.append({
                "minute": minute, "x": round(x, 2), "y": round(y, 2),
                "band_top": round(min(y_low, y_high), 2),
                "band_bottom": round(max(y_low, y_high), 2),
            })
        return projected
