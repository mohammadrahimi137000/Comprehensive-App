from trendo_connector import classify_trendo_window, connection_report, inspect_trendo_controls


def test_classifies_trendo_chrome_window():
    assert classify_trendo_window("GOLD - Trendo", r"C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe") == "browser"


def test_classifies_trendo_desktop_window():
    assert classify_trendo_window("Trendo Trading", r"C:\\Apps\\Trendo\\trendo.exe") == "desktop"


def test_rejects_unrelated_windows():
    assert classify_trendo_window("Microsoft Store", r"C:\\Windows\\System32\\ApplicationFrameHost.exe") is None


def test_execution_is_blocked_until_ui_validation():
    report = connection_report([{"kind": "browser", "title": "Trendo"}])
    assert report["status"] == "detected"
    assert report["execution_enabled"] is False
    assert report["execution_status"] == "blocked_unverified_ui"



def test_control_inspection_rejects_invalid_handle():
    import pytest
    with pytest.raises(ValueError):
        inspect_trendo_controls(0)


def test_control_inspection_rejects_invalid_limit():
    import pytest
    with pytest.raises(ValueError):
        inspect_trendo_controls(123, max_controls=0)


def test_parses_trendo_position_and_net_pnl():
    from trendo_connector import parse_trendo_position_row

    row = "GOLD\n217396516\nSell\n  0.02\n2026/11/03 00:44:03\n3947.28\n3945.21\n0.00\n0.00\n-0.06\n$4.14"
    parsed = parse_trendo_position_row(row)
    assert parsed["position_id"] == "217396516"
    assert parsed["side"] == "SELL"
    assert parsed["volume"] == 0.02
    assert parsed["net_pnl_usd"] == 4.08


def test_rejects_incomplete_or_unknown_position_rows():
    import pytest
    from trendo_connector import parse_trendo_position_row

    with pytest.raises(ValueError):
        parse_trendo_position_row("GOLD\n123456\nBUY\n0.02")
    with pytest.raises(ValueError):
        parse_trendo_position_row("GOLD\n123456\nHOLD\n0.02\n2026/11/03 00:00:00\n1\n0\n0\n0\n0\n0")


def test_positions_parser_marks_duplicate_tickets_ambiguous():
    from trendo_connector import parse_trendo_positions

    row = "GOLD\n217396516\nSell\n0.02\n2026/11/03 00:44:03\n3947.28\n3945.21\n0.00\n0.00\n-0.06\n$4.14"
    result = parse_trendo_positions([
        {"control_type": "Group", "name": row},
        {"control_type": "Group", "name": row},
    ])
    assert result["status"] == "ambiguous_duplicate_ticket"
    assert result["positions"] == []
