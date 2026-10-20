# Resume Bullets (pick 3-4 per role)

**Project line:** *Sahay — Grounded multi-agent healthcare care assistant (LangGraph, MCP, Hybrid RAG, Evals, FastAPI, Next.js, AWS design for 1 lakh DAU)*

### AI / LLM engineer
- Built an 11-node **LangGraph** care assistant with **4 MCP servers** (orders, diagnostics, claims, care journeys); least-privilege tool access per intent and human-in-the-loop confirmation for every write via `interrupt()`.
- Designed **context engineering** under a token budget (tool data > profile > memory > evidence) and a **deterministic grounding verifier** (fabricated citations, invented numbers/ids, ignored live data) with one feedback-driven regeneration.
- Shipped an **eval regression gate** (65 golden + 20 held-out end-to-end cases: intent, tool args, recall@5, MRR, grounded rate, 100 % emergency-recall hard gate) that blocks merges in CI.

### ML / Data science
- Implemented **hybrid retrieval** (BM25 + dense, Reciprocal Rank Fusion, feature rerank, version/freshness gating); diagnosed an RRF failure where low-rank noise outranked the correct chunk and fixed it with relative cut-offs (probe set: 3/5 → 7/7 correct top-1).
- Built a cost model and **model-tier router**: fast tier for classification, smart tier for synthesis, deterministic tool fast-path → **−38 % LLM cost (₹3.7 → ₹2.3 per conversation)** at 8 lakh turns/day.

### SDE / backend
- Designed for **1 lakh DAU** (50 turns/s sustained, 150 burst; Little's-law sizing): stateless FastAPI on ECS, durable LangGraph checkpoints in Aurora, Redis rate-limit + semantic cache, SQS workers, 5-level graceful degradation, circuit breakers and multi-provider fallback.
- Prevented **IDOR by construction** (user id injected by the MCP hub, hidden from the LLM) and **double-booking** (sha256 idempotency keys + optimistic concurrency), with PII redaction (Aadhaar Verhoeff, card Luhn) before any model call.
