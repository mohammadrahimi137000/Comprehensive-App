from datetime import datetime, timezone

from feed_router import Quote
from tick_flow import TickPressure


def test_tick_pressure_is_bounded_and_labeled_as_proxy():
    pressure = TickPressure(capacity=20)
    for i in range(30):
        price = 2000 + i * 0.1
        result = pressure.update(Quote("test", "XAUUSD", "broker",
            datetime.now(timezone.utc), price, price + 0.1))
    assert result["samples"] == 20
    assert result["classification"] == "buy_pressure_proxy"
    assert result["data_type"] == "tick_direction_proxy"
    assert result["tick_imbalance"] == 1
