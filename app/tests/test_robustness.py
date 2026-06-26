"""Robustness & reliability tests.

Covers acceptance criteria:
    AC-9  Malformed JSON or missing required fields return 400 (or 422 for empty
          complaint) with a non-sensitive error — the process never crashes.
    AC-10 Complaints in Bangla and mixed Banglish are processed without error.

Tests run against the live FastAPI TestClient (real HTTP plumbing).
"""

import json

from fastapi.testclient import TestClient

from main import app

client = TestClient(app)


# ---------------------------------------------------------------------------
# Malformed JSON → 400, no crash
# ---------------------------------------------------------------------------

def test_malformed_json_returns_400():
    """AC-9: invalid JSON body must yield 400, not a 500 or process crash."""
    response = client.post(
        "/analyze-ticket",
        content="{this is not valid json",
        headers={"content-type": "application/json"},
    )
    assert response.status_code == 400


def test_empty_body_returns_400():
    response = client.post("/analyze-ticket", content="", headers={"content-type": "application/json"})
    assert response.status_code == 400


def test_non_object_json_returns_400():
    """AC-9: valid JSON that is not an object (e.g. an array, a string) must be rejected."""
    for bad_body in ["[]", '"a string"', "42", "null", "true"]:
        response = client.post(
            "/analyze-ticket",
            content=bad_body,
            headers={"content-type": "application/json"},
        )
        assert response.status_code == 400, f"Body {bad_body!r} should yield 400"


def test_wrong_content_type_returns_400_or_422():
    response = client.post(
        "/analyze-ticket",
        content="ticket_id=TKT-001&complaint=hello",
        headers={"content-type": "application/x-www-form-urlencoded"},
    )
    # Either 400 or 422 is acceptable per spec §4.1.
    assert response.status_code in (400, 422)


# ---------------------------------------------------------------------------
# Missing required fields → 400, no crash
# ---------------------------------------------------------------------------

def test_missing_ticket_id_returns_400_or_422():
    response = client.post(
        "/analyze-ticket",
        json={"complaint": "I have a complaint"},
    )
    assert response.status_code in (400, 422)


def test_missing_complaint_returns_400_or_422():
    response = client.post(
        "/analyze-ticket",
        json={"ticket_id": "TKT-X"},
    )
    assert response.status_code in (400, 422)


def test_missing_both_required_fields_returns_400_or_422():
    response = client.post("/analyze-ticket", json={})
    assert response.status_code in (400, 422)


# ---------------------------------------------------------------------------
# Empty complaint → 422
# ---------------------------------------------------------------------------

def test_empty_complaint_returns_422():
    """AC-9: schema-valid but semantically invalid (empty complaint) → 422."""
    response = client.post(
        "/analyze-ticket",
        json={"ticket_id": "TKT-EMPTY", "complaint": ""},
    )
    assert response.status_code == 422


def test_whitespace_only_complaint_returns_422():
    response = client.post(
        "/analyze-ticket",
        json={"ticket_id": "TKT-WS", "complaint": "   \n\t  "},
    )
    assert response.status_code == 422


# ---------------------------------------------------------------------------
# Error bodies must be non-sensitive (AC-13)
# ---------------------------------------------------------------------------

def test_error_body_does_not_leak_stack_trace():
    response = client.post(
        "/analyze-ticket",
        content="not json",
        headers={"content-type": "application/json"},
    )
    body = response.text.lower()
    # No Python stack trace markers should appear in user-facing errors.
    forbidden = ["traceback", "file \"", "line ", ".py\""]
    for marker in forbidden:
        assert marker not in body, f"Error body leaks stack trace fragment: {marker}"


def test_error_body_does_not_leak_env_vars():
    """AC-13: error responses must not echo any secret-like content."""
    response = client.post(
        "/analyze-ticket",
        json={"ticket_id": "TKT-X"},  # missing required complaint
    )
    body = response.text.lower()
    forbidden = ["api_key", "secret", "token", "password", "gemini"]
    for marker in forbidden:
        assert marker not in body, f"Error body may leak secret marker '{marker}'"


# ---------------------------------------------------------------------------
# Empty / absent transaction_history
# ---------------------------------------------------------------------------

def test_missing_transaction_history_is_accepted():
    """transaction_history is optional; absent must still return 200."""
    response = client.post(
        "/analyze-ticket",
        json={
            "ticket_id": "TKT-NO-HIST",
            "complaint": "I think my account has been compromised.",
            "language": "en",
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert body["ticket_id"] == "TKT-NO-HIST"
    assert body["relevant_transaction_id"] is None
    assert body["evidence_verdict"] == "insufficient_data"


def test_empty_transaction_history_is_accepted():
    response = client.post(
        "/analyze-ticket",
        json={
            "ticket_id": "TKT-EMPTY-HIST",
            "complaint": "Please check my recent activity.",
            "transaction_history": [],
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert body["relevant_transaction_id"] is None


def test_transaction_history_with_unknown_extra_fields_is_accepted():
    """Harness may send extra metadata fields; extra='ignore' on the model must keep parse working."""
    response = client.post(
        "/analyze-ticket",
        json={
            "ticket_id": "TKT-EXTRA",
            "complaint": "Some complaint text.",
            "transaction_history": [
                {
                    "transaction_id": "TXN-X",
                    "timestamp": "2026-04-14T00:00:00Z",
                    "type": "transfer",
                    "amount": 100,
                    "counterparty": "+8801700000000",
                    "status": "completed",
                    "extra_unknown_field": "should be ignored",
                }
            ],
            "metadata": {"harness_only": True, "raw_customer_id": 12345},
            "campaign_context": "x",
        },
    )
    assert response.status_code == 200


# ---------------------------------------------------------------------------
# Bangla & Banglish complaints (AC-10)
# ---------------------------------------------------------------------------

def test_bangla_complaint_processed_without_error():
    """AC-10: Bangla complaint must be processed without error."""
    response = client.post(
        "/analyze-ticket",
        json={
            "ticket_id": "TKT-BN-1",
            "language": "bn",
            "complaint": "আমার ১০০০ টাকা ভুল নম্বরে চলে গেছে। ফেরত দিন।",
            "transaction_history": [
                {
                    "transaction_id": "TXN-BN-1",
                    "timestamp": "2026-04-14T08:00:00Z",
                    "type": "transfer",
                    "amount": 1000,
                    "counterparty": "+8801700000001",
                    "status": "completed",
                }
            ],
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert body["ticket_id"] == "TKT-BN-1"
    # Engine should classify as wrong_transfer based on Bangla cue 'ভুল নম্বরে'.
    assert body["case_type"] == "wrong_transfer"
    assert body["relevant_transaction_id"] == "TXN-BN-1"


def test_banglish_complaint_processed_without_error():
    """AC-10: mixed Banglish complaint must be processed without error."""
    response = client.post(
        "/analyze-ticket",
        json={
            "ticket_id": "TKT-BL-1",
            "language": "mixed",
            "complaint": "Ami ekhon 750 taka ekta merchant ke pathailam, kintu payment fail hoise ar taka kete nise.",
            "transaction_history": [
                {
                    "transaction_id": "TXN-BL-1",
                    "timestamp": "2026-04-14T08:30:00Z",
                    "type": "payment",
                    "amount": 750,
                    "counterparty": "MERCHANT-99",
                    "status": "failed",
                }
            ],
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert body["ticket_id"] == "TKT-BL-1"
    assert body["relevant_transaction_id"] == "TXN-BL-1"
    # Should classify as payment_failed based on Banglish cues 'payment fail' / 'taka kete nise'.
    assert body["case_type"] == "payment_failed"


# ---------------------------------------------------------------------------
# Process never crashes — concurrency / repeated calls
# ---------------------------------------------------------------------------

def test_repeated_calls_do_not_crash():
    """Stability under repeated judge harness calls."""
    request_body = {
        "ticket_id": "TKT-REPEAT",
        "complaint": "I sent 100 taka to wrong number.",
        "transaction_history": [
            {
                "transaction_id": "TXN-REPEAT",
                "timestamp": "2026-04-14T09:00:00Z",
                "type": "transfer",
                "amount": 100,
                "counterparty": "+8801700000099",
                "status": "completed",
            }
        ],
    }
    for i in range(20):
        body = {**request_body, "ticket_id": f"TKT-REPEAT-{i}"}
        response = client.post("/analyze-ticket", json=body)
        assert response.status_code == 200


def test_mixed_valid_and_invalid_calls_do_not_crash_process():
    """Even after invalid calls, subsequent valid calls must succeed."""
    # First, a malformed request.
    bad = client.post(
        "/analyze-ticket",
        content="not json",
        headers={"content-type": "application/json"},
    )
    assert bad.status_code == 400

    # Then, a valid request — must still work.
    good = client.post(
        "/analyze-ticket",
        json={
            "ticket_id": "TKT-AFTER-BAD",
            "complaint": "I have an issue with my last transaction.",
            "transaction_history": [],
        },
    )
    assert good.status_code == 200


# ---------------------------------------------------------------------------
# /health must remain reachable throughout
# ---------------------------------------------------------------------------

def test_health_remains_healthy_after_errors():
    """After error traffic, /health must still respond 200."""
    client.post(
        "/analyze-ticket",
        content="not json",
        headers={"content-type": "application/json"},
    )
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}