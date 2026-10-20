"""Production storage adapters: Redis limiter + cache, Postgres checkpointer, and a remote MCP
server behind service auth. Postgres runs when SAHAY_TEST_PG_URL is set (CI service / local)."""

import asyncio
import os
import socket
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import pytest

from sahay.factory import build_agent
from sahay.rag.embed import HashingEmbedder

fakeredis = pytest.importorskip("fakeredis")


@pytest.fixture
def redis():
    return fakeredis.FakeAsyncRedis()


async def test_redis_limiter_is_shared_across_replicas(redis):
    from sahay.reliability.redis_backends import RedisTokenBucket

    pod_a, pod_b = RedisTokenBucket(redis, 60, burst=3), RedisTokenBucket(redis, 60, burst=3)
    got = [(await (pod_a if i % 2 else pod_b).acquire("U1001"))[0] for i in range(4)]
    assert got == [True, True, True, False]  # one budget, not one per pod


async def test_redis_limiter_fails_open(redis):
    from sahay.reliability.redis_backends import RedisTokenBucket

    lim = RedisTokenBucket(redis, 60, burst=2)

    async def down(*a, **k):
        raise ConnectionError("redis down")

    lim._script = down
    assert (await lim.acquire("U1"))[0]


async def test_redis_semantic_cache(redis):
    from sahay.reliability.redis_backends import RedisSemanticCache

    a, b = RedisSemanticCache(redis, HashingEmbedder(), 0.9), RedisSemanticCache(redis, HashingEmbedder(), 0.9)
    await a.put("how long does a lab test refund take", "refund_cancel", "v3", "kb1", {"draft": {"answer": "x"}})
    assert (await b.get("how long does a lab test refund take", "refund_cancel", "v3", "kb1"))["draft"]["answer"] == "x"
    assert await b.get("how long does a lab test refund take", "refund_cancel", "v3", "kb2") is None
    assert await b.get("where is my order", "order_status", "v3", "kb1") is None


async def test_agent_on_redis_cache(redis):
    async with build_agent(data_dir=Path(tempfile.mkdtemp()), redis=redis) as ag:
        q = "how long does a refund take for a cancelled medicine order?"
        a = await ag.run_turn(user_id="U1001", thread_id="r1", message=q)
        b = await ag.run_turn(user_id="U1002", thread_id="r2", message=q)
        assert not a["cache_hit"] and b["cache_hit"]


async def test_redis_turn_lock_serialises_across_agents(redis):
    async with build_agent(data_dir=Path(tempfile.mkdtemp()), redis=redis) as ag:
        rs = await asyncio.gather(*[ag.run_turn(user_id="U1001", thread_id="rl", message="Where is my order ORD-1042?") for _ in range(4)])
        assert all(r["status"] == "answered" for r in rs)
        assert len((await ag.thread("U1001", "rl"))["messages"]) == 8


PG = os.environ.get("SAHAY_TEST_PG_URL")


@pytest.mark.skipif(not PG, reason="set SAHAY_TEST_PG_URL to run against Postgres")
async def test_postgres_checkpointer_resumes_confirmation_across_restarts():
    from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver

    d = Path(tempfile.mkdtemp())
    thread = f"pg-{time.time_ns()}"
    async with AsyncPostgresSaver.from_conn_string(PG) as cp:
        await cp.setup()
        async with build_agent(data_dir=d, checkpointer=cp) as ag:
            r = await ag.run_turn(user_id="U1001", thread_id=thread, message="Cancel order ORD-1043")
            assert r["status"] == "needs_confirmation"
    # "another replica": fresh process state, same database
    async with AsyncPostgresSaver.from_conn_string(PG) as cp:
        async with build_agent(data_dir=d, checkpointer=cp) as ag:
            r = await ag.run_turn(user_id="U1001", thread_id=thread, resume={"approved": True})
            assert "cancelled" in r["answer"]
            th = await ag.thread("U1001", thread)
            assert len(th["messages"]) == 2


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


async def test_remote_mcp_server_requires_service_token(monkeypatch):
    port, data = _free_port(), tempfile.mkdtemp()
    env = {**os.environ, "SAHAY_MCP_TOKEN": "svc-secret", "SAHAY_DATA_DIR": data}
    proc = subprocess.Popen([sys.executable, "-m", "sahay.mcp_servers.servers", "orders", "--http", str(port)],
                            env=env, cwd=Path(__file__).parent.parent, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        import httpx

        for _ in range(100):
            try:
                httpx.get(f"http://127.0.0.1:{port}/mcp", timeout=0.2)
                break
            except httpx.HTTPError:
                await asyncio.sleep(0.1)
        assert httpx.post(f"http://127.0.0.1:{port}/mcp", json={}).status_code == 401  # no token, no data

        monkeypatch.setenv("SAHAY_MCP_ORDERS_URL", f"http://127.0.0.1:{port}/mcp")
        monkeypatch.setenv("SAHAY_MCP_TOKEN", "svc-secret")
        async with build_agent(data_dir=Path(data)) as ag:
            assert ag.deps.hub.tools["get_order_status"].server == "orders"
            r = await ag.run_turn(user_id="U1001", thread_id="remote", message="Where is my order ORD-1042?")
            assert "out for delivery" in r["answer"]
    finally:
        proc.terminate()
        proc.wait(5)
