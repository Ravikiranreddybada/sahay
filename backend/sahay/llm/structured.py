"""Reliable structured output.

"A schema violation waiting to happen" usually comes from asking for JSON in prose. Instead:
1. The schema is a *forced tool* (tool_choice={type: tool}); the model can only answer by
   filling typed arguments.
2. The arguments are validated by Pydantic (enums, ranges, required fields).
3. On a ValidationError the exact error is fed back once as a repair turn.
4. Still invalid -> raise; the caller has a deterministic safe fallback. We never pass an
   unvalidated dict downstream.
"""

from __future__ import annotations

import json
from typing import Any, TypeVar

from pydantic import BaseModel, ValidationError

from ..obs.tracing import span
from .base import LLMResponse, Tier, ToolSpec
from .router import ModelRouter

T = TypeVar("T", bound=BaseModel)


class StructuredOutputError(Exception):
    pass


def _extract_payload(resp: LLMResponse, tool_name: str) -> Any:
    for tc in resp.tool_calls:
        if tc.name == tool_name:
            return tc.args
    text = resp.text.strip()
    if text.startswith("```"):
        text = text.strip("`").split("\n", 1)[-1]
    return json.loads(text) if text else None


async def structured(
    router: ModelRouter,
    schema: type[T],
    *,
    tier: Tier,
    system: str,
    messages: list[dict[str, Any]],
    task: str,
    hints: dict[str, Any] | None = None,
    max_tokens: int = 800,
) -> T:
    tool_name = f"emit_{task}"
    tool = ToolSpec(name=tool_name, description=f"Return the {task} result.", input_schema=schema.model_json_schema())
    convo = list(messages)
    for attempt in range(2):
        resp = await router.generate(
            tier=tier, system=system, messages=convo, task=task, tools=[tool],
            tool_choice={"type": "tool", "name": tool_name}, max_tokens=max_tokens, hints=hints,
        )
        try:
            payload = _extract_payload(resp, tool_name)
            return schema.model_validate(payload)
        except (ValidationError, json.JSONDecodeError, TypeError) as e:
            with span("structured.repair", kind="guard", task=task, attempt=attempt) as sp:
                sp.set(error=str(e)[:500])
            if attempt == 1:
                raise StructuredOutputError(f"{task}: {e}") from e
            tc = next((t for t in resp.tool_calls if t.name == tool_name), None)
            if tc is None:
                convo = convo + [
                    {"role": "assistant", "content": resp.text or "(no output)"},
                    {"role": "user", "content": f"Invalid output: {e}. Call {tool_name} with valid arguments."},
                ]
            else:
                convo = convo + [
                    {"role": "assistant", "content": [{"type": "tool_use", "id": tc.id, "name": tc.name, "input": tc.args}]},
                    {"role": "user", "content": [{"type": "tool_result", "tool_use_id": tc.id, "is_error": True,
                                                  "content": f"Schema validation failed: {e}. Call {tool_name} again with corrected arguments."}]},
                ]
    raise StructuredOutputError(task)
