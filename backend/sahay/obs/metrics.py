"""Prometheus metrics. These feed the SLO alerts in docs/SYSTEM_DESIGN.md."""

from prometheus_client import Counter, Histogram

REQUESTS = Counter("sahay_requests_total", "Chat turns", ["intent", "outcome"])
LATENCY = Histogram(
    "sahay_turn_latency_seconds", "End-to-end turn latency", ["intent"],
    buckets=(0.1, 0.25, 0.5, 1, 2, 3, 5, 8, 13),
)
NODE_LATENCY = Histogram("sahay_node_latency_seconds", "Per graph node latency", ["node"])
LLM_TOKENS = Counter("sahay_llm_tokens_total", "LLM tokens", ["model", "direction"])
LLM_ERRORS = Counter("sahay_llm_errors_total", "LLM call failures", ["model", "kind"])
TOOL_CALLS = Counter("sahay_tool_calls_total", "MCP tool calls", ["server", "tool", "status"])
CACHE = Counter("sahay_semantic_cache_total", "Semantic cache lookups", ["result"])
GROUNDING = Counter("sahay_grounding_total", "Verifier verdicts", ["verdict"])
ESCALATIONS = Counter("sahay_escalations_total", "Emergency / human escalations", ["reason"])
