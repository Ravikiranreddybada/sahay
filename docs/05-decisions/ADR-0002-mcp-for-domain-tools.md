# ADR-0002: Domain tools as MCP servers

**Context.** The agent needs live data from orders, diagnostics, claims and journeys; owned by different teams; today reached by brittle glue scripts.
**Decision.** One MCP server per bounded context (`orders`, `care_services`, `claims`, `care_journeys`). Agent talks to them only via `MCPHub`. In-process in dev, Streamable HTTP (stateless) in prod.
**Alternatives.** Direct REST calls from nodes (N bespoke clients, no shared semantics); one mega tool server (one team's outage takes all tools down).
**Consequences.** + Standard discovery/schemas/annotations; servers reusable by other agents and Claude Desktop; independent scaling and SLOs. − One more hop (~2-5 ms internal); need hub-level policies (solved once).
