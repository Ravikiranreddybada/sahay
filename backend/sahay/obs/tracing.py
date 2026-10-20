"""Span tracer for the agent pipeline.

Why own it instead of only Langfuse/Phoenix: the debugging story ("which node pulled stale
context?") needs node-level spans with *inputs, outputs, token counts and the retrieved
chunk ids* stored next to each other and queryable by the UI. The span shape is
OpenTelemetry-compatible (trace_id/span_id/parent_id/attributes), so an OTLP exporter
can forward the same data to Langfuse / Phoenix / Tempo in production.
"""

from __future__ import annotations

import contextvars
import json
import sqlite3
import threading
import time
import uuid
from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import Any, Iterator

_current_trace: contextvars.ContextVar["Trace | None"] = contextvars.ContextVar("trace", default=None)
_current_span: contextvars.ContextVar["Span | None"] = contextvars.ContextVar("span", default=None)


@dataclass
class Span:
    name: str
    trace_id: str
    span_id: str = field(default_factory=lambda: uuid.uuid4().hex[:16])
    parent_id: str | None = None
    kind: str = "node"  # node | llm | tool | retrieval | guard
    start: float = field(default_factory=time.perf_counter)
    end: float | None = None
    status: str = "ok"
    attributes: dict[str, Any] = field(default_factory=dict)

    @property
    def duration_ms(self) -> float:
        return round(((self.end or time.perf_counter()) - self.start) * 1000, 2)

    def set(self, **attrs: Any) -> None:
        self.attributes.update(attrs)

    def to_dict(self, t0: float) -> dict[str, Any]:
        return {
            "span_id": self.span_id,
            "parent_id": self.parent_id,
            "name": self.name,
            "kind": self.kind,
            "status": self.status,
            "offset_ms": round((self.start - t0) * 1000, 2),
            "duration_ms": self.duration_ms,
            "attributes": self.attributes,
        }


@dataclass
class Trace:
    trace_id: str
    thread_id: str
    user_id: str
    query: str
    started_at: float = field(default_factory=time.time)
    t0: float = field(default_factory=time.perf_counter)
    spans: list[Span] = field(default_factory=list)
    meta: dict[str, Any] = field(default_factory=dict)

    def totals(self) -> dict[str, Any]:
        tok_in = sum(s.attributes.get("tokens_in", 0) for s in self.spans)
        tok_out = sum(s.attributes.get("tokens_out", 0) for s in self.spans)
        cost = sum(s.attributes.get("cost_usd", 0.0) for s in self.spans)
        return {
            "tokens_in": tok_in,
            "tokens_out": tok_out,
            "cost_usd": round(cost, 6),
            "llm_calls": sum(1 for s in self.spans if s.kind == "llm"),
            "tool_calls": sum(1 for s in self.spans if s.kind == "tool"),
            "latency_ms": round((time.perf_counter() - self.t0) * 1000, 2),
        }

    def to_dict(self) -> dict[str, Any]:
        return {
            "trace_id": self.trace_id,
            "thread_id": self.thread_id,
            "user_id": self.user_id,
            "query": self.query,
            "started_at": self.started_at,
            "meta": self.meta,
            "totals": self.totals(),
            "spans": [s.to_dict(self.t0) for s in self.spans],
        }


def current_trace() -> Trace | None:
    return _current_trace.get()


@contextmanager
def start_trace(thread_id: str, user_id: str, query: str) -> Iterator[Trace]:
    trace = Trace(trace_id=uuid.uuid4().hex, thread_id=thread_id, user_id=user_id, query=query)
    tok = _current_trace.set(trace)
    try:
        yield trace
    finally:
        _current_trace.reset(tok)


@contextmanager
def span(name: str, kind: str = "node", **attrs: Any) -> Iterator[Span]:
    trace = _current_trace.get()
    parent = _current_span.get()
    s = Span(
        name=name,
        trace_id=trace.trace_id if trace else "detached",
        parent_id=parent.span_id if parent else None,
        kind=kind,
        attributes=dict(attrs),
    )
    tok = _current_span.set(s)
    try:
        yield s
    except Exception as exc:
        s.status = "error"
        s.set(error=f"{type(exc).__name__}: {exc}")
        raise
    finally:
        s.end = time.perf_counter()
        _current_span.reset(tok)
        if trace is not None:
            trace.spans.append(s)


class TraceStore:
    """SQLite in dev. In prod the same rows go to Postgres (hot, 7 days) + S3 parquet (cold)."""

    def __init__(self, path: str) -> None:
        self._lock = threading.Lock()
        self._db = sqlite3.connect(path, check_same_thread=False)
        self._db.execute(
            """CREATE TABLE IF NOT EXISTS traces (
                trace_id TEXT PRIMARY KEY, thread_id TEXT, user_id TEXT, query TEXT,
                started_at REAL, intent TEXT, latency_ms REAL, cost_usd REAL,
                grounded INTEGER, body TEXT)"""
        )
        self._db.execute("CREATE INDEX IF NOT EXISTS ix_traces_started ON traces(started_at DESC)")
        self._db.execute(
            """CREATE TABLE IF NOT EXISTS feedback (
                trace_id TEXT, rating INTEGER, comment TEXT, created_at REAL)"""
        )
        self._db.commit()
        self.exporter: Any | None = None  # OTLPExporter when SAHAY_OTLP_ENDPOINT is set

    def save(self, trace: Trace) -> None:
        body = trace.to_dict()
        if self.exporter is not None:
            self.exporter.submit(body)
        with self._lock:
            self._db.execute(
                "INSERT OR REPLACE INTO traces VALUES (?,?,?,?,?,?,?,?,?,?)",
                (
                    trace.trace_id,
                    trace.thread_id,
                    trace.user_id,
                    trace.query,
                    trace.started_at,
                    trace.meta.get("intent"),
                    body["totals"]["latency_ms"],
                    body["totals"]["cost_usd"],
                    int(bool(trace.meta.get("grounded"))),
                    json.dumps(body, default=str),
                ),
            )
            self._db.commit()

    def list(self, limit: int = 50) -> list[dict[str, Any]]:
        with self._lock:
            rows = self._db.execute(
                "SELECT trace_id, thread_id, user_id, query, started_at, intent, latency_ms, cost_usd, grounded "
                "FROM traces ORDER BY started_at DESC LIMIT ?",
                (limit,),
            ).fetchall()
        keys = ["trace_id", "thread_id", "user_id", "query", "started_at", "intent", "latency_ms", "cost_usd", "grounded"]
        return [dict(zip(keys, r)) for r in rows]

    def get(self, trace_id: str) -> dict[str, Any] | None:
        with self._lock:
            row = self._db.execute("SELECT body FROM traces WHERE trace_id=?", (trace_id,)).fetchone()
        return json.loads(row[0]) if row else None

    def owner(self, trace_id: str) -> str | None:
        with self._lock:
            row = self._db.execute("SELECT user_id FROM traces WHERE trace_id=?", (trace_id,)).fetchone()
        return row[0] if row else None

    def threads_of(self, user_id: str) -> list[str]:
        with self._lock:
            return [r[0] for r in self._db.execute("SELECT DISTINCT thread_id FROM traces WHERE user_id=?", (user_id,)).fetchall()]

    def delete_user(self, user_id: str) -> int:
        """Right to erasure (DPDP Act 2023 s.12): drop the member's traces and their feedback."""
        with self._lock:
            ids = [r[0] for r in self._db.execute("SELECT trace_id FROM traces WHERE user_id=?", (user_id,)).fetchall()]
            self._db.executemany("DELETE FROM feedback WHERE trace_id=?", [(i,) for i in ids])
            self._db.execute("DELETE FROM traces WHERE user_id=?", (user_id,))
            self._db.commit()
        return len(ids)

    def add_feedback(self, trace_id: str, rating: int, comment: str | None) -> None:
        with self._lock:
            self._db.execute("INSERT INTO feedback VALUES (?,?,?,?)", (trace_id, rating, comment, time.time()))
            self._db.commit()
