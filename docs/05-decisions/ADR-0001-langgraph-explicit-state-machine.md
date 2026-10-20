# ADR-0001: LangGraph explicit state machine

**Context.** Support turns must finish in seconds, be debuggable node by node, pause for user confirmation, and resume on any replica.
**Decision.** Model the turn as an explicit LangGraph `StateGraph` with named nodes and conditional edges; bounded loops (tool ≤ 4, verify ≤ 1).
**Alternatives.** (a) Single ReAct loop with all tools — unbounded, every failure looks the same in logs. (b) CrewAI/role agents — abstraction hides the control flow we need to own. (c) Hand-rolled async code — re-implements checkpointing and interrupts.
**Consequences.** + Each node unit-testable; traces map 1:1 to nodes; `interrupt()` gives HITL for free. − More upfront design; new intents need routing edits (acceptable: intents are a product decision).
