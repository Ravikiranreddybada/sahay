# Reliability and Graceful Degradation

## Failure-mode table
| Failure | Detection | Mechanism | User sees |
|---|---|---|---|
| LLM 429 / 5xx / timeout | router error, span status | retry ×2 with jittered backoff → fallback model → breaker | normal answer, slightly slower |
| LLM slow (p95 ↑) | latency histogram | timeout 20 s per call; breaker opens after 5 consecutive failures; half-open probe after 30 s | fallback model |
| Provider fully down | breaker open on all models | **Degradation level 3** (below) | extractive cited answer / handoff |
| MCP server slow | per-call 5 s timeout | user-safe error; answer explains; other tools unaffected (bulkhead) | "the claims service is slow, here is what I know…" |
| MCP server down | errors + health check | circuit per server; intent routes to KB + handoff | policy answer + ticket |
| Double submit / retry | thread lock + idempotency key | second request waits/rejects; write replays first result | one booking, not two |
| Pod crash mid-turn | ALB health check | stateless; client retries; checkpoint resumes last completed node | retry works |
| Bad deploy (prompt) | eval gate in CI; canary metrics | block merge; auto-rollback on grounded-rate drop | nothing |
| KB bad edit | eval gate on KB PRs; `kb_version` in cache key | block; old cache invalidated by construction | nothing |
| Redis down | connection errors | rate limit fails **open** with local bucket; cache bypassed | slower, still works |
| Aurora writer failover | driver reconnect | ~30 s failover; turns in that window retried | brief errors |

## Degradation ladder (automated by a load/health controller flag)
| Level | Trigger | Change | Quality impact | Cost/latency impact |
|---|---|---|---|---|
| L0 | normal | — | — | — |
| L1 | smart-model p95 > 6 s or 429 rate > 2 % | answer + plan on **fast tier** | small (eval-measured) | −60 % cost, −40 % latency |
| L2 | L1 + still saturated | planner off: **deterministic fast-path only**; list tools for missing ids | ambiguous asks get list results | −1 LLM call/turn |
| L3 | providers unavailable | **offline engine** (extractive, cited answers from KB + templated tool results) | lower fluency, still grounded | ~0 LLM |
| L4 | everything degraded | static notice + emergency path + human handoff for writes | minimal | — |

The emergency path is identical at every level (it never used the LLM).

The offline engine in this repo (`sahay/llm/offline_llm.py`) **is** the L3 mode — it is exercised
by every CI run, so the degraded mode is tested daily, not discovered during an outage.

## Disaster recovery
| | Target |
|---|---|
| Region | ap-south-1 (Mumbai) primary, ap-south-2 (Hyderabad) warm standby |
| Aurora Global Database | RPO ≈ 1 s typical, ≤ 5 min target |
| RTO | 30 min (Route 53 failover + scale up standby ECS) |
| Backups | Aurora PITR 7 days; S3 versioning on KB + traces |
