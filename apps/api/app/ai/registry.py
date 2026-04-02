"""Provider registry and lazy provider initialization."""

from __future__ import annotations

from dataclasses import dataclass, field

from app.ai.providers import (
    AIConfigurationError,
    AIProvider,
    AnthropicProvider,
    GoogleProvider,
    OpenAIProvider,
)
from app.core.config import settings

SUPPORTED_PROVIDERS = {"openai", "anthropic", "google"}


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


@dataclass(slots=True)
class ProviderRegistry:
    """In-memory provider instance cache."""

    _cache: dict[str, AIProvider] = field(default_factory=dict)

    def get(self, provider_name: str) -> AIProvider:
        """Return initialized provider instance for a provider name."""

        normalized = normalize_provider_name(provider_name)
        existing = self._cache.get(normalized)
        if existing is not None:
            return existing

        provider = self._build_provider(normalized)
        self._cache[normalized] = provider
        return provider

    def _build_provider(self, provider_name: str) -> AIProvider:
        if provider_name == "openai":
            return OpenAIProvider(api_key=settings.openai_api_key)
        if provider_name == "anthropic":
            return AnthropicProvider(api_key=settings.anthropic_api_key)
        if provider_name == "google":
            return GoogleProvider(api_key=settings.google_api_key)
        raise AIConfigurationError(
            f"Unsupported AI provider '{provider_name}'. Supported providers: {', '.join(sorted(SUPPORTED_PROVIDERS))}."
        )


_PROVIDER_REGISTRY = ProviderRegistry()


def get_provider_registry() -> ProviderRegistry:
    """Return singleton provider registry."""

    return _PROVIDER_REGISTRY
