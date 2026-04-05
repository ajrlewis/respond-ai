"""Error types for AI configuration and provider invocation failures."""


class AIConfigurationError(RuntimeError):
    """Raised when provider/model configuration is invalid."""


class AIProviderError(RuntimeError):
    """Raised when provider invocation fails."""


__all__ = ["AIConfigurationError", "AIProviderError"]
