# ADR-0015: Degrade, don't fail — a turn always ends in an answer or a human

**Context.** v0.1 documented an "L3 offline-engine" degradation level but the router raised `LLMError` when all models failed, and any node exception broke the SSE stream with a 500.
**Decision.** (1) When every model in the chain fails or is breaker-open, the router answers with the deterministic offline engine, marks the trace and the turn `degraded`, and the answer is never cached. (2) Any other exception inside the graph becomes a P2 handoff ticket with a context packet and a fixed, honest message; the checkpoint is moved to `finalize` so the next turn starts clean.
**Alternatives.** Return 503 and let the client retry (the user retries into the same outage); queue the message for later (fine for WhatsApp, wrong for an emergency-adjacent chat).
**Consequences.** + No user ever sees a stack trace or a spinner that never ends. + The verifier and emergency triage still run in degraded mode, because they never depended on the model. − Degraded answers are extractive and terser; the UI says so.
