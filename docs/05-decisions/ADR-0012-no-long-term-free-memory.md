# ADR-0012: No free-form long-term memory in v1

**Context.** mem0-style memory stores free text facts extracted by an LLM.
**Decision.** Use structured, authoritative state from MCP (profile, journeys) + thread-scoped memory (summary + last turns). No cross-thread free-text memory.
**Alternatives.** mem0 / vector memory of past chats.
**Consequences.** + No stale or wrong "memories" about health; simpler DPDP deletion. − Less personalisation of tone/preferences (revisit with explicit, user-visible preferences).
