import asyncio

import pytest

from sahay.agent.schemas import IntentResult
from sahay.agent.verify import verify_draft
from sahay.config import Settings
from sahay.context.budget import assemble
from sahay.llm.base import LLMError, LLMResponse, ToolCall
from sahay.llm.router import ModelRouter
from sahay.llm.structured import structured
from sahay.rag.embed import HashingEmbedder
from sahay.reliability.breaker import CircuitBreaker
from sahay.reliability.cache import SemanticCache
from sahay.reliability.ratelimit import TokenBucket


def test_breaker_opens_and_half_opens():
    b = CircuitBreaker("m", failure_threshold=2, reset_timeout_s=0.05)
    b.record_failure(); b.record_failure()
    assert b.state == "open" and not b.allow()
    import time; time.sleep(0.06)
    assert b.allow() and not b.allow()  # exactly one half-open probe
    b.record_success()
    assert b.state == "closed"


class FlakyThenBad:
    """First call: invalid schema. Second call: valid. Exercises the repair loop."""
    name = "flaky"

    def __init__(self):
        self.calls = 0

    async def generate(self, **kw):
        self.calls += 1
        args = {"intent": "not_an_intent", "confidence": 2} if self.calls == 1 else {"intent": "order_status", "confidence": 0.9, "search_query": "x"}
        return LLMResponse(tool_calls=[ToolCall("1", "emit_classify", args)])


async def test_structured_repairs_once():
    p = FlakyThenBad()
    r = ModelRouter(Settings(), provider=p)
    out = await structured(r, IntentResult, tier="fast", system="s", messages=[{"role": "user", "content": "q"}], task="classify")
    assert out.intent == "order_status" and p.calls == 2


class AlwaysDown:
    name = "down"
    calls = 0

    async def generate(self, **kw):
        AlwaysDown.calls += 1
        raise LLMError("503")


async def test_router_falls_back_then_raises():
    s = Settings(llm_max_retries=0, model_smart="a", model_fallback="b", degrade_to_offline=False)
    r = ModelRouter(s, provider=AlwaysDown())
    with pytest.raises(LLMError):
        await r.generate(tier="smart", system="s", messages=[], task="t")
    assert AlwaysDown.calls == 2  # primary + fallback


def test_rate_limit():
    tb = TokenBucket(per_minute=60, burst=3)
    assert [tb.allow("u")[0] for _ in range(4)] == [True, True, True, False]
    assert tb.allow("other")[0]


async def test_semantic_cache_namespacing():
    c = SemanticCache(HashingEmbedder(), threshold=0.9)
    await c.put("how long does a lab test refund take", "refund_cancel", "v3", "kb1", {"draft": 1})
    assert await c.get("how long does a lab test refund take", "refund_cancel", "v3", "kb1")
    assert await c.get("how long does a lab test refund take", "refund_cancel", "v3", "kb2") is None  # kb changed
    assert await c.get("how long does a lab test refund take", "refund_cancel", "v4", "kb1") is None  # prompt changed
    assert await c.get("where is my order", "order_status", "v3", "kb1") is None  # never cached intent


def test_budget_keeps_tools_drops_evidence():
    ev = [{"id": f"d#{i}", "title": "t", "section": "s", "version": "1", "text": "word " * 400} for i in range(6)]
    tr = [{"tool": "x", "ref": "tool:x", "result": {"a": 1}}]
    ctx = assemble(query="q", budget=800, tool_results=tr, evidence=ev, profile=None, memory=[], summary=None, notes=[])
    assert "tool:x" in ctx.included and ctx.dropped and ctx.included.index("tool:x") == 0


def test_verifier_catches_invented_number_and_fake_cite():
    ctx = "[refund_policy#lab-tests] refunds in 5-7 working days"
    bad = {"answer": "Refund in 3 days [refund_policy#lab-tests] [made#up]", "citations": [], "abstained": False}
    v = verify_draft(bad, ctx, ["refund_policy#lab-tests"], had_tools=False)
    assert not v["ok"] and any("numbers" in p for p in v["problems"]) and any("not in context" in p for p in v["problems"])
    good = {"answer": "Refunds take 5-7 working days. [refund_policy#lab-tests]", "citations": ["refund_policy#lab-tests"], "abstained": False}
    assert verify_draft(good, ctx, ["refund_policy#lab-tests"], had_tools=False)["ok"]


def test_verifier_requires_tool_use_when_available():
    v = verify_draft({"answer": "Policy says X. [a#b]", "citations": ["a#b"]}, "[a#b] X", ["a#b", "tool:get_order_status"], had_tools=True)
    assert "live tool result was available but not used" in v["problems"]
