from pathlib import Path


def test_async_session_factory_disables_expire_on_commit() -> None:
    database_module = Path(__file__).resolve().parents[1] / "app" / "core" / "database.py"
    source = database_module.read_text()
    assert "expire_on_commit=False" in source
