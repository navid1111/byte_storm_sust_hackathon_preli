"""Schema-contract tests for the public API (T011, spec §6, §7, §9).

These tests pin the wire contract end-to-end against the real FastAPI app:

    * /health returns the exact body shape judges will pattern-match on.
    * /analyze-ticket always returns the full set of required fields with the
      exact enum values, exact types, and the right semantic 4xx codes for
      malformed input.
    * Error responses never leak stack traces, file paths, secrets, or the
      raw request body.

The production app is imported directly (rather than a stub) so a regression
in ``app/api/routes.py``, ``app/main.py``, or ``app/models/*.py`` will fail
these tests. ``raise_server_exceptions=False`` lets the catch-all handler be
exercised without the TestClient re-raising.
"""
from __future__ import annotations

import re
from typing import Any

from fastapi.testclient import TestClient

from main import app

# Spec §6.1 / §7 — exact allowed enum values.
ALLOWED_EVIDENCE_VERDICTS = {"consistent", "inconsistent", "insufficient_data"}
ALLOWED_CASE_TYPES = {
    "wrong_transfer",
    "payment_failed",
    "refund_request",
    "duplicate_payment",
    "merchant_settlement_delay",
    "agent_cash_in_issue",
    "phishing_or_social_engineering",
    "other",
}
ALLOWED_SEVERITIES = {"low", "medium", "high", "critical"}
ALLOWED_DEPARTMENTS = {
    "customer_support",
    "dispute_resolution",
    "payments_ops",
    "merchant_operations",
    "agent_operations",
    "fraud_risk",
}

# Spec §6.1 — every response must contain these keys, exactly.
REQUIRED_RESPONSE_FIELDS = {
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
    "confidence",
    "reason_codes",
}

# A single happy-path request that the investigator can chew on. We do not
# care which fields it returns — only that the contract holds.
HAPPY_PATH_REQUEST: dict[str, Any] = {
    "ticket_id": "T-SCHEMA-001",
    "complaint": (
        "I sent 1500 BDT to merchant 01812345678 yesterday for order #A-991 "
        "but the merchant says they never received it. bKash USSD shows "
        "completed. Please refund."
    ),
    "language": "en",
    "channel": "in_app_chat",
    "user_type": "customer",
    "transaction_history": [
        {
            "transaction_id": "TXN-HAPPY-1",
            "timestamp": "2026-06-25T10:15:00Z",
            "type": "transfer",
            "amount": 1500.0,
            "counterparty": "01812345678",
            "status": "completed",
        },
    ],
    "metadata": {"source": "test_schema_contract"},
}

client = TestClient(app, raise_server_exceptions=False)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
_SECRET_KEYWORDS = (
    "api_key", "apikey", "secret", "token", "password", "passwd", "pwd",
    "bearer", "authorization",
)
_LEAK_PATTERNS = (
    re.compile(r"traceback", re.IGNORECASE),
    re.compile(r"\b[A-Za-z]:\\\\[^\s\"']+"),  # Windows-style file path
    re.compile(r"(/[A-Za-z0-9_.-]+){3,}"),    # POSIX-style absolute path
)


def _assert_no_leak(body: dict[str, Any]) -> None:
    """Assert that an error body does not contain stack traces, paths, or secrets."""
    serialized = repr(body).lower()
    for pat in _LEAK_PATTERNS:
        assert pat.search(serialized) is None, (pat.pattern, body)
    for kw in _SECRET_KEYWORDS:
        # We only forbid the keyword as a *value* — "code": "missing_field"
        # containing "token" is a false positive we accept.
        assert f"'{kw}'" not in serialized, (kw, body)
        assert f'"{kw}"' not in serialized, (kw, body)


# ---------------------------------------------------------------------------
# /health (spec §4)
# ---------------------------------------------------------------------------
def test_health_returns_200():
    resp = client.get("/health")
    assert resp.status_code == 200, (resp.status_code, resp.text)


def test_health_body_is_exactly_status_ok():
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


# ---------------------------------------------------------------------------
# /analyze-ticket — happy path contract (spec §6)
# ---------------------------------------------------------------------------
def test_analyze_ticket_happy_path_returns_200():
    resp = client.post("/analyze-ticket", json=HAPPY_PATH_REQUEST)
    assert resp.status_code == 200, (resp.status_code, resp.text)


def test_analyze_ticket_response_contains_all_required_fields():
    resp = client.post("/analyze-ticket", json=HAPPY_PATH_REQUEST)
    assert resp.status_code == 200
    body = resp.json()
    missing = REQUIRED_RESPONSE_FIELDS - set(body.keys())
    assert not missing, (missing, sorted(body.keys()))


def test_analyze_ticket_response_ticket_id_echoes_request():
    resp = client.post("/analyze-ticket", json=HAPPY_PATH_REQUEST)
    assert resp.status_code == 200
    assert resp.json()["ticket_id"] == HAPPY_PATH_REQUEST["ticket_id"]


# ---------------------------------------------------------------------------
# Enum value conformance (spec §7)
# ---------------------------------------------------------------------------
def _envelope_body() -> dict[str, Any]:
    resp = client.post("/analyze-ticket", json=HAPPY_PATH_REQUEST)
    assert resp.status_code == 200, (resp.status_code, resp.text)
    return resp.json()


def test_evidence_verdict_is_allowed_value():
    assert _envelope_body()["evidence_verdict"] in ALLOWED_EVIDENCE_VERDICTS


def test_case_type_is_allowed_value():
    assert _envelope_body()["case_type"] in ALLOWED_CASE_TYPES


def test_severity_is_allowed_value():
    assert _envelope_body()["severity"] in ALLOWED_SEVERITIES


def test_department_is_allowed_value():
    assert _envelope_body()["department"] in ALLOWED_DEPARTMENTS


# ---------------------------------------------------------------------------
# Field type conformance (spec §6.1)
# ---------------------------------------------------------------------------
def test_field_types_match_spec():
    body = _envelope_body()

    assert isinstance(body["ticket_id"], str)
    assert body["relevant_transaction_id"] is None or isinstance(
        body["relevant_transaction_id"], str
    )
    assert isinstance(body["evidence_verdict"], str)
    assert isinstance(body["case_type"], str)
    assert isinstance(body["severity"], str)
    assert isinstance(body["department"], str)
    assert isinstance(body["agent_summary"], str)
    assert isinstance(body["recommended_next_action"], str)
    assert isinstance(body["customer_reply"], str)
    assert isinstance(body["human_review_required"], bool)

    confidence = body["confidence"]
    assert isinstance(confidence, (int, float)) and not isinstance(confidence, bool)
    assert 0.0 <= float(confidence) <= 1.0

    assert isinstance(body["reason_codes"], list)
    # Every reason code (when present) is itself a string.
    for code in body["reason_codes"]:
        assert isinstance(code, str), (code, body["reason_codes"])


# ---------------------------------------------------------------------------
# Malformed / missing input (spec §4.1, §9)
# ---------------------------------------------------------------------------
def test_malformed_json_returns_400():
    resp = client.post(
        "/analyze-ticket",
        data="this is not json",
        headers={"content-type": "application/json"},
    )
    assert resp.status_code == 400, (resp.status_code, resp.text)
    _assert_no_leak(resp.json())


def test_missing_ticket_id_returns_400():
    payload = dict(HAPPY_PATH_REQUEST)
    payload.pop("ticket_id")
    resp = client.post("/analyze-ticket", json=payload)
    assert resp.status_code == 400, (resp.status_code, resp.text)
    _assert_no_leak(resp.json())


def test_missing_complaint_returns_400():
    payload = dict(HAPPY_PATH_REQUEST)
    payload.pop("complaint")
    resp = client.post("/analyze-ticket", json=payload)
    assert resp.status_code == 400, (resp.status_code, resp.text)
    _assert_no_leak(resp.json())


def test_blank_complaint_returns_422():
    payload = dict(HAPPY_PATH_REQUEST)
    payload["complaint"] = "   \n\t  "
    resp = client.post("/analyze-ticket", json=payload)
    assert resp.status_code == 422, (resp.status_code, resp.text)
    _assert_no_leak(resp.json())


def test_empty_complaint_string_returns_422():
    payload = dict(HAPPY_PATH_REQUEST)
    payload["complaint"] = ""
    resp = client.post("/analyze-ticket", json=payload)
    assert resp.status_code == 422, (resp.status_code, resp.text)
    _assert_no_leak(resp.json())


# ---------------------------------------------------------------------------
# Error-response hygiene (spec §9)
# ---------------------------------------------------------------------------
def test_error_response_shape_is_detail_only():
    # The most representative malformed case. The canonical error envelope is
    # a single non-sensitive "detail" field (spec §4.1).
    resp = client.post(
        "/analyze-ticket",
        data="not json",
        headers={"content-type": "application/json"},
    )
    assert resp.status_code == 400
    body = resp.json()
    assert set(body.keys()) == {"detail"}, body


def test_error_body_does_not_echo_request_payload():
    # Plant a unique marker in the body — it must never appear in the error.
    payload = dict(HAPPY_PATH_REQUEST)
    payload["complaint"] = (
        "I lost my card. Please block it. Marker-SCHEMA-MUST-NOT-LEAK-9981."
    )
    payload["ticket_id"] = "T-LEAK-9981"
    resp = client.post("/analyze-ticket", json=payload)
    # Even on success, the marker must not be re-emitted in the response.
    serialized = repr(resp.json())
    assert "Marker-SCHEMA-MUST-NOT-LEAK-9981" not in serialized
    assert "T-LEAK-9981" in serialized  # ticket_id is the legitimate echo
