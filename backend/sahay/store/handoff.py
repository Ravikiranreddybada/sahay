"""Human handoff queue. The ticket carries a ready-made context packet (intent, entities,
redacted transcript, what the bot already tried) so the human agent does not re-ask the user
everything — the main cost of a bad bot-to-human handoff."""

from __future__ import annotations

import json
import sqlite3
import threading
import time
import uuid
from typing import Any


class HandoffQueue:
    def __init__(self, path: str) -> None:
        self._lock = threading.Lock()
        self.db = sqlite3.connect(path, check_same_thread=False)
        self.db.execute(
            "CREATE TABLE IF NOT EXISTS handoffs (ticket_id TEXT PRIMARY KEY, thread_id TEXT, user_id TEXT, "
            "priority TEXT, reason TEXT, packet TEXT, status TEXT, created_at REAL)"
        )
        self.db.commit()

    def create(self, *, thread_id: str, user_id: str, priority: str, reason: str, packet: dict[str, Any]) -> str:
        tid = "HND-" + uuid.uuid4().hex[:8].upper()
        with self._lock:
            self.db.execute(
                "INSERT INTO handoffs VALUES (?,?,?,?,?,?,?,?)",
                (tid, thread_id, user_id, priority, reason, json.dumps(packet, default=str), "open", time.time()),
            )
            self.db.commit()
        return tid

    def resolve(self, ticket_id: str, note: str | None = None) -> bool:
        with self._lock:
            cur = self.db.execute("UPDATE handoffs SET status='resolved', packet=json_set(packet, '$.resolution', ?) "
                                  "WHERE ticket_id=? AND status='open'", (note or "", ticket_id))
            self.db.commit()
        return cur.rowcount == 1

    def list(self, limit: int = 50) -> list[dict[str, Any]]:
        with self._lock:
            rows = self.db.execute(
                "SELECT ticket_id, thread_id, user_id, priority, reason, packet, status, created_at "
                "FROM handoffs ORDER BY status='open' DESC, priority ASC, created_at DESC LIMIT ?",
                (limit,),
            ).fetchall()
        keys = ["ticket_id", "thread_id", "user_id", "priority", "reason", "packet", "status", "created_at"]
        return [{**dict(zip(keys, r)), "packet": json.loads(r[5])} for r in rows]
