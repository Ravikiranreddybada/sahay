# ADR-0010: Versioned SOPs and freshness

**Context.** Policies change; old versions linger in vector stores and get retrieved with real citations.
**Decision.** Frontmatter `doc_id`, `version`, `effective_date`, `review_by`, `intents`. Only the latest version per `doc_id` is indexed. Past-`review_by` chunks are soft-penalised and flagged STALE to the model and user. `kb_version` is part of the cache key.
**Alternatives.** Delete old files by hand (humans forget); hard-drop stale docs (loses the only available answer).
**Consequences.** + v1 refund policy (10-14 days) can never be served once v2 (5-7 days) exists — tested. − Owners must maintain `review_by` (dashboard of stale docs via `/v1/kb`).
