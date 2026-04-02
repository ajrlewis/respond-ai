"""Provider-agnostic embedding model clients with telemetry logging."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
import logging
from time import perf_counter
from typing import Any

from app.ai.factory import resolve_embedding_spec
from app.ai.providers import AIConfigurationError
from app.ai.registry import get_provider_registry
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
        except Exception:
            attempt += 1
            if attempt > max_retries:
                raise
            logger.warning("Retrying sync embedding call provider=%s attempt=%d/%d", provider, attempt, max_retries)


async def _run_with_retry_async(operation, *, provider: str) -> Any:
    max_retries = max(0, int(settings.ai_max_retries))
    timeout_seconds = max(1, int(settings.ai_timeout_seconds))
    attempt = 0
    while True:
        try:
            return await asyncio.wait_for(operation(), timeout=timeout_seconds)
        except AIConfigurationError:
            raise
        except Exception:
            attempt += 1
            if attempt > max_retries:
                raise
            logger.warning("Retrying async embedding call provider=%s attempt=%d/%d", provider, attempt, max_retries)


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

        provider_impl = get_provider_registry().get(self.provider)
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
            result = _run_with_retry_sync(
                lambda: provider_impl.embed_texts(model=self.model, texts=texts),
                provider=self.provider,
            )
            response_payload = result.response_payload
            input_tokens = result.usage.input_tokens
            output_tokens = result.usage.output_tokens
            total_tokens = result.usage.total_tokens
            normalized_input_tokens = result.usage.normalized_input_tokens
            normalized_output_tokens = result.usage.normalized_output_tokens
            raw_usage_payload = result.usage.raw_usage_payload
            return result.vectors
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

        provider_impl = get_provider_registry().get(self.provider)
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
            result = await _run_with_retry_async(
                lambda: provider_impl.aembed_texts(model=self.model, texts=texts),
                provider=self.provider,
            )
            response_payload = result.response_payload
            input_tokens = result.usage.input_tokens
            output_tokens = result.usage.output_tokens
            total_tokens = result.usage.total_tokens
            normalized_input_tokens = result.usage.normalized_input_tokens
            normalized_output_tokens = result.usage.normalized_output_tokens
            raw_usage_payload = result.usage.raw_usage_payload
            return result.vectors
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


__all__ = ["EmbeddingModelClient", "get_embedding_model"]
