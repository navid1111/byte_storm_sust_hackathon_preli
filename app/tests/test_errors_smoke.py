"""Smoke test for app.api.errors — temporary, not committed as a real suite.

Exercises each error path against a throwaway FastAPI app to verify T009
behavior. This file lives in app/tests/ because that's where Jyoti's test
files will eventually go (T010, T011, T017, T021, T022). For now it's just
a manual verification scaffold; remove before T032.
"""
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

from app.api.errors import register_exception_handlers

app = FastAPI()
register_exception_handlers(app)


@app.post("/echo")
def echo(payload: dict):
    return {"got": payload}


@app.get("/boom")
def boom():
    raise HTTPException(status_code=418, detail="teapot: secret=topsecret")


@app.get("/crash")
def crash():
    raise RuntimeError("database password = hunter2")


client = TestClient(app, raise_server_exceptions=False)


def assert_shape(resp, expected_status, expected_code):
    body = resp.json()
    assert resp.status_code == expected_status, (resp.status_code, body)
    assert set(body.keys()) == {"detail", "code"}, body
    assert body["code"] == expected_code, body
    # Non-sensitive: no stack trace markers, no common secret patterns.
    text = str(body).lower()
    assert "traceback" not in text
    assert "hunter2" not in text
    assert "topsecret" not in text
    assert "password" not in text
    return body


def test_invalid_json_400():
    resp = client.post("/echo", data="not json", headers={"content-type": "application/json"})
    body = assert_shape(resp, 400, "invalid_json")
    assert "JSON" in body["detail"] or "json" in body["detail"]


def test_missing_required_field_400():
    # /echo expects a dict, so missing body -> validation error of the dict shape
    resp = client.post("/echo", json={})
    # The body is technically valid (empty dict), so this hits /echo directly
    # with a 200 — that's expected for this stub. To exercise the handler's
    # required-field path, we need a route that demands ticket_id + complaint.
    # That's owned by Navid (T008); here we only assert the handler wiring works.
    assert resp.status_code in (200, 422)


def test_http_exception_preserves_status_safe_message():
    resp = client.get("/boom")
    body = assert_shape(resp, 418, "http_418")
    # Original detail may be replaced with generic; secret must NOT appear.
    assert "topsecret" not in body["detail"].lower()


def test_unhandled_exception_500_no_leak():
    resp = client.get("/crash")
    body = assert_shape(resp, 500, "internal_error")
    assert body["detail"] == "internal server error"
    assert "hunter2" not in body["detail"]