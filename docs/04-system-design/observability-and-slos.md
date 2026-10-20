# Observability and SLOs

## SLIs / SLOs
| SLI | SLO | Window | Alert |
|---|---|---|---|
| Availability (non-5xx turns) | 99.9 % | 30 d (43 min budget) | burn rate 14.4× over 1 h |
| p95 turn latency (tool turns) | ≤ 4 s | 1 h | > 5 s for 15 min |
| p95 latency cached FAQ | ≤ 1.5 s | 1 h | |
| Emergency path p99 | ≤ 300 ms | 1 h | any breach pages |
| Grounded rate (verifier pass on first or second draft) | ≥ 98 % | 1 d | < 96 % for 1 h |
| Abstain rate | 5-15 % (band) | 1 d | outside band → KB gap or retrieval regression |
| Tool error rate per server | ≤ 1 % | 1 h | > 3 % 10 min |
| LLM fallback rate | ≤ 5 % | 1 h | > 15 % → provider incident |
| Cost per turn | ≤ $0.008 | 1 d | > $0.010 |

## Metrics exported (`/metrics`)
`sahay_requests_total{intent,outcome}`, `sahay_turn_latency_seconds{intent}`, `sahay_node_latency_seconds{node}`,
`sahay_llm_tokens_total{model,direction}`, `sahay_llm_errors_total{model,kind}`, `sahay_tool_calls_total{server,tool,status}`,
`sahay_semantic_cache_total{result}`, `sahay_grounding_total{verdict}`, `sahay_escalations_total{reason}`.

## Traces
- Every turn = one trace; spans per node, LLM call, tool call, retrieval, context assembly.
- Span attributes: tokens, cost, model, fallback flag, retrieved chunk ids + ranks, included/dropped refs, tool args/result, verifier problems.
- Sampling in prod: 10 % of normal traces + **100 %** of errors, abstains, verifier failures, 👎 feedback, escalations.
- Built-in trace inspector in the web app (waterfall + span attributes) — the debugging UI.

## Dashboards
1. Golden signals per intent (rate, errors, p50/p95).
2. Quality: grounded %, abstain %, regeneration %, 👍/👎 ratio, top verifier problems.
3. Cost: tokens and $ per turn by node and model; cache hit rates (provider + semantic).
4. Dependencies: per MCP server latency/error; LLM per model latency/429s; breaker states.
