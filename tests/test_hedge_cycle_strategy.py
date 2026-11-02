from hedge_cycle_strategy import HedgeCyclePolicy, PositionSnapshot


def test_disabled_policy_emits_no_intents():
    policy = HedgeCyclePolicy()
    assert policy.evaluate(0, []) == []


def test_starts_with_buy_and_sell_and_respects_five_second_interval():
    policy = HedgeCyclePolicy(enabled=True)
    intents = policy.evaluate(100, [])
    assert [(x.action, x.side) for x in intents] == [("OPEN", "BUY"), ("OPEN", "SELL")]
    assert policy.evaluate(104.9, []) == []
    assert [(x.action, x.side) for x in policy.evaluate(105, [])] == [
        ("OPEN", "BUY"), ("OPEN", "SELL")
    ]


def test_closes_each_position_at_independent_usd_threshold():
    policy = HedgeCyclePolicy(enabled=True)
    positions = [
        PositionSnapshot("a", "BUY", 1.0),
        PositionSnapshot("b", "SELL", -0.5),
        PositionSnapshot("c", "BUY", 0.4),
    ]
    intents = policy.evaluate(100, positions)
    assert [(x.action, x.position_id, x.reason) for x in intents] == [
        ("CLOSE", "a", "take_profit"),
        ("CLOSE", "b", "stop_loss"),
    ]


def test_adds_only_profitable_leader_direction_after_winner_exists():
    policy = HedgeCyclePolicy(enabled=True)
    positions = [
        PositionSnapshot("a", "SELL", 0.3),
        PositionSnapshot("b", "BUY", -0.1),
    ]
    intents = policy.evaluate(100, positions)
    assert [(x.action, x.side) for x in intents] == [("OPEN", "SELL")]


def test_open_position_cap_prevents_new_exposure():
    policy = HedgeCyclePolicy(enabled=True, max_open_positions=2)
    positions = [
        PositionSnapshot("a", "BUY", -0.1),
        PositionSnapshot("b", "SELL", -0.1),
    ]
    assert policy.evaluate(100, positions) == []
