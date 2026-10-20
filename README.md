# Sahay — Grounded Care Assistant

A multi-agent healthcare **care assistant** that is *reliably right instead of confidently wrong*: query
resolution for orders, lab reports, claims and refunds, plus personalised **vaccination** and **surgery**
journeys. LangGraph + MCP + hybrid RAG + eval gate. Designed for **1 lakh daily active users**.

```
guard_in ─► classify ─► plan_tools ⇄ confirm(HITL) ─► retrieve ─► answer ─► verify ─► finalize
   │            ├─► handoff        (4 MCP servers)       │ cache hit ─────────────────▲
   └─► emergency (no LLM)  └─► smalltalk                └────── regenerate once ◄──┘
```

| | |
|---|---|
| Agent runtime | LangGraph state machine, 11 nodes, bounded loops, `interrupt()` for write confirmation, durable checkpoints (Postgres or SQLite), per-thread turn lock (Redis across replicas) |
| Tools | 5 MCP servers, 22 tools, Streamable HTTP with service-token auth; hub injects `user_id` + per-user idempotency keys (no IDOR, no double booking, no cross-user replay) |
| Retrieval | Structure-aware chunking, BM25 + dense + RRF, version gate (superseded *and* not-yet-effective SOPs never served), stale flags, atomic re-index |
| Context | Token-budgeted assembly (tool data > profile > memory > evidence), member profile per thread, pinned governing rules, cited ids |
| Safety | Deterministic emergency triage in English, Hinglish and Devanagari (0 LLM calls), PII redaction with Aadhaar/Luhn checksums (also in traces and outbox), **threat rule pack** (13 ATR-style rules, OWASP LLM Top 10, Hinglish + Devanagari, every example a test) → read-only mode; indirect-injection lines stripped from tool/KB data |
| Privacy | DPDP Act data rights: export everything (`GET /v1/me/data`), erase conversation history (`DELETE /v1/me/history`); OTLP export ships no health data |
| Grounding | Deterministic verifier against tool data + evidence only (never chat memory), as a 9-criterion **scorecard**: fake citations, invented numbers/ids, ignored live data, dosing language, claimed actions that never ran, "it's safe" verdicts, interactions not from the medicine database |
| Family health records | Caregiver view of a parent's records under **scoped, expiring consent** (checked in the MCP server); brands → molecules incl. combination products; same molecule from two prescribers; recorded interactions with source (**the database decides, the model explains**); lab trends across labs and units with the conversion cited; visit brief with the questions worth asking |
| Auth | Signed session tokens; user identity never from the request body; `ops` role for traces, handoffs, KB, evals, channels |
| Reliability | Model tiers, retries, circuit breaker, fallback model, **offline-engine degradation** on full outage, crash → handoff (never a 500), Redis limiter + semantic cache keyed by prompt+KB version |
| Channels | WhatsApp Cloud API webhook (signature check, retry dedupe, Yes/No buttons resume the graph) over the same agent; vaccine reminders 7 days / 1 day before each dose, exactly once |
| Evals | 78 golden + 24 held-out end-to-end cases + **counterfactual invariance** suite (141 runs: gender, age, name, locality, language must not change the decision), hard gates (emergency recall, write confirmation, cross-user leak, counterfactual consistency), CI gate |
| Observability | Own span store + **OTLP/JSON export with OpenTelemetry GenAI conventions** (`invoke_agent`, `chat`, `execute_tool`) to any collector, privacy allow-list |
| UI | Next.js: chat with live node stream + confirm cards + grounding scorecard + voice input (en-IN / hi-IN), **Health tab** (family switcher, molecule chips, flags, lab sparklines with reference band, visit brief, data rights), WhatsApp simulator + reminders + outbox, trace waterfall, eval dashboard (golden / held-out / counterfactual), KB freshness + handoff queue |

## Run it
```bash
python3 -m venv .venv && .venv/bin/pip install -e "backend[dev]"
cd backend && ../.venv/bin/uvicorn sahay.main:app --port 8000      # API (offline engine if no key)
cd web && npm install && npm run dev                              # http://localhost:3000
cd backend && ../.venv/bin/pytest -q && ../.venv/bin/python -m evals.run_evals
docker compose up --build                                         # full stack: Postgres, Redis, remote MCP server
```
Set `ANTHROPIC_API_KEY` to use Claude (Haiku 5.5 fast tier, Sonnet 5.5 smart tier). Without it, the deterministic
offline engine runs everything — it is also the production degradation mode (ADR-0015).

## Status (honest)
| Area | State |
|---|---|
| Backend, graph, MCP, RAG, safety, auth, channels, evals, web build | ✅ built; 123 tests pass (incl. real Postgres, Redis via fakeredis+Lua, remote MCP over HTTP) |
| Golden 78/78, held-out 24/24, counterfactual 15/15 (141 runs) | ✅ offline engine — gates proven to fail when triage is broken or biased on purpose; caveats in [docs/06-evals/eval-strategy.md](docs/06-evals/eval-strategy.md) |
| Medicine interaction table | ⚠️ small curated demo set with sources; not a clinical reference (production: licensed DDI source behind the same call, ADR-0018) |
| Health tab in a browser | ⏳ typecheck + prod build pass; not yet clicked through in a browser |
| Docker compose (API ×2 workers, Postgres, Redis, remote MCP, web) | ✅ built and run end-to-end; first run found a migration race (fixed) |
| Terraform | ✅ `init` + `validate` + `fmt` pass; never `apply`-ed (no AWS account used) |
| Real-model eval numbers | ⏳ not measured (needs `ANTHROPIC_API_KEY`) |
| WhatsApp to a real number | ⏳ needs a Meta app, number and token; today replies go to the outbox as `simulated` |
| Traces / handoffs / outbox in Postgres | 🧭 still SQLite files; checkpoints, cache, limiter and locks have prod backends |

v0.3 (October 2026, from a sweep of trending GitHub repos — see [research](docs/01-research/github-repo-research.md#october-2026-sweep--trending-repos-and-what-v03-took)) added family health records, the verifier scorecard, the threat rule pack, the counterfactual gate, OTLP export and DPDP data rights, and found INC-017…019 on the way.

The October 2026 audit (INC-009…016 in [docs/07-debugging/incident-log.md](docs/07-debugging/incident-log.md)) found and fixed: emergency phrasings that were missed, a cross-user idempotency replay, a wrong-child vaccine answer, raw PII in traces, no API auth, crashes on LLM outage, lost messages under concurrent turns, and a verifier that trusted numbers from chat memory.

## Docs
Start at [docs/README.md](docs/README.md): research (what we took from 30+ repos), tech stack, architecture,
**system design for 1 lakh users** (capacity math, scaling, caching, degradation ladder, cost model ₹2.3/conversation),
22 ADRs, eval strategy, failure-mode playbook + 19 real incidents, build guide, interview kit.

## Layout
```
backend/sahay/   agent/ (graph, nodes, verifier, prompts)  llm/ (router, adapters, offline engine, structured)  health/ (catalog, labs)
                 mcp_servers/ (servers, hub, store)  channels/ (whatsapp, reminders, outbox)  rag/  context/
                 safety/ (+ rules/threat_rules.yaml)  obs/ (+ otel.py)  reliability/ (breaker, cache, limiter, redis)  store/  auth.py  main.py
backend/data/kb/ versioned SOPs     backend/evals/ golden + held-out + counterfactual + runner     backend/tests/
web/             Next.js app        infra/terraform/   docker-compose.yml   .github/workflows/ci.yml   docs/
```
