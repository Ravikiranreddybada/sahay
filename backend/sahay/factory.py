"""Builds the dependency graph once (API lifespan, eval runner, tests)."""

from __future__ import annotations

from contextlib import asynccontextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any, AsyncIterator

from .agent.graph import Agent, Deps, load_prompts
from .channels.outbox import Outbox
from .channels.reminders import ReminderService
from .channels.whatsapp import WhatsAppChannel
from .config import Settings, get_settings
from .llm.base import LLM
from .llm.router import ModelRouter
from .mcp_servers import servers
from .mcp_servers.hub import MCPHub
from .mcp_servers.store import DomainStore
from .obs.tracing import TraceStore
from .rag.index import HybridIndex
from .reliability.cache import SemanticCache
from .store.handoff import HandoffQueue


@asynccontextmanager
async def build_agent(settings: Settings | None = None, *, provider: LLM | None = None, data_dir: Path | None = None,
                      checkpointer: Any | None = None, redis: Any | None = None) -> AsyncIterator[Agent]:
    s = settings or get_settings()
    d = data_dir or s.data_dir
    d.mkdir(parents=True, exist_ok=True)
    servers.set_store(DomainStore(d / "domain.sqlite", reseed_stale=s.env == "dev"))
    index = HybridIndex()
    index.load_dir(s.kb_dir)
    if redis is not None:
        from .reliability.redis_backends import RedisSemanticCache

        cache: Any = RedisSemanticCache(redis, index.embedder, s.semantic_cache_threshold, s.semantic_cache_ttl_s)
    else:
        cache = SemanticCache(index.embedder, s.semantic_cache_threshold, s.semantic_cache_ttl_s)
    hub = MCPHub()
    await hub.start()
    deps = Deps(
        settings=s, router=ModelRouter(s, provider=provider), hub=hub, index=index, cache=cache,
        traces=TraceStore(str(d / "traces.sqlite")), handoffs=HandoffQueue(str(d / "handoffs.sqlite")),
        prompts=load_prompts(),
    )
    if s.otlp_endpoint:
        from .obs.otel import OTLPExporter

        hdrs = dict(kv.split("=", 1) for kv in (s.otlp_headers or "").split(",") if "=" in kv)
        prov = "sahay.offline" if deps.router.mode == "offline" else "anthropic"
        deps.traces.exporter = OTLPExporter(s.otlp_endpoint, hdrs, provider=prov)
    agent = Agent(deps, checkpointer)
    agent.redis = redis
    try:
        yield agent
    finally:
        await hub.stop()


@dataclass
class Channels:
    outbox: Outbox
    whatsapp: WhatsAppChannel
    reminders: ReminderService


def build_channels(agent: Agent, settings: Settings, data_dir: Path) -> Channels:
    outbox = Outbox(str(data_dir / "channels.sqlite"))
    wa = WhatsAppChannel(settings, agent, outbox)
    return Channels(outbox=outbox, whatsapp=wa, reminders=ReminderService(servers.store(), outbox, wa))
