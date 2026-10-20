# ADR-0013: Deterministic tool fast-path

**Context.** ~50 % of tool turns contain exactly one id that maps to exactly one read tool ("status of ORD-1042"). Asking the smart model to plan that costs ~$0.0034 and ~600 ms for zero information gain.
**Decision.** `plan_tools` first checks a rule table (intent + entity → tool + args) for **read** tools; if it matches, the call is made without the LLM. Ambiguous asks and every write go through the LLM planner (+ confirmation).
**Alternatives.** Always LLM-plan (simple, slow, costly); never LLM-plan (brittle for multi-step asks).
**Consequences.** + −1 smart call on ~half of tool turns; −38 % total LLM cost with tiering. − Rule table must stay in sync with tool schemas (covered by tests).
