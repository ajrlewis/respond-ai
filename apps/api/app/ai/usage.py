"""Provider-agnostic usage extraction and normalization helpers."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from app.ai.providers.base import ProviderUsage


def estimate_text_tokens(text: str) -> int:
    """Best-effort token estimate used when providers omit usage metadata."""

    if not text:
        return 0
    return max(1, len(text) // 4)


def estimate_texts_tokens(texts: list[str]) -> int:
    """Best-effort aggregate token estimate for multiple texts."""

    return sum(estimate_text_tokens(text) for text in texts)


def extract_usage_payload(payload: Any) -> dict[str, Any]:
    """Extract the most useful usage block from provider/langchain payloads."""

    if payload is None:
        return {}

    if isinstance(payload, Mapping):
        usage = payload.get("usage")
        if isinstance(usage, Mapping):
            return dict(usage)
        token_usage = payload.get("token_usage")
        if isinstance(token_usage, Mapping):
            return dict(token_usage)
        usage_metadata = payload.get("usage_metadata")
        if isinstance(usage_metadata, Mapping):
            return dict(usage_metadata)
        return dict(payload)

    usage_metadata = getattr(payload, "usage_metadata", None)
    if isinstance(usage_metadata, Mapping):
        return dict(usage_metadata)

    response_metadata = getattr(payload, "response_metadata", None)
    if isinstance(response_metadata, Mapping):
        response_dict = dict(response_metadata)
        usage = response_dict.get("usage")
        if isinstance(usage, Mapping):
            return dict(usage)
        token_usage = response_dict.get("token_usage")
        if isinstance(token_usage, Mapping):
            return dict(token_usage)
        prompt_feedback = response_dict.get("prompt_feedback")
        if isinstance(prompt_feedback, Mapping):
            response_dict["prompt_feedback"] = dict(prompt_feedback)
        return response_dict

    usage = getattr(payload, "usage", None)
    if isinstance(usage, Mapping):
        return dict(usage)

    return {}


def _as_int(value: Any) -> int | None:
    if value is None:
        return None
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, (int, float)):
        return int(value)
    if isinstance(value, str):
        stripped = value.strip()
        if stripped.isdigit():
            return int(stripped)
    return None


def _first_int(payload: Mapping[str, Any], keys: list[str]) -> int | None:
    for key in keys:
        if key in payload:
            parsed = _as_int(payload.get(key))
            if parsed is not None:
                return parsed
    return None


def normalize_usage_payload(
    raw_usage: dict[str, Any] | None,
    *,
    input_fallback_tokens: int = 0,
    output_fallback_tokens: int = 0,
) -> ProviderUsage:
    """Normalize usage fields across OpenAI/Anthropic/Google payload variants."""

    payload = dict(raw_usage or {})
    usage_like: Mapping[str, Any] = payload
    nested = payload.get("usage")
    if isinstance(nested, Mapping):
        usage_like = nested

    input_tokens = _first_int(
        usage_like,
        [
            "prompt_tokens",
            "input_tokens",
            "prompt_token_count",
            "input_token_count",
            "promptTokens",
        ],
    )
    output_tokens = _first_int(
        usage_like,
        [
            "completion_tokens",
            "output_tokens",
            "candidates_token_count",
            "output_token_count",
            "completionTokens",
        ],
    )
    total_tokens = _first_int(
        usage_like,
        [
            "total_tokens",
            "total_token_count",
            "totalTokens",
        ],
    )

    normalized_input = input_tokens if input_tokens is not None else max(0, int(input_fallback_tokens))
    normalized_output = output_tokens if output_tokens is not None else max(0, int(output_fallback_tokens))

    if total_tokens is None:
        total_tokens = normalized_input + normalized_output

    return ProviderUsage(
        input_tokens=max(0, int(input_tokens or 0)),
        output_tokens=max(0, int(output_tokens or 0)),
        total_tokens=max(0, int(total_tokens or 0)),
        normalized_input_tokens=max(0, int(normalized_input)),
        normalized_output_tokens=max(0, int(normalized_output)),
        raw_usage_payload=payload,
    )
