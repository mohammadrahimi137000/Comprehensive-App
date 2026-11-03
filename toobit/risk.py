"""Conservative sizing helpers; contract multiplier and filters must come from exchangeInfo."""
from __future__ import annotations

from decimal import Decimal, ROUND_DOWN


def calculate_contract_quantity(*, entry_price: float, stop_price: float, risk_usdt: float, contract_multiplier: float, max_notional_usdt: float, min_quantity: float, quantity_step: float) -> Decimal:
    values = (entry_price, stop_price, risk_usdt, contract_multiplier, max_notional_usdt, min_quantity, quantity_step)
    if any(float(value) <= 0 for value in values):
        raise ValueError("All sizing inputs must be positive")
    distance = abs(Decimal(str(entry_price)) - Decimal(str(stop_price)))
    if distance == 0:
        raise ValueError("Stop distance cannot be zero")
    multiplier = Decimal(str(contract_multiplier))
    raw_by_risk = Decimal(str(risk_usdt)) / (distance * multiplier)
    raw_by_notional = Decimal(str(max_notional_usdt)) / (Decimal(str(entry_price)) * multiplier)
    raw = min(raw_by_risk, raw_by_notional)
    step = Decimal(str(quantity_step))
    quantity = (raw / step).to_integral_value(rounding=ROUND_DOWN) * step
    if quantity < Decimal(str(min_quantity)):
        raise ValueError("Calculated quantity is below the contract minimum")
    return quantity.normalize()
