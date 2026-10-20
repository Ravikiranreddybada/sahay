# ADR-0003: Stateless API, durable checkpoints

**Context.** 1 lakh DAU, rolling deploys, HITL pauses that can last minutes.
**Decision.** API pods keep no conversation state. LangGraph checkpointer persists state per `thread_id` (SQLite dev, Aurora PostgreSQL prod) with `durability="exit"` for turns and per-node durability only around interrupts.
**Alternatives.** Sticky sessions with in-memory state (breaks on deploy/scale-in); Redis-only state (durability and size limits for long threads).
**Consequences.** + Any pod serves any turn; confirm can land anywhere; deploys are invisible. − ~5 ms read + write per turn; storage ~13 GB/day managed by daily partitions.
