# MCP Layer

## Servers (one per bounded context)
| Server | Tools | Owner team (prod) |
|---|---|---|
| `orders` | `get_order_status`, `list_recent_orders`, `cancel_order`✍ | Pharmacy |
| `care_services` | `get_lab_report_status`, `search_lab_tests`, `search_doctor_slots`, `book_consultation`✍ | Diagnostics, Consult |
| `claims` | `get_claim_status`, `list_claims`, `find_network_hospitals` | Insurance |
| `care_journeys` | `get_vaccination_schedule`, `get_surgery_journey`, `get_surgery_checklist` | Care programs |

✍ = write tool (`destructiveHint=True`), needs user confirmation.

Run any server standalone (Streamable HTTP):
```bash
python -m sahay.mcp_servers.servers orders --http 8101
```

## The hub (client side) — `sahay/mcp_servers/hub.py`
| Concern | Mechanism |
|---|---|
| Discovery | `list_tools()` on startup; schemas cached as `ToolSpec` |
| **User scoping** | `user_id` removed from every schema the LLM sees, injected from the session per call → IDOR via prompt is impossible |
| **Least privilege** | `INTENT_TOOLS` allow-list per intent; read-only mode drops write tools when injection is suspected |
| **Idempotency** | `idempotency_key = sha256(thread, tool, canonical_args)`; server stores first result; replays return it with `idempotent_replay=true` |
| Concurrency | `book_consultation` uses an optimistic `UPDATE … WHERE booked_by IS NULL`; loser gets "slot just taken" |
| Timeouts | `asyncio.wait_for(call, 5s)`; timeout becomes a user-safe error, never a hung turn |
| Error hygiene | Deliberate `ToolError` messages pass through; crashes are masked by the SDK (no stack traces to the model) |
| Tracing | span per call with args, result, latency, status; Prometheus counter by server/tool/status |
| Indirect injection | Results wrapped in `<data source=…>` and instruction-like lines scrubbed before the model sees them |

## Prod topology 🧭
Each server is its own ECS service behind an internal ALB, `stateless_http=True` so any replica serves
any request. The hub points to them with `SAHAY_MCP_<NAME>_URL`. Bulkheads: separate connection pools
per server, so a slow claims system cannot starve order lookups.
