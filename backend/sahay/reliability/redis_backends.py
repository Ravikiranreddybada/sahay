"""Redis-backed limiter and semantic cache: the multi-replica versions of ratelimit.py and
cache.py. Same interfaces, so the graph and API do not know which one they run on.

Why Redis and not per-pod memory: with 12 API pods behind a load balancer, an in-process
30/min limit is really 360/min, and an FAQ answered on pod 3 is a cache miss on pod 7.

Failure policy: Redis is an optimisation, never a dependency of a correct answer.
* limiter: if Redis is down, fail *open* to the local bucket (a Redis blip must not 429 the
  whole user base) and count it in metrics.
* cache: if Redis is down, behave as a miss / a no-op put.
"""

from __future__ import annotations

import json
import logging
import time
import uuid
from typing import Any

import numpy as np

from ..obs import metrics
from ..rag.embed import Embedder
from .cache import CACHEABLE_INTENTS
from .ratelimit import REDIS_LUA, TokenBucket

log = logging.getLogger("sahay.redis")


class RedisTokenBucket:
    def __init__(self, redis: Any, per_minute: int, burst: int | None = None, prefix: str = "sahay:rl:") -> None:
        self.r = redis
        self.rate = per_minute / 60.0
        self.capacity = float(burst or max(5, per_minute // 3))
        self.prefix = prefix
        self._script = redis.register_script(REDIS_LUA)
        self._local = TokenBucket(per_minute, burst)

    async def acquire(self, key: str, cost: float = 1.0) -> tuple[bool, float]:
        try:
            ok, tokens = await self._script(keys=[self.prefix + key], args=[self.rate, self.capacity, int(time.time() * 1000), cost])
        except Exception as e:  # noqa: BLE001 - fail open, see module docstring
            log.warning("redis limiter unavailable, using local bucket: %s", e)
            metrics.CACHE.labels("redis_error").inc()
            return self._local.allow(key, cost)
        tokens = float(tokens)
        retry = 0.0 if ok else (cost - tokens) / self.rate
        return bool(ok), round(retry, 2)


class RedisSemanticCache:
    """Entries live in one hash per namespace (intent|prompt_version|kb_version), so a KB or
    prompt change orphans the old namespace and its TTL cleans it up. Lookup is brute-force
    cosine over the namespace (≤ a few thousand FAQ phrasings, ~1 ms in numpy). Past that,
    the same interface goes onto a Redis vector index (RediSearch HNSW)."""

    def __init__(self, redis: Any, embedder: Embedder, threshold: float = 0.93, ttl_s: int = 3600, max_entries: int = 5000,
                 prefix: str = "sahay:sc:") -> None:
        self.r, self.e, self.threshold, self.ttl, self.max, self.prefix = redis, embedder, threshold, ttl_s, max_entries, prefix

    def _key(self, intent: str, prompt_version: str, kb_version: str) -> str:
        return f"{self.prefix}{intent}|{prompt_version}|{kb_version}"

    async def get(self, query: str, intent: str, prompt_version: str, kb_version: str) -> dict[str, Any] | None:
        if intent not in CACHEABLE_INTENTS:
            return None
        try:
            raw = await self.r.hgetall(self._key(intent, prompt_version, kb_version))
        except Exception as e:  # noqa: BLE001
            log.warning("redis cache get failed: %s", e)
            metrics.CACHE.labels("redis_error").inc()
            return None
        now = time.time()
        rows = [json.loads(v) for v in raw.values()]
        rows = [x for x in rows if x["exp"] > now]
        if not rows:
            metrics.CACHE.labels("miss").inc()
            return None
        q = self.e.embed([query])[0]
        mat = np.array([x["vec"] for x in rows], dtype=np.float32)
        sims = mat @ q
        i = int(sims.argmax())
        if sims[i] >= self.threshold:
            metrics.CACHE.labels("hit").inc()
            return {**rows[i]["value"], "cache_similarity": round(float(sims[i]), 3)}
        metrics.CACHE.labels("miss").inc()
        return None

    async def put(self, query: str, intent: str, prompt_version: str, kb_version: str, value: dict[str, Any]) -> None:
        if intent not in CACHEABLE_INTENTS:
            return
        key = self._key(intent, prompt_version, kb_version)
        vec = self.e.embed([query])[0]
        entry = {"vec": [round(float(x), 5) for x in vec], "value": value, "exp": time.time() + self.ttl}
        try:
            if await self.r.hlen(key) >= self.max:
                return  # full: keep serving what we have; the namespace TTL resets the set
            await self.r.hset(key, uuid.uuid4().hex[:12], json.dumps(entry, default=str))
            await self.r.expire(key, self.ttl)
        except Exception as e:  # noqa: BLE001
            log.warning("redis cache put failed: %s", e)
            metrics.CACHE.labels("redis_error").inc()
