import pytest

from chart_projection import ChartProjection


def projection():
    return ChartProjection(
        chart_left=100, chart_top=100, chart_right=900, chart_bottom=700,
        price_at_top=2050, y_at_top=100,
        price_at_bottom=1950, y_at_bottom=700,
        last_candle_x=850, pixels_per_minute=3.0,
    )


def test_maps_prices_and_future_minutes_to_screen_pixels():
    item = projection()
    assert item.price_to_y(2050) == 100
    assert item.price_to_y(1950) == 700
    assert item.project_point(5, 2000) == (865, 400)


def test_projects_forecast_uncertainty_band():
    result = projection().project_forecast([
        {"minute": 1, "mid": 2000, "low": 1998, "high": 2002},
        {"minute": 2, "mid": 2001, "low": 1999, "high": 2003},
    ])
    assert result[0]["x"] == 853
    assert result[0]["band_top"] < result[0]["band_bottom"]
    assert result[1]["x"] > result[0]["x"]


def test_rejects_invalid_anchors_and_non_monotonic_forecast():
    with pytest.raises(ValueError):
        ChartProjection(0, 0, 10, 10, 100, 0, 100, 10, 5, 1)
    with pytest.raises(ValueError, match="strictly increasing"):
        projection().project_forecast([
            {"minute": 1, "mid": 1, "low": 0, "high": 2},
            {"minute": 1, "mid": 1, "low": 0, "high": 2},
        ])
