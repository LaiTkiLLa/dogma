"""CORS configuration tests."""

from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app


def test_cors_origin_list_parses_comma_separated() -> None:
    settings = Settings(cors_origins="http://a.com, http://b.com ,https://c.com")
    assert settings.cors_origin_list == [
        "http://a.com",
        "http://b.com",
        "https://c.com",
    ]


def test_cors_allows_configured_origin() -> None:
    origin = "http://localhost:5173"
    client = TestClient(create_app(Settings(cors_origins=origin)))

    response = client.options(
        "/health",
        headers={
            "Origin": origin,
            "Access-Control-Request-Method": "GET",
        },
    )

    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == origin
    assert response.headers["access-control-allow-credentials"] == "true"


def test_cors_disabled_when_origins_empty() -> None:
    client = TestClient(create_app(Settings(cors_origins="")))

    response = client.get(
        "/health",
        headers={"Origin": "http://localhost:5173"},
    )

    assert response.status_code == 200
    assert "access-control-allow-origin" not in response.headers
