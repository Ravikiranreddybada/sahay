"""Semantic cache for *non-personal* answers.

Policy/FAQ questions repeat heavily ("refund time for lab test?") - at 1 lakh users the
top ~300 FAQ phrasings cover a large share of policy traffic. Serving them from cache cuts
p50 latency from seconds to milliseconds and removes LLM cost for those turns.

Hard rules (each prevents a real incident):
* Never cache a turn that used a tool result: it contains one user's data.
* The key includes prompt_version and kb_version: a policy update or prompt change must
  never be answered from the old cache.
* Cosine threshold is high (0.93); a near-miss returns a wrong-policy answer, which is worse
  than a cache miss.
Dev: in-process numpy. Prod: Redis with a vector index (RedisVL), same interface.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any

import numpy as np

from ..obs import metrics
from ..rag.embed import Embedder

# order_status is absent on purpose: its answer is always live, per-user data.
CACHEABLE_INTENTS = {"policy_faq", "refund_cancel", "lab_booking", "claim_status", "vaccination_journey", "surgery_journey", "consult_booking"}


@dataclass
class _Entry:
    vec: np.ndarray
    namespace: str
    value: dict[str, Any]
    expires: float


class SemanticCache:
    def __init__(self, embedder: Embedder, threshold: float = 0.93, ttl_s: int = 3600, max_entries: int = 5000) -> None:
        self.e = embedder
        self.threshold = threshold
        self.ttl = ttl_s
        self.max = max_entries
        self.entries: list[_Entry] = []

    def _ns(self, intent: str, prompt_version: str, kb_version: str) -> str:
        return f"{intent}|{prompt_version}|{kb_version}"

    async def get(self, query: str, intent: str, prompt_version: str, kb_version: str) -> dict[str, Any] | None:
        if intent not in CACHEABLE_INTENTS or not self.entries:
            return None
        ns = self._ns(intent, prompt_version, kb_version)
        now = time.time()
        self.entries = [x for x in self.entries if x.expires > now]
        cands = [x for x in self.entries if x.namespace == ns]
        if not cands:
            metrics.CACHE.labels("miss").inc()
            return None
        q = self.e.embed([query])[0]
        sims = np.array([float(x.vec @ q) for x in cands])
        i = int(sims.argmax())
        if sims[i] >= self.threshold:
            metrics.CACHE.labels("hit").inc()
            return {**cands[i].value, "cache_similarity": round(float(sims[i]), 3)}
        metrics.CACHE.labels("miss").inc()
        return None

    async def put(self, query: str, intent: str, prompt_version: str, kb_version: str, value: dict[str, Any]) -> None:
        if intent not in CACHEABLE_INTENTS:
            return
        if len(self.entries) >= self.max:
            self.entries.pop(0)
        self.entries.append(_Entry(self.e.embed([query])[0], self._ns(intent, prompt_version, kb_version), value, time.time() + self.ttl))
