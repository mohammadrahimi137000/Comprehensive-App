"""Guarded policy for the requested 5-second GOLD hedge-cycle strategy.

This module is deliberately execution-agnostic. It emits intents only; it does not
click Trendo, submit orders, or infer USD PnL from chart prices. A verified broker
adapter must supply per-position net PnL and confirm every fill/close before live
execution can be enabled.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

Side = Literal["BUY", "SELL"]


@dataclass(frozen=True)
class PositionSnapshot:
    position_id: str
    side: Side
    net_pnl_usd: float


@dataclass(frozen=True)
class OrderIntent:
    action: Literal["OPEN", "CLOSE"]
    side: Side
    reason: str
    position_id: str | None = None


@dataclass
class HedgeCyclePolicy:
    interval_seconds: float = 5.0
    take_profit_usd: float = 1.0
    stop_loss_usd: float = 0.5
    max_open_positions: int = 10
    enabled: bool = False
    _last_cycle_at: float | None = None
    _sequence: int = 0

    def __post_init__(self) -> None:
        if self.interval_seconds <= 0:
            raise ValueError("interval_seconds must be positive")
        if self.take_profit_usd <= 0 or self.stop_loss_usd <= 0:
            raise ValueError("profit and loss thresholds must be positive")
        if self.max_open_positions < 2:
            raise ValueError("max_open_positions must be at least 2")

    def evaluate(
        self,
        now: float,
        positions: list[PositionSnapshot],
    ) -> list[OrderIntent]:
        """Return close intents first, then due open intents; never executes them."""
        if not self.enabled:
            return []

        intents: list[OrderIntent] = []
        remaining: list[PositionSnapshot] = []
        for position in positions:
            if position.net_pnl_usd >= self.take_profit_usd:
                intents.append(OrderIntent(
                    "CLOSE", position.side, "take_profit", position.position_id
                ))
            elif position.net_pnl_usd <= -self.stop_loss_usd:
                intents.append(OrderIntent(
                    "CLOSE", position.side, "stop_loss", position.position_id
                ))
            else:
                remaining.append(position)

        # Do not add exposure while any close is awaiting broker confirmation.
        if intents:
            return intents

        if self._last_cycle_at is not None and now - self._last_cycle_at < self.interval_seconds:
            return []

        capacity = self.max_open_positions - len(remaining)
        if capacity <= 0:
            return []

        # Once a side has a profitable open position, add only in the direction
        # of the strongest profitable position. Otherwise start/continue with a
        # BUY+SELL hedge pair (never a partial pair).
        winners = [p for p in remaining if p.net_pnl_usd > 0]
        if winners:
            leader = max(winners, key=lambda p: p.net_pnl_usd)
            sides: list[Side] = [leader.side]
        else:
            sides = ["BUY", "SELL"]

        if len(sides) > capacity:
            return []

        self._sequence += 1
        self._last_cycle_at = now
        return [
            OrderIntent("OPEN", side, f"cycle_{self._sequence}")
            for side in sides
        ]
