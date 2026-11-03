from trendo_order_form_layout import analyze_order_form_layout


def _word(text, left, top, right, bottom, confidence=96):
    return {
        "text": text,
        "confidence": confidence,
        "bounds_screen": {
            "left": left, "top": top, "right": right, "bottom": bottom,
        },
    }


def test_maps_tp_and_sl_to_same_row_numeric_candidates_only():
    report = {
        "words": [
            _word("Take", 100, 100, 150, 125),
            _word("profit", 155, 100, 220, 125),
            _word("12.50", 500, 101, 560, 125),
            _word("Stop", 100, 180, 150, 205),
            _word("loss", 155, 180, 205, 205),
            _word("5.00", 500, 181, 550, 205),
            _word("0.02", 300, 400, 350, 425),
        ],
        "lines": [
            {"text": "Take profit", "candidate": True},
            {"text": "Stop loss", "candidate": True},
        ],
    }
    result = analyze_order_form_layout(report)
    fields = {item["field"]: item for item in result["fields"]}
    assert fields["take_profit"]["value_candidate"] == "12.50"
    assert fields["stop_loss"]["value_candidate"] == "5.00"
    assert fields["take_profit"]["candidate_verified"] is False
    assert result["execution_enabled"] is False
    assert result["execution_status"] == "blocked_unverified_ui"


def test_does_not_associate_distant_volume_number():
    report = {
        "words": [
            _word("Size:", 100, 100, 160, 125),
            _word("0.02", 600, 400, 650, 425),
        ],
        "lines": [],
    }
    result = analyze_order_form_layout(report)
    volume = next(item for item in result["fields"] if item["field"] == "volume")
    assert volume["value_candidate"] is None
    assert volume["candidate_verified"] is False


def test_empty_report_stays_blocked():
    result = analyze_order_form_layout({})
    assert result["fields"] == []
    assert result["execution_enabled"] is False
    assert result["execution_status"] == "blocked_unverified_ui"
