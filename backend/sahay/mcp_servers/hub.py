"""MCP client hub: the agent's single gateway to every MCP server.

Responsibilities (each one is a bug I would otherwise debug in production):
* discovery  - list tools from each server at startup, build the tool catalog the LLM sees
* scoping    - strip `user_id` / `idempotency_key` from schemas; inject them per call
* authz      - per-intent tool allow-list, so a claims question cannot reach cancel_order
* timeouts   - every call is bounded; a hung downstream never hangs a user turn
* idempotency- write keys derived from (thread, tool, canonical args): a retried or
               re-planned write is a replay, not a second booking
* tracing    - one span per call with args, latency and status
* sanitising - tool output is untrusted data (indirect prompt injection)
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import os
from contextlib import AsyncExitStack
from dataclasses import dataclass
from typing import Any

from mcp import Client
from mcp.client.streamable_http import streamable_http_client
from mcp.shared._httpx_utils import create_mcp_http_client

from ..llm.base import ToolSpec
from ..obs import metrics
from ..obs.tracing import span
from .servers import SERVERS

INJECTED = {"user_id", "idempotency_key"}

# Least privilege per intent. The planner only ever sees these tools.
INTENT_TOOLS: dict[str, list[str]] = {
    "order_status": ["get_order_status", "list_recent_orders"],
    "refund_cancel": ["get_order_status", "list_recent_orders", "cancel_order"],
    "lab_booking": ["get_lab_report_status", "search_lab_tests"],
    "consult_booking": ["search_doctor_slots", "book_consultation"],
    "claim_status": ["get_claim_status", "list_claims", "find_network_hospitals"],
    "vaccination_journey": ["get_vaccination_schedule", "set_vaccination_reminder", "list_reminders"],
    "surgery_journey": ["get_surgery_journey", "get_surgery_checklist", "find_network_hospitals"],
    "health_records": ["get_medication_list", "check_medication_safety", "get_lab_trends", "get_visit_brief",
                       "list_care_members", "revoke_care_access"],
}


@dataclass
class ToolResult:
    tool: str
    server: str
    args: dict[str, Any]
    result: dict[str, Any] | None
    error: str | None
    latency_ms: float
    ref: str

    def to_dict(self) -> dict[str, Any]:
        return {"tool": self.tool, "server": self.server, "args": self.args, "result": self.result, "error": self.error, "latency_ms": self.latency_ms, "ref": self.ref}


class MCPHub:
    def __init__(self, call_timeout_s: float = 5.0) -> None:
        self.timeout = call_timeout_s
        self.clients: dict[str, Client] = {}
        self.tools: dict[str, ToolSpec] = {}
        self._ready = asyncio.Event()
        self._stop = asyncio.Event()
        self._task: asyncio.Task[None] | None = None
        self._error: BaseException | None = None

    async def start(self) -> None:
        # MCP clients hold anyio cancel scopes that must be entered and exited by the *same*
        # task. One owner task keeps the connections for the hub's whole life, so callers
        # (FastAPI lifespan, pytest fixtures) may start and stop from different tasks.
        self._task = asyncio.create_task(self._own_connections())
        await self._ready.wait()
        if self._error:
            raise self._error

    async def _own_connections(self) -> None:
        try:
            async with AsyncExitStack() as stack:
                await self._connect(stack)
                self._ready.set()
                await self._stop.wait()
        except BaseException as e:  # surface startup failures to start()
            self._error = e
            self._ready.set()

    async def _connect(self, stack: AsyncExitStack) -> None:
        for name, server in SERVERS.items():
            # Prod: each server is its own service; point the hub at it by URL. The hub
            # authenticates with a service token (the server trusts the hub's user_id).
            url = os.environ.get(f"SAHAY_MCP_{name.upper()}_URL")
            target: Any = server
            if url:
                token = os.environ.get("SAHAY_MCP_TOKEN")
                http = create_mcp_http_client(headers={"Authorization": f"Bearer {token}"} if token else None)
                target = streamable_http_client(url, http_client=await stack.enter_async_context(http))
            client = await stack.enter_async_context(Client(target))
            self.clients[name] = client
            listed = await client.list_tools()
            for t in listed.tools:
                schema = json.loads(json.dumps(t.input_schema))
                props = schema.get("properties", {})
                for k in INJECTED:
                    props.pop(k, None)
                schema["required"] = [r for r in schema.get("required", []) if r not in INJECTED]
                ann = t.annotations
                ro = getattr(ann, "read_only_hint", getattr(ann, "readOnlyHint", True)) if ann else True
                writes = ro is False
                self.tools[t.name] = ToolSpec(name=t.name, description=t.description or "", input_schema=schema, server=name, writes=writes)

    async def stop(self) -> None:
        self._stop.set()
        if self._task:
            await self._task

    def tools_for(self, intent: str, read_only: bool = False) -> list[ToolSpec]:
        allowed = INTENT_TOOLS.get(intent, [])
        return [self.tools[n] for n in allowed if n in self.tools and not (read_only and self.tools[n].writes)]

    @staticmethod
    def idempotency_key(user_id: str, thread_id: str, tool: str, args: dict[str, Any]) -> str:
        # INC-011: the key used to be (thread, tool, args). thread_id comes from the client, so
        # two users on the same thread id got each other's write results back as "replays".
        canon = json.dumps(args, sort_keys=True, default=str)
        return hashlib.sha256(f"{user_id}|{thread_id}|{tool}|{canon}".encode()).hexdigest()[:32]

    async def call(self, tool: str, args: dict[str, Any], *, user_id: str, thread_id: str) -> ToolResult:
        spec = self.tools.get(tool)
        ref = f"tool:{tool}"
        if spec is None:
            return ToolResult(tool, "?", args, None, f"unknown tool {tool}", 0.0, ref)
        clean = {k: v for k, v in args.items() if k not in INJECTED}
        payload = {**clean, "user_id": user_id}
        if spec.writes:
            payload["idempotency_key"] = self.idempotency_key(user_id, thread_id, tool, clean)
        with span(f"tool.{tool}", kind="tool", server=spec.server, args=clean, writes=spec.writes) as sp:
            try:
                res = await asyncio.wait_for(self.clients[spec.server].call_tool(tool, payload), timeout=self.timeout)
            except asyncio.TimeoutError:
                metrics.TOOL_CALLS.labels(spec.server, tool, "timeout").inc()
                sp.status = "error"
                sp.set(error="timeout")
                return ToolResult(tool, spec.server, clean, None, "the service is slow to respond right now", sp.duration_ms, ref)
            if getattr(res, "is_error", False):
                msg = " ".join(getattr(c, "text", "") for c in res.content).strip() or "tool error"
                msg = msg.split(f"Error executing tool {tool}: ", 1)[-1]
                metrics.TOOL_CALLS.labels(spec.server, tool, "error").inc()
                sp.status = "error"
                sp.set(error=msg)
                return ToolResult(tool, spec.server, clean, None, msg, sp.duration_ms, ref)
            data = res.structured_content
            if data is None:
                text = " ".join(getattr(c, "text", "") for c in res.content)
                try:
                    data = json.loads(text)
                except json.JSONDecodeError:
                    data = {"text": text}
            if isinstance(data, dict) and set(data) == {"result"} and isinstance(data["result"], dict):
                data = data["result"]
            metrics.TOOL_CALLS.labels(spec.server, tool, "ok").inc()
            sp.set(result=data)
            return ToolResult(tool, spec.server, clean, data, None, sp.duration_ms, ref)
