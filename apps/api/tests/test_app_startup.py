from fastapi import FastAPI

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
    assert "/api/questions/{session_id}/drafts" in route_paths
    assert "/api/questions/{session_id}/drafts/{draft_id}" in route_paths
    assert "/api/questions/{session_id}/drafts/compare" in route_paths
    assert "/api/documents" in route_paths
    assert "/api/evals/run" in route_paths
    assert "/api/evals/runs" in route_paths
    assert "/api/evals/runs/{run_id}" in route_paths
