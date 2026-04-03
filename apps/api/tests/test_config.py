from app.core.config import Settings


def test_database_url_default_targets_localhost() -> None:
    settings = Settings(_env_file=None)

    assert settings.database_url == "postgresql+psycopg://respondai:respondai@localhost:5432/respondai"


def test_settings_use_single_database_url_field() -> None:
    settings = Settings(
        _env_file=None,
        database_url="postgresql+psycopg://user:pass@localhost:5432/respondai",
    )
    dumped = settings.model_dump()
    assert dumped["database_url"] == "postgresql+psycopg://user:pass@localhost:5432/respondai"


def test_logging_level_default_is_info() -> None:
    settings = Settings(_env_file=None)

    assert settings.logging_level == "INFO"


def test_default_ai_provider_settings() -> None:
    settings = Settings(_env_file=None)

    assert settings.ai_provider == "openai"
    assert settings.large_llm_model == "gpt-4o"
    assert settings.small_llm_model == "gpt-4o-mini"
    assert settings.embedding_model == "text-embedding-3-small"
