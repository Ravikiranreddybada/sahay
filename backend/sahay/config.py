"""Central settings. Every knob that changes model behaviour lives here, so an eval run
can record the exact config it ran against (see evals/run_evals.py)."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="SAHAY_", env_file=".env", extra="ignore")

    env: str = "dev"

    # LLM. Provider "auto" = Anthropic if ANTHROPIC_API_KEY is set, else the offline engine.
    llm_provider: str = "auto"  # auto | anthropic | offline
    model_fast: str = "claude-haiku-5-5"  # intent, routing, verification
    model_smart: str = "claude-sonnet-5-5"  # answer synthesis, tool planning
    model_fallback: str = "claude-haiku-5-5"  # used when the breaker opens on model_smart
    llm_timeout_s: float = 20.0
    llm_max_retries: int = 2
    # L3 of the degradation ladder (docs/04-system-design): when every model fails, the
    # deterministic offline engine answers instead of the turn crashing with a 500.
    degrade_to_offline: bool = True

    # Context engineering
    context_budget_tokens: int = 6000
    retrieval_top_k: int = 5
    retrieval_candidates: int = 20
    min_retrieval_score: float = 0.012  # RRF floor; below this we treat retrieval as a miss
    max_tool_steps: int = 4
    max_verify_retries: int = 1

    # Reliability
    rate_limit_per_min: int = 30
    semantic_cache_threshold: float = 0.93
    semantic_cache_ttl_s: int = 3600
    breaker_failures: int = 5
    breaker_reset_s: float = 30.0

    # Storage. Dev = SQLite files; prod = Postgres/Redis URLs (see docs/SYSTEM_DESIGN.md).
    data_dir: Path = ROOT / "var"
    kb_dir: Path = ROOT / "data" / "kb"
    redis_url: str | None = None
    database_url: str | None = None

    # Auth. The API never trusts a user_id from the request body: it comes from a signed
    # session token. dev_login mints tokens for the seeded demo personas (dev only).
    auth_secret: str = "dev-only-secret-change-me"
    token_ttl_s: int = 12 * 3600
    dev_login: bool = True
    ops_key: str | None = None  # optional static key for ops endpoints (CI, dashboards)

    # Channels
    whatsapp_verify_token: str = "sahay-dev-verify"
    whatsapp_app_secret: str | None = None  # Meta app secret: verifies X-Hub-Signature-256
    whatsapp_access_token: str | None = None  # Graph API token; unset = outbox only (no network)
    whatsapp_phone_number_id: str | None = None
    reminder_interval_s: int = 3600  # background vaccine-reminder sweep; 0 disables

    # Observability: OTLP/HTTP collector base URL (e.g. http://tempo:4318). Unset = no export.
    otlp_endpoint: str | None = None
    otlp_headers: str | None = None  # "Authorization=Basic xyz,X-Scope-OrgID=sahay"

    # Prompt version is part of every trace + cache key: a prompt change must never
    # be served from a cache filled by the old prompt.
    prompt_version: str = "v4"

    @property
    def domain_db(self) -> Path:
        return self.data_dir / "domain.sqlite"

    @property
    def traces_db(self) -> Path:
        return self.data_dir / "traces.sqlite"

    @property
    def checkpoint_db(self) -> Path:
        return self.data_dir / "checkpoints.sqlite"


@lru_cache
def get_settings() -> Settings:
    s = Settings()
    s.data_dir.mkdir(parents=True, exist_ok=True)
    return s
