"""Per-user token bucket. In-process for dev; prod uses the same algorithm as one atomic
Redis Lua script (see docs/SYSTEM_DESIGN.md) so limits hold across all API replicas."""

from __future__ import annotations

import time
from dataclasses import dataclass


@dataclass
class _Bucket:
    tokens: float
    updated: float


class TokenBucket:
    def __init__(self, per_minute: int, burst: int | None = None) -> None:
        self.rate = per_minute / 60.0
        self.capacity = float(burst or max(5, per_minute // 3))
        self._b: dict[str, _Bucket] = {}

    def allow(self, key: str, cost: float = 1.0) -> tuple[bool, float]:
        now = time.monotonic()
        b = self._b.get(key) or _Bucket(self.capacity, now)
        b.tokens = min(self.capacity, b.tokens + (now - b.updated) * self.rate)
        b.updated = now
        ok = b.tokens >= cost
        if ok:
            b.tokens -= cost
        self._b[key] = b
        retry_after = 0.0 if ok else (cost - b.tokens) / self.rate
        return ok, round(retry_after, 2)

    async def acquire(self, key: str, cost: float = 1.0) -> tuple[bool, float]:
        return self.allow(key, cost)


REDIS_LUA = """
-- KEYS[1]=bucket key, ARGV: rate_per_s, capacity, now_ms, cost
local b = redis.call('HMGET', KEYS[1], 't', 'u')
local t = tonumber(b[1]) or tonumber(ARGV[2])
local u = tonumber(b[2]) or tonumber(ARGV[3])
t = math.min(tonumber(ARGV[2]), t + (tonumber(ARGV[3]) - u) / 1000 * tonumber(ARGV[1]))
local ok = 0
if t >= tonumber(ARGV[4]) then t = t - tonumber(ARGV[4]); ok = 1 end
redis.call('HSET', KEYS[1], 't', t, 'u', ARGV[3])
redis.call('PEXPIRE', KEYS[1], 120000)
return {ok, tostring(t)}
"""
