from trendo_uia_inspector import inspect_trendo_window_detailed


def test_detailed_inspector_rejects_invalid_hwnd():
    import pytest
    with pytest.raises(ValueError):
        inspect_trendo_window_detailed(0)


def test_detailed_inspector_rejects_invalid_limit():
    import pytest
    with pytest.raises(ValueError):
        inspect_trendo_window_detailed(123, max_controls=0)


def test_detailed_inspector_is_read_only_on_non_windows(monkeypatch):
    import trendo_uia_inspector as inspector
    monkeypatch.setattr(inspector.sys, "platform", "linux")
    result = inspector.inspect_trendo_window_detailed(123)
    assert result["status"] == "unsupported_platform"
    assert result["execution_enabled"] is False
