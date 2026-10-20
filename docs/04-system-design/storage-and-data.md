# Storage and Data

## Aurora PostgreSQL (OLTP)
```sql
-- LangGraph checkpoints (library-managed tables) + our partitioning wrapper
CREATE TABLE checkpoints (... , created_at timestamptz NOT NULL) PARTITION BY RANGE (created_at);
-- daily partitions created by pg_partman; retention 30 days

CREATE TABLE handoffs (
  ticket_id text PRIMARY KEY, thread_id text NOT NULL, user_id text NOT NULL,
  priority text CHECK (priority IN ('P1','P2','P3')), reason text,
  packet jsonb NOT NULL, status text DEFAULT 'open', created_at timestamptz DEFAULT now()
);
CREATE INDEX ON handoffs (status, priority, created_at);

CREATE TABLE feedback (trace_id text, rating smallint, comment text, created_at timestamptz DEFAULT now());

CREATE TABLE kb_chunks (
  chunk_id text PRIMARY KEY, doc_id text, doc_version text, heading_path text, body text,
  review_by date, intents text[], content_hash text, embedder_id text,
  embedding vector(1024)
);
CREATE INDEX ON kb_chunks USING hnsw (embedding vector_cosine_ops) WITH (m = 16, ef_construction = 64);
CREATE INDEX ON kb_chunks USING gin (to_tsvector('english', heading_path || ' ' || body));
```

## Redis
| Key | Type | Purpose |
|---|---|---|
| `rl:{user}` | hash | token bucket (Lua) |
| `lock:thread:{id}` | string NX, TTL 30 s | one turn per thread at a time |
| `sc:{ns}` | RedisVL index | semantic cache |
| `emb:{sha}` | string | query embedding cache |
| `tool:{user}:{tool}:{args}` | string, TTL 30 s | short tool read cache |

## S3 trace lake
`s3://sahay-traces/dt=YYYY-MM-DD/hour=HH/*.parquet` → Athena for analysis (intent mix, abstain reasons,
tool error rates); source for mining new eval cases from 👎 feedback.

## Retention summary
| Data | Hot | Cold | Deletion |
|---|---|---|---|
| Checkpoints | 30 d | — | partition drop |
| Traces | 7 d (sampled 10 % + all errors/👎/abstains) | 90 d S3 | lifecycle rule |
| Tickets | 1 y | — | job |
| Raw PII | never stored | — | redacted at ingress |
