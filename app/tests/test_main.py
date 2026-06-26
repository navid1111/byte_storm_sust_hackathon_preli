"""Phase 1 endpoint/app-level tests (Navid).

Covers the wiring of /health, /analyze-ticket, /metrics, CORS, and 404 behavior.
Deeper schema-contract and health timing tests are Jyoti's (T010, T011).
"""

from fastapi.testclient import TestClient

from main import app

client = TestClient(app)

REQUIRED_RESPONSE_FIELDS = [
    "ticket_id",
    "relevant_transaction_id",
    "evidence_verdict",
    "case_type",
    "severity",
    "department",
    "agent_summary",
    "recommended_next_action",
    "customer_reply",
    "human_review_required",
]


def test_health_returns_ok():
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_analyze_ticket_happy_path_has_all_required_fields():
    payload = {
        "ticket_id": "TKT-001",
        "complaint": "I sent 5000 taka to a wrong number around 2pm today",
    }
    response = client.post("/analyze-ticket", json=payload)
    assert response.status_code == 200
    body = response.json()
    for field in REQUIRED_RESPONSE_FIELDS:
        assert field in body, f"missing required field: {field}"


def test_analyze_ticket_echoes_ticket_id():
    response = client.post(
        "/analyze-ticket", json={"ticket_id": "XYZ-9", "complaint": "please help"}
    )
    assert response.status_code == 200
    assert response.json()["ticket_id"] == "XYZ-9"


def test_analyze_ticket_reply_is_safe_by_construction():
    response = client.post(
        "/analyze-ticket", json={"ticket_id": "T", "complaint": "where is my money"}
    )
    reply = response.json()["customer_reply"].lower()
    # Phase 1 stub must not ask for credentials or promise a refund.
    assert "never ask for your pin" in reply
    assert "we will refund" not in reply


def test_analyze_ticket_blank_complaint_does_not_crash():
    response = client.post(
        "/analyze-ticket", json={"ticket_id": "T", "complaint": "   "}
    )
    assert response.status_code in (400, 422)


def test_analyze_ticket_missing_complaint_does_not_crash():
    response = client.post("/analyze-ticket", json={"ticket_id": "T"})
    assert response.status_code in (400, 422)


def test_analyze_ticket_malformed_json_does_not_crash():
    response = client.post(
        "/analyze-ticket",
        content=b"{not valid json",
        headers={"content-type": "application/json"},
    )
    assert response.status_code in (400, 422)


def test_metrics_endpoint_exposed():
    response = client.get("/metrics")
    assert response.status_code == 200
    assert "# HELP" in response.text
    assert "# TYPE" in response.text


def test_cors_preflight_echoes_origin():
    response = client.options(
        "/health",
        headers={
            "Origin": "http://example.com",
            "Access-Control-Request-Method": "GET",
        },
    )
    assert response.status_code == 200
    assert response.headers.get("access-control-allow-origin") == "http://example.com"
    assert response.headers.get("access-control-allow-credentials") == "true"


def test_unknown_route_returns_404():
    assert client.get("/does-not-exist").status_code == 404
