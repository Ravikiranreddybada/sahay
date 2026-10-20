# Talking Points (questions you will get, and the 30-second answer)

**"Why not just a bigger prompt / longer context?"** Long context raises cost ~10× and lowers citation precision. Our failures were in retrieval and routing, not prompt length — INC-001 is the proof: the right chunk existed, fusion buried it.

**"How do you know a prompt change helped?"** Golden set through the full graph, metrics vs baseline, gate in CI; per-case diffs show which cases flipped. Nightly real-model run + LLM-judge for faithfulness (tracked, not gated, because judges drift).

**"How do you stop hallucinations?"** Four layers: abstain without calling the model when nothing is retrieved; ids on every context block + citation rule; deterministic verifier (fabricated cites, numbers/ids not in context); regenerate once with the problems, else safe abstain + handoff.

**"Retrieval fails — why?"** Stale embeddings (model changed, vectors not), bad chunking (heading split from table), wrong top-k (too many → wrong citation), superseded versions indexed. Each has a mechanism here: embedder id, structure-aware chunks, k=5 + per-doc cap, version gate.

**"What breaks at 1 lakh users?"** Provider quota and latency, not CPU. So: admission control + token governor, two providers, fast-path and tiering to cut calls, cache for FAQs, degradation ladder down to the offline engine. API sizing via Little's law: 150 turns/s × 2.5 s = 375 in flight → 4 pods, run 6 for HA.

**"Latency vs accuracy trade-off you made?"** Verifier is deterministic (0 ms) instead of LLM-judge per turn (+400 ms). Classification on the fast tier. Cross-encoder reranker *not* enabled until evals show ≥ 3 pts gain for ≤ 150 ms.

**"Failure mode you personally hit?"** Eight logged in `docs/07-debugging/incident-log.md`. Best two: INC-001 (RRF fusion promoted noise over the right chunk — measured each retriever alone to prove it) and INC-008 (a carried order id from turn 1 made a policy question in turn 2 trigger a live lookup — memory as a correctness hazard).

**"Security?"** User id injected server-side → no IDOR by prompt; read-only mode on injection signals; tool output treated as untrusted data; PII redacted before the model.
