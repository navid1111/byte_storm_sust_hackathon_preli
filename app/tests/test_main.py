from fastapi.testclient import TestClient

from main import app

client = TestClient(app)


def test_home_returns_hello_world():
    response = client.get("/")
    assert response.status_code == 200
    assert response.json() == "Hello World"


def test_home_content_type():
    response = client.get("/")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("application/json")


def test_metrics_endpoint_exposed():
    response = client.get("/metrics")
    assert response.status_code == 200
    # Prometheus exposition format always begins with `# HELP` lines.
    assert "# HELP" in response.text
    assert "# TYPE" in response.text


def test_metrics_contains_http_requests_metric():
    response = client.get("/metrics")
    assert response.status_code == 200
    # Default metric name exposed by prometheus-fastapi-instrumentator.
    assert "http_requests" in response.text


def test_cors_allows_any_origin():
    response = client.options(
        "/",
        headers={
            "Origin": "http://example.com",
            "Access-Control-Request-Method": "GET",
        },
    )
    assert response.status_code == 200
    # With allow_origins=["*"] and allow_credentials=True the middleware
    # echoes the request Origin (it cannot reply with literal "*" when
    # credentials are allowed per the CORS spec).
    assert response.headers.get("access-control-allow-origin") == "http://example.com"
    assert response.headers.get("access-control-allow-credentials") == "true"


def test_unknown_route_returns_404():
    response = client.get("/does-not-exist")
    assert response.status_code == 404