"""Schemas for client deployment configuration payloads."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class ClientManifestOut(BaseModel):
    """Public subset of client manifest information."""

    client_id: str
    display_name: str
    environment_label: str
    enabled_features: list[str] = Field(default_factory=list)


class WorkspaceBrandingOut(BaseModel):
    """Workspace branding values consumed by the web app."""

    company_name: str
    logo_src: str | None = None
    workspace_title: str
    workspace_subtitle: str
    start_title: str
    start_subtitle: str


class WorkspaceClientConfigOut(BaseModel):
    """Combined client + branding + workspace settings payload."""

    client: ClientManifestOut
    branding: WorkspaceBrandingOut
    workspace: dict[str, Any] = Field(default_factory=dict)
