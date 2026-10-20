"""Structure-aware chunking for SOP / policy markdown.

Fixed-size chunking is the #1 cause of "retrieval returned the right doc but the wrong
half of the answer": a refund timeline table gets cut away from the heading that says
*which* product it applies to. So:
* Split on headings; every chunk carries its heading path ("Refunds > Lab tests > Timeline").
* Never split inside a list or table block.
* Pack blocks up to `max_words`; carry the last sentence over as overlap.
* Each chunk gets a content hash -> incremental re-index + stale detection.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field
from datetime import date
from typing import Any

import yaml


@dataclass
class Chunk:
    id: str
    doc_id: str
    title: str
    heading_path: str
    text: str
    doc_version: str
    effective_date: str
    review_by: str | None
    intents: list[str] = field(default_factory=list)
    content_hash: str = ""

    @property
    def embed_text(self) -> str:
        # The heading path is part of what gets embedded: it is the cheapest context injection.
        return f"{self.title} > {self.heading_path}\n{self.text}"

    def is_stale(self, today: date | None = None) -> bool:
        if not self.review_by:
            return False
        return date.fromisoformat(self.review_by) < (today or date.today())

    def to_evidence(self) -> dict[str, Any]:
        return {
            "id": self.id, "doc_id": self.doc_id, "title": self.title, "section": self.heading_path,
            "text": self.text, "version": self.doc_version, "stale": self.is_stale(),
        }


def parse_doc(raw: str) -> tuple[dict[str, Any], str]:
    if raw.startswith("---"):
        _, fm, body = raw.split("---", 2)
        return yaml.safe_load(fm) or {}, body.strip()
    return {}, raw


def _blocks(body: str) -> list[tuple[list[str], str]]:
    """Yield (heading_path, block_text). Lists/tables stay whole."""
    path: list[str] = []
    out: list[tuple[list[str], str]] = []
    buf: list[str] = []

    def flush() -> None:
        if buf and "".join(buf).strip():
            out.append((list(path), "\n".join(buf).strip()))
        buf.clear()

    def is_list(line: str) -> bool:
        return bool(re.match(r"^\s*([-*|]|\d+\.)", line))

    for line in body.splitlines():
        m = re.match(r"^(#{1,4})\s+(.*)", line)
        if m:
            flush()
            level = len(m.group(1))
            path[:] = path[: level - 1] + [m.group(2).strip()]
            continue
        if not line.strip():
            if buf and not is_list(buf[-1]):  # lists/tables survive blank lines
                flush()
            continue
        if buf and is_list(line) != is_list(buf[-1]):
            flush()
        buf.append(line)
    flush()
    return out


def chunk_document(doc_id: str, raw: str, max_words: int = 110) -> list[Chunk]:
    meta, body = parse_doc(raw)
    title = meta.get("title", doc_id)
    chunks: list[Chunk] = []
    groups: dict[str, list[str]] = {}
    order: list[str] = []
    for path, block in _blocks(body):
        key = " > ".join(path[1:] if len(path) > 1 else path) or title
        if key not in groups:
            groups[key] = []
            order.append(key)
        groups[key].append(block)

    for key in order:
        cur: list[str] = []
        words = 0
        packs: list[str] = []
        for block in groups[key]:
            n = len(block.split())
            if cur and words + n > max_words:
                packs.append("\n".join(cur))
                last_sent = re.split(r"(?<=[.!?])\s+", cur[-1])[-1]
                cur, words = ([last_sent], len(last_sent.split())) if len(last_sent.split()) < 30 else ([], 0)
            cur.append(block)
            words += n
        if cur:
            packs.append("\n".join(cur))
        for i, text in enumerate(packs):
            slug = re.sub(r"[^a-z0-9]+", "-", key.lower()).strip("-")[:40]
            cid = f"{doc_id}#{slug}" + (f"-{i}" if len(packs) > 1 else "")
            chunks.append(
                Chunk(
                    id=cid, doc_id=doc_id, title=title, heading_path=key, text=text,
                    doc_version=str(meta.get("version", "1")),
                    effective_date=str(meta.get("effective_date", "")),
                    review_by=str(meta["review_by"]) if meta.get("review_by") else None,
                    intents=list(meta.get("intents", [])),
                    content_hash=hashlib.sha256(text.encode()).hexdigest()[:16],
                )
            )
    return chunks
