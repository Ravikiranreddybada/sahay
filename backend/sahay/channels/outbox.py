"""Outbound message log + inbound dedupe for messaging channels.

Every message we send (chat reply, vaccine reminder) is written here first, with its
delivery status. Without a provider token the status is `simulated` and nothing leaves the
machine, so the full channel flow runs in dev, CI and demos.
"""

from __future__ import annotations

import json
import sqlite3
import threading
import time
import uuid
from typing import Any


class Outbox:
    def __init__(self, path: str) -> None:
        self._lock = threading.Lock()
        self.db = sqlite3.connect(path, check_same_thread=False)
        self.db.executescript(
            """CREATE TABLE IF NOT EXISTS outbox (id TEXT PRIMARY KEY, channel TEXT, recipient TEXT, user_id TEXT, kind TEXT,
                   body TEXT, payload TEXT, status TEXT, error TEXT, created_at REAL);
               CREATE TABLE IF NOT EXISTS inbound_seen (msg_id TEXT PRIMARY KEY, seen_at REAL);"""
        )
        self.db.commit()

    def record(self, *, channel: str, recipient: str, user_id: str | None, kind: str, body: str, payload: dict[str, Any],
               status: str, error: str | None = None) -> str:
        mid = "OUT-" + uuid.uuid4().hex[:10]
        with self._lock:
            self.db.execute("INSERT INTO outbox VALUES (?,?,?,?,?,?,?,?,?,?)",
                            (mid, channel, recipient, user_id, kind, body, json.dumps(payload), status, error, time.time()))
            self.db.commit()
        return mid

    def first_time(self, msg_id: str) -> bool:
        """WhatsApp retries a webhook until it gets a 200, so one user message can arrive 2-3
        times. Processing it twice would answer twice, or confirm a cancellation twice."""
        with self._lock:
            cur = self.db.execute("INSERT OR IGNORE INTO inbound_seen VALUES (?,?)", (msg_id, time.time()))
            self.db.commit()
        return cur.rowcount == 1

    def list(self, limit: int = 50) -> list[dict[str, Any]]:
        with self._lock:
            rows = self.db.execute(
                "SELECT id, channel, recipient, user_id, kind, body, status, error, created_at FROM outbox ORDER BY created_at DESC LIMIT ?",
                (limit,)).fetchall()
        keys = ["id", "channel", "recipient", "user_id", "kind", "body", "status", "error", "created_at"]
        return [dict(zip(keys, r)) for r in rows]
