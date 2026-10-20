# Step-by-Step Build Guide (how to build Sahay from zero)

Each step: **goal → files → how to verify**. Do them in order; each step stands on the previous one.

### Step 1 — Project skeleton
- `backend/pyproject.toml`, `backend/sahay/config.py` (all knobs in one Settings object, env prefix `SAHAY_`).
- Verify: `python -c "from sahay.config import get_settings; print(get_settings())"`.

### Step 2 — Observability first
- `obs/tracing.py`: contextvar-based `start_trace` / `span`, OTel-shaped spans, SQLite `TraceStore`.
- `obs/metrics.py`: Prometheus counters/histograms.
- Why first: every later component emits spans; debugging without them is guessing.

### Step 3 — LLM contract and providers
- `llm/base.py` (`LLM` protocol, `ToolSpec`, `LLMResponse`, price table), `llm/anthropic_llm.py` (cached system block, tool_choice), `llm/offline_llm.py` (deterministic engine).
- `reliability/breaker.py`, `llm/router.py` (tiers, retries with jitter, breaker, fallback, cost spans).
- `llm/structured.py`: forced tool + Pydantic validation + one repair turn.
- Verify: unit tests — breaker opens after N failures; repair path recovers from one bad output.

### Step 4 — Knowledge base
- Write SOPs in `data/kb/*.md` with frontmatter (`doc_id, version, effective_date, review_by, intents`). Include one superseded doc and one past review.
- `rag/chunker.py` (headings, lists whole, hash), `rag/embed.py` (hashing embedder, synonyms, stemmer), `rag/index.py` (BM25 + dense + RRF + rerank + version gate).
- Verify: probe queries return the right chunk first (see INC-001 for the bug you will likely hit).

### Step 5 — Safety
- `safety/pii.py` (Verhoeff, Luhn), `safety/injection.py`, `safety/triage.py`.
- Verify: tests for valid/invalid Aadhaar, negated red flags, injection scores.

### Step 6 — Domain + MCP
- `mcp_servers/store.py` (schema + seed users/orders/claims/journeys), `mcp_servers/servers.py` (4 `MCPServer`s; `user_id` first param; `ToolError` for user-safe errors; write tools with `idempotency_key`).
- `mcp_servers/hub.py` (discovery, injected params, allow-list, timeouts, idempotency keys, spans).
- Verify: another user's order → "not found"; cancel twice → second is `idempotent_replay`.

### Step 7 — Context & caching
- `context/budget.py`, `reliability/cache.py`, `reliability/ratelimit.py`.
- Verify: budget drops lowest-priority evidence first; cache misses on product swap, hits on paraphrase.

### Step 8 — Agent graph
- `agent/state.py` (`TURN_RESET`), `agent/schemas.py`, `agent/prompts/*.md`, `agent/verify.py`, `agent/graph.py` (nodes + edges + `interrupt()`), `store/handoff.py`.
- Verify: integration tests per intent; confirm/decline flow; emergency bypass; follow-up carry-over.

### Step 9 — API
- `api/` + `main.py`: lifespan builds deps (index, hub, router, checkpointer); `/v1/chat`, `/v1/chat/stream`, `/v1/chat/confirm`, traces, feedback, KB, metrics.
- Verify: `curl` examples in [runbook-local-dev.md](runbook-local-dev.md).

### Step 10 — Evals
- `evals/golden.yaml`, `evals/run_evals.py`, `evals/baseline.json`.
- Verify: `python -m evals.run_evals` exits 0; break a prompt on purpose → exits 1.

### Step 11 — Web app
- `web/` Next.js: chat + confirm card + live node timeline; trace inspector; evals dashboard; KB freshness view.

### Step 12 — Infra and CI
- `Dockerfile`s, `docker-compose.yml`, `infra/terraform/*.tf`, `.github/workflows/ci.yml`, `backend/loadtest/*`.
