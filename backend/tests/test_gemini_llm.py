import json

import httpx
import pytest

from sahay.llm.base import ToolSpec
from sahay.llm.gemini_llm import GeminiLLM
from sahay.llm.router import ModelRouter
from sahay.config import Settings


@pytest.fixture
def gemini_key(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")


@pytest.mark.asyncio
async def test_gemini_maps_text_tools_and_usage(gemini_key):
    captured = {}

    async def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        captured["api_key"] = request.headers.get("x-goog-api-key")
        captured["body"] = json.loads(request.content)
        return httpx.Response(200, json={
            "modelVersion": "gemini-3.5-flash-lite-001",
            "candidates": [{"finishReason": "STOP", "content": {"parts": [{"text": "Done."}, {"functionCall": {"id": "c1", "name": "lookup", "args": {"id": "42"}}}]}}],
            "usageMetadata": {"promptTokenCount": 11, "cachedContentTokenCount": 3, "candidatesTokenCount": 7},
        })

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        llm = GeminiLLM(client=client)
        result = await llm.generate(
            model="gemini-3.5-flash-lite", system="Be precise.", messages=[{"role": "user", "content": "Check this."}],
            tools=[ToolSpec("lookup", "Look something up.", {"type": "object", "properties": {"id": {"type": "string"}}})],
            tool_choice={"type": "tool", "name": "lookup"},
        )

    assert "key=test-key" not in captured["url"]
    assert captured["api_key"] == "test-key"
    assert captured["body"]["toolConfig"]["functionCallingConfig"]["mode"] == "ANY"
    assert captured["body"]["tools"][0]["functionDeclarations"][0]["parametersJsonSchema"]["type"] == "object"
    assert result.text == "Done."
    assert result.tool_calls[0].name == "lookup"
    assert result.tokens_in == 11 and result.cached_tokens == 3 and result.tokens_out == 7


def test_gemini_translates_tool_repair_turn():
    contents = GeminiLLM._contents([
        {"role": "assistant", "content": [{"type": "tool_use", "id": "call-1", "name": "emit_answer", "input": {"answer": "x"}}]},
        {"role": "user", "content": [{"type": "tool_result", "tool_use_id": "call-1", "is_error": True, "content": "Fix schema."}]},
    ])
    assert contents[0]["role"] == "model"
    assert contents[1]["parts"][0]["functionResponse"] == {"id": "call-1", "name": "emit_answer", "response": {"error": "Fix schema."}}


def test_gemini_uses_gemini_model_fallback(gemini_key):
    router = ModelRouter(Settings(), provider=type("GeminiProvider", (), {"name": "gemini"})())
    assert router._model_for("smart") == "gemini-3.5-flash-lite"
    assert router._fallback_model() == "gemini-3.5-flash-lite"
