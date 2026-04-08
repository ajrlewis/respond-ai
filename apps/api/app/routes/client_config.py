"""Routes exposing client deployment config to frontend clients."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter

from app.core.client_config import load_branding_config, load_client_manifest, load_workspace_config
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
    logo_src = (
        _read_optional_string(branding_payload, "logo_src")
        or _read_optional_string(branding_payload, "logo_url")
        or _read_optional_string(branding_payload, "logo_path")
    )
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
