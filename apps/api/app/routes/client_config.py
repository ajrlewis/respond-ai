"""Routes exposing client deployment config to frontend clients."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse

from app.core.client_config import (
    load_branding_config,
    load_client_manifest,
    load_workspace_config,
    resolve_config_path,
)
from app.schemas.client_config import ClientManifestOut, WorkspaceBrandingOut, WorkspaceClientConfigOut

router = APIRouter(prefix="/api/client-config", tags=["client-config"])

_DEFAULT_COMPANY_NAME = "Acme Capital"
_DEFAULT_WORKSPACE_TITLE = "Response Workspace"
_DEFAULT_WORKSPACE_SUBTITLE = "Document review workflow for submission responses."
_DEFAULT_START_TITLE = "Submission Workspace"
_DEFAULT_START_SUBTITLE = "Upload a questionnaire or start from example questions to generate a draft response."


def _read_string(payload: dict[str, Any], key: str, default: str) -> str:
    value = payload.get(key)
    if not isinstance(value, str):
        return default
    candidate = value.strip()
    return candidate or default


def _read_optional_string(payload: dict[str, Any], key: str) -> str | None:
    value = payload.get(key)
    if not isinstance(value, str):
        return None
    candidate = value.strip()
    return candidate or None


def _read_string_list(payload: dict[str, Any], key: str) -> list[str]:
    raw = payload.get(key)
    if not isinstance(raw, list):
        return []
    values: list[str] = []
    for item in raw:
        if not isinstance(item, str):
            continue
        candidate = item.strip()
        if candidate:
            values.append(candidate)
    return values


def _normalize_logo_src(value: str | None) -> str | None:
    if value is None:
        return None

    candidate = value.strip()
    if not candidate:
        return None
    if candidate.startswith(("http://", "https://", "/")):
        return candidate

    if candidate.startswith("config/assets/"):
        rel_path = candidate.removeprefix("config/assets/").strip("/")
    elif candidate.startswith("assets/"):
        rel_path = candidate.removeprefix("assets/").strip("/")
    else:
        rel_path = Path(candidate).name

    if not rel_path:
        return None
    return f"/api/client-config/assets/{rel_path}"


@router.get("/assets/{asset_path:path}")
async def get_client_config_asset(asset_path: str) -> FileResponse:
    """Serve client asset files from repo-level `config/assets`."""

    safe_rel = asset_path.strip().lstrip("/")
    assets_root = resolve_config_path("assets").resolve()
    target = (assets_root / safe_rel).resolve()
    try:
        target.relative_to(assets_root)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail="Client asset not found.") from exc

    if not target.exists() or not target.is_file():
        raise HTTPException(status_code=404, detail="Client asset not found.")
    return FileResponse(target)


@router.get("/workspace", response_model=WorkspaceClientConfigOut)
async def get_workspace_client_config() -> WorkspaceClientConfigOut:
    """Expose client, branding, and workspace config for frontend initialization."""

    client_payload = load_client_manifest(required=False)
    branding_payload = load_branding_config(required=False)
    workspace_payload = load_workspace_config(required=False)

    client = ClientManifestOut(
        client_id=_read_string(client_payload, "client_id", "default"),
        display_name=_read_string(client_payload, "display_name", _DEFAULT_COMPANY_NAME),
        environment_label=_read_string(client_payload, "environment_label", "development"),
        enabled_features=_read_string_list(client_payload, "enabled_features"),
    )

    company_name = _read_string(branding_payload, "company_name", client.display_name)
    logo_src_raw = (
        _read_optional_string(branding_payload, "logo_src")
        or _read_optional_string(branding_payload, "logo_url")
        or _read_optional_string(branding_payload, "logo_path")
    )
    logo_src = _normalize_logo_src(logo_src_raw)
    branding = WorkspaceBrandingOut(
        company_name=company_name,
        logo_src=logo_src,
        workspace_title=_read_string(branding_payload, "workspace_title", _DEFAULT_WORKSPACE_TITLE),
        workspace_subtitle=_read_string(branding_payload, "workspace_subtitle", _DEFAULT_WORKSPACE_SUBTITLE),
        start_title=_read_string(branding_payload, "start_title", _DEFAULT_START_TITLE),
        start_subtitle=_read_string(branding_payload, "start_subtitle", _DEFAULT_START_SUBTITLE),
    )

    return WorkspaceClientConfigOut(
        client=client,
        branding=branding,
        workspace=workspace_payload if isinstance(workspace_payload, dict) else {},
    )
