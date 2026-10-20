# ADR-0004: Hybrid retrieval with RRF, small k

**Context.** Queries mix exact tokens (HbA1c, ORD-1042) and paraphrase ("kid's jab").
**Decision.** BM25 + dense, relative score cut-offs, Reciprocal Rank Fusion (k=60), feature rerank (intent prior, heading match, stale penalty, per-doc cap), top-k=5.
**Alternatives.** Dense only (misses ids); weighted score sum (needs recalibration per embedding model); cross-encoder on everything (+150 ms; adopt only if evals justify).
**Consequences.** + Robust without tuning; explainable ranks in traces. − Found and fixed one fusion bug (INC-001): low-rank noise in both lists outranked the right chunk → relative cut-offs.
