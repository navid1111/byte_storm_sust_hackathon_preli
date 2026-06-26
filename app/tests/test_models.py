"""Phase 0 model + enum contract tests (Navid).

Verifies the exact enum values from spec §7, required-field validation, and the
tolerant parsing of optional/extra fields. Complements Jyoti's endpoint-level
schema contract tests (T011).
"""

import pytest
from pydantic import ValidationError

from config import Settings
from models.enums import (
    CaseType,
    Department,
    EvidenceVerdict,
    Severity,
    TransactionStatus,
    TransactionType,
)
from models.request import TicketRequest
from models.response import TicketAnalysis


def test_enum_values_match_spec_exactly():
    assert {v.value for v in EvidenceVerdict} == {
        "consistent",
        "inconsistent",
        "insufficient_data",
    }
    assert {v.value for v in CaseType} == {
        "wrong_transfer",
        "payment_failed",
        "refund_request",
        "duplicate_payment",
        "merchant_settlement_delay",
        "agent_cash_in_issue",
        "phishing_or_social_engineering",
        "other",
    }
    assert {v.value for v in Severity} == {"low", "medium", "high", "critical"}
    assert {v.value for v in Department} == {
        "customer_support",
        "dispute_resolution",
        "payments_ops",
        "merchant_operations",
        "agent_operations",
        "fraud_risk",
    }
    assert {v.value for v in TransactionType} == {
        "transfer",
        "payment",
        "cash_in",
        "cash_out",
        "settlement",
        "refund",
    }
    assert {v.value for v in TransactionStatus} == {
        "completed",
        "failed",
        "pending",
        "reversed",
    }


def test_str_enum_serializes_to_value():
    assert EvidenceVerdict.CONSISTENT.value == "consistent"
    assert str(Department.FRAUD_RISK) == "fraud_risk"


def test_request_requires_ticket_id_and_complaint():
    with pytest.raises(ValidationError):
        TicketRequest(complaint="hi")
    with pytest.raises(ValidationError):
        TicketRequest(ticket_id="TKT-1")


@pytest.mark.parametrize("blank", ["", "   ", "\n\t"])
def test_blank_complaint_rejected(blank):
    with pytest.raises(ValidationError):
        TicketRequest(ticket_id="TKT-1", complaint=blank)


@pytest.mark.parametrize("blank", ["", "   "])
def test_blank_ticket_id_rejected(blank):
    with pytest.raises(ValidationError):
        TicketRequest(ticket_id=blank, complaint="real complaint")


def test_request_ignores_extra_fields_and_defaults_history():
    req = TicketRequest(
        ticket_id="TKT-1",
        complaint="I sent money to a wrong number",
        surprise_field="should be ignored",
    )
    assert req.transaction_history == []
    assert not hasattr(req, "surprise_field")


def test_request_parses_transaction_history():
    req = TicketRequest(
        ticket_id="TKT-1",
        complaint="failed payment",
        transaction_history=[
            {
                "transaction_id": "TXN-1",
                "timestamp": "2026-04-14T14:08:22Z",
                "type": "transfer",
                "amount": 5000,
                "counterparty": "+8801719876543",
                "status": "completed",
            }
        ],
    )
    assert req.transaction_history[0].transaction_id == "TXN-1"
    assert req.transaction_history[0].amount == 5000.0


def test_tolerant_to_odd_optional_values():
    # An unusual channel / status must not reject the whole ticket (AC-9).
    req = TicketRequest(
        ticket_id="TKT-1",
        complaint="hello",
        channel="some_new_channel",
        transaction_history=[{"transaction_id": "TXN-9", "status": "weird"}],
    )
    assert req.channel == "some_new_channel"
    assert req.transaction_history[0].status == "weird"


def test_response_model_round_trip_and_enum_typing():
    analysis = TicketAnalysis(
        ticket_id="TKT-1",
        relevant_transaction_id="TXN-1",
        evidence_verdict="consistent",
        case_type="wrong_transfer",
        severity="high",
        department="dispute_resolution",
        agent_summary="summary",
        recommended_next_action="next",
        customer_reply="reply",
        human_review_required=True,
        confidence=0.9,
        reason_codes=["wrong_transfer"],
    )
    dumped = analysis.model_dump()
    assert dumped["evidence_verdict"] == "consistent"
    assert dumped["case_type"] == "wrong_transfer"
    assert dumped["relevant_transaction_id"] == "TXN-1"


def test_response_optional_fields_default():
    analysis = TicketAnalysis(
        ticket_id="TKT-1",
        relevant_transaction_id=None,
        evidence_verdict="insufficient_data",
        case_type="other",
        severity="low",
        department="customer_support",
        agent_summary="s",
        recommended_next_action="n",
        customer_reply="r",
        human_review_required=False,
    )
    assert analysis.confidence is None
    assert analysis.reason_codes == []


def test_response_rejects_bad_enum_and_extra():
    with pytest.raises(ValidationError):
        TicketAnalysis(
            ticket_id="TKT-1",
            relevant_transaction_id=None,
            evidence_verdict="maybe",  # not a valid enum
            case_type="other",
            severity="low",
            department="customer_support",
            agent_summary="s",
            recommended_next_action="n",
            customer_reply="r",
            human_review_required=False,
        )


def test_settings_defaults(monkeypatch):
    for var in ("LLM_ENABLED", "GEMINI_API_KEY", "MODEL_NAME", "PORT", "REQUEST_TIMEOUT_S"):
        monkeypatch.delenv(var, raising=False)
    s = Settings()
    assert s.llm_enabled is False
    assert s.llm_provider == "gemini"
    assert s.llm_ready is False
    assert s.port == 8000


def test_settings_llm_ready_requires_key(monkeypatch):
    monkeypatch.setenv("LLM_ENABLED", "true")
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    assert Settings().llm_ready is False
    monkeypatch.setenv("GEMINI_API_KEY", "dummy")
    assert Settings().llm_ready is True
