from __future__ import annotations

import json

import pytest

from app.core import client_config


@pytest.fixture(autouse=True)
def _clear_client_config_cache() -> None:
    client_config.clear_client_config_caches()
    yield
    client_config.clear_client_config_caches()


def test_load_json_config_reads_object_from_env_override(tmp_path, monkeypatch) -> None:
    config_root = tmp_path / "config"
    config_root.mkdir()
    (config_root / "client.json").write_text(
        json.dumps({"client_id": "gresham-house"}),
        encoding="utf-8",
    )
    monkeypatch.setenv("RESPONDAI_CONFIG_ROOT", str(config_root))

    payload = client_config.load_client_manifest(required=True)

    assert payload == {"client_id": "gresham-house"}


def test_load_json_config_returns_empty_dict_for_missing_optional(tmp_path, monkeypatch) -> None:
    config_root = tmp_path / "config"
    config_root.mkdir()
    monkeypatch.setenv("RESPONDAI_CONFIG_ROOT", str(config_root))

    payload = client_config.load_workspace_config()

    assert payload == {}


def test_load_json_config_raises_for_invalid_json(tmp_path, monkeypatch) -> None:
    config_root = tmp_path / "config"
    config_root.mkdir()
    (config_root / "branding.json").write_text("{not-json}", encoding="utf-8")
    monkeypatch.setenv("RESPONDAI_CONFIG_ROOT", str(config_root))

    with pytest.raises(RuntimeError, match="Invalid client config JSON"):
        client_config.load_branding_config(required=True)
