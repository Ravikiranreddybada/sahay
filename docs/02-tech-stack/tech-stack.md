# Tech Stack

Each row: what, why, the alternative we rejected, and the dev vs prod substitute.

## Core runtime
| Layer | Choice | Why | Rejected | Dev → Prod |
|---|---|---|---|---|
| Language | Python 3.11+ (tested on 3.14) | LangGraph/MCP SDKs are Python-first; async I/O fits LLM+tool latency | Node.js (weaker eval/ML tooling) | same |
| API | FastAPI + Uvicorn | Async, Pydantic-native, SSE streaming, OpenAPI for free | Flask (sync), Django (heavy) | Uvicorn → Gunicorn+Uvicorn workers on ECS Fargate |
| Agent runtime | **LangGraph 1.x** | Explicit state machine, conditional edges, `interrupt()` HITL, per-thread checkpoints, streaming of node updates | Free-form ReAct loop (untraceable, unbounded); CrewAI (role-play abstraction, less control) | same |
| Orchestration helpers | LangChain core (minimal) | Only where it fits; we call providers directly for control over caching/tool_choice | Full LangChain chains | same |
| Tool protocol | **MCP Python SDK 2.x** | Standard protocol: same servers usable from the agent, Claude Desktop, other teams; annotations carry read/write semantics | Bespoke REST glue per service ("brittle glue scripts") | In-process `Client(server)` → Streamable HTTP services (`stateless_http`) |
| LLM | **Anthropic Claude** — Haiku 5.5 (fast tier), Sonnet 5.5 (smart tier) | Strong tool use + forced tool_choice for schemas; prompt caching for the stable system prefix | One big model for everything (3-5x cost, 2x latency on narrow tasks) | Offline deterministic engine → Anthropic API / AWS Bedrock (second provider for capacity) |
| Structured output | Pydantic v2 + forced tool call + repair loop | Typed contract between nodes; validation errors are caught and repaired once | "Reply in JSON" prose prompts | same |

## Retrieval
| Layer | Choice | Why | Rejected | Dev → Prod |
|---|---|---|---|---|
| Lexical | BM25 (own, ~40 lines) | Exact ids, drug and test names (HbA1c, ORD-1042) | Dense only | Postgres full-text / OpenSearch |
| Dense | Hashing embedder (offline) | Deterministic, zero-dependency, CI-friendly | sentence-transformers (500 MB download in CI) | Voyage / Cohere / bge-m3 embeddings; **pgvector HNSW** |
| Fusion | Reciprocal Rank Fusion + feature rerank | Rank-only fusion; no score calibration across retrievers | Weighted score sum (needs retuning on every model swap) | + cross-encoder reranker (Cohere Rerank / bge-reranker) behind a flag |
| Vector DB | in-memory numpy | KB is ~10³-10⁴ chunks | — | pgvector (≤ ~10M chunks); Qdrant if KB grows past that |

## State, cache, queues
| Concern | Dev | Prod | Why |
|---|---|---|---|
| Graph checkpoints | SQLite (`AsyncSqliteSaver`) | **Aurora PostgreSQL** (`langgraph-checkpoint-postgres`) | Durable HITL across pods; resume on any replica |
| Semantic cache | in-process numpy | **ElastiCache Redis** + RedisVL vector index | Shared across replicas, TTL eviction |
| Rate limiting | in-process token bucket | Redis Lua token bucket (atomic) | Limits must hold across N replicas |
| Traces | SQLite | OTLP → Langfuse / Phoenix; raw spans → Kinesis → S3 (parquet) → Athena/ClickHouse | Hot debugging + cheap cold analytics |
| Async jobs | — | **SQS** + worker service | KB ingestion/re-embed, eval runs, reminder fan-out |
| Scheduler | — | EventBridge Scheduler | Vaccination 7d/1d reminders |

## Frontend
| Choice | Why |
|---|---|
| **Next.js 16 (App Router) + TypeScript 5.9** | Listed in the role's stack; SSR shell, API proxy route, easy Vercel/ECS deploy |
| Plain CSS with design tokens (`app/globals.css`) | Zero build plugins; light/dark tokens on `:root`; Tailwind was considered and skipped to keep the UI dependency-free |
| SSE (EventSource / fetch stream) | Node-by-node progress streaming; simpler than WebSockets behind ALB |

## Quality
| Tool | Use |
|---|---|
| pytest + pytest-asyncio | Unit + graph integration tests |
| `evals/run_evals.py` | Golden-set eval + regression gate (exit code fails CI) |
| GitHub Actions | tests + eval gate on every PR |
| k6 / Locust | Load tests (scripts in `backend/loadtest/`) |
| Prometheus client | `/metrics` for SLO dashboards |

## Infra
| Concern | Choice |
|---|---|
| Containers | Docker, docker-compose for local full stack |
| Cloud | **AWS**: ALB, ECS Fargate (api, mcp-*, worker), Aurora PG, ElastiCache Redis, SQS, S3, CloudWatch, Secrets Manager, WAF |
| IaC | Terraform (`infra/terraform`) |
| CDN / edge | CloudFront in front of Next.js static assets |
