"""Routing: department, severity, human-review (decision-rules §3.2–§3.4).

OWNER: Shadman (T015). This is a working baseline wired in by Navid's Phase 2
orchestrator so the pipeline is complete and testable; Shadman refines the
thresholds/edge-cases in Phase 2/3.
"""

from __future__ import annotations

from models.enums import CaseType, Department, EvidenceVerdict, Severity

# Deterministic case_type → department map (decision-rules §3.2).
_DEPARTMENT_BY_CASE = {
    CaseType.PHISHING_OR_SOCIAL_ENGINEERING: Department.FRAUD_RISK,
    CaseType.WRONG_TRANSFER: Department.DISPUTE_RESOLUTION,
    CaseType.PAYMENT_FAILED: Department.PAYMENTS_OPS,
    CaseType.DUPLICATE_PAYMENT: Department.PAYMENTS_OPS,
    CaseType.MERCHANT_SETTLEMENT_DELAY: Department.MERCHANT_OPERATIONS,
    CaseType.AGENT_CASH_IN_ISSUE: Department.AGENT_OPERATIONS,
    CaseType.OTHER: Department.CUSTOMER_SUPPORT,
}

HIGH_VALUE = 25_000.0
MID_VALUE = 1_000.0


def department(case_type: CaseType, severity: Severity) -> Department:
    if case_type == CaseType.REFUND_REQUEST:
        # Contested / higher-severity refunds escalate to dispute resolution;
        # simple low-severity refunds stay with customer support (§3.2).
        return (
            Department.DISPUTE_RESOLUTION
            if severity in {Severity.HIGH, Severity.CRITICAL}
            else Department.CUSTOMER_SUPPORT
        )
    return _DEPARTMENT_BY_CASE.get(case_type, Department.CUSTOMER_SUPPORT)


def severity(case_type: CaseType, amount: float | None, verdict: EvidenceVerdict) -> Severity:
    amt = amount or 0.0
    if case_type == CaseType.PHISHING_OR_SOCIAL_ENGINEERING:
        return Severity.CRITICAL
    if amt >= HIGH_VALUE and verdict == EvidenceVerdict.CONSISTENT:
        return Severity.CRITICAL
    if case_type in {CaseType.WRONG_TRANSFER, CaseType.PAYMENT_FAILED}:
        return Severity.HIGH
    if amt >= HIGH_VALUE:
        return Severity.HIGH
    if case_type in {
        CaseType.DUPLICATE_PAYMENT,
        CaseType.MERCHANT_SETTLEMENT_DELAY,
        CaseType.AGENT_CASH_IN_ISSUE,
    }:
        return Severity.MEDIUM
    if amt >= MID_VALUE:
        return Severity.MEDIUM
    return Severity.LOW


def human_review_required(
    case_type: CaseType,
    severity: Severity,
    verdict: EvidenceVerdict,
    amount: float | None,
    user_type: str | None,
) -> bool:
    if case_type == CaseType.PHISHING_OR_SOCIAL_ENGINEERING:
        return True
    if verdict in {EvidenceVerdict.INCONSISTENT, EvidenceVerdict.INSUFFICIENT_DATA}:
        return True
    if severity in {Severity.HIGH, Severity.CRITICAL}:
        return True
    if case_type in {
        CaseType.WRONG_TRANSFER,
        CaseType.DUPLICATE_PAYMENT,
        CaseType.PAYMENT_FAILED,
    }:
        return True
    if (amount or 0.0) >= HIGH_VALUE:
        return True
    if user_type in {"merchant", "agent"} and case_type in {
        CaseType.MERCHANT_SETTLEMENT_DELAY,
        CaseType.AGENT_CASH_IN_ISSUE,
    }:
        return True
    return False
