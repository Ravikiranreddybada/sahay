# ADR-0006: Deterministic safety outside the model

**Context.** Emergency recall must be 100 % and independent of provider uptime; PII must never reach logs or providers.
**Decision.** Rule-based triage first in the graph (bypasses LLM, cache, tools); regex+checksum PII redaction at ingress; deterministic grounding verifier after every draft.
**Alternatives.** LLM classifier for triage (non-deterministic, outage-coupled); LLM-as-judge on every turn (+cost, +latency, judge drift).
**Consequences.** + Properties hold under model regressions; testable to 100 %. − Rules need maintenance; false positives accepted (cheap). An LLM second net may be added, never as replacement.
