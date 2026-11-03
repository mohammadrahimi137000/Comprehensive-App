import pytest

import trendo_visual_inspector as visual


def test_rejects_invalid_hwnd():
    with pytest.raises(ValueError):
        visual.inspect_trendo_visual_ocr(0)


def test_rejects_invalid_confidence():
    with pytest.raises(ValueError):
        visual.inspect_trendo_visual_ocr(123, min_confidence=101)


def test_non_windows_is_read_only_and_unsupported(monkeypatch):
    monkeypatch.setattr(visual.sys, "platform", "linux")
    result = visual.inspect_trendo_visual_ocr(123)
    assert result["status"] == "unsupported_platform"
    assert result["execution_enabled"] is False
    assert result["words"] == []
