"""Context assembly under a token budget.

"What should the model see, when, in what form" made explicit and testable:

priority 0  user turn + safety notes           never dropped
priority 1  live tool results (MCP)            ground truth about *this* user; never dropped
priority 2  user profile / journey state       small, high value
priority 3  conversation memory                rolling summary + last N turns
priority 4  retrieved KB evidence              best-first, cut when the budget runs out

Everything is rendered with stable ids ([refund_policy#lab-tests], [tool:get_order_status])
so the model can cite and the verifier can check citations. The span records exactly which
evidence was included and which was dropped for budget — the first thing to look at when an
answer "ignored" a document.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

from ..obs.tracing import span
from ..safety.injection import sanitize_untrusted


def count_tokens(text: str) -> int:
    # ~4 chars/token for English; Indic scripts run closer to 2-3, so this over-reserves
    # for Hindi/Kannada text, which is the safe direction for a budget.
    return max(1, len(text) // 4 + text.count("\n") // 4)


@dataclass
class Section:
    name: str
    priority: int
    text: str
    ref: str | None = None
    tokens: int = 0


@dataclass
class AssembledContext:
    text: str
    included: list[str] = field(default_factory=list)
    dropped: list[str] = field(default_factory=list)
    tokens: int = 0
    # Only tool results, profile + KB evidence. The verifier checks numbers/ids against this, never
    # against chat memory: otherwise a number the bot invented in turn 2 is "in context" in
    # turn 3 and launders itself into a grounded fact (INC-013).
    grounding: str = ""


def assemble(
    *,
    query: str,
    budget: int,
    tool_results: list[dict[str, Any]],
    evidence: list[dict[str, Any]],
    profile: dict[str, Any] | None,
    memory: list[dict[str, str]],
    summary: str | None,
    notes: list[str],
) -> AssembledContext:
    sections: list[Section] = []
    fired: dict[str, list[str]] = {}

    def wrap(text: str, ref: str) -> str:
        out, hits = sanitize_untrusted(text, ref)
        if hits:
            fired[ref] = hits
        return out

    for n in notes:
        sections.append(Section("note", 0, f"NOTE: {n}"))
    for tr in tool_results:
        body = json.dumps(tr["result"], ensure_ascii=False) if tr.get("result") is not None else f"ERROR: {tr.get('error')}"
        sections.append(Section("tool", 1, wrap(body, tr["ref"]), ref=tr["ref"]))
    if profile:
        sections.append(Section("profile", 2, "USER PROFILE: " + json.dumps(profile, ensure_ascii=False)))
    if summary:
        sections.append(Section("summary", 3, f"CONVERSATION SUMMARY: {summary}"))
    for m in memory[-6:]:
        sections.append(Section("turn", 3, f"{m['role'].upper()}: {m['content'][:600]}"))
    for ev in evidence:
        stale = " (STALE: past review date, tell the user to confirm)" if ev.get("stale") else ""
        head = f"[{ev['id']}] {ev['title']} > {ev['section']} (v{ev['version']}){stale}"
        sections.append(Section("evidence", 4, wrap(f"{head}\n{ev['text']}", ev["id"]), ref=ev["id"]))

    for s in sections:
        s.tokens = count_tokens(s.text)
    out = AssembledContext(text="")
    used = count_tokens(query)
    keep: list[Section] = []
    for s in sorted(sections, key=lambda x: x.priority):  # stable: evidence keeps rank order
        if s.priority <= 1 or used + s.tokens <= budget:
            keep.append(s)
            used += s.tokens
            if s.ref:
                out.included.append(s.ref)
        elif s.ref:
            out.dropped.append(s.ref)
    order = {"note": 0, "profile": 1, "summary": 2, "turn": 3, "tool": 4, "evidence": 5}
    keep.sort(key=lambda s: order[s.name])
    out.text = "\n\n".join(s.text for s in keep)
    out.grounding = "\n\n".join(s.text for s in keep if s.name in {"tool", "profile", "evidence"})
    out.tokens = used
    if fired:
        with span("guard.indirect_injection", kind="guard", sources=fired):
            pass
    with span("context.assemble", kind="node", budget=budget, tokens=used, included=out.included, dropped=out.dropped):
        pass
    return out
