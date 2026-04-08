"""Helpers for repo-level client deployment configuration under `config/`."""

from __future__ import annotations

import json
import os
from functools import lru_cache
from json import JSONDecodeError
from pathlib import Path
from typing import Any

_CONFIG_ROOT_ENV_VAR = "RESPONDAI_CONFIG_ROOT"


def _resolve_api_root() -> Path:
    """Return API app root directory (`<repo>/apps/api` or container `/app`)."""

    return Path(__file__).resolve().parents[2]


@lru_cache(maxsize=1)
def resolve_config_root() -> Path:
    """Locate repo-level config directory, supporting explicit env override."""

    override = os.getenv(_CONFIG_ROOT_ENV_VAR, "").strip()
    if override:
        return Path(override).expanduser().resolve()

    api_root = _resolve_api_root()
    candidates = [api_root]
    candidates.extend(list(api_root.parents)[:3])

    for base_path in candidates:
        candidate = (base_path / "config").resolve()
        if candidate.is_dir():
            return candidate

    return (api_root.parents[1] / "config").resolve()


def resolve_config_path(relative_path: str) -> Path:
    """Resolve a file path under repo-level `config/`."""

    normalized = relative_path.strip().lstrip("/")
    return resolve_config_root() / normalized


@lru_cache(maxsize=64)
def _load_json_object(relative_path: str) -> dict[str, Any]:
    path = resolve_config_path(relative_path)
    if not path.exists():
        raise RuntimeError(f"Client config not found: {relative_path}")

    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except JSONDecodeError as exc:
        raise RuntimeError(f"Invalid client config JSON: {relative_path}") from exc

    if not isinstance(payload, dict):
        raise RuntimeError(f"Client config must be a JSON object: {relative_path}")
    return payload


def load_json_config(relative_path: str, *, required: bool = False) -> dict[str, Any]:
    """Load one JSON object from `config/`, optionally requiring file presence."""

    normalized = relative_path if relative_path.endswith(".json") else f"{relative_path}.json"
    if not required and not resolve_config_path(normalized).exists():
        return {}
    return _load_json_object(normalized)


def load_client_manifest(*, required: bool = False) -> dict[str, Any]:
    """Load `config/client.json`."""

    return load_json_config("client.json", required=required)


def load_branding_config(*, required: bool = False) -> dict[str, Any]:
    """Load `config/branding.json`."""

    return load_json_config("branding.json", required=required)


def load_workspace_config(*, required: bool = False) -> dict[str, Any]:
    """Load `config/workspace.json`."""

    return load_json_config("workspace.json", required=required)


def load_retrieval_config(*, required: bool = False) -> dict[str, Any]:
    """Load `config/retrieval.json`."""

    return load_json_config("retrieval.json", required=required)


def clear_client_config_caches() -> None:
    """Clear module caches (useful in tests)."""

    resolve_config_root.cache_clear()
    _load_json_object.cache_clear()


__all__ = [
    "clear_client_config_caches",
    "load_branding_config",
    "load_client_manifest",
    "load_json_config",
    "load_retrieval_config",
    "load_workspace_config",
    "resolve_config_path",
    "resolve_config_root",
]
