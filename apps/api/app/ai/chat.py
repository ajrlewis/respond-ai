"""Provider-agnostic chat model clients with telemetry logging."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
import logging
from time import perf_counter
from typing import Any, Generic, TypeVar

from pydantic import BaseModel

from app.ai.factory import ModelPurpose, resolve_chat_spec
from app.ai.providers import AIConfigurationError, AIProviderError, StructuredCompletionResult
from app.ai.registry import get_provider_registry
from app.core.config import settings
from app.services.observability import (
    LLMLogRecord,
    estimate_cost_usd,
    log_llm_call_async,
    sanitize_payload,
)

logger = logging.getLogger(__name__)
StructuredOutputT = TypeVar("StructuredOutputT", bound=BaseModel)


async def _run_with_retry(
    operation,
    *,
    provider: str,
    purpose: str,
) -> Any:
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
            result = await _run_with_retry(
                lambda: provider_impl.acomplete(
                    model=self.model,
                    system_prompt=system_prompt,
                    user_prompt=user_prompt,
                    temperature=selected_temperature,
                ),
                provider=self.provider,
                purpose=self.purpose,
            )
            response_payload = result.response_payload
            input_tokens = result.usage.input_tokens
            output_tokens = result.usage.output_tokens
            total_tokens = result.usage.total_tokens
            normalized_input_tokens = result.usage.normalized_input_tokens
            normalized_output_tokens = result.usage.normalized_output_tokens
            raw_usage_payload = result.usage.raw_usage_payload
            return result.text
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


@dataclass(slots=True)
class StructuredModelClient(Generic[StructuredOutputT]):
    """Purpose-configured chat client returning structured Pydantic output."""

    purpose: ModelPurpose
    provider: str
    model: str
    schema: type[StructuredOutputT]

    async def ainvoke(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
        temperature: float | None = None,
        request_metadata: dict[str, Any] | None = None,
    ) -> StructuredOutputT:
        selected_temperature = float(settings.ai_temperature if temperature is None else temperature)
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
            result: StructuredCompletionResult[StructuredOutputT] = await _run_with_retry(
                lambda: provider_impl.acomplete_structured(
                    model=self.model,
                    system_prompt=system_prompt,
                    user_prompt=user_prompt,
                    response_schema=self.schema,
                    temperature=selected_temperature,
                ),
                provider=self.provider,
                purpose=self.purpose,
            )
            response_payload = result.response_payload
            input_tokens = result.usage.input_tokens
            output_tokens = result.usage.output_tokens
            total_tokens = result.usage.total_tokens
            normalized_input_tokens = result.usage.normalized_input_tokens
            normalized_output_tokens = result.usage.normalized_output_tokens
            raw_usage_payload = result.usage.raw_usage_payload
            return result.parsed
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
                    call_type="chat_completion_structured",
                    purpose=self.purpose,
                    request_payload=sanitize_payload(
                        {
                            "temperature": selected_temperature,
                            "response_format": self.schema.__name__,
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


def get_chat_model(*, purpose: ModelPurpose) -> ChatModelClient:
    """Get provider-agnostic plain-text chat model client for a purpose."""

    spec = resolve_chat_spec(purpose=purpose)
    return ChatModelClient(purpose=purpose, provider=spec.provider, model=spec.model)


def get_structured_model(
    *,
    schema: type[StructuredOutputT],
    purpose: ModelPurpose,
) -> StructuredModelClient[StructuredOutputT]:
    """Get provider-agnostic structured-output model client for a purpose."""

    spec = resolve_chat_spec(purpose=purpose)
    return StructuredModelClient(purpose=purpose, provider=spec.provider, model=spec.model, schema=schema)


__all__ = [
    "AIConfigurationError",
    "AIProviderError",
    "ChatModelClient",
    "StructuredModelClient",
    "get_chat_model",
    "get_structured_model",
]
