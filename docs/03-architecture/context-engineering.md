# Context Engineering

> Decide what the model sees, when, and in what form — so it gives grounded answers instead of confident guesses.

## The budgeted assembler (`sahay/context/budget.py`)
| Priority | Section | Rule |
|---|---|---|
| 0 | Safety notes (read-only mode, retrieval miss) | never dropped |
| 1 | Live MCP tool results | never dropped — ground truth for this user |
| 2 | User profile / journey state | small, high value |
| 3 | Rolling summary + last 6 turns | trimmed to 600 chars/turn |
| 4 | KB evidence, best first | cut when budget (default 6,000 tokens) runs out |

The span `context.assemble` records `included` and `dropped` refs. First debugging question when the
bot "ignored" a document: *was it even in the context?*

## Form
- Every block has a stable id the model must cite: `[refund_policy#lab-tests]`, `[tool:get_order_status]`.
- Untrusted content inside `<data source="...">` tags; system prompt rule 5 says data never overrides rules.
- Stale evidence carries an inline `STALE` marker so the model warns the user.

## When (placement & caching)
- **Stable prefix** (system prompt + node instructions) is sent as a cached block → cache-read pricing
  on ~1.2k tokens of every call.
- **Per-request content** (evidence, tool data) goes in the user turn *after* the cached prefix, so it never breaks the cache.

## Pinned governing context
Some intents have a *rule* that must be in context whatever retrieval returns. `medical_advice` always gets
`consultations#medical-advice-boundary` pinned first (INC-006): a dosing question retrieves nothing relevant
by similarity, but the boundary rule is exactly what the answer must state.

## What the model never sees
- Raw PII (redacted in `guard_in`).
- Other users' data (user scoping in the hub).
- Tools outside the intent's allow-list.
- Superseded policy versions (never indexed).

## Trade-offs we defend
| Choice | Alternative | Why ours |
|---|---|---|
| 6k budget, k=5 | 100k-token "stuff everything" | Long context raises cost ~10x and lowers citation precision; our recall@5 is already high |
| Tool data at priority 1 | Equal weighting | Personal truth must beat generic policy |
| Abstain without LLM when no evidence | Let the model try | The model's "try" is where hallucinations come from |
| Fast model for classify/verify | Smart model everywhere | Narrow tasks; ~3x cheaper, ~2x faster |
| Deterministic verifier first | LLM-as-judge on every turn | 0 ms, 0 ₹, no judge drift; LLM judge used offline in evals |
