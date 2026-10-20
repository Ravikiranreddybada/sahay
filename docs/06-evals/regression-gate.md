# Regression Gate

```bash
cd backend
python -m evals.run_evals                 # run + compare to baseline, exit 1 on regression
python -m evals.run_evals --update-baseline   # accept current metrics (reviewed PR only)
python -m evals.run_evals --only order-status-explicit -v   # debug one case with trace
```
Output: console table + `evals/reports/<timestamp>.json` (metrics, per-case results, config snapshot:
provider, models, prompt_version, kb_version, top_k, budget).

CI (`.github/workflows/ci.yml`) runs tests and the gate on every PR; failure blocks merge.

### Reading a failed gate
1. Look at the per-case table: which cases flipped from pass to fail?
2. Run that case with `-v` → prints the trace (nodes, tool calls, retrieved ids, verifier problems).
3. Classify the cause: routing (intent), planning (tool/args), retrieval (ids/ranks), context (dropped refs), synthesis (verifier problems), or safety.
4. Fix the *layer* that failed (see [../07-debugging/failure-mode-playbook.md](../07-debugging/failure-mode-playbook.md)) — not the prompt by default.
