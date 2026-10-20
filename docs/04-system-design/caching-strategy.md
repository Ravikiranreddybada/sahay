# Caching Strategy — 5 Layers

| # | Layer | Key | TTL | Hit rate (est.) | Saves |
|---|---|---|---|---|---|
| 1 | **Provider prompt cache** | stable system prefix | 5 min (refreshed by traffic) | ~95 % of calls | ~50 % of input-token cost |
| 2 | **Semantic answer cache** (Redis vector) | (intent, prompt_version, kb_version) + query embedding ≥ 0.93 cosine | 1 h | 15-35 % of FAQ turns | a full LLM turn |
| 3 | Query-embedding cache | sha256(normalised query) | 24 h | 30 % | embedding API call |
| 4 | Tool read cache (per user, very short) | (user, tool, args) | 15-30 s | follow-up turns | MCP round-trip |
| 5 | Static catalog cache (lab catalog, hospitals) | tool+args | 10 min | high | domain DB load |

## Never cached
- Any answer that used a tool result (contains one user's data) — enforced in code (`finalize` only caches when `tool_results` is empty).
- `order_status` intent at all (always live).
- Emergency responses (static text, no need).
- Anything with PII placeholders.

## Invalidation
- `kb_version` (hash of indexed chunk hashes) and `prompt_version` are **part of the key** → a policy edit or prompt change invalidates by construction; no manual purge.
- Write tools invalidate layer 4 for that user (e.g., after `cancel_order`, the cached order status is dropped).

## Why threshold 0.93
A semantic near-miss returns the *wrong policy*, which is worse than a miss. 0.93 was chosen so that
paraphrases hit ("refund time for lab test" ≈ "how long lab test refund") while product swaps miss
("refund time for lab test" vs "refund time for medicine"); covered by unit tests.
