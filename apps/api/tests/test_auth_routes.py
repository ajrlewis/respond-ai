from fastapi.testclient import TestClient

from app.core.config import settings
from app.main import create_app


def _client() -> TestClient:
    app = create_app(register_startup=False)
    return TestClient(app)


def test_login_success_sets_session_cookie() -> None:
    with _client() as client:
        response = client.post(
            "/auth/login",
            json={"username": settings.app_demo_username, "password": settings.app_demo_password},
        )

    assert response.status_code == 200
    payload = response.json()
    assert payload["authenticated"] is True
    assert payload["user"]["username"] == settings.app_demo_username
    cookie_header = response.headers.get("set-cookie", "").lower()
    assert "httponly" in cookie_header
    assert "samesite=lax" in cookie_header


def test_login_failure_returns_401() -> None:
    with _client() as client:
        response = client.post("/auth/login", json={"username": "wrong", "password": "wrong"})

    assert response.status_code == 401
    assert response.json()["detail"] == "Invalid username or password."


def test_auth_me_returns_user_when_authenticated() -> None:
    with _client() as client:
        login_response = client.post(
            "/auth/login",
            json={"username": settings.app_demo_username, "password": settings.app_demo_password},
        )
        assert login_response.status_code == 200

        response = client.get("/auth/me")

    assert response.status_code == 200
    assert response.json()["authenticated"] is True
    assert response.json()["user"]["username"] == settings.app_demo_username


def test_auth_me_returns_401_when_unauthenticated() -> None:
    with _client() as client:
        response = client.get("/auth/me")

    assert response.status_code == 401
    assert response.json()["detail"] == "Authentication required."


def test_protected_route_rejects_unauthenticated_request() -> None:
    with _client() as client:
        response = client.get("/api/documents")

    assert response.status_code == 401
    assert response.json()["detail"] == "Authentication required."


def test_logout_invalidates_session() -> None:
    with _client() as client:
        login_response = client.post(
            "/auth/login",
            json={"username": settings.app_demo_username, "password": settings.app_demo_password},
        )
        assert login_response.status_code == 200
        assert client.get("/auth/me").status_code == 200

        logout_response = client.post("/auth/logout")
        assert logout_response.status_code == 200

        me_after_logout = client.get("/auth/me")

    assert me_after_logout.status_code == 401
    assert me_after_logout.json()["detail"] == "Authentication required."


def test_cors_allows_only_configured_origin_and_never_wildcard() -> None:
    configured_origin = settings.app_web_origin.split(",")[0].strip() or "http://localhost:3000"

    with _client() as client:
        allowed = client.options(
            "/auth/login",
            headers={
                "Origin": configured_origin,
                "Access-Control-Request-Method": "POST",
            },
        )
        blocked = client.options(
            "/auth/login",
            headers={
                "Origin": "http://not-allowed-origin.local",
                "Access-Control-Request-Method": "POST",
            },
        )

    assert allowed.status_code in {200, 204}
    assert allowed.headers.get("access-control-allow-origin") == configured_origin
    assert allowed.headers.get("access-control-allow-credentials") == "true"
    assert allowed.headers.get("access-control-allow-origin") != "*"
    assert blocked.headers.get("access-control-allow-origin") is None
