# Scaling Strategy

| Tier | Scales by | Signal | Min → Max | Notes |
|---|---|---|---|---|
| API pods (ECS Fargate) | horizontal | **in-flight turns per pod** (custom metric) > 80, or p95 > 4 s | 6 → 40 | CPU is not the signal: pods wait on I/O |
| MCP servers | horizontal, per domain | p95 latency, RPS | 2 → 6 each | stateless HTTP; bulkheaded pools |
| Worker | horizontal | SQS queue depth / age | 1 → 20 | ingestion, eval runs, reminder fan-out |
| Redis | vertical → cluster mode | memory, ops/s | r7g.large ×2 → cluster | ops/s here is tiny; memory dominated by cache |
| Aurora PG | read replicas; writer vertical | writer CPU, replica lag | 1 writer + 1 reader → +2 readers | partitioned checkpoint table |
| pgvector | read replicas | QPS | rides Aurora readers | 40 MB index; fits in buffer cache |
| LLM | quota + second provider | 429 rate, p95 | — | see llm-capacity doc |

## Statelessness checklist (why any pod can serve any request)
- Conversation state → Postgres checkpoint by `thread_id`.
- HITL pause → the interrupt is *in the checkpoint*; confirm can land on a different pod.
- Rate limits / cache → Redis.
- Index → loaded from Postgres/pgvector (or baked read-only into the image for small KBs).
- No sticky sessions needed on the ALB (SSE reconnect resumes from the last checkpoint).

## Concurrency control inside a pod
- Global `asyncio.Semaphore(150)` per pod → beyond that, **shed with 503 + Retry-After** (fail fast, not queue forever).
- Per-dependency pools: LLM client (max 200 connections), MCP HTTP pools per server (max 50 each).
- Per-thread lock (Redis `SET NX` on `thread_id`, TTL 30 s) → a double-submitted message cannot run two graph turns on one thread concurrently.

## Data partitioning
- Checkpoints partitioned **by day** (`created_at`), dropped after 30 days (instant, no VACUUM storm).
- Traces never in the OLTP DB in prod: Firehose → S3 (parquet, partitioned by `dt/hour`).
- Sharding is not needed at this scale; if needed later, shard checkpoints by `hash(thread_id)`.
