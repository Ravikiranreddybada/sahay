"""Model router: tier -> model, retries with jittered backoff, circuit breaker, fallback model,
and one trace span per call with tokens + cost.

The trade-off it encodes: intent/verification run on the fast tier (≈200-400 ms, cheap) because
they are narrow classification jobs; only synthesis and tool planning pay for the smart tier.
"""

from __future__ import annotations

import asyncio
import os
import random
from typing import Any

from ..config import Settings
from ..obs import metrics
from ..obs.tracing import current_trace, span
from ..reliability.breaker import CircuitBreaker
from .base import LLM, LLMError, LLMResponse, Tier, ToolSpec, cost_usd
from .offline_llm import OfflineLLM


class ModelRouter:
    def __init__(self, settings: Settings, provider: LLM | None = None) -> None:
        self.s = settings
        if provider is not None:
            self.provider = provider
        elif settings.llm_provider == "anthropic" or (
            settings.llm_provider == "auto" and os.environ.get("ANTHROPIC_API_KEY")
        ):
            from .anthropic_llm import AnthropicLLM

            self.provider = AnthropicLLM(timeout_s=settings.llm_timeout_s)
        else:
            self.provider = OfflineLLM()
        self.breakers: dict[str, CircuitBreaker] = {}
        self._offline = OfflineLLM()

    @property
    def mode(self) -> str:
        return self.provider.name

    def _breaker(self, model: str) -> CircuitBreaker:
        if model not in self.breakers:
            self.breakers[model] = CircuitBreaker(model, self.s.breaker_failures, self.s.breaker_reset_s)
        return self.breakers[model]

    def _model_for(self, tier: Tier) -> str:
        return self.s.model_fast if tier == "fast" else self.s.model_smart

    async def generate(
        self,
        *,
        tier: Tier,
        system: str,
        messages: list[dict[str, Any]],
        task: str,
        tools: list[ToolSpec] | None = None,
        tool_choice: dict[str, Any] | None = None,
        max_tokens: int = 1024,
        hints: dict[str, Any] | None = None,
    ) -> LLMResponse:
        primary = self._model_for(tier)
        chain = [primary] if primary == self.s.model_fallback else [primary, self.s.model_fallback]
        last_err: Exception | None = None
        for model in chain:
            br = self._breaker(model)
            if not br.allow():
                metrics.LLM_ERRORS.labels(model, "breaker_open").inc()
                continue
            for attempt in range(self.s.llm_max_retries + 1):
                with span(f"llm.{task}", kind="llm", model=model, tier=tier, attempt=attempt) as sp:
                    try:
                        resp = await asyncio.wait_for(
                            self.provider.generate(
                                model=model, system=system, messages=messages, tools=tools,
                                tool_choice=tool_choice, max_tokens=max_tokens, task=task, hints=hints,
                            ),
                            timeout=self.s.llm_timeout_s,
                        )
                    except (LLMError, asyncio.TimeoutError) as e:
                        br.record_failure()
                        metrics.LLM_ERRORS.labels(model, type(e).__name__).inc()
                        sp.status = "error"
                        sp.set(error=str(e) or type(e).__name__)
                        last_err = e
                        if attempt < self.s.llm_max_retries:
                            await asyncio.sleep(min(2.0, 0.2 * 2**attempt) * (0.5 + random.random()))
                        continue
                    br.record_success()
                    real_model = resp.model or model
                    c = cost_usd(real_model, resp.tokens_in - resp.cached_tokens, resp.tokens_out) + cost_usd(
                        real_model, int(resp.cached_tokens * 0.1), 0
                    )
                    sp.set(
                        tokens_in=resp.tokens_in, tokens_out=resp.tokens_out, cached_tokens=resp.cached_tokens,
                        cost_usd=c, stop_reason=resp.stop_reason, fallback=model != primary,
                        tool_calls=[{"name": t.name, "args": t.args} for t in resp.tool_calls],
                    )
                    metrics.LLM_TOKENS.labels(real_model, "in").inc(resp.tokens_in)
                    metrics.LLM_TOKENS.labels(real_model, "out").inc(resp.tokens_out)
                    return resp
        if self.s.degrade_to_offline and self.provider.name != "offline":
            # Every model is down or its breaker is open. A grounded, extractive answer from
            # the offline engine beats an error page; the trace and the UI mark the turn.
            with span(f"llm.{task}", kind="llm", model="offline", tier=tier, degraded=True, cause=str(last_err)[:200]):
                resp = await self._offline.generate(model="offline", system=system, messages=messages, tools=tools,
                                                    tool_choice=tool_choice, max_tokens=max_tokens, task=task, hints=hints)
            metrics.LLM_ERRORS.labels(primary, "degraded_offline").inc()
            if (tr := current_trace()) is not None:
                tr.meta["degraded"] = True
            return resp
        raise LLMError(f"all models failed for task={task}: {last_err}")
