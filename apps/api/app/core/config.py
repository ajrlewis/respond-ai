"""Application configuration."""

from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


def _resolve_env_file() -> str:
    """Search upward for .env, preferring API-local first."""

    config_path = Path(__file__).resolve()
    api_root = config_path.parents[2]

    # Local layout: <repo>/apps/api/app/core/config.py
    # Container layout: /app/app/core/config.py
    candidates = [api_root]
    candidates.extend(list(api_root.parents)[:3])

    for base_path in candidates:
        candidate = base_path / ".env"
        if candidate.exists():
            return str(candidate)

    return ".env"


class Settings(BaseSettings):
    """Environment-backed settings for the API."""

    model_config = SettingsConfigDict(env_file=_resolve_env_file(), env_file_encoding="utf-8", extra="ignore")

    app_name: str = "RespondAI API"
    app_env: str = "development"
    api_v1_prefix: str = "/api"
    logging_level: str = Field(default="INFO", description="Root logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL).")

    database_url: str = Field(
        default="postgresql+psycopg://respondai:respondai@localhost:5432/respondai",
        description="Primary Postgres database URL.",
    )

    ai_provider: str = Field(default="openai", description="Default AI provider (openai|anthropic|google).")

    openai_api_key: str = ""
    anthropic_api_key: str = ""
    google_api_key: str = ""

    large_llm_provider: str = ""
    large_llm_model: str = "gpt-4o"
    small_llm_provider: str = ""
    small_llm_model: str = "gpt-4o-mini"
    embedding_provider: str = ""
    embedding_model: str = "text-embedding-3-small"
    embedding_dimension: int = 1536
    eval_llm_provider: str = ""
    eval_llm_model: str = ""

    ai_temperature: float = 0.0
    ai_max_retries: int = 2
    ai_timeout_seconds: int = 60
    enable_llm_judge_evals: bool = False

    model_pricing_json: str = Field(
        default="{}",
        description=(
            "Optional JSON map of per-model token rates in USD. "
            "Format: {\"model\": {\"input_per_1k\": 0.0, \"output_per_1k\": 0.0}}"
        ),
    )

    retrieval_top_k: int = 10
    final_evidence_k: int = 6


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return cached settings instance."""

    return Settings()


settings = get_settings()
