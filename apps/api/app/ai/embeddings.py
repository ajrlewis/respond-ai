"""Embedding model clients built on thin provider/model factory wiring."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
import logging
from time import perf_counter
from typing import Any

from app.ai.errors import AIConfigurationError, AIProviderError
from app.ai.factory import EMBEDDING_PROVIDERS, normalize_provider_name, resolve_embedding_spec
from app.ai.usage import estimate_texts_tokens, normalize_usage_payload
from app.core.config import settings
from app.services.observability import (
    LLMLogRecord,
    estimate_cost_usd,
    log_llm_call_async,
    log_llm_call_sync,
    sanitize_payload,
)

logger = logging.getLogger(__name__)


def _run_with_retry_sync(operation, *, provider: str) -> Any:
    max_retries = max(0, int(settings.ai_max_retries))
    attempt = 0
    while True:
        try:
            return operation()
        except AIConfigurationError:
            raise
        except Exception as exc:
            attempt += 1
            if attempt > max_retries:
                raise
            logger.warning(
                "Retrying sync embedding call provider=%s attempt=%d/%d error=%s",
                provider,
                attempt,
                max_retries,
                exc,
            )


async def _run_with_retry_async(operation, *, provider: str) -> Any:
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
                "Retrying async embedding call provider=%s attempt=%d/%d error=%s",
                provider,
                attempt,
                max_retries,
                exc,
            )


def _provider_api_key(provider: str) -> str:
    if provider == "openai":
        return settings.openai_api_key.strip()
    if provider == "google":
        return settings.google_api_key.strip()
    return ""


def _require_api_key(provider: str) -> str:
    key = _provider_api_key(provider)
    if key:
        return key
    setting = "OPENAI_API_KEY" if provider == "openai" else "GOOGLE_API_KEY"
    raise AIConfigurationError(f"{setting} is required when using provider={provider} for embeddings.")


def build_embedding_backend(*, provider: str, model: str) -> Any:
    """Instantiate LangChain embedding adapter for a provider/model."""

    normalized = normalize_provider_name(provider)
    if normalized not in EMBEDDING_PROVIDERS:
        raise AIConfigurationError(
            "Anthropic does not provide embeddings in this stack. Configure EMBEDDING_PROVIDER to openai or google."
        )

    if normalized == "openai":
        try:
            from langchain_openai import OpenAIEmbeddings
        except ImportError as exc:  # pragma: no cover - dependency guard
            raise AIConfigurationError(
                "langchain-openai is not installed. Add it to API dependencies to use OpenAI embeddings."
            ) from exc
        return OpenAIEmbeddings(model=model, api_key=_require_api_key("openai"))

    if normalized == "google":
        try:
            from langchain_google_genai import GoogleGenerativeAIEmbeddings
        except ImportError as exc:  # pragma: no cover - dependency guard
            raise AIConfigurationError(
                "langchain-google-genai is not installed. Add it to API dependencies to use Google embeddings."
            ) from exc
        return GoogleGenerativeAIEmbeddings(model=model, google_api_key=_require_api_key("google"))

    raise AIConfigurationError(
        f"Unsupported embedding provider '{normalized}'. Supported providers: {', '.join(sorted(EMBEDDING_PROVIDERS))}."
    )


@dataclass(slots=True)
class EmbeddingModelClient:
    """Configured embedding model client."""

    provider: str
    model: str

    def embed_text(
        self,
        text: str,
        *,
        purpose: str = "embedding",
        request_metadata: dict[str, Any] | None = None,
    ) -> list[float]:
        vectors = self.embed_texts([text], purpose=purpose, request_metadata=request_metadata)
        return vectors[0] if vectors else []

    def embed_texts(
        self,
        texts: list[str],
        *,
        purpose: str = "embedding",
        request_metadata: dict[str, Any] | None = None,
    ) -> list[list[float]]:
        if not texts:
            return []

        backend = build_embedding_backend(provider=self.provider, model=self.model)
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
            try:
                vectors = _run_with_retry_sync(lambda: backend.embed_documents(texts), provider=self.provider)
            except Exception as exc:
                raise AIProviderError(f"{self.provider} embeddings failed: {exc}") from exc

            usage = normalize_usage_payload(
                {},
                input_fallback_tokens=estimate_texts_tokens(texts),
                output_fallback_tokens=0,
            )
            input_tokens = usage.input_tokens
            output_tokens = usage.output_tokens
            total_tokens = usage.total_tokens
            normalized_input_tokens = usage.normalized_input_tokens
            normalized_output_tokens = usage.normalized_output_tokens
            response_payload = {
                "embedding_count": len(vectors),
                "vector_dimensions": len(vectors[0]) if vectors else 0,
            }
            return vectors
        except Exception as exc:
            status = "error"
            error_message = str(exc)
            raise
        finally:
            latency_ms = int((perf_counter() - started) * 1000)
            log_llm_call_sync(
                LLMLogRecord(
                    provider=self.provider,
                    model_name=self.model,
                    call_type="embedding",
                    purpose=purpose,
                    request_payload=sanitize_payload(
                        {
                            "input_count": len(texts),
                            "input_chars_total": sum(len(item) for item in texts),
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

    async def aembed_text(
        self,
        text: str,
        *,
        purpose: str = "embedding",
        request_metadata: dict[str, Any] | None = None,
    ) -> list[float]:
        vectors = await self.aembed_texts([text], purpose=purpose, request_metadata=request_metadata)
        return vectors[0] if vectors else []

    async def aembed_texts(
        self,
        texts: list[str],
        *,
        purpose: str = "embedding",
        request_metadata: dict[str, Any] | None = None,
    ) -> list[list[float]]:
        if not texts:
            return []

        backend = build_embedding_backend(provider=self.provider, model=self.model)
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
            async def _invoke() -> list[list[float]]:
                if hasattr(backend, "aembed_documents"):
                    return await backend.aembed_documents(texts)
                return await asyncio.to_thread(backend.embed_documents, texts)

            try:
                vectors = await _run_with_retry_async(_invoke, provider=self.provider)
            except Exception as exc:
                raise AIProviderError(f"{self.provider} async embeddings failed: {exc}") from exc

            usage = normalize_usage_payload(
                {},
                input_fallback_tokens=estimate_texts_tokens(texts),
                output_fallback_tokens=0,
            )
            input_tokens = usage.input_tokens
            output_tokens = usage.output_tokens
            total_tokens = usage.total_tokens
            normalized_input_tokens = usage.normalized_input_tokens
            normalized_output_tokens = usage.normalized_output_tokens
            response_payload = {
                "embedding_count": len(vectors),
                "vector_dimensions": len(vectors[0]) if vectors else 0,
            }
            return vectors
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
                    call_type="embedding",
                    purpose=purpose,
                    request_payload=sanitize_payload(
                        {
                            "input_count": len(texts),
                            "input_chars_total": sum(len(item) for item in texts),
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


def get_embedding_model() -> EmbeddingModelClient:
    """Get provider-agnostic embedding model client."""

    spec = resolve_embedding_spec()
    return EmbeddingModelClient(provider=spec.provider, model=spec.model)


__all__ = ["EmbeddingModelClient", "build_embedding_backend", "get_embedding_model"]
