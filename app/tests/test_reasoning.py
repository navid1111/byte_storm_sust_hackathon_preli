"""Tests for the Evidence Reasoning Engine.

Covers acceptance criteria:
    AC-4  relevant_transaction_id is in history or None (never invented)
    AC-5  evidence_verdict: consistent / inconsistent / insufficient_data
    AC-7  phishing sets case_type, department, human_review_required correctly
    AC-8  ambiguous / disputed / suspicious / high-value → human_review_required = True

These tests load hand-authored fixtures from app/tests/fixtures/cases.json (T000).
They are intentionally written against the public engine entry point
(`app.engine.investigator.analyze`) and the public response Pydantic model
(`app.models.response.TicketAnalysis`) so they fail loudly if either drifts.
"""

import json
from pathlib import Path

import pytest

from engine.investigator import analyze
from models.request import TicketRequest
from models.response import TicketAnalysis

FIXTURES_PATH = Path(__file__).parent / "fixtures" / "cases.json"


def _load_cases():
    with FIXTURES_PATH.open("r", encoding="utf-8") as f:
        data = json.load(f)
    return data["cases"]


ALL_CASES = _load_cases()
CASE_NAMES = [c["name"] for c in ALL_CASES]
CASES_BY_NAME = {c["name"]: c for c in ALL_CASES}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _ids_from_history(request: dict) -> set[str]:
    return {entry["transaction_id"] for entry in request.get("transaction_history", [])}


def _run_case(name: str) -> TicketAnalysis:
    case = CASES_BY_NAME[name]
    return analyze(TicketRequest(**case["request"]))


# ---------------------------------------------------------------------------
# Schema sanity (these must hold for every case)
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("name", CASE_NAMES)
def test_response_is_a_valid_ticket_analysis(name):
    result = _run_case(name)
    assert isinstance(result, TicketAnalysis)


@pytest.mark.parametrize("name", CASE_NAMES)
def test_response_ticket_id_echoed(name):
    """AC-3: response.ticket_id must equal the request.ticket_id."""
    case = CASES_BY_NAME[name]
    result = _run_case(name)
    assert result.ticket_id == case["ticket_id"]


@pytest.mark.parametrize("name", CASE_NAMES)
def test_relevant_transaction_id_is_never_invented(name):
    """AC-4: relevant_transaction_id must be in the request's history or None."""
    case = CASES_BY_NAME[name]
    result = _run_case(name)
    history_ids = _ids_from_history(case["request"])
    if result.relevant_transaction_id is None:
        assert result.relevant_transaction_id is None
    else:
        assert result.relevant_transaction_id in history_ids


# ---------------------------------------------------------------------------
# Matching (decision-rules §1)
# ---------------------------------------------------------------------------

def test_match_wrong_transfer_picks_correct_entry():
    """The 5000 BDT completed transfer to wrong number should be selected."""
    result = _run_case("wrong_transfer_5000_completed")
    assert result.relevant_transaction_id == "TXN-9101"


def test_match_duplicate_picks_one_of_the_duplicates():
    """Two same-amount entries to MERCHANT-09; pick must be one of them."""
    result = _run_case("duplicate_payment_same_counterparty")
    assert result.relevant_transaction_id in {"TXN-3301", "TXN-3302"}


def test_match_bangla_wrong_transfer_picks_correct_entry():
    """বাংলা complaint 'ভুল নম্বরে পাঠাইছি' + 3000 taka should match the 3000 transfer."""
    result = _run_case("wrong_transfer_bangla")
    assert result.relevant_transaction_id == "TXN-4401"


def test_match_banglish_wrong_transfer_picks_correct_entry():
    """Banglish 'bhul number e pathaisi 2000 taka' should match the 2000 transfer."""
    result = _run_case("wrong_transfer_banglish")
    assert result.relevant_transaction_id == "TXN-5501"


def test_match_phishing_with_empty_history_is_null():
    """When the report is about a phishing call and history is empty, no transaction matches."""
    result = _run_case("phishing_pin_request")
    assert result.relevant_transaction_id is None


def test_match_empty_history_is_null():
    """When transaction_history is empty, the matched ID must be None."""
    result = _run_case("empty_history_insufficient_data")
    assert result.relevant_transaction_id is None


def test_match_merchant_settlement_picks_pending_settlement():
    result = _run_case("merchant_settlement_delay")
    assert result.relevant_transaction_id == "TXN-7701"


def test_match_agent_cash_in_picks_pending_cash_in():
    result = _run_case("agent_cash_in_not_reflected")
    assert result.relevant_transaction_id == "TXN-8801"


# ---------------------------------------------------------------------------
# Evidence verdict (decision-rules §2)
# ---------------------------------------------------------------------------

def test_verdict_consistent_for_supported_claim():
    """5000 BDT transfer, status completed → consistent."""
    result = _run_case("wrong_transfer_5000_completed")
    assert result.evidence_verdict.value == "consistent"


def test_verdict_inconsistent_for_deducted_but_completed():
    """Customer says payment failed + deducted, but entry shows status=completed."""
    result = _run_case("payment_failed_inconsistent_deducted_but_completed")
    assert result.evidence_verdict.value == "inconsistent"


def test_verdict_insufficient_data_for_empty_history():
    result = _run_case("empty_history_insufficient_data")
    assert result.evidence_verdict.value == "insufficient_data"


def test_verdict_insufficient_data_for_phishing_no_history():
    """Phishing reports with empty history → insufficient_data (claim cannot be checked)."""
    result = _run_case("phishing_pin_request")
    assert result.evidence_verdict.value == "insufficient_data"


def test_verdict_consistent_for_failed_payment_with_failed_status():
    """Customer says deducted but failed + entry status=failed → consistent (data supports it)."""
    result = _run_case("prompt_injection_attempt")
    assert result.evidence_verdict.value == "consistent"


# ---------------------------------------------------------------------------
# Classification (decision-rules §3.1, §5)
# ---------------------------------------------------------------------------

def test_classify_wrong_transfer():
    result = _run_case("wrong_transfer_5000_completed")
    assert result.case_type.value == "wrong_transfer"


def test_classify_payment_failed():
    result = _run_case("payment_failed_inconsistent_deducted_but_completed")
    assert result.case_type.value == "payment_failed"


def test_classify_phishing_overrides_other_signals():
    """§3.1 order: phishing checked first; overrides any other case_type signals."""
    result = _run_case("phishing_pin_request")
    assert result.case_type.value == "phishing_or_social_engineering"


def test_classify_duplicate():
    result = _run_case("duplicate_payment_same_counterparty")
    assert result.case_type.value == "duplicate_payment"


def test_classify_merchant_settlement():
    result = _run_case("merchant_settlement_delay")
    assert result.case_type.value == "merchant_settlement_delay"


def test_classify_agent_cash_in():
    result = _run_case("agent_cash_in_not_reflected")
    assert result.case_type.value == "agent_cash_in_issue"


def test_classify_bangla_wrong_transfer():
    result = _run_case("wrong_transfer_bangla")
    assert result.case_type.value == "wrong_transfer"


def test_classify_banglish_wrong_transfer():
    result = _run_case("wrong_transfer_banglish")
    assert result.case_type.value == "wrong_transfer"


# ---------------------------------------------------------------------------
# Routing (decision-rules §3.2 / §3.3 / §3.4)
# ---------------------------------------------------------------------------

def test_department_dispute_resolution_for_wrong_transfer():
    result = _run_case("wrong_transfer_5000_completed")
    assert result.department.value == "dispute_resolution"


def test_department_payments_ops_for_payment_failed():
    result = _run_case("payment_failed_inconsistent_deducted_but_completed")
    assert result.department.value == "payments_ops"


def test_department_fraud_risk_for_phishing():
    result = _run_case("phishing_pin_request")
    assert result.department.value == "fraud_risk"


def test_department_customer_support_for_insufficient_data():
    result = _run_case("empty_history_insufficient_data")
    assert result.department.value == "customer_support"


def test_department_merchant_operations():
    result = _run_case("merchant_settlement_delay")
    assert result.department.value == "merchant_operations"


def test_department_agent_operations():
    result = _run_case("agent_cash_in_not_reflected")
    assert result.department.value == "agent_operations"


def test_severity_critical_for_phishing():
    result = _run_case("phishing_pin_request")
    assert result.severity.value == "critical"


def test_severity_high_for_wrong_transfer_completed():
    """§3.3 anchor: wrong_transfer + completed → high (the 5000 BDT anchor)."""
    result = _run_case("wrong_transfer_5000_completed")
    assert result.severity.value == "high"


def test_severity_high_for_payment_failed_with_deduction_claim():
    result = _run_case("payment_failed_inconsistent_deducted_but_completed")
    assert result.severity.value == "high"


def test_severity_medium_for_duplicate_payment():
    result = _run_case("duplicate_payment_same_counterparty")
    assert result.severity.value == "medium"


# ---------------------------------------------------------------------------
# human_review_required (decision-rules §3.4)
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "name",
    [
        "wrong_transfer_5000_completed",
        "payment_failed_inconsistent_deducted_but_completed",
        "empty_history_insufficient_data",
        "phishing_pin_request",
        "duplicate_payment_same_counterparty",
        "wrong_transfer_bangla",
        "wrong_transfer_banglish",
        "prompt_injection_attempt",
        "merchant_settlement_delay",
        "agent_cash_in_not_reflected",
    ],
)
def test_human_review_required_true_for_all_worked_cases(name):
    """AC-7, AC-8: every worked sample is either a money dispute, phishing,
    ambiguous evidence, or has severity high/medium — all require human review."""
    result = _run_case(name)
    assert result.human_review_required is True


def test_phishing_always_requires_human_review():
    """AC-7: phishing case_type must always set human_review_required=true."""
    result = _run_case("phishing_pin_request")
    assert result.human_review_required is True


# ---------------------------------------------------------------------------
# Confidence + reason_codes (optional but recommended)
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("name", CASE_NAMES)
def test_confidence_in_unit_interval_when_present(name):
    result = _run_case(name)
    if result.confidence is not None:
        assert 0.0 <= result.confidence <= 1.0


@pytest.mark.parametrize("name", CASE_NAMES)
def test_reason_codes_are_strings_when_present(name):
    result = _run_case(name)
    if result.reason_codes is not None:
        assert isinstance(result.reason_codes, list)
        for code in result.reason_codes:
            assert isinstance(code, str)
            # Convention: short snake_case labels.
            assert code.replace("_", "").isalnum() or code == ""