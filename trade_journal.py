"""Manual trade journal. This module records notes only and never sends orders."""
from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from pathlib import Path


class TradeJournal:
    def __init__(self, database_path: str | Path = "data/market.db"):
        self.database_path = Path(database_path)
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(self.database_path) as connection:
            connection.execute("""
                CREATE TABLE IF NOT EXISTS trade_journal (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    symbol TEXT NOT NULL,
                    direction TEXT NOT NULL CHECK(direction IN ('long', 'short')),
                    entry_price REAL NOT NULL CHECK(entry_price > 0),
                    stop_loss REAL NOT NULL CHECK(stop_loss > 0),
                    take_profit REAL,
                    opened_at TEXT NOT NULL,
                    closed_at TEXT,
                    exit_price REAL,
                    outcome_r REAL,
                    screenshot_path TEXT,
                    notes TEXT NOT NULL DEFAULT '',
                    status TEXT NOT NULL DEFAULT 'open' CHECK(status IN ('open', 'closed'))
                )
            """)

    @staticmethod
    def _validate_prices(direction, entry, stop, target):
        if direction not in {"long", "short"}:
            raise ValueError("direction must be 'long' or 'short'")
        if entry <= 0 or stop <= 0 or entry == stop:
            raise ValueError("Entry and stop must be positive and different")
        if direction == "long" and stop >= entry:
            raise ValueError("Long stop loss must be below entry")
        if direction == "short" and stop <= entry:
            raise ValueError("Short stop loss must be above entry")
        if target is not None:
            if target <= 0:
                raise ValueError("Take profit must be positive")
            if direction == "long" and target <= entry:
                raise ValueError("Long take profit must be above entry")
            if direction == "short" and target >= entry:
                raise ValueError("Short take profit must be below entry")

    def create_trade(
        self, symbol: str, direction: str, entry_price: float,
        stop_loss: float, take_profit: float | None = None,
        screenshot_path: str | None = None, notes: str = "",
        opened_at: datetime | None = None,
    ) -> int:
        symbol = symbol.strip().upper()
        if not symbol:
            raise ValueError("symbol is required")
        entry, stop = float(entry_price), float(stop_loss)
        target = float(take_profit) if take_profit is not None else None
        self._validate_prices(direction, entry, stop, target)
        opened_at = opened_at or datetime.now(timezone.utc)
        if opened_at.tzinfo is None:
            raise ValueError("opened_at must be timezone-aware")
        with sqlite3.connect(self.database_path) as connection:
            cursor = connection.execute("""
                INSERT INTO trade_journal
                    (symbol, direction, entry_price, stop_loss, take_profit,
                     opened_at, screenshot_path, notes)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                symbol, direction, entry, stop, target,
                opened_at.astimezone(timezone.utc).isoformat(),
                screenshot_path, notes,
            ))
            return int(cursor.lastrowid)

    def close_trade(self, trade_id: int, exit_price: float,
                    closed_at: datetime | None = None) -> float:
        exit_value = float(exit_price)
        if exit_value <= 0:
            raise ValueError("exit price must be positive")
        closed_at = closed_at or datetime.now(timezone.utc)
        if closed_at.tzinfo is None:
            raise ValueError("closed_at must be timezone-aware")
        with sqlite3.connect(self.database_path) as connection:
            row = connection.execute(
                "SELECT direction, entry_price, stop_loss, status "
                "FROM trade_journal WHERE id=?", (int(trade_id),)
            ).fetchone()
            if row is None:
                raise ValueError("trade not found")
            direction, entry, stop, status = row
            if status != "open":
                raise ValueError("trade is already closed")
            risk = abs(entry - stop)
            pnl = exit_value - entry if direction == "long" else entry - exit_value
            outcome_r = pnl / risk
            connection.execute("""
                UPDATE trade_journal
                SET exit_price=?, outcome_r=?, closed_at=?, status='closed'
                WHERE id=? AND status='open'
            """, (
                exit_value, outcome_r, closed_at.astimezone(timezone.utc).isoformat(),
                int(trade_id),
            ))
        return round(outcome_r, 4)

    def list_trades(self, symbol: str | None = None, limit: int = 200) -> list[dict]:
        if not 1 <= int(limit) <= 10000:
            raise ValueError("limit must be between 1 and 10000")
        query = "SELECT * FROM trade_journal"
        parameters = []
        if symbol:
            query += " WHERE symbol=?"
            parameters.append(symbol.strip().upper())
        query += " ORDER BY id DESC LIMIT ?"
        parameters.append(int(limit))
        with sqlite3.connect(self.database_path) as connection:
            connection.row_factory = sqlite3.Row
            rows = connection.execute(query, parameters).fetchall()
        return [dict(row) for row in rows]
