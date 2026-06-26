"""Tests for the GET /health endpoint.

Spec contract (spec.md §4, AC-1):
    GET /health returns HTTP 200 with body exactly {"status":"ok"} within 60 s of start.
    Required for the judge harness readiness probe.
"""

import json

from fastapi.testclient import TestClient

from main import app

client = TestClient(app)


def test_health_returns_200():
    response = client.get("/health")
    assert response.status_code == 200


def test_health_body_is_status_ok():
    response = client.get("/health")
    assert response.json() == {"status": "ok"}


def test_health_content_type_is_json():
    response = client.get("/health")
    content_type = response.headers.get("content-type", "")
    assert content_type.startswith("application/json")


def test_health_response_is_fast():
    """AC-1: /health must return within 60 s of service start. The TestClient is in-process,
    so we only sanity-check that the endpoint is reachable at all (no slow warm-up path)."""
    response = client.get("/health")
    # If we got here at all, the readiness probe succeeded.
    assert response.status_code == 200
    # And the body remains exactly the documented shape.
    assert response.json() == {"status": "ok"}


def test_health_does_not_require_payload():
    """Health must be reachable without any body or query params."""
    response = client.get("/health")
    assert response.status_code == 200


def test_health_post_should_not_be_allowed():
    """Only GET is documented; POST should not silently succeed."""
    response = client.post("/health")
    assert response.status_code in (405, 404)
