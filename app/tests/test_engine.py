"""Phase 2 reasoning-engine unit tests (Navid).

Covers matcher / verdict / classifier / router / reply and the end-to-end
investigator, against decision-rules.md. Jyoti's T017 adds fixture-driven cases.
"""

from engine import classifier, matcher, reply, router, verdict
from engine.investigator import analyze
from models.enums import CaseType, Department, EvidenceVerdict, Severity
from models.request import TicketRequest, TransactionEntry


def _txn(**kw):
    return TransactionEntry(**kw)


WRONG_TRANSFER_TXN = _txn(
    transaction_id="TXN-9101",
    timestamp="2026-04-14T14:08:22Z",
    type="transfer",
    amount=5000,
    counterparty="+8801719876543",
    status="completed",
)


# --- matcher (decision-rules §1) --------------------------------------------


def test_match_amount_and_recency():
    r = matcher.match("I sent 5000 taka to a wrong number around 2pm today", [WRONG_TRANSFER_TXN])
    assert r.transaction_id == "TXN-9101"
    assert "amount_match" in r.cues
    assert r.score >= matcher.MATCH_THRESHOLD


def test_match_empty_history_returns_none():
    r = matcher.match("anything", [])
    assert r.transaction_id is None
    assert r.entry is None


def test_match_no_strong_cue_returns_none():
    # Only a vague intent word, no amount/counterparty → below threshold.
    r = matcher.match("I made a transfer", [WRONG_TRANSFER_TXN])
    assert r.transaction_id is None


def test_match_by_counterparty_tail():
    r = matcher.match("I paid the number ending 6543 by transfer", [WRONG_TRANSFER_TXN])
    assert r.transaction_id == "TXN-9101"
    assert "counterparty_match" in r.cues


def test_match_picks_best_of_multiple():
    other = _txn(transaction_id="TXN-1", type="payment", amount=99, status="completed")
    r = matcher.match("sent 5000 to wrong number today", [other, WRONG_TRANSFER_TXN])
    assert r.transaction_id == "TXN-9101"


# --- verdict (decision-rules §2) --------------------------------------------


def test_verdict_consistent_for_matched_transfer():
    history = [WRONG_TRANSFER_TXN]
    r = matcher.match("sent 5000 to wrong number", history)
    assert verdict.decide("sent 5000 to wrong number", r, history) == EvidenceVerdict.CONSISTENT


def test_verdict_inconsistent_when_completed_but_claims_failure():
    history = [WRONG_TRANSFER_TXN]
    r = matcher.match("my 5000 payment failed but money deducted", history)
    assert verdict.decide("my 5000 payment failed but money deducted", r, history) == EvidenceVerdict.INCONSISTENT


def test_verdict_consistent_when_failed_status_matches_claim():
    failed = _txn(transaction_id="TXN-2", type="payment", amount=300, status="failed")
    history = [failed]
    r = matcher.match("payment of 300 failed", history)
    assert verdict.decide("payment of 300 failed", r, history) == EvidenceVerdict.CONSISTENT


def test_verdict_insufficient_when_no_match():
    history = []
    r = matcher.match("hello there", history)
    assert verdict.decide("hello there", r, history) == EvidenceVerdict.INSUFFICIENT_DATA


# --- classifier (decision-rules §3.1, §5) -----------------------------------


def test_classify_phishing_takes_precedence():
    r = matcher.match("someone called asking for my OTP and pin", [])
    assert classifier.classify("someone called asking for my OTP and pin", r, [], "customer") == CaseType.PHISHING_OR_SOCIAL_ENGINEERING


def test_classify_wrong_transfer():
    r = matcher.match("sent to wrong number", [])
    assert classifier.classify("sent to wrong number", r, [], None) == CaseType.WRONG_TRANSFER


def test_classify_payment_failed_by_status():
    failed = _txn(transaction_id="TXN-2", type="payment", amount=300, status="failed")
    r = matcher.match("payment of 300", [failed])
    assert classifier.classify("payment of 300", r, [failed], None) == CaseType.PAYMENT_FAILED


def test_classify_duplicate():
    r = matcher.match("charged twice for the same thing", [])
    assert classifier.classify("charged twice for the same thing", r, [], None) == CaseType.DUPLICATE_PAYMENT


def test_classify_refund():
    r = matcher.match("I want a refund please", [])
    assert classifier.classify("I want a refund please", r, [], None) == CaseType.REFUND_REQUEST


def test_classify_agent_cash_in():
    r = matcher.match("cash in via agent not showing", [])
    assert classifier.classify("cash in via agent not showing", r, [], "agent") == CaseType.AGENT_CASH_IN_ISSUE


def test_classify_merchant_settlement():
    r = matcher.match("settlement not received", [])
    assert classifier.classify("settlement not received", r, [], "merchant") == CaseType.MERCHANT_SETTLEMENT_DELAY


def test_classify_other():
    r = matcher.match("the app is confusing", [])
    assert classifier.classify("the app is confusing", r, [], None) == CaseType.OTHER


# --- router (decision-rules §3.2–§3.4) --------------------------------------


def test_severity_phishing_is_critical():
    assert router.severity(CaseType.PHISHING_OR_SOCIAL_ENGINEERING, None, EvidenceVerdict.INSUFFICIENT_DATA) == Severity.CRITICAL


def test_severity_wrong_transfer_is_high():
    assert router.severity(CaseType.WRONG_TRANSFER, 5000, EvidenceVerdict.CONSISTENT) == Severity.HIGH


def test_severity_high_value_consistent_is_critical():
    assert router.severity(CaseType.REFUND_REQUEST, 30000, EvidenceVerdict.CONSISTENT) == Severity.CRITICAL


def test_severity_mid_value_is_medium():
    assert router.severity(CaseType.OTHER, 2000, EvidenceVerdict.CONSISTENT) == Severity.MEDIUM


def test_severity_low_default():
    assert router.severity(CaseType.OTHER, 50, EvidenceVerdict.CONSISTENT) == Severity.LOW


def test_department_map_and_refund_escalation():
    assert router.department(CaseType.WRONG_TRANSFER, Severity.HIGH) == Department.DISPUTE_RESOLUTION
    assert router.department(CaseType.REFUND_REQUEST, Severity.LOW) == Department.CUSTOMER_SUPPORT
    assert router.department(CaseType.REFUND_REQUEST, Severity.HIGH) == Department.DISPUTE_RESOLUTION
    assert router.department(CaseType.PAYMENT_FAILED, Severity.HIGH) == Department.PAYMENTS_OPS


def test_human_review_rules():
    assert router.human_review_required(CaseType.PHISHING_OR_SOCIAL_ENGINEERING, Severity.CRITICAL, EvidenceVerdict.INSUFFICIENT_DATA, None, None) is True
    assert router.human_review_required(CaseType.OTHER, Severity.LOW, EvidenceVerdict.INSUFFICIENT_DATA, None, None) is False
    assert router.human_review_required(CaseType.REFUND_REQUEST, Severity.LOW, EvidenceVerdict.CONSISTENT, 100, "customer") is False
    assert router.human_review_required(CaseType.MERCHANT_SETTLEMENT_DELAY, Severity.MEDIUM, EvidenceVerdict.CONSISTENT, 500, "merchant") is False
    assert router.human_review_required(CaseType.WRONG_TRANSFER, Severity.HIGH, EvidenceVerdict.CONSISTENT, 5000, "customer", relevant_transaction_id="TXN-1") is True
    assert router.human_review_required(CaseType.WRONG_TRANSFER, Severity.MEDIUM, EvidenceVerdict.INSUFFICIENT_DATA, None, "customer", relevant_transaction_id=None) is False


# --- reply (safe by construction, spec §8) ----------------------------------


def test_reply_is_safe_and_interpolates_txn():
    summary, action, customer = reply.draft(CaseType.WRONG_TRANSFER, "TXN-9101", EvidenceVerdict.CONSISTENT)
    assert "TXN-9101" in summary and "TXN-9101" in customer
    low = customer.lower()
    assert "never ask for your pin" in low
    assert "we will refund" not in low


def test_reply_notes_insufficient_and_inconsistent():
    s1, _, _ = reply.draft(CaseType.OTHER, None, EvidenceVerdict.INSUFFICIENT_DATA)
    assert "insufficient" in s1.lower()
    s2, _, _ = reply.draft(CaseType.PAYMENT_FAILED, "TXN-2", EvidenceVerdict.INCONSISTENT)
    assert "contradict" in s2.lower()


# --- investigator end-to-end (spec §6 worked example) -----------------------


def test_investigator_spec_example():
    ticket = TicketRequest(
        ticket_id="TKT-001",
        complaint="I sent 5000 taka to a wrong number around 2pm today",
        transaction_history=[WRONG_TRANSFER_TXN],
    )
    out = analyze(ticket)
    assert out.ticket_id == "TKT-001"
    assert out.relevant_transaction_id == "TXN-9101"
    assert out.evidence_verdict == EvidenceVerdict.CONSISTENT
    assert out.case_type == CaseType.WRONG_TRANSFER
    assert out.severity == Severity.HIGH
    assert out.department == Department.DISPUTE_RESOLUTION
    assert out.human_review_required is True
    assert "never ask for your pin" in out.customer_reply.lower()
    assert 0.0 <= out.confidence <= 1.0


def test_investigator_phishing_routes_to_fraud_risk():
    ticket = TicketRequest(
        ticket_id="TKT-2",
        complaint="A caller claiming to be bKash asked me to share my OTP to unlock my account",
    )
    out = analyze(ticket)
    assert out.case_type == CaseType.PHISHING_OR_SOCIAL_ENGINEERING
    assert out.department == Department.FRAUD_RISK
    assert out.severity == Severity.CRITICAL
    assert out.human_review_required is True


def test_investigator_empty_history_insufficient():
    ticket = TicketRequest(ticket_id="TKT-3", complaint="kichu ekta hoise, bujhtesi na")
    out = analyze(ticket)
    assert out.relevant_transaction_id is None
    assert out.evidence_verdict == EvidenceVerdict.INSUFFICIENT_DATA
    assert out.human_review_required is False


def test_investigator_bangla_refund():
    ticket = TicketRequest(
        ticket_id="TKT-4",
        complaint="আমার টাকা ফেরত চাই",
        language="bn",
    )
    out = analyze(ticket)
    assert out.case_type == CaseType.REFUND_REQUEST
    assert "we will refund" not in out.customer_reply.lower()
