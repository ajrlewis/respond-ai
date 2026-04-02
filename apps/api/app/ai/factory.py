"""Purpose-aware model/provider factory."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from app.ai.providers import AIConfigurationError
from app.ai.registry import normalize_provider_name
from app.core.config import settings

ModelPurpose = Literal[
    "classification",
    "cross_reference",
    "drafting",
    "revision",
    "evaluation",
    "polish",
    "draft_metadata",
    "revision_intent",
    "embedding",
]


@dataclass(frozen=True, slots=True)
class ResolvedModelSpec:
    """Resolved provider+model configuration for one call purpose."""

    purpose: ModelPurpose
    provider: str
    model: str


_LARGE_PURPOSES = {"drafting", "revision"}


def _require_model(model_name: str, *, setting_name: str) -> str:
    value = model_name.strip()
    if not value:
        raise AIConfigurationError(f"{setting_name} must be set.")
    return value


def _default_provider() -> str:
    return normalize_provider_name(settings.ai_provider)


def _resolve_large_provider() -> str:
    return normalize_provider_name(settings.large_llm_provider or _default_provider())


def _resolve_small_provider() -> str:
    return normalize_provider_name(settings.small_llm_provider or _default_provider())


def _resolve_embedding_provider() -> str:
    return normalize_provider_name(settings.embedding_provider or _default_provider())


def _resolve_eval_provider() -> str:
    return normalize_provider_name(settings.eval_llm_provider or settings.small_llm_provider or _default_provider())


def resolve_chat_spec(*, purpose: ModelPurpose) -> ResolvedModelSpec:
    """Resolve provider/model for a chat purpose."""

    if purpose in _LARGE_PURPOSES:
        return ResolvedModelSpec(
            purpose=purpose,
            provider=_resolve_large_provider(),
            model=_require_model(settings.large_llm_model, setting_name="LARGE_LLM_MODEL"),
        )

    if purpose == "evaluation" and settings.eval_llm_model.strip():
        return ResolvedModelSpec(
            purpose=purpose,
            provider=_resolve_eval_provider(),
            model=_require_model(settings.eval_llm_model, setting_name="EVAL_LLM_MODEL"),
        )

    return ResolvedModelSpec(
        purpose=purpose,
        provider=_resolve_small_provider(),
        model=_require_model(settings.small_llm_model, setting_name="SMALL_LLM_MODEL"),
    )


def resolve_embedding_spec() -> ResolvedModelSpec:
    """Resolve provider/model for embedding purpose."""

    return ResolvedModelSpec(
        purpose="embedding",
        provider=_resolve_embedding_provider(),
        model=_require_model(settings.embedding_model, setting_name="EMBEDDING_MODEL"),
    )


def _provider_api_key(provider: str) -> str:
    if provider == "openai":
        return settings.openai_api_key.strip()
    if provider == "anthropic":
        return settings.anthropic_api_key.strip()
    if provider == "google":
        return settings.google_api_key.strip()
    return ""


def validate_ai_configuration() -> None:
    """Validate configured provider/model wiring and required API keys."""

    specs = [
        resolve_chat_spec(purpose="classification"),
        resolve_chat_spec(purpose="drafting"),
        resolve_chat_spec(purpose="revision"),
        resolve_embedding_spec(),
    ]
    if settings.enable_llm_judge_evals:
        specs.append(resolve_chat_spec(purpose="evaluation"))

    errors: list[str] = []
    for spec in specs:
        if not _provider_api_key(spec.provider):
            setting_name = {
                "openai": "OPENAI_API_KEY",
                "anthropic": "ANTHROPIC_API_KEY",
                "google": "GOOGLE_API_KEY",
            }.get(spec.provider, "API_KEY")
            errors.append(
                f"{setting_name} is required for purpose='{spec.purpose}' (provider='{spec.provider}', model='{spec.model}')."
            )

        if spec.purpose == "embedding" and spec.provider == "anthropic":
            errors.append(
                "EMBEDDING_PROVIDER=anthropic is unsupported in this stack. Use openai or google for embeddings."
            )

    if errors:
        joined = " ".join(errors)
        raise AIConfigurationError(f"Invalid AI configuration. {joined}")
