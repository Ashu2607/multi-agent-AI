"""Central configuration loaded from environment / .env."""
from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT_DIR / "data"
KNOWLEDGE_BASE_DIR = DATA_DIR / "knowledge_base"
STRUCTURED_DIR = DATA_DIR / "structured"
SALES_DB_PATH = DATA_DIR / "sales.db"
CHROMA_DIR = ROOT_DIR / "chroma_store"
REPORTS_DIR = ROOT_DIR / "reports"
APPROVALS_DB_PATH = ROOT_DIR / "approvals.db"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # LLM
    openai_api_key: str = ""
    openai_model: str = "gpt-4o-mini"
    openai_temperature: float = 0.0

    # Web search
    tavily_api_key: str = ""

    # Redis (episodic memory)
    redis_url: str = "redis://localhost:6379/0"

    # Zep Cloud (semantic memory)
    zep_api_key: str = ""

    # "auto" = use Redis/Zep when reachable, fall back to in-memory otherwise.
    # Set to "local" to force the in-memory stores (e.g. offline demo/tests).
    memory_backend: str = "auto"

    # LangSmith / LangChain tracing (Policy 5: LangSmith traces must be enabled for debugging)
    langchain_tracing_v2: bool = True
    langchain_api_key: str = ""
    langchain_project: str = "enterprise-research-assistant"

    # App
    max_research_iterations: int = 3
    sql_row_limit: int = 200
    log_level: str = "INFO"

    # API security: required API-key baseline (M5) + required JWT second
    # layer (M6 - upgraded from optional stretch). No default value on
    # purpose - an empty api_key means auth is misconfigured and every
    # request must be rejected rather than silently let through.
    api_key: str = ""
    jwt_secret: str = ""
    jwt_algorithm: str = "HS256"
    jwt_expires_minutes: int = 60
    demo_username: str = "demo"
    demo_password: str = ""

    # Guardrails (M6): prompt-injection/jailbreak/toxicity -> block,
    # PII -> redact. Ported from Milestone-4 (`app/guardrails/`). Kept as a
    # toggle (default on) so a red-team run can be repeated with detection
    # off to show the "before" baseline without deleting the pipeline.
    block_on_injection: bool = True

    # Vector store transport (M6 Step 1 - Docker Compose 3rd service).
    # Empty (default) = the M3/M5 behavior: an embedded Chroma store reading
    # straight from the local CHROMA_DIR folder - unchanged for local/CLI
    # use and for tests. When running under Docker Compose, set
    # CHROMA_SERVER_HOST=vectorstore so the backend talks to the
    # `chromadb/chroma` container over HTTP instead - same "auto vs local"
    # fallback shape already used for Redis/Zep in MEMORY_BACKEND.
    chroma_server_host: str = ""
    chroma_server_port: int = 8000


@lru_cache
def get_settings() -> Settings:
    settings = Settings()
    _configure_langsmith(settings)
    return settings


def _configure_langsmith(settings: Settings) -> None:
    """LangChain/LangSmith read tracing config from process env vars directly
    (Policy 5: LangSmith traces must be enabled for debugging), so mirror the
    typed settings into os.environ once at startup.

    Tracing is only turned on when a LANGCHAIN_API_KEY is actually present -
    otherwise every LLM/tool call would fail its trace upload with a 401 and
    spam stderr. Add a key (free tier at smith.langchain.com) to enable it."""
    tracing_enabled = settings.langchain_tracing_v2 and bool(settings.langchain_api_key)
    os.environ["LANGCHAIN_TRACING_V2"] = "true" if tracing_enabled else "false"
    if settings.langchain_api_key:
        os.environ["LANGCHAIN_API_KEY"] = settings.langchain_api_key
    os.environ["LANGCHAIN_PROJECT"] = settings.langchain_project
