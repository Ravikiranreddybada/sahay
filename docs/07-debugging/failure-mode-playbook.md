# Failure-Mode Playbook

> Trace it to the real cause — bad chunking, prompt regression, schema mismatch — instead of papering over it with a bigger prompt.

Start every investigation from the **trace** (`/v1/traces/{id}` or the Trace tab). Read spans top-down.

| Symptom | First span to read | Likely root causes | Fix at the right layer |
|---|---|---|---|
| Confident wrong policy number | `retrieval.hybrid` hits + `context.assemble` | superseded doc indexed; wrong chunk ranked first; right chunk dropped for budget | version gate; rerank features / cut-offs; budget priority |
| Right doc, wrong section | `retrieval.hybrid` (section ids) | chunk boundary split heading from table | structure-aware chunker; heading path in embed text |
| Answer ignores user's order | `tool.*` spans, verifier `problems` | wrong intent → no tools; tool error; context priority | classify prompt/lexicon; tool allow-list; priority 1 |
| Wrong tool / args | `llm.plan_tools` `tool_calls` | ambiguous tool descriptions; id not extracted; schema mismatch | sharpen tool docstrings; entity pattern; fast-path rule |
| `structured.repair` span present | `llm.classify` output | enum drift, missing field, prompt changed shape | fix schema or prompt; never loosen schema silently |
| Follow-up loses context | `guard_in` → `classify` (entities) | entities not carried; summary missing | carry-over rules; memory window |
| Old tool result cited this turn | `context.assemble` included refs | turn-level state not reset | `TURN_RESET` (tested) |
| Emergency not escalated | `guard_in` `triage` | missing red-flag phrase; negation false match | add pattern + golden case; recall gate |
| Slow turn | span durations waterfall | provider latency, retries, breaker half-open, tool timeout | router timeouts; fallback; fast-path |
| Cost spike | `llm.*` spans tokens | budget too high; regenerate loop; cache miss after kb change | budget; verifier feedback quality; pre-warm |

## Hypothesis-first discipline
1. Write the hypothesis ("fusion promotes noise") **before** changing anything.
2. Reproduce with a minimal case (one query, one doc).
3. Measure each component in isolation (BM25 ranks vs dense ranks vs fused).
4. Fix one layer; add a golden case; run the gate.
