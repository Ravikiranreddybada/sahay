# ADR-0008: Eval regression gate in CI

**Context.** "It looked right in the demo" is how prompt regressions ship.
**Decision.** `evals/run_evals.py` runs the golden set end-to-end through the real graph, computes metrics, compares to `evals/baseline.json`; exits non-zero on regression beyond tolerance or on any hard-gate miss (emergency recall, cross-user leakage).
**Alternatives.** Manual spot checks; unit tests on prompts only.
**Consequences.** + Every prompt/model/KB change is measured. − Golden set must be curated; mined weekly from 👎 traces.
