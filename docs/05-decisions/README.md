# Architecture Decision Records

Format: Context → Decision → Alternatives → Consequences. Status: Accepted unless noted.

| ADR | Decision |
|---|---|
| [0001](ADR-0001-langgraph-explicit-state-machine.md) | LangGraph explicit state machine, not a free-form ReAct agent |
| [0002](ADR-0002-mcp-for-domain-tools.md) | Domain tools as MCP servers, one per bounded context |
| [0003](ADR-0003-stateless-api-durable-checkpoints.md) | Stateless API; conversation state in Postgres checkpoints |
| [0004](ADR-0004-hybrid-retrieval-rrf.md) | Hybrid BM25 + dense with RRF, small k |
| [0005](ADR-0005-model-tiers-and-router.md) | Two model tiers per node + router with fallback and breaker |
| [0006](ADR-0006-deterministic-safety.md) | Deterministic triage, PII and verification outside the model |
| [0007](ADR-0007-injected-user-scope.md) | `user_id` and idempotency keys injected, hidden from the LLM |
| [0008](ADR-0008-eval-gate-in-ci.md) | Eval regression gate blocks merges |
| [0009](ADR-0009-offline-engine.md) | Deterministic offline engine as CI default and degraded mode |
| [0010](ADR-0010-doc-versioning-freshness.md) | Versioned SOPs; superseded never indexed; stale flagged |
| [0011](ADR-0011-hitl-for-writes.md) | Human-in-the-loop confirmation for every write tool |
| [0012](ADR-0012-no-long-term-free-memory.md) | No free-form long-term memory in v1 |
| [0013](ADR-0013-deterministic-tool-fast-path.md) | Deterministic fast-path skips the LLM planner when the call is unambiguous |
| [0014](ADR-0014-signed-sessions-and-ops-role.md) | Signed sessions; user identity never from the request body; ops role |
| [0015](ADR-0015-degrade-dont-fail.md) | Degrade, don't fail: offline engine on LLM outage, handoff on any crash |
| [0016](ADR-0016-whatsapp-as-thin-channel.md) | WhatsApp is a thin channel over the same agent |
| [0017](ADR-0017-reminders-exactly-once.md) | Vaccine reminders: confirmed opt-in, exactly-once sweep |
| [0018](ADR-0018-medicine-database-decides.md) | The medicine database decides interactions and duplicates; the model only explains |
| [0019](ADR-0019-consent-scoped-family-records.md) | Family records behind scoped, expiring consent, enforced in the MCP server |
| [0020](ADR-0020-counterfactual-invariance-gate.md) | Counterfactual invariance (gender, age, name, locality, language) is a hard eval gate |
| [0021](ADR-0021-threat-rule-pack.md) | Prompt-injection detection as a versioned rule pack with executable examples |
| [0022](ADR-0022-otlp-export-privacy-allowlist.md) | OTLP export with GenAI semantic conventions and a privacy allow-list |
