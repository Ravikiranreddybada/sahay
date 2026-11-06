"""Gemini adapter using the official Gemini GenerateContent REST API.

The shared LLM contract uses Anthropic-style message blocks internally. This adapter
translates those blocks (including the structured-output repair turn) into Gemini
contents and function calls, keeping the agent graph provider-neutral.
"""

from __future__ import annotations

import os
from typing import Any

import httpx

from .base import LLMError, LLMResponse, ToolCall, ToolSpec


class GeminiLLM:
    name = "gemini"
    _endpoint = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"

    def __init__(self, timeout_s: float = 20.0, *, client: httpx.AsyncClient | None = None) -> None:
        api_key = os.environ.get("GEMINI_API_KEY")
        if not api_key:
            raise RuntimeError("GEMINI_API_KEY is required when SAHAY_LLM_PROVIDER=gemini")
        self._api_key = api_key
        self._client = client or httpx.AsyncClient(timeout=timeout_s)

    @staticmethod
    def _contents(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Translate common text and tool blocks to Gemini Content objects."""
        call_names: dict[str, str] = {}
        contents: list[dict[str, Any]] = []
        for message in messages:
            role = "model" if message["role"] == "assistant" else "user"
            raw = message.get("content", "")
            blocks = raw if isinstance(raw, list) else [{"type": "text", "text": str(raw)}]
            parts: list[dict[str, Any]] = []
            for block in blocks:
                kind = block.get("type", "text")
                if kind == "text":
                    parts.append({"text": str(block.get("text", ""))})
                elif kind == "tool_use":
                    call_id = str(block["id"])
                    name = str(block["name"])
                    call_names[call_id] = name
                    parts.append({"functionCall": {"id": call_id, "name": name, "args": block.get("input", {})}})
                elif kind == "tool_result":
                    call_id = str(block["tool_use_id"])
                    name = call_names.get(call_id, "tool_result")
                    response_key = "error" if block.get("is_error") else "result"
                    parts.append({"functionResponse": {
                        "id": call_id, "name": name, "response": {response_key: block.get("content", "")},
                    }})
            if parts:
                contents.append({"role": role, "parts": parts})
        return contents

    @staticmethod
    def _tools(tools: list[ToolSpec] | None) -> list[dict[str, Any]] | None:
        if not tools:
            return None
        return [{"functionDeclarations": [
            {"name": tool.name, "description": tool.description, "parametersJsonSchema": tool.input_schema}
            for tool in tools
        ]}]

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
        payload: dict[str, Any] = {
            "systemInstruction": {"parts": [{"text": system}]},
            "contents": self._contents(messages),
            "generationConfig": {"maxOutputTokens": max_tokens},
            # Care conversations should not be retained by the API for later use.
            "store": False,
        }
        declared_tools = self._tools(tools)
        if declared_tools:
            payload["tools"] = declared_tools
            cfg: dict[str, Any] = {"mode": "AUTO"}
            if tool_choice and tool_choice.get("type") == "tool":
                cfg = {"mode": "ANY", "allowedFunctionNames": [tool_choice["name"]]}
            payload["toolConfig"] = {"functionCallingConfig": cfg}
        try:
            response = await self._client.post(
                self._endpoint.format(model=model), headers={"x-goog-api-key": self._api_key}, json=payload,
            )
        except (httpx.TimeoutException, httpx.RequestError) as exc:
            raise LLMError(str(exc)) from exc
        if response.is_error:
            # Do not let a provider-side validation or model-availability problem turn
            # into a 500. The router will record it and use the safe offline fallback.
            raise LLMError(f"Gemini API {response.status_code}: {response.text[:400]}")
        data = response.json()
        candidates = data.get("candidates", [])
        if not candidates:
            reason = data.get("promptFeedback", {}).get("blockReason", "Gemini returned no candidate")
            raise LLMError(str(reason))

        candidate = candidates[0]
        out = LLMResponse(model=data.get("modelVersion", model), stop_reason=candidate.get("finishReason", ""))
        for index, part in enumerate(candidate.get("content", {}).get("parts", [])):
            if "text" in part:
                out.text += part["text"]
            if call := part.get("functionCall"):
                out.tool_calls.append(ToolCall(
                    id=str(call.get("id") or f"gemini-{index}"), name=str(call["name"]), args=dict(call.get("args") or {}),
                ))
        usage = data.get("usageMetadata", {})
        out.tokens_in = int(usage.get("promptTokenCount") or 0)
        out.cached_tokens = int(usage.get("cachedContentTokenCount") or 0)
        out.tokens_out = int(usage.get("candidatesTokenCount") or 0)
        return out
