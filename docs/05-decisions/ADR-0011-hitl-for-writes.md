# ADR-0011: Human-in-the-loop for writes

**Context.** Cancelling an order or booking a slot is irreversible from the user's view.
**Decision.** Write tools (annotated `destructiveHint`) never execute directly; `plan_tools` sets `pending_action`, `confirm` calls `interrupt()` and the client must send `approved: true`. Decline is recorded and answered.
**Alternatives.** Execute and offer undo (not all actions are undoable); confirm via prompt only (model may skip it).
**Consequences.** + No surprise actions; audit trail. − One extra round-trip on write flows (acceptable).
