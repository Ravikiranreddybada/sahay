# GitHub Repo Research — What We Took From Each

Method: `gh search repos` across 20 queries (agents, RAG, evals, MCP, gateways, guardrails, memory,
observability, medical RAG), sorted by stars, then reading the README / tree of the top candidates.
Star counts as of **2026-10-18**. Rule for inclusion: take an *idea or pattern*, implement it
ourselves at the size this product needs; add a dependency only if building it is not the lesson.

## Agent runtime and app skeleton

| Repo | ★ | What it is | What we took | What we left |
|---|---|---|---|---|
| langchain-ai/langgraph | 43.4k | Stateful agent graphs | **Runtime.** StateGraph, conditional edges, `interrupt()` for human-in-the-loop, checkpointer per thread | Prebuilt ReAct agent: we need explicit nodes we can trace and test individually |
| wassim249/fastapi-langgraph-agent-production-ready-template | 2.7k | FastAPI + LangGraph production template | Layout: `api/ core/ services/ schemas/`, LLM registry with fallback, rate limiter, metrics module, prompts as `.md` files | mem0 memory, DuckDuckGo tool, JWT boilerplate (out of scope for the core lesson) |
| langchain-ai/deepagents | 30.4k | Batteries-included agent harness | Idea of a small fixed set of capabilities per agent (our per-intent tool allow-list) | Planning/todo filesystem — overkill for support turns |
| bytedance/deer-flow | 84k | Long-horizon research super-agent | Node-level progress streaming to the UI | Multi-hour planning loops (support turns must finish in seconds) |
| google-gemini/gemini-fullstack-langgraph-quickstart | 18.3k | Full-stack LangGraph demo | Front-end that shows the agent's steps live next to the chat | Web-search research loop |
| langchain-ai/agent-chat-ui | 3.2k | Chat UI for LangGraph | Interrupt / confirm card UX pattern | Generic UI; we built a domain UI with a trace inspector |
| NirDiamant/agents-towards-production | 21.7k | Production agent tutorials | Checklist: tracing, evals, guardrails, memory, deployment as first-class modules | — |

## RAG

| Repo | ★ | What we took | What we left |
|---|---|---|---|
| infiniflow/ragflow | 92k | **Structure-aware chunking** ("deep document understanding"): chunk by layout/heading, keep tables whole | OCR/layout models — our SOPs are markdown |
| HKUDS/LightRAG | 40k | Dual-level retrieval idea (specific vs. thematic) → our intent-tag prior + heading match rerank features | Graph extraction with an LLM at index time (cost, staleness) |
| microsoft/graphrag | 36k | Lesson: global questions need summaries; ours are local → plain hybrid retrieval is the right call | Whole GraphRAG pipeline |
| langgenius/dify | 158k | Hybrid search + rerank as default; doc versioning in the knowledge base UI | Low-code platform |
| Tencent/WeKnora | 34.5k | Knowledge platform with explicit doc lifecycle → our `version` / `review_by` frontmatter | — |
| yolo-hyl/medical-rag, wizardlancet/OpenOE-Lite | 306 / 94 | Medical RAG must cite evidence and abstain when evidence is missing | Clinical-literature retrieval (we are a support assistant, not a clinical tool) |
| zilliztech/GPTCache | 8.2k | **Semantic cache** concept | Its generic cache: we needed namespacing by prompt/KB version and a "never cache personal data" rule |

## MCP / tools

| Repo | ★ | What we took |
|---|---|---|
| modelcontextprotocol/python-sdk (`mcp` 2.x) | — | **The protocol implementation.** `MCPServer`, `Client`, tool annotations (`readOnlyHint`, `destructiveHint`), `ToolError` vs crash masking, Streamable HTTP for standalone servers |
| PrefectHQ/fastmcp | 28k | Decorator-style tool definition from type hints (now upstream as MCPServer) |
| maximhq/bifrost, katanemo/plano | 8.9k / 7.1k | **Gateway between agent and tools**: auth, timeouts, observability in one choke point → our `MCPHub` |
| casdoor/casdoor | 14.6k | Agent-first IAM: tools act *as the user*, never with a free-form user id → injected `user_id` |

## LLM gateway / reliability

| Repo | ★ | What we took |
|---|---|---|
| BerriAI/litellm | 61k | Model routing tiers, fallbacks, retries, cost tracking per call → `ModelRouter` |
| Portkey-AI/gateway | 13.2k | Circuit breaker + fallback chain semantics; guardrails at the gateway |
| tensorzero/tensorzero | 11.7k | Treat prompts/models as *experiments* with metrics feedback → prompt_version in every trace + eval gate |

## Evals & observability

| Repo | ★ | What we took |
|---|---|---|
| langfuse/langfuse | 36k | Trace → span → generation data model; user feedback attached to traces |
| comet-ml/opik, Arize-ai/phoenix | 22.7k / 11.9k | Span kinds (llm / retrieval / tool), retrieval-hit inspection in UI |
| promptfoo/promptfoo | 26k | **Assertion-style test cases in YAML** + CI gate + red-team cases → `evals/golden.yaml` |
| confident-ai/deepeval, vibrantlabsai/ragas | 18.9k / 16k | Metric definitions: faithfulness, context recall/precision, answer relevancy → our deterministic versions + optional LLM judge |
| mlflow/mlflow | 28k | Record config + metrics per run → `evals/reports/*.json` with the exact settings |
| stanfordnlp/dspy | 38.7k | Mindset: prompts are parameters optimised against a metric, not prose edited by vibe |

## Safety

| Repo | ★ | What we took |
|---|---|---|
| data-privacy-stack/presidio | 11.4k | Recognizer + checksum validation pattern → India-specific recognizers (Aadhaar Verhoeff, card Luhn, PAN, UPI) |
| NVIDIA-NeMo/Guardrails, guardrails-ai/guardrails | 7.3k / 7.5k | Input rails / output rails split → `guard_in` / `verify` nodes |
| protectai/rebuff, superagent-ai/superagent | 1.5k / 6.8k | Layered prompt-injection defence; treat tool output as untrusted (indirect injection) |

## Memory

| Repo | ★ | Decision |
|---|---|---|
| mem0ai/mem0 | 67k | **Not adopted for v1.** Long-term free-form memory in healthcare is a privacy liability; we keep structured profile + journey state from MCP (source of truth) and short-term thread memory. Revisit for preferences only. |

## The synthesis (why this combination is rare)
Most open-source projects are excellent at **one** layer. The product value is in the seams:
- RAG projects don't know the user (no tools); tool/agent projects don't verify grounding.
- Eval projects test prompts in isolation; they don't gate the *whole graph* end-to-end.
- Gateways handle model fallback; none handle *tool* idempotency and user scoping.

Sahay's contribution is wiring these into one graph where each seam has a mechanism and a test.

## October 2026 sweep — trending repos and what v0.3 took

Method: `gh search repos` with `--created ">2026-03-01" --sort stars` across 17 topics (medical agent, health
records, clinical LLM, FHIR MCP, prescriptions, drug interactions, voice agents, agent memory, guardrails,
prompt injection, agent evals, observability, document parsing, durable workflows), plus the overall
"created after July 2026" leaderboard. Then reading the README of each candidate. Most top-starred new repos
are coding-agent harnesses and skills (deepseek-harness, grok-build, ponytail, caveman) — not relevant to a
care assistant. The ideas below come from the smaller, domain-relevant ones.

| Repo | ★ | Idea | What Sahay v0.3 built |
|---|---|---|---|
| shivama205/parchi | new | Caregiver agent: brand → molecule incl. fixed-dose combinations; one molecule from two prescribers; lab values on one axis with cited unit conversion; "appointment brief nobody asked for"; ABDM moves records but does not synthesise them | `health_records` MCP server: `get_medication_list`, `get_lab_trends`, `get_visit_brief`; `health/catalog.py`, `health/labs.py` (IFCC→NGSP, mmol/L→mg/dL, nmol/L→ng/mL, µmol/L→mg/dL, each factor cited); steady-rise detection |
| shubhamjoshipromail-svg/rxcheck | 4 | "The database decides whether an interaction exists. The LLM only explains." | `check_medication_safety` + verifier criteria `no_safety_verdict`, `interactions_from_database` (ADR-0018) |
| wongqihan/triagebench | 3 | TriageGap: same vignette, swap gender / language / ZIP; the decision must not move | `evals/counterfactual.yaml`, 141 runs, hard gate `counterfactual_consistency == 1.0`, proven to fail on injected bias (ADR-0020) |
| Agent-Threat-Rule/agent-threat-rules | 417 | Detection rules as versioned YAML with public ids and executable tests (Sigma for agents) | `safety/rules/threat_rules.yaml`: 13 rules, OWASP LLM Top 10 mapping, Hinglish + Devanagari, every example is a test (ADR-0021) |
| llm-as-a-verifier/llm-as-a-verifier | 3.3k | Fine-grained, criteria-decomposed verification instead of one pass/fail | Verifier returns a 9-criterion scorecard + score; shown per turn in the UI, in the trace and in OTLP |
| grafana/agento11y, anhermon/awesome-agent-observability | 129 / 52 | Agent observability on OpenTelemetry GenAI conventions | `obs/otel.py`: OTLP/JSON export, `invoke_agent` / `chat` / `execute_tool` spans, privacy allow-list (ADR-0022) |
| tigerless-labs/agent-memory, TencentDB-Agent-Memory, MemPalace | 4.2k / 29.5k / 59.6k | Long-term memory runtimes | **Not adopted** (ADR-0012 stands). Instead: DPDP data rights — `GET /v1/me/data` (access) and `DELETE /v1/me/history` (erasure of checkpoints + traces) |
| ServiceNow/eva, xzf-thu/VoiceMem, streamcore-server | 229 / 2.6k / 234 | Voice agents and their evaluation | Browser speech-to-text (Web Speech API, en-IN / hi-IN) in the chat composer; audio never reaches the backend. Full voice pipeline + EVA-style eval is roadmap |
| faulkj/fhirHydrant, DhairyaShah981/fhir-mcp | 18 / 1 | FHIR as an MCP server | Not built: Sahay's records are platform records, not an EHR. The `health_records` tool contracts map to FHIR `MedicationStatement` / `Observation` if an ABDM/FHIR source is added |
| run-llama/ParseBench, baidu/Unlimited-OCR | 603 / 27.8k | Document parsing for agents | Roadmap: prescription / lab-report photo intake feeding the same tables, with a confirm-what-I-could-not-read loop (parchi's pattern) |

### Why this is not in the market
Indian care apps answer "where is my order". None of the open-source projects above combines, in one
grounded graph: a caregiver's consented view of a parent's records, molecule-level duplicate and interaction
flags that the model cannot overrule, lab trends across labs and units with the conversion shown, a visit
brief, an emergency path that cannot be biased by who is asking (and a gate that proves it), and
observability that exports to any OTel backend without exporting health data.
