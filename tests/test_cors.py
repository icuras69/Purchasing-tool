from app.core.config import Settings


def test_vite_dev_origin_is_allowed(client):
    response = client.options(
        "/products/",
        headers={
            "Origin": "http://localhost:5173",
            "Access-Control-Request-Method": "GET",
        },
    )

    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "http://localhost:5173"


def test_vite_dev_origin_can_use_mapping_write_methods(client):
    response = client.options(
        "/product-suppliers",
        headers={
            "Origin": "http://localhost:5173",
            "Access-Control-Request-Method": "PATCH",
        },
    )

    assert response.status_code == 200
    assert "PATCH" in response.headers["access-control-allow-methods"]
    assert "POST" in response.headers["access-control-allow-methods"]


def test_unknown_origin_is_not_allowed(client):
    response = client.options(
        "/products/",
        headers={
            "Origin": "https://example.com",
            "Access-Control-Request-Method": "GET",
        },
    )

    assert "access-control-allow-origin" not in response.headers


def test_settings_adds_deployed_frontend_origin_to_cors_origins():
    settings = Settings(
        _env_file=None,
        frontend_origin="https://purchasing-ai-frontend.onrender.com/",
        cors_origins="https://demo.example.com, https://staging.example.com/",
    )

    assert "http://localhost:5173" in settings.allowed_cors_origins()
    assert "http://127.0.0.1:5173" in settings.allowed_cors_origins()
    assert "https://purchasing-ai-frontend.onrender.com" in settings.allowed_cors_origins()
    assert "https://demo.example.com" in settings.allowed_cors_origins()
    assert "https://staging.example.com" in settings.allowed_cors_origins()
