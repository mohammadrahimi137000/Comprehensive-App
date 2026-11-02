"""Trend-following trade-cycle policy for the 5-minute XAUUSD direction.

This module emits intents only. It never sends orders or assumes that an order
was filled/closed. A broker adapter must reconcile confirmed tickets first.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

Side = Literal["BUY", "SELL"]
Trend = Literal["bullish", "bearish", "sideways", "unknown"]


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
class TrendFollowingPolicy:
    """One trend-aligned starter, profit-confirmed adds, recovery hedge after SL."""

    interval_seconds: float = 2.0
    take_profit_usd: float = 1.0
    stop_loss_usd: float = 0.5
    max_open_positions: int = 10
    enabled: bool = False
    _last_entry_at: float | None = None
    _processed_winners: set[str] = field(default_factory=set)
    _stopped_tickets_waiting_for_absence: set[str] = field(default_factory=set)
    _close_requests_pending: set[str] = field(default_factory=set)
    _recovery_pair_pending: bool = False

    def __post_init__(self) -> None:
        if self.interval_seconds <= 0:
            raise ValueError("interval_seconds must be positive")
        if self.take_profit_usd <= 0 or self.stop_loss_usd <= 0:
            raise ValueError("profit and loss thresholds must be positive")
        if self.max_open_positions < 2:
            raise ValueError("max_open_positions must be at least 2")

    @staticmethod
    def _trend_side(trend: Trend) -> Side | None:
        if trend == "bullish":
            return "BUY"
        if trend == "bearish":
            return "SELL"
        return None

    def evaluate(
        self, now: float, trend: Trend, positions: list[PositionSnapshot]
    ) -> list[OrderIntent]:
        """Return intents only; caller must execute and reconcile them safely."""
        if not self.enabled:
            return []

        intents: list[OrderIntent] = []
        for position in positions:
            if position.net_pnl_usd >= self.take_profit_usd:
                if position.position_id not in self._close_requests_pending:
                    intents.append(OrderIntent(
                        "CLOSE", position.side, "take_profit", position.position_id
                    ))
                    self._close_requests_pending.add(position.position_id)
            elif position.net_pnl_usd <= -self.stop_loss_usd:
                if position.position_id not in self._close_requests_pending:
                    intents.append(OrderIntent(
                        "CLOSE", position.side, "stop_loss", position.position_id
                    ))
                    self._close_requests_pending.add(position.position_id)
                    self._stopped_tickets_waiting_for_absence.add(position.position_id)
                    self._recovery_pair_pending = True

        # Never increase exposure while any close intent needs broker reconciliation.
        if intents:
            return intents

        open_ids = {position.position_id for position in positions}
        # Keep a close request latched while its ticket remains visible. This
        # prevents duplicate CLOSE intents and blocks new exposure until the
        # broker confirms the ticket has disappeared.
        self._close_requests_pending.intersection_update(open_ids)
        if self._close_requests_pending:
            return []
        self._stopped_tickets_waiting_for_absence.intersection_update(open_ids)
        # A stop-out triggers exactly one recovery hedge pair, but only after
        # the stopped ticket is absent from a fresh, verified open-position scan.
        if self._stopped_tickets_waiting_for_absence:
            self._recovery_pair_pending = True
            return []

        capacity = self.max_open_positions - len(positions)
        if capacity <= 0:
            return []
        if self._last_entry_at is not None and now - self._last_entry_at < self.interval_seconds:
            return []

        if self._recovery_pair_pending:
            if capacity < 2:
                return []
            self._last_entry_at = now
            self._recovery_pair_pending = False
            self._processed_winners.update(p.position_id for p in positions)
            return [
                OrderIntent("OPEN", "BUY", "recovery_hedge_after_stop"),
                OrderIntent("OPEN", "SELL", "recovery_hedge_after_stop"),
            ]

        trend_side = self._trend_side(trend)
        if trend_side is None:
            return []

        # A first entry follows the M5 trend; no blind BUY+SELL start.
        if not positions:
            self._last_entry_at = now
            return [OrderIntent("OPEN", trend_side, "initial_m5_trend_entry")]

        # Add only once per newly profitable position, and only in the M5 trend.
        winners = [
            p for p in positions
            if p.net_pnl_usd > 0 and p.position_id not in self._processed_winners
        ]
        if not winners:
            return []
        for winner in winners:
            self._processed_winners.add(winner.position_id)
        aligned = [p for p in winners if p.side == trend_side]
        if not aligned:
            return []
        if capacity < 1:
            return []
        leader = max(aligned, key=lambda p: p.net_pnl_usd)
        self._last_entry_at = now
        return [OrderIntent("OPEN", trend_side, "add_after_new_profitable_position:" + leader.position_id)]
