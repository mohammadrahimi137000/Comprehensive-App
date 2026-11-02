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


def inspect_trendo_controls(hwnd: int, max_controls: int = 250) -> dict:
    """Return a read-only UI Automation inventory for a positively identified window.

    No click, keyboard input, value change, order submission, or close action is
    performed. UIA support is optional; browser content may be unavailable unless
    the browser exposes its accessibility tree.
    """
    if sys.platform != "win32":
        return {"status": "unsupported_platform", "controls": [], "execution_enabled": False}
    if not isinstance(hwnd, int) or hwnd <= 0 or max_controls < 1:
        raise ValueError("A valid HWND and positive max_controls are required")

    try:
        from pywinauto import Desktop
    except ImportError:
        return {
            "status": "dependency_missing",
            "message": "برای بررسی فقط‌خواندنی کنترل‌ها، pywinauto نصب نیست.",
            "controls": [],
            "execution_enabled": False,
        }

    try:
        window = Desktop(backend="uia").window(handle=hwnd)
        if not window.exists(timeout=2):
            return {"status": "window_unavailable", "controls": [], "execution_enabled": False}
        controls = []
        for control in window.descendants():
            if len(controls) >= max_controls:
                break
            try:
                info = control.element_info
                name = (info.name or "").strip()
                control_type = (info.control_type or "").strip()
                automation_id = (info.automation_id or "").strip()
                class_name = (info.class_name or "").strip()
                if not any((name, control_type, automation_id, class_name)):
                    continue
                try:
                    rect = info.rectangle
                    bounds = {
                        "left": int(rect.left), "top": int(rect.top),
                        "right": int(rect.right), "bottom": int(rect.bottom),
                    }
                except Exception:
                    bounds = None
                try:
                    value = control.get_value()
                    value = str(value)[:200] if value is not None else None
                except Exception:
                    value = None
                controls.append({
                    "name": name[:240],
                    "control_type": control_type[:80],
                    "automation_id": automation_id[:120],
                    "class_name": class_name[:120],
                    "enabled": bool(info.enabled),
                    "visible": bool(info.visible),
                    "bounds": bounds,
                    "value": value,
                })
            except Exception:
                continue
        return {
            "status": "inspected",
            "hwnd": hwnd,
            "controls": controls,
            "truncated": len(controls) >= max_controls,
            "execution_enabled": False,
            "message": "فهرست کنترل‌ها فقط خوانده شده؛ هیچ تعاملی با پنل انجام نشده است.",
        }
    except Exception as exc:
        return {
            "status": "inspection_error",
            "error": f"{type(exc).__name__}: {exc}",
            "controls": [],
            "execution_enabled": False,
        }
