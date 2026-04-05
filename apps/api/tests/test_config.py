from app.core.config import Settings


def test_database_url_default_targets_localhost() -> None:
    settings = Settings(_env_file=None)

    assert settings.database_url == "postgresql+psycopg://respondai:respondai@localhost:5432/respondai"


def test_redis_and_celery_urls_default_to_localhost() -> None:
    settings = Settings(_env_file=None)

    assert settings.app_redis_url == "redis://localhost:6379/0"
    assert settings.app_celery_broker_url == "redis://localhost:6379/1"
    assert settings.app_celery_result_backend == "redis://localhost:6379/2"


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


def test_demo_auth_defaults() -> None:
    settings = Settings(_env_file=None)

    assert settings.app_demo_username == "admin"
    assert settings.app_demo_password == "admin1234"
    assert settings.app_session_secret == "respondai-demo-session-secret"
    assert settings.app_web_origin == "http://localhost:3000"
