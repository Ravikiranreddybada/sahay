"""FastAPI entrypoint. `uvicorn sahay.main:app --port 8000`"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import uuid
from contextlib import AsyncExitStack, asynccontextmanager
from pathlib import Path
from typing import Any, AsyncIterator

from fastapi import BackgroundTasks, Depends, FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, PlainTextResponse, Response, StreamingResponse
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest
from pydantic import BaseModel, Field

from . import auth
from .auth import Principal
from .channels import whatsapp as wa
from .config import Settings, get_settings
from .factory import build_agent, build_channels
from .mcp_servers import servers
from .obs.otel import to_otlp
from .reliability.ratelimit import TokenBucket
from .safety.injection import rules_catalog

log = logging.getLogger("sahay.api")
DEMO_PERSONAS = {"U1001", "U1002", "U1003"}


class ChatIn(BaseModel):
    thread_id: str | None = Field(None, max_length=64, pattern=r"^[A-Za-z0-9_.:-]+$")
    message: str = Field(min_length=1, max_length=2000)


class ConfirmIn(BaseModel):
    thread_id: str = Field(max_length=64, pattern=r"^[A-Za-z0-9_.:-]+$")
    approved: bool


class FeedbackIn(BaseModel):
    trace_id: str = Field(max_length=64)
    rating: int = Field(ge=-1, le=1)
    comment: str | None = Field(None, max_length=1000)


class LoginIn(BaseModel):
    persona: str = Field(description="U1001 | U1002 | U1003 | ops")


class ResolveIn(BaseModel):
    note: str | None = Field(None, max_length=500)


class SimulateIn(BaseModel):
    phone: str = Field(pattern=r"^\d{10,15}$")
    text: str = Field(min_length=1, max_length=2000)


def check_settings(s: Settings) -> None:
    if s.env != "dev":
        if s.auth_secret == Settings.model_fields["auth_secret"].default or len(s.auth_secret) < 32:
            raise RuntimeError("SAHAY_AUTH_SECRET must be set to a strong secret outside dev")
        if s.dev_login:
            raise RuntimeError("SAHAY_DEV_LOGIN must be false outside dev")


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    s = get_settings()
    check_settings(s)
    app.state.settings = s
    async with AsyncExitStack() as stack:
        # Durable conversation state: Postgres in prod (any replica can resume any thread,
        # including a paused confirmation), SQLite on a laptop.
        if s.database_url:
            from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver

            cp = await stack.enter_async_context(AsyncPostgresSaver.from_conn_string(s.database_url))
            await _migrate_once(s.database_url, cp)
        else:
            from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver

            cp = await stack.enter_async_context(AsyncSqliteSaver.from_conn_string(str(s.checkpoint_db)))
        redis = None
        if s.redis_url:
            import redis.asyncio as aioredis

            redis = aioredis.from_url(s.redis_url, socket_timeout=0.25, socket_connect_timeout=0.5)
            stack.push_async_callback(redis.aclose)
        agent = await stack.enter_async_context(build_agent(s, checkpointer=cp, redis=redis))
        app.state.agent = agent
        app.state.channels = build_channels(agent, s, s.data_dir)
        if redis is not None:
            from .reliability.redis_backends import RedisTokenBucket

            app.state.limiter = RedisTokenBucket(redis, s.rate_limit_per_min)
        else:
            app.state.limiter = TokenBucket(s.rate_limit_per_min)
        sweeper = asyncio.create_task(_reminder_loop(app, s.reminder_interval_s)) if s.reminder_interval_s > 0 else None
        try:
            yield
        finally:
            if sweeper:
                sweeper.cancel()


async def _migrate_once(url: str, cp: Any) -> None:
    """Every worker of every replica starts at once. Two concurrent `setup()` calls race on
    CREATE TABLE and one worker dies with UniqueViolation (found on the first real
    `docker compose up`). A Postgres advisory lock lets exactly one run the migrations."""
    import psycopg

    async with await psycopg.AsyncConnection.connect(url, autocommit=True) as conn:
        await conn.execute("SELECT pg_advisory_lock(727274)")
        try:
            await cp.setup()
        finally:
            await conn.execute("SELECT pg_advisory_unlock(727274)")


async def _reminder_loop(app: FastAPI, every_s: int) -> None:
    while True:
        await asyncio.sleep(every_s)
        try:
            await app.state.channels.reminders.sweep()
        except Exception:  # noqa: BLE001 - a failed sweep retries next interval; the log key makes it safe
            log.exception("reminder sweep failed")


app = FastAPI(title="Sahay API", version="0.3.0", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=["http://localhost:3000", "http://127.0.0.1:3000", *filter(None, os.environ.get("SAHAY_CORS_ORIGINS", "").split(","))], allow_methods=["*"], allow_headers=["*"])


def _agent(req: Request):
    return req.app.state.agent


async def _limit(req: Request, key: str) -> None:
    ok, retry = await req.app.state.limiter.acquire(key)
    if not ok:
        raise HTTPException(429, "Too many messages. Please wait a moment.", headers={"Retry-After": str(int(retry) + 1)})


def _sse(ev: dict[str, Any]) -> bytes:
    return f"event: {ev['type']}\ndata: {json.dumps(ev, default=str)}\n\n".encode()


# ------------------------------------------------------------------------------- auth
@app.post("/v1/auth/dev-login")
async def dev_login(body: LoginIn, req: Request) -> dict[str, Any]:
    s: Settings = req.app.state.settings
    if not s.dev_login:
        raise HTTPException(404, "Not found")
    await _limit(req, f"login:{req.client.host if req.client else '?'}")
    if body.persona == "ops":
        return {"token": auth.issue(s.auth_secret, "ops-demo", "ops", s.token_ttl_s), "role": "ops", "sub": "ops-demo"}
    if body.persona not in DEMO_PERSONAS:
        raise HTTPException(400, "Unknown demo persona")
    return {"token": auth.issue(s.auth_secret, body.persona, "member", s.token_ttl_s), "role": "member", "sub": body.persona}


@app.get("/v1/me")
async def me(p: Principal = Depends(auth.member)) -> dict[str, Any]:
    rows = servers.store().q("SELECT name, city, plan FROM users WHERE user_id=?", (p.sub,))
    return {"user_id": p.sub, **(rows[0] if rows else {})}


# ------------------------------------------------------------------------------- chat (member)
@app.post("/v1/chat")
async def chat(body: ChatIn, req: Request, p: Principal = Depends(auth.member)) -> dict[str, Any]:
    await _limit(req, p.sub)
    return await _agent(req).run_turn(user_id=p.sub, thread_id=body.thread_id or f"t-{uuid.uuid4().hex[:10]}", message=body.message)


@app.post("/v1/chat/stream")
async def chat_stream(body: ChatIn, req: Request, p: Principal = Depends(auth.member)) -> StreamingResponse:
    await _limit(req, p.sub)
    thread_id = body.thread_id or f"t-{uuid.uuid4().hex[:10]}"

    async def gen() -> AsyncIterator[bytes]:
        async for ev in _agent(req).stream_turn(user_id=p.sub, thread_id=thread_id, message=body.message):
            yield _sse(ev)

    return StreamingResponse(gen(), media_type="text/event-stream", headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


@app.post("/v1/chat/confirm")
async def chat_confirm(body: ConfirmIn, req: Request, p: Principal = Depends(auth.member)) -> dict[str, Any]:
    agent = _agent(req)
    if not await agent._pending({"configurable": {"thread_id": f"{p.sub}:{body.thread_id}"}}):
        raise HTTPException(409, "Nothing is waiting for confirmation on this thread.")
    return await agent.run_turn(user_id=p.sub, thread_id=body.thread_id, resume={"approved": body.approved})


@app.post("/v1/chat/confirm/stream")
async def chat_confirm_stream(body: ConfirmIn, req: Request, p: Principal = Depends(auth.member)) -> StreamingResponse:
    agent = _agent(req)
    if not await agent._pending({"configurable": {"thread_id": f"{p.sub}:{body.thread_id}"}}):
        raise HTTPException(409, "Nothing is waiting for confirmation on this thread.")

    async def gen() -> AsyncIterator[bytes]:
        async for ev in agent.stream_turn(user_id=p.sub, thread_id=body.thread_id, resume={"approved": body.approved}):
            yield _sse(ev)

    return StreamingResponse(gen(), media_type="text/event-stream", headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


@app.get("/v1/threads/{thread_id}")
async def get_thread(thread_id: str, req: Request, p: Principal = Depends(auth.member)) -> dict[str, Any]:
    return await _agent(req).thread(p.sub, thread_id)


@app.post("/v1/feedback")
async def feedback(body: FeedbackIn, req: Request, p: Principal = Depends(auth.member)) -> dict[str, str]:
    traces = _agent(req).deps.traces
    if traces.owner(body.trace_id) != p.sub:
        raise HTTPException(404, "trace not found")
    traces.add_feedback(body.trace_id, body.rating, body.comment)
    return {"status": "ok"}


# ------------------------------------------------------------------------------- health records (member)
HEALTH_MEMBER = Query(None, max_length=40, pattern=r"^[A-Za-z][A-Za-z .'-]*$")


@app.get("/v1/health/members")
async def health_members(req: Request, p: Principal = Depends(auth.member)) -> dict[str, Any]:
    tr = await _agent(req).deps.hub.call("list_care_members", {}, user_id=p.sub, thread_id="ui-health")
    return tr.result or {"members": [], "error": tr.error}


@app.get("/v1/health/overview")
async def health_overview(req: Request, member: str | None = HEALTH_MEMBER, p: Principal = Depends(auth.member)) -> dict[str, Any]:
    """Same MCP tools, same consent checks as the chat: the UI gets no back door."""
    hub = _agent(req).deps.hub
    args = {"member": member} if member else {}
    out: dict[str, Any] = {}
    for key, tool in [("medications", "get_medication_list"), ("labs", "get_lab_trends"), ("brief", "get_visit_brief")]:
        tr = await hub.call(tool, args, user_id=p.sub, thread_id="ui-health")
        out[key] = tr.result if tr.result is not None else {"error": tr.error}
    return out


@app.get("/v1/me/data")
async def my_data(req: Request, p: Principal = Depends(auth.member)) -> dict[str, Any]:
    """Right of access (DPDP Act 2023 s.11): everything Sahay holds about this member, one JSON."""
    st, agent = servers.store(), _agent(req)
    q = lambda sql: st.q(sql, (p.sub,))  # noqa: E731
    return {
        "user_id": p.sub,
        "profile": (q("SELECT name, city, plan, language FROM users WHERE user_id=?") or [None])[0],
        "family_members": q("SELECT member_id, name, relation FROM members WHERE account_user_id=? AND relation!='self'"),
        "consents_held": q("SELECT consent_id, member_id, scopes, granted_at, expires_at, revoked FROM consents WHERE grantee_user_id=?"),
        "medications": q("SELECT name, instructions, prescriber, started_on, status FROM medications WHERE member_id=?"),
        "lab_results": q("SELECT analyte, value, unit, lab, collected_on FROM lab_results WHERE member_id=?"),
        "orders": q("SELECT order_id, items, status, amount, placed_at FROM orders WHERE user_id=?"),
        "claims": q("SELECT claim_id, hospital, status, claimed, approved FROM claims WHERE user_id=?"),
        "lab_bookings": q("SELECT booking_id, test, status FROM lab_bookings WHERE user_id=?"),
        "reminders": q("SELECT reminder_id, child_id, channel, active FROM reminders WHERE user_id=?"),
        "conversation_threads": agent.deps.traces.threads_of(p.sub),
        "note": "Records you hold for family members are listed as consents; their own data belongs to them.",
    }


@app.delete("/v1/me/history")
async def erase_my_history(req: Request, p: Principal = Depends(auth.member)) -> dict[str, Any]:
    """Right to erasure (DPDP Act 2023 s.12) for conversation data: checkpoints, traces, feedback.
    Orders, claims and medical records stay (legal retention), and emergency tickets stay with ops."""
    agent = _agent(req)
    threads = agent.deps.traces.threads_of(p.sub)
    erased = 0
    for t in threads:
        try:
            await agent.graph.checkpointer.adelete_thread(f"{p.sub}:{t}")
            erased += 1
        except Exception:  # noqa: BLE001 - one bad thread must not block the rest
            log.exception("checkpoint delete failed")
    return {"threads_erased": erased, "traces_erased": agent.deps.traces.delete_user(p.sub)}


# ------------------------------------------------------------------------------- ops
@app.get("/v1/traces", dependencies=[Depends(auth.ops)])
async def list_traces(req: Request, limit: int = 50) -> list[dict[str, Any]]:
    return _agent(req).deps.traces.list(min(limit, 200))


@app.get("/v1/traces/{trace_id}")
async def get_trace(trace_id: str, req: Request) -> dict[str, Any]:
    # ops see every trace; a member may open the trace of their own turn (the chat side panel)
    s: Settings = req.app.state.settings
    tok = auth._bearer(req)
    principal = auth.verify(s.auth_secret, tok) if tok else auth.ops(req)
    t = _agent(req).deps.traces.get(trace_id)
    if not t or (principal.role == "member" and t["user_id"] != principal.sub):
        raise HTTPException(404, "trace not found")
    return t


@app.get("/v1/traces/{trace_id}/otlp")
async def get_trace_otlp(trace_id: str, req: Request) -> dict[str, Any]:
    """The trace as OTLP/JSON (GenAI semantic conventions, privacy allow-list): POST it to any collector."""
    t = await get_trace(trace_id, req)
    mode = _agent(req).deps.router.mode
    return to_otlp(t, service_version=app.version, provider="sahay.offline" if mode == "offline" else "anthropic")


@app.get("/v1/safety/rules", dependencies=[Depends(auth.ops)])
async def safety_rules() -> dict[str, Any]:
    return rules_catalog()


@app.get("/v1/handoffs", dependencies=[Depends(auth.ops)])
async def handoffs(req: Request) -> list[dict[str, Any]]:
    return _agent(req).deps.handoffs.list()


@app.post("/v1/handoffs/{ticket_id}/resolve", dependencies=[Depends(auth.ops)])
async def resolve_handoff(ticket_id: str, body: ResolveIn, req: Request) -> dict[str, Any]:
    if not _agent(req).deps.handoffs.resolve(ticket_id, body.note):
        raise HTTPException(404, "No open ticket with that id.")
    return {"ticket_id": ticket_id, "status": "resolved"}


@app.get("/v1/kb", dependencies=[Depends(auth.ops)])
async def kb(req: Request) -> dict[str, Any]:
    deps = _agent(req).deps
    docs: dict[str, dict[str, Any]] = {}
    for c in deps.index.chunks:
        d = docs.setdefault(c.doc_id, {"doc_id": c.doc_id, "title": c.title, "version": c.doc_version, "review_by": c.review_by,
                                       "effective_date": c.effective_date, "stale": c.is_stale(), "chunks": 0, "sections": []})
        d["chunks"] += 1
        d["sections"].append(c.heading_path)
    files = sorted(p.name for p in deps.settings.kb_dir.glob("*.md"))
    return {"kb_version": deps.kb_version, "embedder": deps.index.embedder.id, "files": files, "indexed_docs": list(docs.values()),
            "scheduled": deps.index.scheduled}


@app.post("/v1/kb/reindex", dependencies=[Depends(auth.ops)])
async def kb_reindex(req: Request) -> dict[str, Any]:
    deps = _agent(req).deps
    out = await asyncio.to_thread(deps.index.load_dir, deps.settings.kb_dir)
    return {**out, "kb_version": deps.kb_version}


@app.get("/v1/evals/latest", dependencies=[Depends(auth.ops)])
async def evals_latest(set: str = Query("golden", pattern="^(golden|heldout)$")) -> dict[str, Any]:  # noqa: A002
    for p in sorted((Path(__file__).resolve().parent.parent / "evals" / "reports").glob("*.json"), reverse=True):
        rep = json.loads(p.read_text())
        if rep.get("set", "golden") == set and rep["metrics"]["cases"] > 10:  # skip --only debug runs
            return rep
    raise HTTPException(404, f"no {set} eval report yet; run `python -m evals.run_evals --set {set}`")


# ------------------------------------------------------------------------------- channels
@app.get("/v1/channels/whatsapp/webhook")
async def wa_verify(req: Request) -> Response:
    """Meta's one-time subscription handshake."""
    q = req.query_params
    if q.get("hub.mode") == "subscribe" and q.get("hub.verify_token") == req.app.state.settings.whatsapp_verify_token:
        return PlainTextResponse(q.get("hub.challenge", ""))
    raise HTTPException(403, "verification failed")


@app.post("/v1/channels/whatsapp/webhook")
async def wa_webhook(req: Request, background: BackgroundTasks) -> dict[str, str]:
    s: Settings = req.app.state.settings
    raw = await req.body()
    if s.whatsapp_app_secret:
        if not wa.verify_signature(s.whatsapp_app_secret, raw, req.headers.get("x-hub-signature-256")):
            raise HTTPException(401, "bad signature")
    elif s.env != "dev":
        raise HTTPException(503, "SAHAY_WHATSAPP_APP_SECRET is not configured")
    try:
        msgs = wa.parse(json.loads(raw))
    except (json.JSONDecodeError, AttributeError) as e:
        raise HTTPException(400, "malformed payload") from e
    channel = req.app.state.channels.whatsapp

    async def work() -> None:
        for m in msgs:
            await channel.handle(m)

    # Meta wants a 200 within seconds and retries otherwise: acknowledge now, answer after.
    background.add_task(work)
    return {"status": "accepted", "messages": str(len(msgs))}


@app.post("/v1/channels/whatsapp/simulate", dependencies=[Depends(auth.ops)])
async def wa_simulate(body: SimulateIn, req: Request) -> dict[str, Any]:
    """Run one inbound WhatsApp message through the real channel code, synchronously."""
    ch = req.app.state.channels
    ids = await ch.whatsapp.handle(wa.Inbound(msg_id=f"sim-{uuid.uuid4().hex[:10]}", phone=body.phone, text=body.text))
    outbox = {o["id"]: o for o in ch.outbox.list(100)}
    return {"replies": [outbox[i] for i in ids if i in outbox]}


@app.get("/v1/channels/outbox", dependencies=[Depends(auth.ops)])
async def outbox(req: Request, limit: int = 50) -> list[dict[str, Any]]:
    return req.app.state.channels.outbox.list(min(limit, 200))


@app.get("/v1/reminders/due", dependencies=[Depends(auth.ops)])
async def reminders_due(req: Request) -> list[dict[str, Any]]:
    return [{k: v for k, v in r.items() if k != "phone"} for r in req.app.state.channels.reminders.due()]


@app.post("/v1/reminders/run", dependencies=[Depends(auth.ops)])
async def reminders_run(req: Request) -> dict[str, Any]:
    return await req.app.state.channels.reminders.sweep()


# ------------------------------------------------------------------------------- platform
@app.get("/v1/meta")
async def meta(req: Request) -> dict[str, Any]:
    d = _agent(req).deps
    return {"mode": d.router.mode, "models": {"fast": d.settings.model_fast, "smart": d.settings.model_smart},
            "prompt_version": d.settings.prompt_version, "kb_version": d.kb_version, "tools": sorted(d.hub.tools),
            "breakers": {k: v.state for k, v in d.router.breakers.items()},
            "storage": {"checkpoints": "postgres" if d.settings.database_url else "sqlite",
                        "cache": "redis" if d.settings.redis_url else "memory"},
            "dev_login": d.settings.dev_login}


@app.get("/healthz")
async def healthz() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/readyz")
async def readyz(req: Request) -> JSONResponse:
    d = _agent(req).deps
    ok = bool(d.index.chunks) and bool(d.hub.tools)
    return JSONResponse({"ready": ok, "chunks": len(d.index.chunks), "tools": len(d.hub.tools)}, status_code=200 if ok else 503)


@app.get("/metrics")
async def prom() -> Response:
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)
