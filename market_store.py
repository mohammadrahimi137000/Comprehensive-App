"""Local SQLite persistence for normalized market candles and forecast snapshots."""
from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Iterable, Mapping

from analysis_engine import Candle


class MarketStore:
    def __init__(self, database_path: str | Path = "data/market.db"):
        self.database_path = Path(database_path)
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.database_path, timeout=15)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA journal_mode=WAL")
        connection.execute("PRAGMA foreign_keys=ON")
        return connection

    def _initialize(self) -> None:
        with self._connect() as connection:
            connection.executescript("""
                CREATE TABLE IF NOT EXISTS candles (
                    source TEXT NOT NULL,
                    symbol TEXT NOT NULL,
                    timeframe TEXT NOT NULL,
                    timestamp TEXT NOT NULL,
                    open REAL NOT NULL,
                    high REAL NOT NULL,
                    low REAL NOT NULL,
                    close REAL NOT NULL,
                    volume REAL NOT NULL DEFAULT 0,
                    received_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    PRIMARY KEY (source, symbol, timeframe, timestamp),
                    CHECK (high >= low),
                    CHECK (volume >= 0)
                );
                CREATE INDEX IF NOT EXISTS idx_candles_lookup
                    ON candles(symbol, timeframe, timestamp DESC);
                CREATE TABLE IF NOT EXISTS forecast_snapshots (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    source TEXT NOT NULL,
                    symbol TEXT NOT NULL,
                    timeframe TEXT NOT NULL,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    payload TEXT NOT NULL
                );
            """)

    def upsert_candles(
        self, source: str, symbol: str, timeframe: str,
        values: Iterable[Candle | Mapping[str, object] | tuple],
    ) -> int:
        if not all((source.strip(), symbol.strip(), timeframe.strip())):
            raise ValueError("source, symbol and timeframe are required")
        rows = []
        for value in values:
            candle = Candle.from_value(value)
            rows.append((
                source.strip(), symbol.strip().upper(), timeframe.strip().upper(),
                str(candle.timestamp), candle.open, candle.high, candle.low,
                candle.close, candle.volume,
            ))
        if not rows:
            return 0
        with self._connect() as connection:
            connection.executemany("""
                INSERT INTO candles
                    (source, symbol, timeframe, timestamp, open, high, low, close, volume)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(source, symbol, timeframe, timestamp) DO UPDATE SET
                    open=excluded.open, high=excluded.high, low=excluded.low,
                    close=excluded.close, volume=excluded.volume,
                    received_at=CURRENT_TIMESTAMP
            """, rows)
        return len(rows)

    def get_candles(
        self, symbol: str, timeframe: str, limit: int = 500,
        source: str | None = None,
    ) -> list[dict]:
        if limit < 1 or limit > 100_000:
            raise ValueError("limit must be between 1 and 100000")
        query = """SELECT source, symbol, timeframe, timestamp, open, high, low,
                          close, volume, received_at
                   FROM candles WHERE symbol=? AND timeframe=?"""
        parameters: list[object] = [symbol.strip().upper(), timeframe.strip().upper()]
        if source:
            query += " AND source=?"
            parameters.append(source.strip())
        query += " ORDER BY timestamp DESC LIMIT ?"
        parameters.append(int(limit))
        with self._connect() as connection:
            rows = connection.execute(query, parameters).fetchall()
        return [dict(row) for row in reversed(rows)]


    def list_sources(self, symbol: str, timeframe: str) -> list[dict]:
        with self._connect() as connection:
            rows = connection.execute(
                """SELECT source, COUNT(*) AS candle_count, MAX(timestamp) AS latest_timestamp
                   FROM candles WHERE symbol=? AND timeframe=?
                   GROUP BY source ORDER BY latest_timestamp DESC""",
                (symbol.strip().upper(), timeframe.strip().upper()),
            ).fetchall()
        return [dict(row) for row in rows]

    def save_forecast(self, source: str, symbol: str, timeframe: str, payload: Mapping) -> int:
        encoded = json.dumps(payload, ensure_ascii=False, allow_nan=False)
        with self._connect() as connection:
            cursor = connection.execute(
                "INSERT INTO forecast_snapshots(source, symbol, timeframe, payload) "
                "VALUES (?, ?, ?, ?)",
                (source, symbol.strip().upper(), timeframe.strip().upper(), encoded),
            )
            return int(cursor.lastrowid)

    def latest_forecasts(self, symbol: str, limit: int = 50) -> list[dict]:
        if limit < 1 or limit > 10_000:
            raise ValueError("limit must be between 1 and 10000")
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT id, source, symbol, timeframe, created_at, payload "
                "FROM forecast_snapshots WHERE symbol=? ORDER BY id DESC LIMIT ?",
                (symbol.strip().upper(), int(limit)),
            ).fetchall()
        return [{**dict(row), "payload": json.loads(row["payload"])} for row in rows]
