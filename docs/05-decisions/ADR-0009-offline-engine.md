# ADR-0009: Deterministic offline engine

**Context.** CI must not depend on API keys or network; degraded mode must be tested before it is needed.
**Decision.** `OfflineLLM` implements the same `LLM` contract: lexicon intent scoring, regex entities, rule tool planning, extractive cited answers. Default when no API key; L3 degradation mode in prod.
**Alternatives.** Mock responses per test (brittle, tests nothing real); recorded cassettes (stale).
**Consequences.** + Whole graph + evals run in seconds offline; a baseline the real model must beat to justify cost. − Less fluent; not a substitute for real-model evals (run nightly with the key).
