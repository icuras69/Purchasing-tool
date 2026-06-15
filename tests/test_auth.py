from datetime import UTC, datetime, timedelta

import jwt
import pytest
from pydantic import ValidationError

from app.core.config import Settings
from app.core.security import create_access_token, settings


def test_correct_login_succeeds(unauthenticated_client):
    response = unauthenticated_client.post(
        "/auth/login",
        json={"email": "admin@example.com", "password": "test-admin-password"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["token_type"] == "bearer"
    assert body["access_token"]
    assert body["expires_in"] == 3600
    assert "password" not in body
    assert response.headers["cache-control"] == "no-store"


@pytest.mark.parametrize(
    "payload",
    [
        {"email": "admin@example.com", "password": "wrong-password"},
        {"email": "other@example.com", "password": "test-admin-password"},
    ],
)
def test_invalid_login_fails_with_generic_401(unauthenticated_client, payload):
    response = unauthenticated_client.post("/auth/login", json=payload)

    assert response.status_code == 401
    assert response.json() == {"detail": "Invalid email or password."}
    assert payload["password"] not in response.text
    assert payload["email"] not in response.text


def test_health_remains_public(unauthenticated_client):
    response = unauthenticated_client.get("/health")

    assert response.status_code == 200


def test_missing_token_fails_on_protected_endpoint(unauthenticated_client):
    response = unauthenticated_client.get("/products/")

    assert response.status_code == 401


def test_malformed_token_fails(unauthenticated_client):
    response = unauthenticated_client.get(
        "/products/",
        headers={"Authorization": "Bearer not-a-valid-token"},
    )

    assert response.status_code == 401
    assert "not-a-valid-token" not in response.text


def test_expired_token_fails(unauthenticated_client):
    expired = jwt.encode(
        {
            "sub": settings.admin_email,
            "role": "admin",
            "exp": datetime.now(UTC) - timedelta(minutes=1),
        },
        settings.jwt_secret_key,
        algorithm=settings.jwt_algorithm,
    )

    response = unauthenticated_client.get(
        "/products/",
        headers={"Authorization": f"Bearer {expired}"},
    )

    assert response.status_code == 401
    assert expired not in response.text


def test_valid_admin_token_accesses_products_endpoint(unauthenticated_client):
    token, _expires_in = create_access_token(settings.admin_email)

    response = unauthenticated_client.get(
        "/products/",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200


def test_current_user_endpoint_returns_minimal_admin_info(client):
    response = client.get("/auth/me")

    assert response.status_code == 200
    assert response.json() == {"email": "admin@example.com", "role": "admin"}


def test_docs_and_openapi_are_not_public_when_debug_false(unauthenticated_client):
    assert unauthenticated_client.get("/docs").status_code == 404
    assert unauthenticated_client.get("/redoc").status_code == 404
    assert unauthenticated_client.get("/openapi.json").status_code == 404


def test_startup_configuration_validation_catches_missing_security_secrets():
    with pytest.raises(ValidationError) as exc_info:
        Settings(
            _env_file=None,
            debug=False,
            admin_email="",
            admin_password_hash="",
            jwt_secret_key="",
        )

    assert "ADMIN_EMAIL" in str(exc_info.value)
    assert "ADMIN_PASSWORD_HASH" in str(exc_info.value)
    assert "JWT_SECRET_KEY" in str(exc_info.value)


def test_security_headers_are_present_on_responses(client):
    response = client.get("/products/")

    assert response.headers["x-content-type-options"] == "nosniff"
    assert response.headers["x-frame-options"] == "DENY"
    assert response.headers["referrer-policy"] == "no-referrer"
