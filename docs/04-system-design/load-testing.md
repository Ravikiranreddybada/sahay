# Load Testing

Scripts: [`backend/loadtest/k6.js`](../../backend/loadtest/k6.js), [`backend/loadtest/locustfile.py`](../../backend/loadtest/locustfile.py).

## Plan
| Test | Shape | Pass criteria |
|---|---|---|
| Smoke | 5 VUs, 2 min | 0 errors |
| Baseline | ramp to 50 turns/s, hold 15 min | p95 ≤ 4 s, error < 0.5 %, no pod > 80 % in-flight |
| Burst | 50 → 150 turns/s in 60 s, hold 5 min | autoscale within 3 min; shed (503) < 2 %; no 5xx from crashes |
| Soak | 30 turns/s, 4 h | no memory growth; checkpoint write latency flat |
| Provider brownout | inject 30 % LLM timeouts (fault flag) | fallback rate ↑, breaker opens, p95 ≤ 8 s, no retry storm |
| MCP outage | kill `mcp-claims` | claim turns degrade to KB + ticket; other intents unaffected |

Run locally (offline engine, measures *our* overhead, not the provider's):
```bash
k6 run -e BASE=http://localhost:8000 backend/loadtest/k6.js
```
Mix used: 35 % order/lab/claim status, 25 % policy FAQ, 15 % journeys, 10 % booking, 10 % follow-ups, 5 % safety cases.
