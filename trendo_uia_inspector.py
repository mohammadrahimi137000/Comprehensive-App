"""Detailed, strictly read-only UI Automation inventory for Trendo.

The inspector never invokes controls, sends keystrokes, changes values, or submits
orders. Flutter/canvas-rendered controls may remain absent from the accessibility
tree; missing controls are reported as an accessibility limitation, not inferred.
"""
from __future__ import annotations

import sys
from typing import Any


def _safe(call, default=None):
    try:
        return call()
    except Exception:
        return default


def inspect_trendo_window_detailed(hwnd: int, max_controls: int = 1200) -> dict:
    """Recursively inventory all UIA descendants and classify order-form candidates."""
    if sys.platform != "win32":
        return {
            "status": "unsupported_platform",
            "hwnd": hwnd,
            "controls": [],
            "order_form_candidates": [],
            "execution_enabled": False,
        }
    if not isinstance(hwnd, int) or hwnd <= 0:
        raise ValueError("A valid positive HWND is required")
    if not isinstance(max_controls, int) or max_controls < 1:
        raise ValueError("max_controls must be a positive integer")

    try:
        from pywinauto import Desktop
    except ImportError:
        return {
            "status": "dependency_missing",
            "message": "pywinauto نصب نیست؛ بررسی UI Automation ممکن نیست.",
            "controls": [],
            "order_form_candidates": [],
            "execution_enabled": False,
        }

    try:
        window = Desktop(backend="uia").window(handle=hwnd)
        if not window.exists(timeout=2):
            return {
                "status": "window_unavailable", "hwnd": hwnd,
                "controls": [], "order_form_candidates": [],
                "execution_enabled": False,
            }

        root_info = window.element_info
        rows: list[dict[str, Any]] = []
        wrappers = list(window.descendants())
        # UIA descendants are already recursively enumerated by pywinauto.
        # Build stable parent links when the provider exposes parent() reliably.
        wrapper_ids = {id(item): index for index, item in enumerate(wrappers)}
        for index, control in enumerate(wrappers[:max_controls]):
            info = control.element_info
            rect = _safe(lambda: info.rectangle)
            bounds = None
            if rect is not None:
                bounds = {
                    "left": int(rect.left), "top": int(rect.top),
                    "right": int(rect.right), "bottom": int(rect.bottom),
                }
            parent_index = None
            parent = _safe(lambda: control.parent())
            if parent is not None:
                parent_index = wrapper_ids.get(id(parent))
            runtime_id = _safe(lambda: list(info.runtime_id), None)
            value = _safe(lambda: control.get_value(), None)
            if value is not None:
                value = str(value)[:500]
            name = str(_safe(lambda: info.name, "") or "")[:300]
            control_type = str(_safe(lambda: info.control_type, "") or "")[:100]
            automation_id = str(_safe(lambda: info.automation_id, "") or "")[:160]
            class_name = str(_safe(lambda: info.class_name, "") or "")[:160]
            framework_id = str(_safe(lambda: info.framework_id, "") or "")[:100]
            native_handle = _safe(lambda: int(info.handle), None)
            row = {
                "index": index,
                "parent_index": parent_index,
                "name": name,
                "control_type": control_type,
                "automation_id": automation_id,
                "class_name": class_name,
                "framework_id": framework_id,
                "runtime_id": runtime_id,
                "native_window_handle": native_handle,
                "process_id": _safe(lambda: int(info.process_id), None),
                "value": value,
                "is_enabled": bool(_safe(lambda: info.enabled, False)),
                "is_visible": bool(_safe(lambda: info.visible, False)),
                "bounds": bounds,
            }
            rows.append(row)

        # Order-related items are candidates only. Text labels are included so
        # Flutter's flattened accessibility tree can still be inspected.
        order_terms = (
            "order", "buy", "sell", "price", "volume", "lot", "size",
            "stop loss", "take profit", "sl", "tp", "ثبت", "خرید",
            "فروش", "حد ضرر", "حد سود", "قیمت", "حجم",
        )
        candidate_indexes = set()
        for row in rows:
            searchable = " ".join((
                row["name"], row["value"] or "", row["automation_id"],
                row["class_name"],
            )).casefold()
            if any(term in searchable for term in order_terms):
                candidate_indexes.add(row["index"])
                if row["parent_index"] is not None:
                    candidate_indexes.add(row["parent_index"])
            if row["control_type"] in {"Edit", "ComboBox", "Button", "CheckBox", "RadioButton"}:
                candidate_indexes.add(row["index"])

        order_candidates = [
            {**row, "candidate_reason": (
                "order_related_label_or_value"
                if any(term in " ".join((row["name"], row["value"] or "")).casefold()
                       for term in order_terms)
                else "interactive_control_type"
            ), "verified": False}
            for row in rows if row["index"] in candidate_indexes
        ]
        nonempty = sum(bool(
            row["name"] or row["control_type"] or row["automation_id"]
            or row["class_name"] or row["value"]
        ) for row in rows)
        return {
            "status": "inspected",
            "hwnd": hwnd,
            "root": {
                "name": str(_safe(lambda: root_info.name, "") or ""),
                "class_name": str(_safe(lambda: root_info.class_name, "") or ""),
                "framework_id": str(_safe(lambda: root_info.framework_id, "") or ""),
                "process_id": _safe(lambda: int(root_info.process_id), None),
            },
            "enumeration": "recursive_uia_descendants",
            "controls": rows,
            "control_count": len(rows),
            "nonempty_control_count": nonempty,
            "order_form_candidates": order_candidates,
            "truncated": len(wrappers) > max_controls,
            "accessibility_warning": (
                "اگر Trendo بخشی از رابط را با Flutter Canvas یا تصویر رسم کند، "
                "آن بخش ممکن است در UI Automation دیده نشود. نبودن کنترل در این فهرست "
                "به معنی نبودن آن روی صفحه نیست."
            ),
            "execution_enabled": False,
            "execution_status": "blocked_unverified_ui",
            "message": (
                "فقط اطلاعات قابل‌دسترسی UI Automation خوانده شد؛ هیچ کلیک، "
                "تغییر مقدار، فشردن کلید یا ثبت سفارشی انجام نشد."
            ),
        }
    except Exception as exc:
        return {
            "status": "inspection_error",
            "hwnd": hwnd,
            "error": f"{type(exc).__name__}: {exc}",
            "controls": [],
            "order_form_candidates": [],
            "execution_enabled": False,
        }
