from trendo_connector import classify_trendo_window, connection_report


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
