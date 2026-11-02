"""Read-only discovery of Trendo desktop/browser windows.

This module deliberately does not click, type, submit, or modify orders. Trendo
has no supported public trading API in this project; visual order execution
must not be enabled until controls and post-submit verification are validated.
"""
from __future__ import annotations

import ctypes
import os
import sys
from dataclasses import asdict, dataclass
from typing import Callable


@dataclass(frozen=True)
class TrendoWindow:
    hwnd: int
    title: str
    process_id: int
    process_path: str
    kind: str  # "browser" or "desktop"


def classify_trendo_window(title: str, process_path: str = "") -> str | None:
    """Return browser/desktop only for positively identified Trendo windows."""
    title_text = (title or "").casefold()
    path_text = (process_path or "").replace("/", "\\").casefold()
    browser_processes = ("\\chrome.exe", "\\msedge.exe", "\\firefox.exe", "\\brave.exe", "\\opera.exe")
    desktop_markers = ("trendo.exe", "trendo terminal", "trendo trading")
    if any(marker in path_text for marker in desktop_markers):
        return "desktop"
    if any(marker in title_text for marker in ("trendo", "trendo.com")):
        return "browser" if any(path_text.endswith(name) for name in browser_processes) else "desktop"
    return None


def _process_path(pid: int) -> str:
    if sys.platform != "win32":
        return ""
    PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
    handle = ctypes.windll.kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, int(pid))
    if not handle:
        return ""
    try:
        buffer = ctypes.create_unicode_buffer(32768)
        size = ctypes.c_ulong(len(buffer))
        if ctypes.windll.kernel32.QueryFullProcessImageNameW(handle, 0, buffer, ctypes.byref(size)):
            return buffer.value
        return ""
    finally:
        ctypes.windll.kernel32.CloseHandle(handle)


def discover_trendo_windows(enumerator: Callable | None = None) -> list[dict]:
    """Find visible Trendo windows without interacting with the trading UI."""
    if sys.platform != "win32":
        return []
    import win32gui
    import win32process

    rows: list[dict] = []

    def visit(hwnd, _):
        try:
            if not win32gui.IsWindowVisible(hwnd) or win32gui.IsIconic(hwnd):
                return
            title = win32gui.GetWindowText(hwnd).strip()
            if not title:
                return
            _, pid = win32process.GetWindowThreadProcessId(hwnd)
            path = _process_path(pid)
            kind = classify_trendo_window(title, path)
            if kind:
                rect = win32gui.GetWindowRect(hwnd)
                if rect[2] - rect[0] < 250 or rect[3] - rect[1] < 150:
                    return
                rows.append(asdict(TrendoWindow(
                    hwnd=int(hwnd), title=title, process_id=int(pid),
                    process_path=path, kind=kind,
                )))
                rows[-1]["bounds"] = list(rect)
        except Exception:
            return

    (enumerator or win32gui.EnumWindows)(visit, None)
    # Deduplicate HWNDs defensively.
    return list({row["hwnd"]: row for row in rows}.values())


def connection_report(windows: list[dict]) -> dict:
    browser = [w for w in windows if w.get("kind") == "browser"]
    desktop = [w for w in windows if w.get("kind") == "desktop"]
    return {
        "status": "detected" if windows else "not_detected",
        "browser_windows": browser,
        "desktop_windows": desktop,
        "execution_enabled": False,
        "execution_status": "blocked_unverified_ui",
        "message": (
            "Trendo شناسایی شد؛ اتصال فعلاً فقط مشاهده‌ای است. "
            "اجرای سفارش تا اعتبارسنجی کنترل‌ها و تأیید پس از ثبت غیرفعال است."
            if windows else "پنجره Trendo پیدا نشد؛ نسخه ویندوز یا صفحه Trendo را باز کنید."
        ),
    }
