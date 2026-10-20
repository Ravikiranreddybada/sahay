"""Anthropic adapter.

Two context-engineering details that matter at scale:
* The system prompt is sent as a cached block (cache_control=ephemeral). It is the stable
  prefix of every call, so ~70-90% of input tokens are billed at the cache-read rate.
* Retrieved evidence goes in the *user* turn, after the cached prefix, so a cache hit is
  never broken by per-request content.
"""

from __future__ import annotations

import os
from typing import Any

import anthropic

from .base import LLMError, LLMResponse, ToolCall, ToolSpec


class AnthropicLLM:
    name = "anthropic"

    def __init__(self, timeout_s: float = 20.0) -> None:
        # Retries are owned by our router (it also handles fallback), so SDK retries are off.
        self._client = anthropic.AsyncAnthropic(
            api_key=os.environ.get("ANTHROPIC_API_KEY"), timeout=timeout_s, max_retries=0
        )

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
    ) -> LLMResponse:
        kwargs: dict[str, Any] = {
            "model": model,
            "max_tokens": max_tokens,
            "system": [{"type": "text", "text": system, "cache_control": {"type": "ephemeral"}}],
            "messages": messages,
        }
        if tools:
            kwargs["tools"] = [t.to_anthropic() for t in tools]
        if tool_choice:
            kwargs["tool_choice"] = tool_choice
        try:
            msg = await self._client.messages.create(**kwargs)
        except (anthropic.APITimeoutError, anthropic.APIConnectionError, anthropic.RateLimitError) as e:
            raise LLMError(str(e)) from e
        except anthropic.APIStatusError as e:
            if e.status_code >= 500 or e.status_code == 529:
                raise LLMError(str(e)) from e
            raise

        out = LLMResponse(model=model, stop_reason=msg.stop_reason or "")
        for block in msg.content:
            if block.type == "text":
                out.text += block.text
            elif block.type == "tool_use":
                out.tool_calls.append(ToolCall(id=block.id, name=block.name, args=dict(block.input)))
        u = msg.usage
        out.tokens_in = (u.input_tokens or 0) + (getattr(u, "cache_read_input_tokens", 0) or 0)
        out.cached_tokens = getattr(u, "cache_read_input_tokens", 0) or 0
        out.tokens_out = u.output_tokens or 0
        return out
