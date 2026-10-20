# Product Vision

## One line
A care assistant that is **reliably right instead of confidently wrong**: every answer is grounded in
a live record or a versioned policy, every action is confirmed, every emergency reaches a human.

## Who it serves
| User | Moment | What they need in < 10 seconds |
|---|---|---|
| Patient / customer | "Where is my medicine order?" | Live status + ETA from the order system, not a policy paragraph |
| Parent | "Is Aarav's next vaccine due?" | Child-specific due date, what's due the same day, how to book |
| Surgery patient | "What do I do before my cataract surgery?" | Current journey stage, next step, procedure checklist |
| Insured user | "Why is my claim stuck?" | Claim status + exact pending documents |
| Anyone in distress | "Chest pain, can't breathe" | 112 + nearest ER + human agent, in one message, no LLM in the path |
| CS agent (internal) | Bot hands off a user | A context packet: intent, entities, what bot tried — no re-asking |
| AI engineer (internal) | "Why did the bot say 3 days?" | A trace: which chunk, which version, which tool, which prompt |

## Product principles
1. **Live data beats documents.** If a tool knows the answer for this user, the tool wins.
2. **Abstain over guess.** "Let me connect you" is a success state, not a failure.
3. **Actions need consent.** No write (cancel, book) without an explicit "yes" from the user.
4. **Safety is deterministic.** Emergency detection and PII redaction never depend on a model.
5. **Measured, not eyeballed.** No prompt/model change ships without passing the eval gate.
6. **Cheap by default.** Route narrow tasks to small models; cache non-personal answers.

## Non-goals (v1)
- Diagnosis, prescribing, dose changes (explicitly refused and routed to a doctor).
- Voice channel (designed for, not built).
- Multi-lingual generation beyond English (input in Hinglish works for routing; see roadmap).

## Success metrics (north star + guards)
| Metric | Target | Why |
|---|---|---|
| Containment rate (resolved without human) | ≥ 70% | Core business value |
| Grounded-answer rate (verifier pass) | ≥ 98% | Trust |
| Emergency recall | 100% (hard gate) | Patient safety |
| Wrong tool / wrong-args rate | ≤ 2% | Action correctness |
| p95 turn latency | ≤ 4 s (tool turns), ≤ 1.5 s (cached FAQ) | UX |
| Cost per conversation (LLM) | ≤ ₹2.5 (model: ₹2.3, see cost-model) | Unit economics at 1 lakh DAU |
