"""Read-only Trendo position polling and automatic P/L journal synchronization."""
from __future__ import annotations

from datetime import datetime, timezone

from trendo_connector import (
    discover_trendo_windows,
    inspect_trendo_controls,
    parse_trendo_positions,
)
from trendo_position_journal import TrendoPositionJournal


class TrendoPositionSync:
    """Poll visible Trendo rows and persist verified per-ticket P/L snapshots."""

    def __init__(self, journal: TrendoPositionJournal):
        self.journal = journal

    def poll_once(self) -> dict:
        windows = discover_trendo_windows()
        if not windows:
            return {
                "status": "trendo_not_detected",
                "recorded": 0,
                "positions": [],
                "execution_enabled": False,
            }

        all_positions = []
        window_reports = []
        for window in windows:
            report = inspect_trendo_controls(int(window["hwnd"]))
            parsed = parse_trendo_positions(report.get("controls", []))
            window_reports.append({
                "title": window.get("title", ""),
                "inspection_status": report.get("status"),
                "parsed_status": parsed.get("status"),
                "rejected": parsed.get("rejected", []),
            })
            # Only complete, unambiguous parser results may be persisted.
            if parsed.get("status") == "ok":
                all_positions.extend(parsed["positions"])

        tickets = [item["position_id"] for item in all_positions]
        if len(tickets) != len(set(tickets)):
            return {
                "status": "ambiguous_multiple_windows",
                "recorded": 0,
                "positions": [],
                "windows": window_reports,
                "execution_enabled": False,
            }

        # An empty or partial scan is not treated as proof that positions closed.
        if not all_positions:
            return {
                "status": "no_verified_positions",
                "recorded": 0,
                "positions": [],
                "windows": window_reports,
                "execution_enabled": False,
            }

        captured_at = datetime.now(timezone.utc)
        recorded = self.journal.record_positions(all_positions, captured_at)
        return {
            "status": "ok",
            "captured_at": captured_at.isoformat(),
            "recorded": recorded,
            "positions": all_positions,
            "windows": window_reports,
            "execution_enabled": False,
            "note": (
                "فقط سود و زیان شناورِ ردیف‌های قابل‌تأیید ذخیره شد؛ "
                "ناپدیدشدن ردیف به‌معنی بسته‌شدن معامله فرض نمی‌شود."
            ),
        }
