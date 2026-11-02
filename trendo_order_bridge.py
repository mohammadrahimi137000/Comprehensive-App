"""Fail-closed Trendo order bridge.

This module prepares and validates order requests, and inspects the UIA tree for
possible order-form controls. It intentionally does not click, type, submit, or
close positions: no stable Trendo order controls or post-submit receipt have
been verified for this installation yet.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from math import isfinite
from typing import Any

SUPPORTED_SYMBOLS = {"GOLD", "XAUUSD"}
SUPPORTED_SIDES = {"BUY", "SELL"}


@dataclass(frozen=True)
class TrendoOrderRequest:
    symbol: str
    side: str
    volume: float
    stop_loss: float | None = None
    take_profit: float | None = None
    client_order_id: str = ""

    def validate(self) -> "TrendoOrderRequest":
        symbol = self.symbol.strip().upper()
        side = self.side.strip().upper()
        if symbol not in SUPPORTED_SYMBOLS:
            raise ValueError("Only GOLD/XAUUSD order requests are supported")
        if side not in SUPPORTED_SIDES:
            raise ValueError("side must be BUY or SELL")
        if not isinstance(self.volume, (int, float)) or isinstance(self.volume, bool):
            raise ValueError("volume must be numeric")
        if not isfinite(float(self.volume)) or self.volume <= 0:
            raise ValueError("volume must be finite and positive")
        for name, value in (("stop_loss", self.stop_loss), ("take_profit", self.take_profit)):
            if value is not None and (
                not isinstance(value, (int, float)) or isinstance(value, bool)
                or not isfinite(float(value)) or value <= 0
            ):
                raise ValueError(f"{name} must be a finite positive price or None")
        if self.stop_loss is not None and self.take_profit is not None:
            if side == "BUY" and self.stop_loss >= self.take_profit:
                raise ValueError("For BUY, stop_loss must be below take_profit")
            if side == "SELL" and self.stop_loss <= self.take_profit:
                raise ValueError("For SELL, stop_loss must be above take_profit")
        if not self.client_order_id.strip():
            raise ValueError("client_order_id is required for duplicate protection")
        return TrendoOrderRequest(
            symbol=symbol, side=side, volume=float(self.volume),
            stop_loss=float(self.stop_loss) if self.stop_loss is not None else None,
            take_profit=float(self.take_profit) if self.take_profit is not None else None,
            client_order_id=self.client_order_id.strip(),
        )


def inspect_order_form_controls(hwnd: int, inspector=None) -> dict:
    """Read-only UIA inspection; returns candidates, never actionable selectors."""
    if inspector is None:
        from trendo_connector import inspect_trendo_controls
        inspector = inspect_trendo_controls
    report = inspector(hwnd)
    if report.get("status") != "inspected":
        return {
            "status": report.get("status", "inspection_failed"),
            "candidates": [],
            "execution_enabled": False,
            "message": report.get("message", "UIA inspection was not successful."),
        }

    candidates = []
    for item in report.get("controls", []):
        if not item.get("visible") or not item.get("enabled"):
            continue
        kind = str(item.get("control_type", ""))
        label = " ".join(str(item.get(key, "")) for key in ("name", "automation_id", "class_name")).casefold()
        signals = []
        if kind in {"Edit", "ComboBox", "Spinner"}:
            if any(word in label for word in ("volume", "lot", "amount", "size", "حجم")):
                signals.append("volume_field_candidate")
            if any(word in label for word in ("symbol", "instrument", "نماد")):
                signals.append("symbol_field_candidate")
            if any(word in label for word in ("stop", "sl", "حد ضرر")):
                signals.append("stop_loss_field_candidate")
            if any(word in label for word in ("take", "profit", "tp", "حد سود")):
                signals.append("take_profit_field_candidate")
        if kind in {"Button", "Text"}:
            if any(word in label for word in ("buy", "خرید")):
                signals.append("buy_action_candidate")
            if any(word in label for word in ("sell", "فروش")):
                signals.append("sell_action_candidate")
        if signals:
            candidates.append({
                "control_type": kind,
                "name": item.get("name", ""),
                "automation_id": item.get("automation_id", ""),
                "bounds": item.get("bounds"),
                "signals": signals,
                "verified": False,
            })
    return {
        "status": "candidates_found" if candidates else "no_order_form_candidates",
        "hwnd": hwnd,
        "candidates": candidates,
        "execution_enabled": False,
        "message": (
            "کاندیداها فقط از متن و نوع کنترل استخراج شده‌اند؛ "
            "هیچ selector یا اقدام معاملاتی تأیید نشده است."
        ),
    }


class TrendoExecutionBridge:
    """Fail-closed boundary between strategy intents and Trendo UI."""

    execution_enabled = False

    def prepare_order(self, request: TrendoOrderRequest) -> dict:
        validated = request.validate()
        return {
            "status": "blocked_unverified_execution",
            "request": asdict(validated),
            "submitted": False,
            "ticket": None,
            "execution_enabled": False,
            "reason": (
                "Trendo UI order controls and a reliable post-submit ticket "
                "confirmation have not been verified. No UI action was performed."
            ),
        }

    def execute_order(self, request: TrendoOrderRequest) -> dict:
        """Never submit until a separately reviewed, verified adapter exists."""
        return self.prepare_order(request)

    def close_position(self, ticket: str) -> dict:
        if not str(ticket).strip():
            raise ValueError("ticket is required")
        return {
            "status": "blocked_unverified_execution",
            "ticket": str(ticket).strip(),
            "submitted": False,
            "execution_enabled": False,
            "reason": "Position-close control and close confirmation are not verified.",
        }
