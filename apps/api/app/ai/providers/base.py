"""Provider interface contracts for AI model integrations."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Generic, TypeVar

from pydantic import BaseModel

StructuredOutputT = TypeVar("StructuredOutputT", bound=BaseModel)


class AIConfigurationError(RuntimeError):
    """Raised when provider/model configuration is invalid."""


class AIProviderError(RuntimeError):
    """Raised when provider invocation fails."""


@dataclass(slots=True)
class ProviderUsage:
    """Normalized usage shape across providers."""

    input_tokens: int = 0
    output_tokens: int = 0
    total_tokens: int = 0
    normalized_input_tokens: int = 0
    normalized_output_tokens: int = 0
    raw_usage_payload: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class ChatCompletionResult:
    """Plain-text completion payload with usage and provider metadata."""

    text: str
    usage: ProviderUsage
    response_payload: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class StructuredCompletionResult(Generic[StructuredOutputT]):
    """Structured completion payload with normalized usage."""

    parsed: StructuredOutputT
    usage: ProviderUsage
    response_payload: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class EmbeddingResult:
    """Embedding payload with usage metadata."""

    vectors: list[list[float]]
    usage: ProviderUsage
    response_payload: dict[str, Any] = field(default_factory=dict)


class AIProvider(ABC):
    """Interface every provider implementation must satisfy."""

    name: str

    @abstractmethod
    async def acomplete(
        self,
        *,
        model: str,
        system_prompt: str,
        user_prompt: str,
        temperature: float,
    ) -> ChatCompletionResult:
        """Generate a plain-text completion."""

    @abstractmethod
    async def acomplete_structured(
        self,
        *,
        model: str,
        system_prompt: str,
        user_prompt: str,
        response_schema: type[StructuredOutputT],
        temperature: float,
    ) -> StructuredCompletionResult[StructuredOutputT]:
        """Generate a structured completion."""

    @abstractmethod
    def embed_texts(
        self,
        *,
        model: str,
        texts: list[str],
    ) -> EmbeddingResult:
        """Synchronously embed multiple input texts."""

    @abstractmethod
    async def aembed_texts(
        self,
        *,
        model: str,
        texts: list[str],
    ) -> EmbeddingResult:
        """Asynchronously embed multiple input texts."""
