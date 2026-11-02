from trend_following_strategy import PositionSnapshot, TrendFollowingPolicy


def test_starts_with_one_order_in_confirmed_m5_direction():
    policy = TrendFollowingPolicy(enabled=True)
    intents = policy.evaluate(100, "bearish", [])
    assert [(i.action, i.side, i.reason) for i in intents] == [
        ("OPEN", "SELL", "initial_m5_trend_entry")
    ]


def test_no_entry_when_m5_trend_is_sideways_or_unknown():
    policy = TrendFollowingPolicy(enabled=True)
    assert policy.evaluate(100, "sideways", []) == []
    assert policy.evaluate(103, "unknown", []) == []


def test_adds_only_after_a_new_position_becomes_profitable_and_in_trend():
    policy = TrendFollowingPolicy(enabled=True)
    policy.evaluate(100, "bearish", [PositionSnapshot("s1", "SELL", -0.1)])
    # A starter position turning profitable is a new profit confirmation.
    added = policy.evaluate(102, "bearish", [PositionSnapshot("s1", "SELL", 0.2)])
    assert [(i.action, i.side, i.reason) for i in added] == [
        ("OPEN", "SELL", "add_after_new_profitable_position:s1")
    ]
    assert policy.evaluate(104, "bearish", [PositionSnapshot("s1", "SELL", 0.3)]) == []


def test_does_not_add_again_for_same_winner_or_against_m5_trend():
    policy = TrendFollowingPolicy(enabled=True)
    policy.evaluate(100, "bearish", [PositionSnapshot("s1", "SELL", 0.1)])
    assert policy.evaluate(102, "bullish", [PositionSnapshot("s1", "SELL", 0.2)]) == []
    assert policy.evaluate(104, "bearish", [PositionSnapshot("s1", "SELL", 0.3)]) == []


def test_stop_loss_requests_close_then_waits_for_ticket_to_disappear_before_hedge():
    policy = TrendFollowingPolicy(enabled=True)
    losing = [PositionSnapshot("s1", "SELL", -0.5)]
    close = policy.evaluate(100, "bearish", losing)
    assert [(i.action, i.position_id, i.reason) for i in close] == [
        ("CLOSE", "s1", "stop_loss")
    ]
    # Still visible: do not submit recovery orders before close is confirmed.
    assert policy.evaluate(102, "bearish", losing) == []
    # A fresh verified snapshot no longer contains the stopped ticket.
    pair = policy.evaluate(104, "bearish", [])
    assert [(i.action, i.side, i.reason) for i in pair] == [
        ("OPEN", "BUY", "recovery_hedge_after_stop"),
        ("OPEN", "SELL", "recovery_hedge_after_stop"),
    ]


def test_take_profit_closes_only_the_matching_position():
    policy = TrendFollowingPolicy(enabled=True)
    intents = policy.evaluate(
        100, "bullish",
        [PositionSnapshot("a", "BUY", 1.0), PositionSnapshot("b", "SELL", 0.2)],
    )
    assert [(i.action, i.position_id, i.reason) for i in intents] == [
        ("CLOSE", "a", "take_profit")
    ]


def test_two_second_interval_and_ten_position_cap():
    policy = TrendFollowingPolicy(enabled=True, max_open_positions=10)
    policy.evaluate(100, "bullish", [])
    assert policy.evaluate(101.9, "bullish", []) == []
    # A newly profitable ticket can trigger an add, but not beyond the cap.
    full = [PositionSnapshot(str(i), "BUY", 0.2) for i in range(10)]
    assert policy.evaluate(102, "bullish", full) == []
