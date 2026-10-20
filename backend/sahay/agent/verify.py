"""Grounding verifier. Runs on every draft before the user sees it.

Cheap, deterministic checks catch the failure modes that matter most in support:
* fabricated citation       - cites a source that was not in the context
* invented number / id      - "refund in 3 days", "₹1,500", "ORD-9999" not present in context
* ignored live data         - tool result present but the answer cites only policy text
* uncited claim             - non-abstained answer with zero citations
* medical boundary          - dosing / prescribing language not coming from a record
* phantom action            - "I've cancelled it" when no write tool succeeded this turn
* safety claim              - "it's safe to take with ..." (absence in a database is never safety)
* ungrounded interaction    - names a medicine interaction without a health-record tool result
Each check is a named criterion with its own pass/fail (criteria decomposition, from
llm-as-a-verifier): the UI shows a scorecard, and the trace says *which* rule failed.
A failed draft gets one regeneration with the problems as feedback; if it fails again the
user gets a safe abstain + human handoff instead of a confident wrong answer.
"""

from __future__ import annotations

import re
from typing import Any

CITE = re.compile(r"\[([a-z_]+#[a-z0-9-]+|tool:[a-z_]+)\]")
NUM = re.compile(r"(?:₹\s?)?\b\d[\d,]*(?:\.\d+)?\b")
ID = re.compile(r"\b(?:ORD|CLM|LAB|BKG|S)-\d+\b")
DOSING = [
    re.compile(r"\btake\b[^.]{0,40}\b(\d+\s?mg|tablet|capsule|twice|once|times a day|daily)\b", re.I),
    re.compile(r"\byou (should|can|may) (start|stop|take|increase|reduce)\b[^.]{0,40}\b(medicine|tablet|dose|insulin|metformin)", re.I),
]
# First-person claims of a completed action. A model that "helpfully" says it cancelled an
# order it never touched is the most expensive hallucination in support (the user stops
# watching for a delivery that is still coming).
ACTION_CLAIM = re.compile(r"\b(i|we)('ve| have| just)? (cancel+ed|booked|scheduled|refunded|set up|turned on|activated|revoked)\b", re.I)
# A clear database result is not a safety verdict (rxcheck: the database decides, the model explains).
SAFE_CLAIM = re.compile(
    r"\b(is|are|it's|it is|they're|that's)\s+(completely |perfectly |totally |absolutely )?safe\b(?! for a person)"
    r"|\b(no|without any) (known )?(drug )?interactions?\b(?!\s+(or duplicate\s+)?(is|are)\s+recorded)|\bwon'?t interact\b|\bfine to take\b", re.I)
INTERACTION_WORD = re.compile(r"\binteract(s|ion|ions)?\b", re.I)
HEALTH_TOOLS = {"tool:check_medication_safety", "tool:get_medication_list", "tool:get_visit_brief"}
CRITERIA = ["citation_integrity", "cited", "live_data_used", "numbers_grounded", "ids_grounded", "medical_boundary",
            "action_honesty", "no_safety_verdict", "interactions_from_database"]



def _norm_num(s: str) -> str:
    n = s.replace("₹", "").replace(",", "").strip()
    return n[:-2] if n.endswith(".0") else n


def verify_draft(draft: dict[str, Any], context_text: str, context_refs: list[str], had_tools: bool, had_write: bool = False) -> dict[str, Any]:
    """`context_text` must be the grounding text (tool results + evidence), not chat memory."""
    from ..health.catalog import find_mentions

    crit: dict[str, str | None] = dict.fromkeys(CRITERIA)  # None = pass, str = the problem
    answer: str = draft.get("answer", "")
    abstained = bool(draft.get("abstained"))
    inline = set(CITE.findall(answer))
    declared = set(draft.get("citations", []))
    refs = set(context_refs)
    cites = inline | declared

    fabricated = sorted(cites - refs)
    if fabricated:
        crit["citation_integrity"] = f"cites sources not in context: {fabricated}"
    if not abstained and not cites:
        crit["cited"] = "factual answer without any citation"
    if had_tools and not abstained and not any(c.startswith("tool:") for c in cites):
        crit["live_data_used"] = "live tool result was available but not used"

    body = CITE.sub("", answer)
    ctx_nums = {_norm_num(n) for n in NUM.findall(context_text)}
    bad_nums = [n for n in NUM.findall(body) if _norm_num(n) not in ctx_nums and len(_norm_num(n)) > 0 and _norm_num(n) not in {"1", "2"}]
    if bad_nums:
        crit["numbers_grounded"] = f"numbers not found in context: {sorted(set(bad_nums))}"
    bad_ids = [i for i in ID.findall(body) if i not in context_text]
    if bad_ids:
        crit["ids_grounded"] = f"ids not found in context: {sorted(set(bad_ids))}"
    for pat in DOSING:
        m = pat.search(body)
        if m and m.group(0) not in context_text:
            crit["medical_boundary"] = f"medical advice boundary: '{m.group(0)}'"
            break
    if not had_write and (m := ACTION_CLAIM.search(body)):
        crit["action_honesty"] = f"claims an action that was not performed: '{m.group(0)}'"
    if (m := SAFE_CLAIM.search(body)) and m.group(0) not in context_text:
        crit["no_safety_verdict"] = f"states a medicine safety verdict: '{m.group(0)}'"
    if INTERACTION_WORD.search(body) and find_mentions(body) and not (cites & HEALTH_TOOLS):
        crit["interactions_from_database"] = "names a medicine interaction without a medicine-database result"

    problems = [p for p in crit.values() if p]
    scorecard = {k: v is None for k, v in crit.items()}
    return {"ok": not problems, "problems": problems, "citations": sorted(cites), "scorecard": scorecard,
            "score": round(sum(scorecard.values()) / len(scorecard), 3)}
