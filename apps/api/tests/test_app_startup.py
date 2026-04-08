from fastapi import FastAPI
from fastapi.testclient import TestClient

import app.main as main_module
from app.main import app


def test_main_app_imports_and_registers_core_routes() -> None:
    assert isinstance(app, FastAPI)
    route_paths = {route.path for route in app.routes}
    assert "/health" in route_paths
    assert "/auth/login" in route_paths
    assert "/auth/logout" in route_paths
    assert "/auth/me" in route_paths
    assert "/api/questions/ask" in route_paths
    assert "/api/questions/{session_id}/review" in route_paths
    assert "/api/questions/{session_id}/events" in route_paths
    assert "/api/questions/thread/{thread_id}/events" in route_paths
    assert "/api/questions/{session_id}/drafts" in route_paths
    assert "/api/questions/{session_id}/drafts/{draft_id}" in route_paths
    assert "/api/questions/{session_id}/drafts/compare" in route_paths
    assert "/api/documents" in route_paths
    assert "/api/response-documents" in route_paths
    assert "/api/response-documents/sample" in route_paths
    assert "/api/response-documents/{document_id}/events" in route_paths
    assert "/api/response-documents/{document_id}/generate" in route_paths
    assert "/api/response-documents/{document_id}/versions" in route_paths
    assert "/api/response-documents/{document_id}/versions/{version_id}/approve" in route_paths
    assert "/api/response-documents/{document_id}/versions/{version_id}" in route_paths
    assert "/api/response-documents/{document_id}/compare" in route_paths
    assert "/api/response-documents/{document_id}/ai-revise" in route_paths
    assert "/api/evals/run" in route_paths
    assert "/api/evals/runs" in route_paths
    assert "/api/evals/runs/{run_id}" in route_paths


def test_startup_validates_schema_revision(monkeypatch) -> None:
    calls: list[str] = []

    def fake_validate_ai_configuration() -> None:
        calls.append("validate_ai_configuration")

    async def fake_assert_schema_current_async() -> None:
        calls.append("assert_schema_current_async")

    class FakeEventBus:
        async def close(self) -> None:
            calls.append("workflow_event_bus.close")

    monkeypatch.setattr(main_module, "validate_ai_configuration", fake_validate_ai_configuration)
    monkeypatch.setattr(main_module, "assert_schema_current_async", fake_assert_schema_current_async)
    monkeypatch.setattr(main_module, "workflow_event_bus", FakeEventBus())

    with TestClient(main_module.create_app(register_startup=True)) as client:
        health_response = client.get("/health")
        assert health_response.status_code == 200

    assert "validate_ai_configuration" in calls
    assert "assert_schema_current_async" in calls
    assert "workflow_event_bus.close" in calls
