"""Thin LangChain-backed model factory and purpose-based routing."""

from __future__ import annotations

import asyncio
from collections.abc import Mapping
from dataclasses import dataclass
import logging
from time import perf_counter
from typing import Any, Literal

from app.ai.errors import AIConfigurationError, AIProviderError
from app.ai.usage import estimate_text_tokens, extract_usage_payload, normalize_usage_payload
from app.core.config import settings
from app.services.observability import (
    LLMLogRecord,
    estimate_cost_usd,
    log_llm_call_async,
    sanitize_payload,
)

logger = logging.getLogger(__name__)

ModelPurpose = Literal[
    "classification",
    "planning",
    "cross_reference",
    "evidence_evaluation",
    "drafting",
    "revision",
    "evaluation",
    "polish",
    "draft_metadata",
    "revision_intent",
    "embedding",
]

SUPPORTED_PROVIDERS = {"openai", "anthropic", "google"}
EMBEDDING_PROVIDERS = {"openai", "google"}
_LARGE_PURPOSES = {"drafting", "revision"}


@dataclass(frozen=True, slots=True)
class ResolvedModelSpec:
    """Resolved provider+model configuration for one call purpose."""

    purpose: ModelPurpose
    provider: str
    model: str


@dataclass(slots=True)
class ChatModelClient:
    """Purpose-configured chat client returning plain text."""

    purpose: ModelPurpose
    provider: str
    model: str

    async def ainvoke(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
        temperature: float | None = None,
        request_metadata: dict[str, Any] | None = None,
    ) -> str:
        selected_temperature = float(settings.ai_temperature if temperature is None else temperature)

        started = perf_counter()
        status = "success"
        error_message: str | None = None
        response_payload: dict[str, Any] = {}
        input_tokens = 0
        output_tokens = 0
        total_tokens = 0
        normalized_input_tokens = 0
        normalized_output_tokens = 0
        raw_usage_payload: dict[str, Any] = {}

        try:
            message = await _invoke_chat_message(
                provider=self.provider,
                model=self.model,
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                temperature=selected_temperature,
                purpose=self.purpose,
            )
            text = _coerce_text(getattr(message, "content", ""))
            raw_usage_payload = extract_usage_payload(message)
            usage = normalize_usage_payload(
                raw_usage_payload,
                input_fallback_tokens=estimate_text_tokens(system_prompt) + estimate_text_tokens(user_prompt),
                output_fallback_tokens=estimate_text_tokens(text),
            )
            input_tokens = usage.input_tokens
            output_tokens = usage.output_tokens
            total_tokens = usage.total_tokens
            normalized_input_tokens = usage.normalized_input_tokens
            normalized_output_tokens = usage.normalized_output_tokens
            response_payload = {
                "content": text,
                "response_metadata": dict(getattr(message, "response_metadata", {}) or {}),
            }
            return text
        except Exception as exc:
            status = "error"
            error_message = str(exc)
            raise
        finally:
            latency_ms = int((perf_counter() - started) * 1000)
            await log_llm_call_async(
                LLMLogRecord(
                    provider=self.provider,
                    model_name=self.model,
                    call_type="chat_completion",
                    purpose=self.purpose,
                    request_payload=sanitize_payload(
                        {
                            "temperature": selected_temperature,
                            "messages": [
                                {"role": "system", "content": system_prompt},
                                {"role": "user", "content": user_prompt},
                            ],
                            "metadata": request_metadata or {},
                        }
                    ),
                    response_payload=sanitize_payload(response_payload),
                    input_tokens=input_tokens,
                    output_tokens=output_tokens,
                    total_tokens=total_tokens,
                    normalized_input_tokens=normalized_input_tokens,
                    normalized_output_tokens=normalized_output_tokens,
                    raw_usage_payload=sanitize_payload(raw_usage_payload),
                    estimated_cost_usd=estimate_cost_usd(
                        model_name=self.model,
                        input_tokens=normalized_input_tokens or input_tokens,
                        output_tokens=normalized_output_tokens or output_tokens,
                    ),
                    latency_ms=latency_ms,
                    status=status,
                    error_message=error_message,
                )
            )


def _require_model(model_name: str, *, setting_name: str) -> str:
    value = model_name.strip()
    if not value:
        raise AIConfigurationError(f"{setting_name} must be set.")
    return value


def normalize_provider_name(provider_name: str | None) -> str:
    """Normalize provider names and apply the global default."""

    name = (provider_name or "").strip().lower()
    if not name:
        name = settings.ai_provider.strip().lower() or "openai"
    if name not in SUPPORTED_PROVIDERS:
        raise AIConfigurationError(
            f"Unsupported AI provider '{name}'. Supported providers: {', '.join(sorted(SUPPORTED_PROVIDERS))}."
        )
    return name


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


def _required_api_key(provider: str) -> str:
    key = _provider_api_key(provider)
    if key:
        return key

    setting_name = {
        "openai": "OPENAI_API_KEY",
        "anthropic": "ANTHROPIC_API_KEY",
        "google": "GOOGLE_API_KEY",
    }.get(provider, "API_KEY")
    raise AIConfigurationError(f"{setting_name} is required when using provider={provider}.")


def validate_ai_configuration() -> None:
    """Validate configured provider/model wiring and required API keys."""

    specs = [
        resolve_chat_spec(purpose="classification"),
        resolve_chat_spec(purpose="planning"),
        resolve_chat_spec(purpose="evidence_evaluation"),
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

        if spec.purpose == "embedding" and spec.provider not in EMBEDDING_PROVIDERS:
            errors.append(
                "EMBEDDING_PROVIDER=anthropic is unsupported in this stack. Use openai or google for embeddings."
            )

    if errors:
        raise AIConfigurationError(f"Invalid AI configuration. {' '.join(errors)}")


def _coerce_text(content: Any) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        rows: list[str] = []
        for item in content:
            if isinstance(item, str):
                rows.append(item)
            elif isinstance(item, Mapping):
                text_value = item.get("text")
                if isinstance(text_value, str):
                    rows.append(text_value)
        return "\n".join(row for row in rows if row.strip())
    return str(content or "")


def _build_messages(*, system_prompt: str, user_prompt: str) -> list[Any]:
    from langchain_core.messages import HumanMessage, SystemMessage

    return [SystemMessage(content=system_prompt), HumanMessage(content=user_prompt)]


def build_chat_backend(*, provider: str, model: str, temperature: float) -> Any:
    """Instantiate a LangChain chat model for a resolved provider/model."""

    if provider == "openai":
        try:
            from langchain_openai import ChatOpenAI
        except ImportError as exc:  # pragma: no cover - dependency guard
            raise AIConfigurationError(
                "langchain-openai is not installed. Add it to API dependencies to use provider=openai."
            ) from exc
        return ChatOpenAI(model=model, api_key=_required_api_key("openai"), temperature=temperature)

    if provider == "anthropic":
        try:
            from langchain_anthropic import ChatAnthropic
        except ImportError as exc:  # pragma: no cover - dependency guard
            raise AIConfigurationError(
                "langchain-anthropic is not installed. Add it to API dependencies to use provider=anthropic."
            ) from exc
        return ChatAnthropic(model=model, anthropic_api_key=_required_api_key("anthropic"), temperature=temperature)

    if provider == "google":
        try:
            from langchain_google_genai import ChatGoogleGenerativeAI
        except ImportError as exc:  # pragma: no cover - dependency guard
            raise AIConfigurationError(
                "langchain-google-genai is not installed. Add it to API dependencies to use provider=google."
            ) from exc
        return ChatGoogleGenerativeAI(model=model, google_api_key=_required_api_key("google"), temperature=temperature)

    raise AIConfigurationError(
        f"Unsupported AI provider '{provider}'. Supported providers: {', '.join(sorted(SUPPORTED_PROVIDERS))}."
    )


async def _run_with_retry(operation, *, provider: str, purpose: str) -> Any:
    max_retries = max(0, int(settings.ai_max_retries))
    timeout_seconds = max(1, int(settings.ai_timeout_seconds))

    attempt = 0
    while True:
        try:
            return await asyncio.wait_for(operation(), timeout=timeout_seconds)
        except AIConfigurationError:
            raise
        except Exception as exc:
            attempt += 1
            if attempt > max_retries:
                raise
            logger.warning(
                "Retrying AI call provider=%s purpose=%s attempt=%d/%d error=%s",
                provider,
                purpose,
                attempt,
                max_retries,
                exc,
            )


async def _invoke_chat_message(
    *,
    provider: str,
    model: str,
    system_prompt: str,
    user_prompt: str,
    temperature: float,
    purpose: str,
) -> Any:
    chat = build_chat_backend(provider=provider, model=model, temperature=temperature)
    messages = _build_messages(system_prompt=system_prompt, user_prompt=user_prompt)
    try:
        return await _run_with_retry(
            lambda: chat.ainvoke(messages),
            provider=provider,
            purpose=purpose,
        )
    except AIConfigurationError:
        raise
    except Exception as exc:
        raise AIProviderError(f"{provider} chat completion failed: {exc}") from exc


def get_chat_model(*, purpose: ModelPurpose) -> ChatModelClient:
    """Get plain-text chat model client for a call purpose."""

    spec = resolve_chat_spec(purpose=purpose)
    return ChatModelClient(purpose=purpose, provider=spec.provider, model=spec.model)


__all__ = [
    "AIConfigurationError",
    "AIProviderError",
    "ChatModelClient",
    "EMBEDDING_PROVIDERS",
    "ModelPurpose",
    "ResolvedModelSpec",
    "SUPPORTED_PROVIDERS",
    "build_chat_backend",
    "get_chat_model",
    "normalize_provider_name",
    "resolve_chat_spec",
    "resolve_embedding_spec",
    "validate_ai_configuration",
]
