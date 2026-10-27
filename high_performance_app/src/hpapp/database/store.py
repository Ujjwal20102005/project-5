"""SQLite persistence: connection pool, WAL, indexes, batched writes."""
from __future__ import annotations

import asyncio
import queue
import sqlite3
import time
from contextlib import contextmanager
from typing import Any, Dict, Iterable, List, Optional, Sequence

SCHEMA = """
CREATE TABLE IF NOT EXISTS results (
    id          TEXT PRIMARY KEY,
    status      TEXT NOT NULL,
    strategy    TEXT NOT NULL,
    digest      TEXT,
    duration_ms REAL NOT NULL,
    created_at  REAL NOT NULL
);
"""
INDEXES = """
CREATE INDEX IF NOT EXISTS idx_results_status_created ON results(status, created_at);
CREATE INDEX IF NOT EXISTS idx_results_created ON results(created_at);
"""

Row = Sequence[Any]  # (id, status, strategy, digest, duration_ms, created_at)
COLUMNS = ("id", "status", "strategy", "digest", "duration_ms", "created_at")


class ConnectionPool:
    """Fixed-size pool of reusable SQLite connections."""

    def __init__(self, path: str, size: int = 5, timeout: float = 5.0) -> None:
        self.path, self.size, self.timeout = path, size, timeout
        self._q: "queue.Queue[sqlite3.Connection]" = queue.Queue(maxsize=size)
        self._all: List[sqlite3.Connection] = []
        for _ in range(size):
            conn = sqlite3.connect(path, check_same_thread=False)
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA synchronous=NORMAL")
            self._all.append(conn)
            self._q.put(conn)

    @contextmanager
    def connection(self):
        conn = self._q.get(timeout=self.timeout)
        try:
            yield conn
        finally:
            self._q.put(conn)

    def close(self) -> None:
        for c in self._all:
            c.close()
        self._all.clear()


class SQLiteStore:
    def __init__(self, path: str, pool_size: int = 5, with_indexes: bool = True) -> None:
        self.pool = ConnectionPool(path, pool_size)
        with self.pool.connection() as conn:
            conn.executescript(SCHEMA + (INDEXES if with_indexes else ""))
            conn.commit()

    # ---- writes ----
    def insert_many(self, rows: Iterable[Row]) -> int:
        """Insert/replace rows in ONE transaction (much faster than per-row commits)."""
        rows = list(rows)
        if not rows:
            return 0
        with self.pool.connection() as conn:
            with conn:
                conn.executemany("INSERT OR REPLACE INTO results VALUES (?,?,?,?,?,?)", rows)
        return len(rows)

    @staticmethod
    def row_from_result(result) -> Row:
        return (result.id, result.status, result.strategy, result.digest,
                result.duration_ms, time.time())

    # ---- reads ----
    def get(self, id_: str) -> Optional[Dict[str, Any]]:
        with self.pool.connection() as conn:
            r = conn.execute("SELECT id,status,strategy,digest,duration_ms,created_at "
                             "FROM results WHERE id=?", (id_,)).fetchone()
        return None if r is None else dict(zip(COLUMNS, r))

    def count(self) -> int:
        with self.pool.connection() as conn:
            return conn.execute("SELECT COUNT(*) FROM results").fetchone()[0]

    def count_by_status(self) -> Dict[str, int]:
        with self.pool.connection() as conn:
            return dict(conn.execute(
                "SELECT status, COUNT(*) FROM results GROUP BY status").fetchall())

    def recent_by_status(self, status: str, limit: int = 20) -> List[Dict[str, Any]]:
        with self.pool.connection() as conn:
            rows = conn.execute(
                "SELECT id,status,strategy,digest,duration_ms,created_at FROM results "
                "WHERE status=? ORDER BY created_at DESC LIMIT ?", (status, limit)).fetchall()
        return [dict(zip(COLUMNS, r)) for r in rows]

    def explain_recent_by_status(self) -> List[str]:
        """SQLite query plan for the hot query; proves indexes are in effect."""
        with self.pool.connection() as conn:
            plan = conn.execute(
                "EXPLAIN QUERY PLAN SELECT * FROM results WHERE status=? "
                "ORDER BY created_at DESC LIMIT ?", ("ok", 20)).fetchall()
        return [row[-1] for row in plan]

    # ---- async wrappers (keep the event loop free) ----
    async def insert_many_async(self, rows: Iterable[Row]) -> int:
        return await asyncio.to_thread(self.insert_many, list(rows))

    async def count_by_status_async(self) -> Dict[str, int]:
        return await asyncio.to_thread(self.count_by_status)

    def close(self) -> None:
        self.pool.close()
