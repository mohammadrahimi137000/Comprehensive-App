"""Capture a visible chart window locally for a manual trade-journal attachment."""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import cv2
import mss
import numpy as np
import win32gui



def capture_window_frame(hwnd: int) -> tuple[np.ndarray, tuple[int, int]]:
    """Capture a visible window into memory without creating a screenshot file."""
    if not win32gui.IsWindow(hwnd) or not win32gui.IsWindowVisible(hwnd) or win32gui.IsIconic(hwnd):
        raise RuntimeError("Chart window is not currently visible")
    left, top, right, bottom = win32gui.GetWindowRect(hwnd)
    if right - left < 100 or bottom - top < 100:
        raise RuntimeError("Chart window bounds are invalid")
    with mss.MSS() as screen:
        virtual = screen.monitors[0]
        capture = {
            "left": max(left, virtual["left"]),
            "top": max(top, virtual["top"]),
            "right": min(right, virtual["left"] + virtual["width"]),
            "bottom": min(bottom, virtual["top"] + virtual["height"]),
        }
        if capture["right"] <= capture["left"] or capture["bottom"] <= capture["top"]:
            raise RuntimeError("Chart window is outside the visible desktop")
        region = {
            "left": capture["left"], "top": capture["top"],
            "width": capture["right"] - capture["left"],
            "height": capture["bottom"] - capture["top"],
        }
        frame = np.asarray(screen.grab(region))
    image = cv2.cvtColor(frame, cv2.COLOR_BGRA2BGR)
    return image, (capture["left"], capture["top"])


def capture_window_screenshot(hwnd: int, output_dir: str | Path = "data/screenshots") -> str:
    if not win32gui.IsWindow(hwnd) or not win32gui.IsWindowVisible(hwnd) or win32gui.IsIconic(hwnd):
        raise RuntimeError("Chart window is not currently visible")
    left, top, right, bottom = win32gui.GetWindowRect(hwnd)
    if right - left < 100 or bottom - top < 100:
        raise RuntimeError("Chart window bounds are invalid")
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    path = output / f"chart_{int(hwnd)}_{stamp}.png"

    with mss.MSS() as screen:
        virtual = screen.monitors[0]
        capture = {
            "left": max(left, virtual["left"]),
            "top": max(top, virtual["top"]),
            "right": min(right, virtual["left"] + virtual["width"]),
            "bottom": min(bottom, virtual["top"] + virtual["height"]),
        }
        if capture["right"] <= capture["left"] or capture["bottom"] <= capture["top"]:
            raise RuntimeError("Chart window is outside the visible desktop")
        region = {
            "left": capture["left"], "top": capture["top"],
            "width": capture["right"] - capture["left"],
            "height": capture["bottom"] - capture["top"],
        }
        frame = np.asarray(screen.grab(region))
    image = cv2.cvtColor(frame, cv2.COLOR_BGRA2BGR)
    if not cv2.imwrite(str(path), image):
        raise RuntimeError("Could not save chart screenshot")
    return str(path)
