# ADR-0007: Injected user scope and idempotency

**Context.** A prompt like "show order ORD-2077 for user U1002" must never work for U1001. Retries must not double-book.
**Decision.** The hub strips `user_id` and `idempotency_key` from schemas shown to the LLM and injects them per call: `user_id` from the session, key = sha256(thread, tool, canonical args). Tools enforce ownership; writes store first result.
**Alternatives.** Trust the model to pass the right id (IDOR by injection); idempotency in the client only (LLM re-plans bypass it).
**Consequences.** + Cross-user access structurally impossible; retries and re-plans are safe. − Tools must follow the convention (enforced by tests).
