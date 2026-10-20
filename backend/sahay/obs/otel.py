"""Stored traces -> OTLP/JSON with OpenTelemetry GenAI semantic-convention names.

Any OTel backend (Grafana Tempo / agent observability, Langfuse, Phoenix, Jaeger) can read
Sahay's turns without a vendor SDK in the hot path: `GET /v1/traces/{id}/otlp` returns the
payload, and with SAHAY_OTLP_ENDPOINT set every saved trace is POSTed to `<endpoint>/v1/traces`
from a background thread (a slow collector never slows a turn).

Privacy by default: this is health data. Only an allow-list of attributes leaves the box:
names, routes, models, token counts, tool *names*, verifier criteria, threat-rule ids.
Never tool arguments, tool results, retrieved text, prompts or answers.
"""

from __future__ import annotations

import json
import logging
import queue
import threading
from typing import Any

log = logging.getLogger("sahay.otel")
SAFE_ATTRS = {"route", "intent", "tier", "attempt", "stop_reason", "fallback", "degraded", "ok", "score", "problems", "writes",
              "status", "interrupted", "approved", "hits", "top_k", "budget", "tokens", "included", "dropped", "calls", "cached"}
KIND_CLIENT, KIND_INTERNAL, KIND_SERVER = 3, 1, 2


def _val(v: Any) -> dict[str, Any]:
    if isinstance(v, bool):
        return {"boolValue": v}
    if isinstance(v, int):
        return {"intValue": str(v)}
    if isinstance(v, float):
        return {"doubleValue": v}
    if isinstance(v, (list, tuple)):
        return {"arrayValue": {"values": [_val(x) for x in v]}}
    if isinstance(v, dict):
        return {"stringValue": json.dumps(v, default=str)[:500]}
    return {"stringValue": str(v)[:500]}


def _attrs(d: dict[str, Any]) -> list[dict[str, Any]]:
    return [{"key": k, "value": _val(v)} for k, v in d.items() if v is not None]


def _span(sp: dict[str, Any], trace: dict[str, Any], provider: str) -> dict[str, Any]:
    a = sp["attributes"]
    attrs: dict[str, Any] = {"sahay.span.kind": sp["kind"]}
    attrs.update({f"sahay.{k}": v for k, v in a.items() if k in SAFE_ATTRS and not isinstance(v, (dict,))})
    name, kind = sp["name"], KIND_INTERNAL
    if sp["kind"] == "llm":
        model = a.get("model", "unknown")
        name, kind = f"chat {model}", KIND_CLIENT
        attrs.update({"gen_ai.operation.name": "chat", "gen_ai.provider.name": "sahay.offline" if model == "offline" else provider,
                      "gen_ai.request.model": model, "gen_ai.usage.input_tokens": a.get("tokens_in"),
                      "gen_ai.usage.output_tokens": a.get("tokens_out"),
                      "gen_ai.response.finish_reasons": [a["stop_reason"]] if a.get("stop_reason") else None,
                      "sahay.task": sp["name"].removeprefix("llm."), "sahay.cost_usd": a.get("cost_usd")})
    elif sp["kind"] == "tool":
        tool = sp["name"].removeprefix("tool.")
        name, kind = f"execute_tool {tool}", KIND_CLIENT
        attrs.update({"gen_ai.operation.name": "execute_tool", "gen_ai.tool.name": tool, "gen_ai.tool.type": "function",
                      "mcp.method.name": "tools/call", "sahay.mcp.server": a.get("server")})
    elif sp["kind"] == "retrieval":
        attrs.update({"sahay.retrieval.hit_ids": [h.get("id") if isinstance(h, dict) else str(h) for h in (a.get("hits") or [])][:10]})
        attrs.pop("sahay.hits", None)
    elif sp["kind"] == "guard":
        if a.get("signals"):
            attrs["sahay.threat_rules"] = list(a["signals"])
        if a.get("sources"):
            attrs["sahay.indirect_injection_rules"] = sorted({r for v in a["sources"].values() for r in v})
        if a.get("scorecard"):
            attrs.update({f"sahay.verify.{k}": v for k, v in a["scorecard"].items()})
        if a.get("pii"):
            attrs["sahay.pii_types"] = sorted(a["pii"])
        if isinstance(a.get("triage"), dict):
            attrs["sahay.triage.emergency"] = bool(a["triage"].get("emergency"))
            attrs["sahay.triage.category"] = a["triage"].get("category")
    start = int(trace["started_at"] * 1e9 + sp["offset_ms"] * 1e6)
    return {
        "traceId": trace["trace_id"], "spanId": sp["span_id"], "parentSpanId": sp["parent_id"] or _root_id(trace),
        "name": name, "kind": kind, "startTimeUnixNano": str(start), "endTimeUnixNano": str(start + int(sp["duration_ms"] * 1e6)),
        "attributes": _attrs(attrs), "status": {"code": 2 if sp["status"] == "error" else 1},
    }


def _root_id(trace: dict[str, Any]) -> str:
    return trace["trace_id"][:16]


def to_otlp(trace: dict[str, Any], *, service_version: str = "0.3.0", provider: str = "anthropic") -> dict[str, Any]:
    start = int(trace["started_at"] * 1e9)
    meta = trace.get("meta") or {}
    root = {
        "traceId": trace["trace_id"], "spanId": _root_id(trace), "name": "invoke_agent sahay", "kind": KIND_SERVER,
        "startTimeUnixNano": str(start), "endTimeUnixNano": str(start + int(trace["totals"]["latency_ms"] * 1e6)),
        "attributes": _attrs({"gen_ai.operation.name": "invoke_agent", "gen_ai.agent.name": "sahay",
                              "gen_ai.conversation.id": trace["thread_id"], "gen_ai.usage.input_tokens": trace["totals"]["tokens_in"],
                              "gen_ai.usage.output_tokens": trace["totals"]["tokens_out"], "sahay.intent": meta.get("intent"),
                              "sahay.grounded": meta.get("grounded"), "sahay.cache_hit": meta.get("cache_hit"),
                              "sahay.cost_usd": trace["totals"]["cost_usd"]}),
        "status": {"code": 2 if meta.get("error") else 1},
    }
    spans = [root] + [_span(s, trace, provider) for s in trace["spans"]]
    return {"resourceSpans": [{
        "resource": {"attributes": _attrs({"service.name": "sahay-api", "service.version": service_version})},
        "scopeSpans": [{"scope": {"name": "sahay.obs.tracing", "version": service_version}, "spans": spans}],
    }]}


class OTLPExporter:
    """Fire-and-forget: a bounded queue drained by one daemon thread. Full queue -> drop + log."""

    def __init__(self, endpoint: str, headers: dict[str, str] | None = None, provider: str = "anthropic") -> None:
        self.url = endpoint.rstrip("/") + "/v1/traces"
        self.headers = {"Content-Type": "application/json", **(headers or {})}
        self.provider = provider
        self.q: queue.Queue[dict[str, Any]] = queue.Queue(maxsize=1000)
        self.sent = self.failed = self.dropped = 0
        threading.Thread(target=self._run, daemon=True, name="otlp-exporter").start()

    def submit(self, trace: dict[str, Any]) -> None:
        try:
            self.q.put_nowait(trace)
        except queue.Full:
            self.dropped += 1

    def _run(self) -> None:
        import httpx

        with httpx.Client(timeout=3.0) as http:
            while True:
                t = self.q.get()
                try:
                    r = http.post(self.url, headers=self.headers, content=json.dumps(to_otlp(t, provider=self.provider)))
                    r.raise_for_status()
                    self.sent += 1
                except Exception as e:  # noqa: BLE001 - observability must never break a turn
                    self.failed += 1
                    log.warning("otlp export failed: %s", e)
