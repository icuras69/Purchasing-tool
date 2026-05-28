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
