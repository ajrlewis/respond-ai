import pytest

from app.ai.factory import resolve_chat_spec, resolve_embedding_spec, validate_ai_configuration
from app.ai.errors import AIConfigurationError
from app.core.config import Settings


def test_resolve_specs_use_default_provider_when_specific_overrides_missing(monkeypatch) -> None:
    monkeypatch.setattr(
        "app.ai.factory.settings",
        Settings(
            _env_file=None,
            ai_provider="openai",
            openai_api_key="test-key",
            large_llm_model="gpt-4o",
            small_llm_model="gpt-4o-mini",
            embedding_model="text-embedding-3-small",
        ),
    )

    classification = resolve_chat_spec(purpose="classification")
    drafting = resolve_chat_spec(purpose="drafting")
    embedding = resolve_embedding_spec()

    assert classification.provider == "openai"
    assert classification.model == "gpt-4o-mini"
    assert drafting.provider == "openai"
    assert drafting.model == "gpt-4o"
    assert embedding.provider == "openai"


def test_resolve_specs_support_mixed_providers(monkeypatch) -> None:
    monkeypatch.setattr(
        "app.ai.factory.settings",
        Settings(
            _env_file=None,
            ai_provider="openai",
            openai_api_key="openai-key",
            anthropic_api_key="anthropic-key",
            google_api_key="google-key",
            large_llm_provider="anthropic",
            large_llm_model="claude-3-5-sonnet-latest",
            small_llm_provider="openai",
            small_llm_model="gpt-4o-mini",
            embedding_provider="google",
            embedding_model="models/text-embedding-004",
        ),
    )

    drafting = resolve_chat_spec(purpose="drafting")
    classification = resolve_chat_spec(purpose="classification")
    embedding = resolve_embedding_spec()

    assert drafting.provider == "anthropic"
    assert drafting.model == "claude-3-5-sonnet-latest"
    assert classification.provider == "openai"
    assert embedding.provider == "google"


def test_validate_ai_configuration_requires_provider_keys(monkeypatch) -> None:
    monkeypatch.setattr(
        "app.ai.factory.settings",
        Settings(
            _env_file=None,
            ai_provider="openai",
            openai_api_key="",
            large_llm_model="gpt-4o",
            small_llm_model="gpt-4o-mini",
            embedding_model="text-embedding-3-small",
        ),
    )

    with pytest.raises(AIConfigurationError):
        validate_ai_configuration()
