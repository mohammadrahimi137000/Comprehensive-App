import pytest

from trendo_order_bridge import (
    TrendoExecutionBridge,
    TrendoOrderRequest,
    inspect_order_form_controls,
)


def test_valid_buy_request_is_prepared_but_not_submitted():
    bridge = TrendoExecutionBridge()
    result = bridge.execute_order(TrendoOrderRequest(
        symbol="xauusd", side="buy", volume=0.02,
        stop_loss=3900, take_profit=3910, client_order_id="test-001",
    ))
    assert result["status"] == "blocked_unverified_execution"
    assert result["submitted"] is False
    assert result["ticket"] is None
    assert result["request"]["symbol"] == "XAUUSD"


@pytest.mark.parametrize("order_request", [
    TrendoOrderRequest("XAUUSD", "BUY", 0, client_order_id="x"),
    TrendoOrderRequest("EURUSD", "BUY", 0.1, client_order_id="x"),
    TrendoOrderRequest("XAUUSD", "HOLD", 0.1, client_order_id="x"),
    TrendoOrderRequest("XAUUSD", "BUY", 0.1),
    TrendoOrderRequest("XAUUSD", "BUY", 0.1, stop_loss=3910, take_profit=3900, client_order_id="x"),
])
def test_invalid_order_requests_are_rejected(order_request):
    with pytest.raises(ValueError):
        order_request.validate()


def test_close_position_is_blocked_without_ui_action():
    result = TrendoExecutionBridge().close_position("123456")
    assert result["submitted"] is False
    assert result["execution_enabled"] is False


def test_order_form_inspection_only_returns_unverified_candidates():
    controls = [
        {"control_type": "Edit", "name": "Volume", "automation_id": "lot",
         "visible": True, "enabled": True, "bounds": None},
        {"control_type": "Button", "name": "BUY", "automation_id": "buy",
         "visible": True, "enabled": True, "bounds": None},
        {"control_type": "Edit", "name": "Password", "automation_id": "pass",
         "visible": True, "enabled": True, "bounds": None},
    ]
    result = inspect_order_form_controls(55, inspector=lambda hwnd: {
        "status": "inspected", "controls": controls,
    })
    assert result["status"] == "candidates_found"
    assert len(result["candidates"]) == 2
    assert all(not item["verified"] for item in result["candidates"])
    assert result["execution_enabled"] is False



def test_flutter_text_buy_sell_are_manual_targets_not_verified_buttons():
    controls = [
        {"name": "Buy", "control_type": "Text", "visible": True,
         "enabled": False,
         "bounds": {"left": 520, "top": 1266, "right": 948, "bottom": 1354}},
        {"name": "Sell", "control_type": "Text", "visible": True,
         "enabled": False,
         "bounds": {"left": 88, "top": 1266, "right": 516, "bottom": 1354}},
    ]
    result = inspect_order_form_controls(
        123, inspector=lambda _hwnd: {"status": "inspected", "controls": controls}
    )
    assert result["status"] == "manual_demo_targets_detected"
    assert {item["side"] for item in result["manual_action_targets"]} == {"BUY", "SELL"}
    assert all(item["verified"] is False for item in result["manual_action_targets"])
    assert all(item["interaction"] == "manual_user_action_only"
               for item in result["manual_action_targets"])
    assert result["manual_demo_preflight"]["both_sides_detected"] is True
    assert result["manual_demo_preflight"]["automatic_click_allowed"] is False
    assert result["execution_enabled"] is False


def test_buy_sell_without_valid_bounds_are_not_manual_targets():
    controls = [
        {"name": "Buy", "control_type": "Text", "visible": True,
         "enabled": True, "bounds": None},
        {"name": "Sell", "control_type": "Text", "visible": True,
         "enabled": True,
         "bounds": {"left": 10, "top": 10, "right": 10, "bottom": 30}},
    ]
    result = inspect_order_form_controls(
        123, inspector=lambda _hwnd: {"status": "inspected", "controls": controls}
    )
    assert result["manual_action_targets"] == []
    assert result["execution_enabled"] is False


def test_non_exact_action_label_is_not_misclassified():
    controls = [{
        "name": "Buy now", "control_type": "Text", "visible": True,
        "enabled": True,
        "bounds": {"left": 1, "top": 1, "right": 20, "bottom": 20},
    }]
    result = inspect_order_form_controls(
        123, inspector=lambda _hwnd: {"status": "inspected", "controls": controls}
    )
    assert result["manual_action_targets"] == []
