"""Structured-output model helpers built on LangChain chat models."""

from __future__ import annotations

import asyncio
from collections.abc import Mapping
from dataclasses import dataclass
import logging
from time import perf_counter
from typing import Any, Generic, TypeVar

from pydantic import BaseModel

from app.ai.errors import AIConfigurationError, AIProviderError
from app.ai.factory import ModelPurpose, build_chat_backend, resolve_chat_spec
from app.ai.usage import estimate_text_tokens, extract_usage_payload, normalize_usage_payload
from app.core.config import settings
from app.services.observability import (
    LLMLogRecord,
    estimate_cost_usd,
    log_llm_call_async,
    sanitize_payload,
)

StructuredOutputT = TypeVar("StructuredOutputT", bound=BaseModel)
logger = logging.getLogger(__name__)


def _build_messages(*, system_prompt: str, user_prompt: str) -> list[Any]:
    from langchain_core.messages import HumanMessage, SystemMessage

    return [SystemMessage(content=system_prompt), HumanMessage(content=user_prompt)]


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
                "Retrying structured AI call provider=%s purpose=%s attempt=%d/%d error=%s",
                provider,
                purpose,
                attempt,
                max_retries,
                exc,
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
            chat = build_chat_backend(provider=self.provider, model=self.model, temperature=selected_temperature)
            messages = _build_messages(system_prompt=system_prompt, user_prompt=user_prompt)

            parsed: BaseModel | dict | Any
            raw_message: Any = None
            output = await _run_with_retry(
                lambda: _invoke_structured_output(chat=chat, schema=self.schema, messages=messages),
                provider=self.provider,
                purpose=self.purpose,
            )

            if isinstance(output, Mapping) and "parsed" in output:
                parsed = output.get("parsed")
                raw_message = output.get("raw")
            else:
                parsed = output

            if parsed is None:
                raise AIProviderError(
                    f"{self.provider} structured completion returned no parsed payload for {self.schema.__name__}."
                )

            if isinstance(parsed, self.schema):
                parsed_model = parsed
            else:
                parsed_model = self.schema.model_validate(parsed)

            raw_usage_payload = extract_usage_payload(raw_message or parsed_model)
            usage = normalize_usage_payload(
                raw_usage_payload,
                input_fallback_tokens=estimate_text_tokens(system_prompt) + estimate_text_tokens(user_prompt),
            )
            input_tokens = usage.input_tokens
            output_tokens = usage.output_tokens
            total_tokens = usage.total_tokens
            normalized_input_tokens = usage.normalized_input_tokens
            normalized_output_tokens = usage.normalized_output_tokens
            response_payload = {
                "parsed": parsed_model.model_dump(),
                "raw_response_metadata": dict(getattr(raw_message, "response_metadata", {}) or {}),
            }
            return parsed_model
        except Exception as exc:
            status = "error"
            error_message = str(exc)
            if isinstance(exc, AIConfigurationError):
                raise
            if isinstance(exc, AIProviderError):
                raise
            raise AIProviderError(f"{self.provider} structured completion failed: {exc}") from exc
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


async def _invoke_structured_output(*, chat: Any, schema: type[StructuredOutputT], messages: list[Any]) -> Any:
    try:
        structured = chat.with_structured_output(schema, include_raw=True)
        return await structured.ainvoke(messages)
    except TypeError:
        structured = chat.with_structured_output(schema)
        return await structured.ainvoke(messages)


def get_structured_model(
    *,
    schema: type[StructuredOutputT],
    purpose: ModelPurpose,
) -> StructuredModelClient[StructuredOutputT]:
    """Get structured-output chat model client for a call purpose."""

    spec = resolve_chat_spec(purpose=purpose)
    return StructuredModelClient(purpose=purpose, provider=spec.provider, model=spec.model, schema=schema)


__all__ = ["StructuredModelClient", "get_structured_model"]
