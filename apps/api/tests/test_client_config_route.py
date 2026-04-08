import asyncio
from pathlib import Path

from fastapi import HTTPException
from app.routes import client_config as client_config_route


def test_workspace_config_route_reads_client_and_branding_payload(monkeypatch) -> None:
    monkeypatch.setattr(
        client_config_route,
        "load_client_manifest",
        lambda required=False: {
            "client_id": "gresham-house",
            "display_name": "Gresham House",
            "environment_label": "production",
            "enabled_features": ["response_documents", "review_workspace_v2"],
        },
    )
    monkeypatch.setattr(
        client_config_route,
        "load_branding_config",
        lambda required=False: {
            "company_name": "Gresham House",
            "workspace_title": "Gresham House Response Workspace",
            "workspace_subtitle": "Evidence-grounded drafting.",
            "start_title": "Submission Workspace",
            "start_subtitle": "Upload or use examples.",
            "logo_path": "config/assets/logo.jpeg",
        },
    )
    monkeypatch.setattr(
        client_config_route,
        "load_workspace_config",
        lambda required=False: {"ui_flags": {"show_example_questions": True}},
    )

    payload = asyncio.run(client_config_route.get_workspace_client_config())

    assert payload.client.client_id == "gresham-house"
    assert payload.client.display_name == "Gresham House"
    assert payload.client.enabled_features == ["response_documents", "review_workspace_v2"]
    assert payload.branding.company_name == "Gresham House"
    assert payload.branding.logo_src == "/api/client-config/assets/logo.jpeg"
    assert payload.workspace == {"ui_flags": {"show_example_questions": True}}


def test_workspace_config_route_uses_defaults_for_missing_values(monkeypatch) -> None:
    monkeypatch.setattr(client_config_route, "load_client_manifest", lambda required=False: {})
    monkeypatch.setattr(client_config_route, "load_branding_config", lambda required=False: {})
    monkeypatch.setattr(client_config_route, "load_workspace_config", lambda required=False: {})

    payload = asyncio.run(client_config_route.get_workspace_client_config())

    assert payload.client.client_id == "default"
    assert payload.client.display_name == "Acme Capital"
    assert payload.client.environment_label == "development"
    assert payload.branding.company_name == "Acme Capital"
    assert payload.branding.workspace_title == "Response Workspace"
    assert payload.branding.start_title == "Submission Workspace"
    assert payload.workspace == {}


def test_workspace_config_route_passes_through_remote_logo_url(monkeypatch) -> None:
    monkeypatch.setattr(client_config_route, "load_client_manifest", lambda required=False: {})
    monkeypatch.setattr(
        client_config_route,
        "load_branding_config",
        lambda required=False: {"logo_url": "https://example.com/logo.png"},
    )
    monkeypatch.setattr(client_config_route, "load_workspace_config", lambda required=False: {})

    payload = asyncio.run(client_config_route.get_workspace_client_config())

    assert payload.branding.logo_src == "https://example.com/logo.png"


def test_get_client_config_asset_returns_file_response(tmp_path, monkeypatch) -> None:
    assets_dir = tmp_path / "config" / "assets"
    assets_dir.mkdir(parents=True)
    logo_path = assets_dir / "logo.jpeg"
    logo_path.write_bytes(b"fake-logo")
    monkeypatch.setattr(client_config_route, "resolve_config_path", lambda relative_path: assets_dir)

    response = asyncio.run(client_config_route.get_client_config_asset("logo.jpeg"))

    assert Path(response.path) == logo_path


def test_get_client_config_asset_blocks_traversal(tmp_path, monkeypatch) -> None:
    assets_dir = tmp_path / "config" / "assets"
    assets_dir.mkdir(parents=True)
    monkeypatch.setattr(client_config_route, "resolve_config_path", lambda relative_path: assets_dir)

    try:
        asyncio.run(client_config_route.get_client_config_asset("../secret.txt"))
        raise AssertionError("Expected HTTPException for path traversal.")
    except HTTPException as exc:
        assert exc.status_code == 404
