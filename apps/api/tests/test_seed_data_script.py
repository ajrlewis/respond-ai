from __future__ import annotations

from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path

import pytest


def _load_seed_data_module():
    script_path = Path(__file__).resolve().parents[1] / "scripts" / "seed_data.py"
    spec = spec_from_file_location("seed_data_script_for_tests", script_path)
    if spec is None or spec.loader is None:
        raise RuntimeError("Unable to load seed_data.py module for tests.")
    module = module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_resolve_docs_dir_uses_config_documents_data(tmp_path, monkeypatch) -> None:
    seed_data = _load_seed_data_module()
    docs_dir = tmp_path / "config" / "documents" / "data"
    docs_dir.mkdir(parents=True)

    monkeypatch.setattr(seed_data, "resolve_config_path", lambda relative_path: docs_dir)

    assert seed_data._resolve_docs_dir() == docs_dir


def test_resolve_docs_dir_raises_when_config_documents_data_missing(tmp_path, monkeypatch) -> None:
    seed_data = _load_seed_data_module()
    missing_docs_dir = tmp_path / "config" / "documents" / "data"

    monkeypatch.setattr(seed_data, "resolve_config_path", lambda relative_path: missing_docs_dir)

    with pytest.raises(FileNotFoundError, match="config/documents/data"):
        seed_data._resolve_docs_dir()
