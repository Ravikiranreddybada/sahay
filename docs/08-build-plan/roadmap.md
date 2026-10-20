# Roadmap — Phases and Exit Criteria

| Phase | Scope | Exit criteria | Status |
|---|---|---|---|
| P0 Research | GitHub repo study, REA competitor study, JD mapping | docs/01-research written | ✅ |
| P1 Foundations | config, tracing, metrics, LLM contract, Anthropic adapter, offline engine, router (retry/breaker/fallback), structured output + repair | unit tests for breaker, structured repair | ✅ |
| P2 Knowledge | SOP corpus with versions, structure-aware chunker, hybrid index (BM25+dense+RRF), freshness | retrieval probes 100 % on probe set | ✅ |
| P3 Safety | PII (checksums), injection scoring + sanitiser, triage | unit tests | ✅ |
| P4 Tools | domain store + seed, 4 MCP servers, hub (scoping, authz, idempotency, timeouts) | IDOR + idempotency tests | ✅ |
| P5 Context | budgeted assembler, semantic cache, rate limiter | unit tests | ✅ |
| P6 Agent graph | state, prompts, nodes, verifier, HITL confirm, handoff, memory | graph integration tests | ✅ |
| P7 API | FastAPI: chat, stream (SSE), confirm, traces, feedback, KB, metrics | curl + proxy tests | ✅ |
| P8 Evals | golden set (~50 cases), runner, metrics, baseline, gate | gate green; gate shown to fail on regression | ✅ |
| P9 Web | Next.js: chat with confirm cards + live node stream, trace inspector, evals dashboard, KB view | typecheck + prod build pass | ✅ (browser walkthrough pending) |
| P10 Infra | Dockerfiles, compose, Terraform (AWS), CI workflow, load tests | `docker compose up` works; CI green | ✅ compose built and run end-to-end (found + fixed a Postgres migration race and a wrong healthcheck); Terraform `validate`/`fmt` pass (added the missing ECS execution role, secrets, logs); never `apply`-ed |
| P11 Hardening | audit (INC-009…016): auth, triage recall, idempotency scope, degradation, locks; Postgres checkpointer; Redis limiter/cache/locks | 91 tests incl. real Postgres; gate green | ✅ (real-model evals, LLM-judge, reranker experiment still 🔜) |
| P13 Care intelligence (v0.3) | family health records MCP server (molecules, duplicates, interactions, lab trends, visit brief, consent), verifier scorecard + medicine criteria, threat rule pack, counterfactual gate, OTLP export, DPDP rights, Health tab, voice input | 123 tests; golden 78/78; counterfactual 15/15 (141 runs); held-out 24/24 | ✅ (licensed DDI source, prescription photo intake, voice replies, consent-granting app 🔜) |
| P12 Journeys+ | vaccination reminders (opt-in write + exactly-once sweep), Hinglish/Devanagari triage, WhatsApp channel | API tests + golden cases | ✅ local; real Meta number + EventBridge worker 🔜 |
