"""Hybrid retrieval: BM25 (exact terms, ids, drug names) + dense vectors (paraphrase)
fused with Reciprocal Rank Fusion, then a cheap feature reranker and dedup.

Why hybrid: dense-only misses "ORD-1042" or "HbA1c"; BM25-only misses "my kid's jab".
Why RRF: the two score scales are incomparable; RRF only uses ranks, so no tuning of
weights against a moving embedding model.

Freshness: every chunk has doc_version + review_by. Superseded versions are dropped at
index time; past-review chunks are down-weighted and *flagged* in the evidence so the
answer node can tell the user to verify, and the trace shows exactly which chunk was stale.
"""

from __future__ import annotations

import math
import threading
from collections import Counter
from dataclasses import dataclass
from datetime import date
from pathlib import Path

import numpy as np

from ..obs.tracing import span
from .chunker import Chunk, chunk_document, parse_doc
from .embed import Embedder, HashingEmbedder, normalize_terms


@dataclass
class Hit:
    chunk: Chunk
    score: float
    bm25_rank: int | None
    dense_rank: int | None


class BM25:
    def __init__(self, docs: list[list[str]], k1: float = 1.4, b: float = 0.72) -> None:
        self.k1, self.b = k1, b
        self.docs = docs
        self.tf = [Counter(d) for d in docs]
        self.dl = np.array([len(d) for d in docs], dtype=np.float32)
        self.avgdl = float(self.dl.mean()) if docs else 1.0
        df: Counter[str] = Counter()
        for d in docs:
            df.update(set(d))
        n = len(docs)
        self.idf = {t: math.log(1 + (n - f + 0.5) / (f + 0.5)) for t, f in df.items()}

    def scores(self, q: list[str]) -> np.ndarray:
        out = np.zeros(len(self.docs), dtype=np.float32)
        for t in set(q):
            idf = self.idf.get(t)
            if idf is None:
                continue
            for i, tf in enumerate(self.tf):
                f = tf.get(t)
                if f:
                    out[i] += idf * f * (self.k1 + 1) / (f + self.k1 * (1 - self.b + self.b * self.dl[i] / self.avgdl))
        return out


class HybridIndex:
    def __init__(self, embedder: Embedder | None = None) -> None:
        self.embedder = embedder or HashingEmbedder()
        self.chunks: list[Chunk] = []
        self.vectors: np.ndarray = np.zeros((0, self.embedder.dim), dtype=np.float32)
        self.bm25: BM25 | None = None
        self._hashes: dict[str, str] = {}
        self.scheduled: list[str] = []
        self._build_lock = threading.Lock()

    # --- build ---------------------------------------------------------------------------
    def load_dir(self, kb_dir: Path, today: date | None = None) -> dict[str, int]:
        today = today or date.today()
        latest: dict[str, tuple[str, str, str]] = {}  # logical doc -> (version, path, raw)
        scheduled: list[str] = []
        for p in sorted(kb_dir.glob("*.md")):
            raw = p.read_text()
            meta, _ = parse_doc(raw)
            logical = meta.get("doc_id", p.stem)
            ver = str(meta.get("version", "1"))
            eff = meta.get("effective_date")
            # Version gate, part 2 (INC-015): a v3 policy committed today with effective_date
            # next month must not be served before it is in force. Highest *effective* version wins.
            if eff and date.fromisoformat(str(eff)) > today:
                scheduled.append(f"{logical}@v{ver}")
                continue
            if logical not in latest or _vkey(ver) > _vkey(latest[logical][0]):
                latest[logical] = (ver, str(p), raw)
        self.scheduled = scheduled
        chunks: list[Chunk] = []
        for logical, (_, _, raw) in latest.items():
            chunks.extend(chunk_document(logical, raw))
        return {**self.build(chunks), "scheduled": len(scheduled)}

    def build(self, chunks: list[Chunk]) -> dict[str, int]:
        prev = self._hashes
        old = {c.id: i for i, c in enumerate(self.chunks)}
        vecs = np.zeros((len(chunks), self.embedder.dim), dtype=np.float32)
        # only new or edited chunks are re-embedded (content-hash diff)
        to_embed = [i for i, c in enumerate(chunks) if c.id not in old or prev.get(c.id) != c.content_hash]
        if to_embed:
            vecs[to_embed] = self.embedder.embed([chunks[i].embed_text for i in to_embed])
        for i, c in enumerate(chunks):
            if i not in to_embed:
                vecs[i] = self.vectors[old[c.id]]
        bm25 = BM25([normalize_terms(c.embed_text) for c in chunks])
        # swap all three together: a search running during a re-index must never see the new
        # chunk list with the old vectors (index-out-of-range or, worse, the wrong chunk's text)
        with self._build_lock:
            self.chunks, self.vectors, self.bm25 = chunks, vecs, bm25
            self._hashes = {c.id: c.content_hash for c in chunks}
        return {"chunks": len(chunks), "re_embedded": len(to_embed), "docs": len({c.doc_id for c in chunks})}

    # --- query ---------------------------------------------------------------------------
    def search(self, query: str, top_k: int = 5, candidates: int = 20, intent: str | None = None, rrf_k: int = 60) -> list[Hit]:
        with self._build_lock:
            chunks, vectors, bm25_idx = self.chunks, self.vectors, self.bm25
        if not chunks or bm25_idx is None:
            return []
        with span("retrieval.hybrid", kind="retrieval", query=query, intent=intent, top_k=top_k) as sp:
            q_terms = normalize_terms(query)
            bm = bm25_idx.scores(q_terms)
            qv = self.embedder.embed([query])[0]
            dense = vectors @ qv
            # Relative cut-offs: RRF rewards a chunk for appearing in *both* lists even at a
            # low rank, so noise from a weak retriever must be dropped before fusion.
            bm_max, de_max = float(bm.max()), float(dense.max())
            bm_order = [int(i) for i in np.argsort(-bm)[:candidates] if bm[i] > 0 and bm[i] >= 0.25 * bm_max]
            de_order = [int(i) for i in np.argsort(-dense)[:candidates] if dense[i] > 0.08 and dense[i] >= 0.45 * de_max]
            bm_rank = {i: r for r, i in enumerate(bm_order)}
            de_rank = {i: r for r, i in enumerate(de_order)}
            fused: dict[int, float] = {}
            for i in set(bm_order) | set(de_order):
                s = 0.0
                if i in bm_rank:
                    s += 1 / (rrf_k + bm_rank[i] + 1)
                if i in de_rank:
                    s += 1 / (rrf_k + de_rank[i] + 1)
                c = chunks[i]
                # rerank features: intent tag prior, heading-term match, staleness penalty
                if intent and intent in c.intents:
                    s *= 1.25
                head = set(normalize_terms(c.heading_path))
                if head & set(q_terms):
                    s *= 1.1
                if c.is_stale():
                    # soft penalty only: a stale-but-right chunk must still beat a fresh-but-wrong
                    # one; the answer node warns the user instead (evidence carries stale=True)
                    s *= 0.92
                fused[i] = s
            ranked = sorted(fused.items(), key=lambda x: -x[1])
            hits: list[Hit] = []
            per_doc: Counter[str] = Counter()
            for i, s in ranked:
                c = chunks[i]
                if per_doc[c.doc_id] >= 3:  # diversity: avoid 5 chunks of one doc
                    continue
                per_doc[c.doc_id] += 1
                hits.append(Hit(c, round(s, 5), bm_rank.get(i), de_rank.get(i)))
                if len(hits) >= top_k:
                    break
            sp.set(
                hits=[{"id": h.chunk.id, "score": h.score, "bm25_rank": h.bm25_rank, "dense_rank": h.dense_rank, "stale": h.chunk.is_stale()} for h in hits],
                embedder=self.embedder.id,
            )
            return hits


def _vkey(v: str) -> tuple[int, ...]:
    return tuple(int(x) for x in v.split(".") if x.isdigit())
