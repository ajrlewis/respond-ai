from app.core.config import Settings


def test_database_url_default_targets_localhost() -> None:
    settings = Settings(_env_file=None)

    assert settings.database_url == "postgresql+psycopg://respondai:respondai@localhost:5432/respondai"


def test_checkpoint_url_defaults_from_database_url() -> None:
    settings = Settings(
        _env_file=None,
        database_url="postgresql+psycopg://user:pass@localhost:5432/respondai",
    )

    assert settings.checkpoint_url == "postgresql://user:pass@localhost:5432/respondai"


def test_checkpoint_url_prefers_explicit_override() -> None:
    settings = Settings(
        _env_file=None,
        database_url="postgresql+psycopg://user:pass@localhost:5432/respondai",
        checkpoint_database_url="postgresql://other:pass@localhost:5432/respondai_checkpoint",
    )

    assert settings.checkpoint_url == "postgresql://other:pass@localhost:5432/respondai_checkpoint"


def test_logging_level_default_is_info() -> None:
    settings = Settings(_env_file=None)

    assert settings.logging_level == "INFO"


def test_default_ai_provider_settings() -> None:
    settings = Settings(_env_file=None)

    assert settings.ai_provider == "openai"
    assert settings.large_llm_model == "gpt-4o"
    assert settings.small_llm_model == "gpt-4o-mini"
    assert settings.embedding_model == "text-embedding-3-small"
