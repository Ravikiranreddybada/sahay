"""Graph state. Conversation-level fields persist across turns via the checkpointer;
turn-level fields are reset by guard_in so a stale tool result from turn 3 can never leak
into the answer of turn 4 (a real class of "context loss / context bleed" bugs)."""

from __future__ import annotations

from typing import Annotated, Any, TypedDict

MAX_MESSAGES = 20


def keep_recent(old: list[dict[str, str]] | None, new: list[dict[str, str]] | None) -> list[dict[str, str]]:
    """Append reducer with a cap. `operator.add` grew the checkpoint by two messages every
    turn forever: a 300-turn thread re-serialised ~300 messages on each step. Older turns
    live on in the rolling summary, which is what the prompt uses anyway."""
    return ((old or []) + (new or []))[-MAX_MESSAGES:]


class AgentState(TypedDict, total=False):
    # conversation-level (persisted)
    user_id: str
    thread_id: str
    messages: Annotated[list[dict[str, str]], keep_recent]
    entities: dict[str, str]
    previous_intent: str | None
    summary: str | None
    profile: dict[str, Any]

    # turn-level (reset each turn)
    query: str
    pii_found: dict[str, int]
    injection_score: float
    read_only: bool
    triage: dict[str, Any]
    intent: str
    confidence: float
    search_query: str
    tool_results: list[dict[str, Any]]
    tool_steps: int
    pending_action: dict[str, Any] | None
    evidence: list[dict[str, Any]]
    context_refs: list[str]
    context_text: str
    grounding_text: str  # tool results + KB evidence only: what the verifier checks facts against
    degraded: bool
    draft: dict[str, Any]
    verify: dict[str, Any]
    verify_attempts: int
    cache_hit: bool
    route: str
    final: dict[str, Any]


TURN_RESET: dict[str, Any] = {
    "tool_results": [], "tool_steps": 0, "pending_action": None, "evidence": [], "context_refs": [],
    "context_text": "", "grounding_text": "", "degraded": False, "draft": {}, "verify": {}, "verify_attempts": 0, "cache_hit": False,
    "final": {}, "route": "", "triage": {}, "pii_found": {}, "injection_score": 0.0, "read_only": False,
}
