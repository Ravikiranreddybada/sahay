"""Provider-neutral LLM contract.

Messages use Anthropic-style content blocks (text / tool_use / tool_result) because that is
the richest common format; adapters translate if a provider needs something else.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal, Protocol

Tier = Literal["fast", "smart"]


@dataclass
class ToolSpec:
    name: str
    description: str
    input_schema: dict[str, Any]
    server: str = "local"
    writes: bool = False  # write tools need human confirmation (see agent/nodes/tools.py)

    def to_anthropic(self) -> dict[str, Any]:
        return {"name": self.name, "description": self.description, "input_schema": self.input_schema}


@dataclass
class ToolCall:
    id: str
    name: str
    args: dict[str, Any]


@dataclass
class LLMResponse:
    text: str = ""
    tool_calls: list[ToolCall] = field(default_factory=list)
    tokens_in: int = 0
    tokens_out: int = 0
    cached_tokens: int = 0
    model: str = ""
    stop_reason: str = ""


class LLMError(Exception):
    """Retryable provider error (timeout, 429, 5xx)."""


class LLM(Protocol):
    name: str

    async def generate(
        self,
        *,
        model: str,
        system: str,
        messages: list[dict[str, Any]],
        tools: list[ToolSpec] | None = None,
        tool_choice: dict[str, Any] | None = None,
        max_tokens: int = 1024,
        task: str = "chat",
        hints: dict[str, Any] | None = None,
    ) -> LLMResponse: ...


# Approximate list prices, USD per 1M tokens (input, output). Used for cost-per-turn
# budgeting in traces; real billing comes from the provider invoice.
PRICES: dict[str, tuple[float, float]] = {
    "claude-sonnet-5-5": (3.0, 15.0),
    "claude-haiku-5-5": (1.0, 5.0),
    "claude-opus-5-5": (5.0, 25.0),
    "offline": (0.0, 0.0),
}


def cost_usd(model: str, tokens_in: int, tokens_out: int) -> float:
    p_in, p_out = PRICES.get(model, (3.0, 15.0))
    return (tokens_in * p_in + tokens_out * p_out) / 1_000_000
