from toobit.config import ToobitConfig
from toobit.execution import ToobitExecutionService
from toobit.risk import calculate_contract_quantity


def test_contract_quantity_respects_risk_and_notional_caps():
    qty = calculate_contract_quantity(
        entry_price=2000, stop_price=1990, risk_usdt=2,
        contract_multiplier=1, max_notional_usdt=100,
        min_quantity=0.001, quantity_step=0.001,
    )
    assert str(qty) == "0.01"


def test_contract_quantity_rejects_zero_stop_distance():
    try:
        calculate_contract_quantity(
            entry_price=2000, stop_price=2000, risk_usdt=2,
            contract_multiplier=1, max_notional_usdt=100,
            min_quantity=0.001, quantity_step=0.001,
        )
    except ValueError as exc:
        assert "zero" in str(exc)
    else:
        raise AssertionError("zero stop distance must be rejected")


class FakeClient:
    def exchange_info(self):
        raise AssertionError("exchangeInfo must not be called in dry-run mode")


def test_execution_defaults_to_dry_run_and_never_sends_order():
    config = ToobitConfig(symbol="XAU-SWAP-USDT", live_trading_enabled=False)
    service = ToobitExecutionService(FakeClient(), config)
    analysis = {
        "symbol": "XAUUSD",
        "directional_bias": "bullish",
        "entry_readiness": {
            "status": "ready_for_manual_review",
            "plan": {"entry": 2000, "stop_loss": 1990, "take_profit": 2015},
        },
    }
    result = service.execute(analysis)
    assert result["status"] == "dry_run"
    assert result["symbol"] == "XAU-SWAP-USDT"


def test_live_execution_remains_blocked_until_protective_order_support():
    config = ToobitConfig(symbol="XAU-SWAP-USDT", live_trading_enabled=True)
    service = ToobitExecutionService(FakeClient(), config)
    analysis = {
        "symbol": "XAUUSD",
        "directional_bias": "bullish",
        "entry_readiness": {
            "status": "ready_for_manual_review",
            "plan": {"entry": 2000, "stop_loss": 1990, "take_profit": 2015},
        },
    }
    result = service.execute(analysis, confirm_live=True)
    assert result["status"] == "blocked"
    assert "stop-loss/take-profit" in result["reason"]
