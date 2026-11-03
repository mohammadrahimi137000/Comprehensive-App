"""Signal-to-order bridge. Dry-run is the default; live mode requires two explicit gates."""
from __future__ import annotations

import re
import uuid
from decimal import Decimal

from .config import ToobitConfig
from .risk import calculate_contract_quantity


class ToobitExecutionService:
    def __init__(self, client, config: ToobitConfig | None = None):
        self.client = client
        self.config = config or ToobitConfig.from_env()
        self.config.validate()

    def _contract(self):
        info = self.client.exchange_info()
        contracts = info.get("contracts", []) if isinstance(info, dict) else []
        match = next((item for item in contracts if item.get("symbol") == self.config.symbol), None)
        if not match:
            raise ValueError(f"Contract {self.config.symbol} was not found in Toobit exchangeInfo; order blocked")
        if match.get("status") != "TRADING":
            raise ValueError(f"Contract status is {match.get('status')}; order blocked")
        return match

    @staticmethod
    def _filters(contract):
        filters = {item.get("filterType"): item for item in contract.get("filters", [])}
        lot = filters.get("LOT_SIZE") or filters.get("LOT_SIZE_FILTER") or {}
        min_qty = lot.get("minQty") or lot.get("minQuantity")
        step = lot.get("stepSize") or lot.get("qtyStep") or min_qty
        multiplier = contract.get("contractMultiplier")
        if not all((min_qty, step, multiplier)):
            raise ValueError("Toobit contract metadata lacks min quantity, quantity step, or contract multiplier")
        return float(min_qty), float(step), float(multiplier)

    def build_intent(self, analysis: dict) -> dict:
        readiness = analysis.get("entry_readiness") or {}
        status = readiness.get("status")
        if status != "ready_for_manual_review":
            return {"status": "blocked", "reason": f"Entry readiness is {status or 'missing'}; no order intent created"}
        if analysis.get("symbol") not in ("XAUUSD", "XAU"):
            return {"status": "blocked", "reason": "Only XAU analysis is allowed by this connector"}
        bias = analysis.get("directional_bias")
        if bias not in ("bullish", "bearish"):
            return {"status": "blocked", "reason": "Neutral or missing directional bias"}
        plan = readiness.get("plan") or {}
        entry = plan.get("entry")
        stop = plan.get("stop_loss")
        take_profit = plan.get("take_profit")
        if not entry or not stop or not take_profit:
            return {"status": "blocked", "reason": "Entry, stop-loss and take-profit are all required"}
        if bias == "bullish" and not (float(stop) < float(entry) < float(take_profit)):
            return {"status": "blocked", "reason": "Invalid long entry/SL/TP geometry"}
        if bias == "bearish" and not (float(take_profit) < float(entry) < float(stop)):
            return {"status": "blocked", "reason": "Invalid short entry/SL/TP geometry"}
        return {"status": "intent_ready", "symbol": self.config.symbol, "direction": bias,
                "entry_reference": float(entry), "stop_loss": float(stop),
                "take_profit": float(take_profit), "source_analysis_status": analysis.get("status")}

    def execute(self, analysis: dict, *, confirm_live: bool = False) -> dict:
        intent = self.build_intent(analysis)
        if intent["status"] != "intent_ready":
            return intent
        if not self.config.live_trading_enabled or not confirm_live:
            return {**intent, "status": "dry_run", "message": "No order was sent. Enable live mode in local environment and explicitly confirm this execution."}
        return {**intent, "status": "blocked", "reason": "Live order submission is intentionally locked until exchange-native protective stop-loss/take-profit placement and fill reconciliation are implemented and tested. No order was sent."}
        contract = self._contract()
        min_qty, step, multiplier = self._filters(contract)
        quantity = calculate_contract_quantity(
            entry_price=intent["entry_reference"], stop_price=intent["stop_loss"],
            risk_usdt=self.config.risk_per_trade_usdt, contract_multiplier=multiplier,
            max_notional_usdt=self.config.max_notional_usdt, min_quantity=min_qty,
            quantity_step=step,
        )
        direction = intent["direction"]
        client_id = "ca_" + uuid.uuid4().hex[:24]
        result = self.client.place_futures_market_order(
            symbol=self.config.symbol, side="BUY" if direction == "bullish" else "SELL",
            position_side="LONG" if direction == "bullish" else "SHORT",
            quantity=format(quantity, "f"), client_order_id=client_id,
        )
        return {**intent, "status": "submitted", "client_order_id": client_id,
                "quantity": format(quantity, "f"), "exchange_response": result,
                "warning": "Entry submitted. Protective SL/TP attachment and fill reconciliation must be confirmed before unattended live use."}
