"""Automatic, read-only synchronization of visible Trendo position P/L.

This module records verified open-position snapshots. It never clicks the UI,
submits orders, or infers a realized close result from a disappearing row.
"""
from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable


class TrendoPositionJournal:
    """Persist one current row and an append-only P/L history per ticket."""

    def __init__(self, database_path: str | Path = "data/market.db"):
        self.database_path = Path(database_path)
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(self.database_path) as db:
            db.execute("""
                CREATE TABLE IF NOT EXISTS trendo_positions (
                    position_id TEXT PRIMARY KEY,
                    symbol TEXT NOT NULL,
                    side TEXT NOT NULL CHECK(side IN ('BUY', 'SELL')),
                    volume REAL NOT NULL,
                    opened_at TEXT NOT NULL,
                    open_price REAL NOT NULL,
                    stop_loss REAL NOT NULL,
                    take_profit REAL NOT NULL,
                    swap_usd REAL NOT NULL,
                    commission_usd REAL NOT NULL,
                    floating_profit_usd REAL NOT NULL,
                    net_pnl_usd REAL NOT NULL,
                    first_seen_at TEXT NOT NULL,
                    last_seen_at TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'open'
                        CHECK(status IN ('open', 'not_seen'))
                )
            """)
            db.execute("""
                CREATE TABLE IF NOT EXISTS trendo_position_pnl_history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    position_id TEXT NOT NULL,
                    captured_at TEXT NOT NULL,
                    floating_profit_usd REAL NOT NULL,
                    swap_usd REAL NOT NULL,
                    commission_usd REAL NOT NULL,
                    net_pnl_usd REAL NOT NULL,
                    FOREIGN KEY(position_id) REFERENCES trendo_positions(position_id)
                )
            """)
            db.execute("""
                CREATE INDEX IF NOT EXISTS idx_trendo_pnl_ticket_time
                ON trendo_position_pnl_history(position_id, captured_at)
            """)

    @staticmethod
    def _validate(position: dict) -> dict:
        required = (
            "position_id", "symbol", "side", "volume", "opened_at",
            "open_price", "stop_loss", "take_profit", "swap_usd",
            "commission_usd", "floating_profit_usd", "net_pnl_usd",
        )
        missing = [key for key in required if key not in position]
        if missing:
            raise ValueError(f"Missing position fields: {', '.join(missing)}")
        row = dict(position)
        row["position_id"] = str(row["position_id"]).strip()
        row["symbol"] = str(row["symbol"]).strip().upper()
        row["side"] = str(row["side"]).strip().upper()
        if not row["position_id"] or row["side"] not in {"BUY", "SELL"}:
            raise ValueError("Invalid ticket or side")
        for key in (
            "volume", "open_price", "stop_loss", "take_profit",
            "swap_usd", "commission_usd", "floating_profit_usd", "net_pnl_usd",
        ):
            row[key] = float(row[key])
        if row["volume"] <= 0 or row["open_price"] <= 0:
            raise ValueError("Volume and open price must be positive")
        expected_net = (
            row["floating_profit_usd"] + row["swap_usd"] + row["commission_usd"]
        )
        if abs(expected_net - row["net_pnl_usd"]) > 0.011:
            raise ValueError("Net P/L does not match floating P/L + swap + commission")
        return row

    def record_positions(
        self, positions: Iterable[dict], captured_at: datetime | None = None
    ) -> int:
        """Upsert current snapshots; repeated polling never creates duplicate tickets."""
        captured_at = captured_at or datetime.now(timezone.utc)
        if captured_at.tzinfo is None:
            raise ValueError("captured_at must be timezone-aware")
        timestamp = captured_at.astimezone(timezone.utc).isoformat()
        rows = [self._validate(item) for item in positions]
        ids = [row["position_id"] for row in rows]
        if len(ids) != len(set(ids)):
            raise ValueError("Duplicate position ticket in one snapshot")

        with sqlite3.connect(self.database_path) as db:
            for row in rows:
                values = (
                    row["position_id"], row["symbol"], row["side"], row["volume"],
                    row["opened_at"], row["open_price"], row["stop_loss"],
                    row["take_profit"], row["swap_usd"], row["commission_usd"],
                    row["floating_profit_usd"], row["net_pnl_usd"], timestamp, timestamp,
                )
                db.execute("""
                    INSERT INTO trendo_positions (
                        position_id, symbol, side, volume, opened_at, open_price,
                        stop_loss, take_profit, swap_usd, commission_usd,
                        floating_profit_usd, net_pnl_usd, first_seen_at, last_seen_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(position_id) DO UPDATE SET
                        symbol=excluded.symbol, side=excluded.side,
                        volume=excluded.volume, opened_at=excluded.opened_at,
                        open_price=excluded.open_price, stop_loss=excluded.stop_loss,
                        take_profit=excluded.take_profit, swap_usd=excluded.swap_usd,
                        commission_usd=excluded.commission_usd,
                        floating_profit_usd=excluded.floating_profit_usd,
                        net_pnl_usd=excluded.net_pnl_usd,
                        last_seen_at=excluded.last_seen_at, status='open'
                """, values)
                db.execute("""
                    INSERT INTO trendo_position_pnl_history (
                        position_id, captured_at, floating_profit_usd,
                        swap_usd, commission_usd, net_pnl_usd
                    ) VALUES (?, ?, ?, ?, ?, ?)
                """, (
                    row["position_id"], timestamp, row["floating_profit_usd"],
                    row["swap_usd"], row["commission_usd"], row["net_pnl_usd"],
                ))
        return len(rows)

    def list_positions(self, status: str = "open", limit: int = 500) -> list[dict]:
        if status not in {"open", "not_seen", "all"}:
            raise ValueError("status must be open, not_seen, or all")
        if not 1 <= int(limit) <= 10000:
            raise ValueError("limit must be between 1 and 10000")
        query = "SELECT * FROM trendo_positions"
        params: list[object] = []
        if status != "all":
            query += " WHERE status=?"
            params.append(status)
        query += " ORDER BY last_seen_at DESC LIMIT ?"
        params.append(int(limit))
        with sqlite3.connect(self.database_path) as db:
            db.row_factory = sqlite3.Row
            return [dict(row) for row in db.execute(query, params).fetchall()]

    def pnl_history(self, position_id: str, limit: int = 1000) -> list[dict]:
        if not 1 <= int(limit) <= 10000:
            raise ValueError("limit must be between 1 and 10000")
        with sqlite3.connect(self.database_path) as db:
            db.row_factory = sqlite3.Row
            rows = db.execute("""
                SELECT captured_at, floating_profit_usd, swap_usd,
                       commission_usd, net_pnl_usd
                FROM trendo_position_pnl_history
                WHERE position_id=? ORDER BY id DESC LIMIT ?
            """, (str(position_id), int(limit))).fetchall()
        return [dict(row) for row in rows]
