# API Reference (FastAPI)

Base: `http://localhost:8000` · OpenAPI at `/docs`.

Auth: `Authorization: Bearer <token>`. **member** tokens carry the user id (the body never does); **ops** tokens (or `X-Ops-Key`) open the operations routes. Dev mints tokens with `/v1/auth/dev-login`.

| Method | Path | Auth | Body / Query | Returns |
|---|---|---|---|---|
| POST | `/v1/auth/dev-login` | — (dev only) | `{persona: U1001\|U1002\|U1003\|ops}` | `{token, role, sub}` |
| GET | `/v1/me` | member | — | Member name, city, plan |
| POST | `/v1/chat` | member | `{thread_id?, message}` | `TurnResponse` (JSON) |
| POST | `/v1/chat/stream` | member | same | SSE: `node` events, then `final` |
| POST | `/v1/chat/confirm` | member | `{thread_id, approved}` | `TurnResponse` (resumes the paused graph); 409 if nothing pending |
| POST | `/v1/chat/confirm/stream` | member | same | SSE, as above |
| GET | `/v1/threads/{thread_id}` | member | — | Own conversation only |
| POST | `/v1/feedback` | member | `{trace_id, rating, comment?}` | ok (own traces only) |
| GET | `/v1/traces?limit=` | ops | — | Recent traces (summary rows) |
| GET | `/v1/traces/{trace_id}` | ops, or member for own turn | — | Full span tree |
| GET | `/v1/traces/{trace_id}/otlp` | ops, or member for own turn | — | The trace as OTLP/JSON (GenAI conventions, privacy allow-list) |
| GET | `/v1/safety/rules` | ops | — | Threat rule pack: ids, OWASP category, weights, examples |
| GET | `/v1/health/members` | member | — | Self + family on the account, with consent status, scopes, expiry |
| GET | `/v1/health/overview?member=` | member | `member`: father / mother / first name | Medicines (molecules, duplicates, interactions), lab trends, visit brief — same MCP tools and consent checks as chat |
| GET | `/v1/me/data` | member | — | Right of access (DPDP Act 2023): everything held about the member |
| DELETE | `/v1/me/history` | member | — | Right to erasure for conversation data: checkpoints, traces, feedback |
| GET | `/v1/handoffs` | ops | — | Handoff tickets, open first |
| POST | `/v1/handoffs/{ticket_id}/resolve` | ops | `{note?}` | Resolves an open ticket |
| GET | `/v1/evals/latest?set=golden\|heldout` | ops | — | Latest eval report |
| GET | `/v1/kb` | ops | — | Indexed docs, versions, stale flags, scheduled versions |
| POST | `/v1/kb/reindex` | ops | — | Incremental re-index stats |
| GET/POST | `/v1/channels/whatsapp/webhook` | Meta signature | Cloud API payload | Verify handshake / accept messages |
| POST | `/v1/channels/whatsapp/simulate` | ops | `{phone, text}` | Runs one inbound message synchronously |
| GET | `/v1/channels/outbox` | ops | — | Sent / simulated / failed outbound messages |
| GET | `/v1/reminders/due` | ops | — | Reminders a sweep would send now |
| POST | `/v1/reminders/run` | ops | — | Runs the sweep (exactly-once) |
| GET | `/v1/meta` | — | — | Engine mode, models, versions, tools, breakers, storage backends |
| GET | `/healthz`, `/readyz` | — | — | Liveness / readiness |
| GET | `/metrics` | — (bind internally) | — | Prometheus |

## `TurnResponse`
```json
{
  "thread_id": "t-…", "trace_id": "…",
  "status": "answered | needs_confirmation | escalated",
  "answer": "Order ORD-1042 … [tool:get_order_status]",
  "intent": "order_status", "confidence": 0.86,
  "citations": ["tool:get_order_status", "medicine_delivery#delivery-times"],
  "grounded": true, "abstained": false, "cache_hit": false,
  "stale_sources": [], "handoff_ticket": null, "degraded": false,
  "pending_action": null,
  "totals": {"latency_ms": 41.2, "tokens_in": 1830, "tokens_out": 96, "cost_usd": 0.0, "llm_calls": 3, "tool_calls": 1}
}
```
Errors: `401` no/invalid session; `403` wrong role; `429` with `Retry-After` when rate-limited; `422` on invalid body. A failure inside the graph is **not** an HTTP error: it returns `status: escalated`, `intent: system_error` and a handoff ticket (ADR-0015).
