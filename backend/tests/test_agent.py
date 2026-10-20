"""Graph integration tests (offline engine, fresh data per test)."""


async def turn(agent, msg, user="U1001", thread="t", **kw):
    return await agent.run_turn(user_id=user, thread_id=thread, message=msg, **kw)


async def test_emergency_bypasses_llm(agent):
    r = await turn(agent, "my husband has chest pain")
    assert r["intent"] == "emergency" and r["totals"]["llm_calls"] == 0 and r["handoff_ticket"]


async def test_fast_path_skips_planner(agent):
    r = await turn(agent, "Where is my order ORD-1042?")
    trace = agent.deps.traces.get(r["trace_id"])
    names = [s["name"] for s in trace["spans"]]
    assert "plan.fast_path" in names and "llm.plan_tools" not in names


async def test_idor_blocked(agent):
    r = await turn(agent, "status of ORD-2077")
    assert "no order ord-2077 found" in r["answer"].lower() and "insulin" not in r["answer"].lower()


async def test_write_requires_confirmation_and_is_idempotent(agent):
    r = await turn(agent, "Cancel order ORD-1043", thread="w")
    assert r["status"] == "needs_confirmation" and r["pending_action"]["tool"] == "cancel_order"
    r = await agent.run_turn(user_id="U1001", thread_id="w", resume={"approved": True})
    assert "cancelled" in r["answer"]
    rows = agent.deps.hub  # second identical call on same thread is a replay
    tr = await rows.call("cancel_order", {"order_id": "ORD-1043", "reason": "customer_request"}, user_id="U1001", thread_id="w")
    assert tr.result["idempotent_replay"] is True


async def test_new_message_declines_pending_action(agent):
    await turn(agent, "Cancel order ORD-1043", thread="d")
    r = await turn(agent, "actually, where is ORD-1042?", thread="d")
    assert r["status"] == "answered" and "ORD-1042" in r["answer"]
    order = agent.deps.hub
    st = await order.call("get_order_status", {"order_id": "ORD-1043"}, user_id="U1001", thread_id="x")
    assert st.result["status"] == "packed"  # not cancelled


async def test_follow_up_carries_entities_and_resets_turn_state(agent):
    await turn(agent, "Where is my order ORD-1042?", thread="f")
    r = await turn(agent, "how long do lab test refunds take?", thread="f")
    assert "tool:get_order_status" not in r["citations"]  # no context bleed from turn 1


async def test_abstain_without_llm_when_nothing_retrieved(agent):
    r = await turn(agent, "What is the capital of France?")
    assert r["abstained"] and r["grounded"]


async def test_policy_answer_cached_second_time(agent):
    q = "how long does a refund take for a cancelled medicine order?"
    a = await turn(agent, q, thread="c1")
    b = await turn(agent, q, thread="c2")
    assert not a["cache_hit"] and b["cache_hit"] and a["answer"] == b["answer"]


async def test_threads_isolated_per_user(agent):
    await turn(agent, "Where is my order ORD-1042?", user="U1001", thread="same")
    th = await agent.thread("U1002", "same")
    assert th["messages"] == []
