"""Reply drafting: agent_summary, recommended_next_action, customer_reply.

OWNER: Shadman (T018/T019). Working baseline wired in by Navid's orchestrator.
Templates are **safe by construction** (decision-rules §5, spec §8): none ask for
PIN/OTP/password/card, none confirm a refund/reversal, none point to a third
party. Shadman adds the defensive sanitizer gate (S1–S4) in Phase 3.
"""

from __future__ import annotations

from models.enums import CaseType, EvidenceVerdict

_SECURITY_NOTE = "For your safety, we will never ask for your PIN, OTP, or password."
_OFFICIAL_NOTE = "Please continue only through the official bKash app or helpline."

# Per-case templates: (agent_summary, recommended_next_action, customer_reply).
_TEMPLATES = {
    CaseType.WRONG_TRANSFER: (
        "Customer reports a transfer sent to the wrong recipient{txn}.",
        "Verify the disputed transfer details and open a wrong-transfer dispute for review.",
        "We understand you may have sent money to the wrong recipient. We have logged "
        "your concern{txn} and escalated it for review. Any eligible amount will be "
        "handled through official channels. " + _SECURITY_NOTE,
    ),
    CaseType.PAYMENT_FAILED: (
        "Customer reports a failed payment with a possible balance deduction{txn}.",
        "Check the transaction status and balance ledger; raise a payments-ops reversal review if deducted.",
        "We're sorry for the trouble with your payment. We have recorded the issue{txn} "
        "and our payments team will review whether any amount was deducted. Any eligible "
        "amount will be returned through official channels. " + _SECURITY_NOTE,
    ),
    CaseType.DUPLICATE_PAYMENT: (
        "Customer reports being charged more than once for the same payment{txn}.",
        "Compare the duplicate transactions and route to payments-ops for a duplicate-charge review.",
        "Thank you for flagging a possible duplicate charge. We have noted it{txn} and "
        "our team will review the transactions. Any eligible amount will be returned "
        "through official channels. " + _SECURITY_NOTE,
    ),
    CaseType.MERCHANT_SETTLEMENT_DELAY: (
        "Merchant reports a settlement not received within the expected window{txn}.",
        "Verify the settlement cycle and escalate to merchant operations for follow-up.",
        "We understand your settlement has not arrived as expected. We have logged the "
        "issue{txn} and our merchant operations team will follow up. " + _OFFICIAL_NOTE,
    ),
    CaseType.AGENT_CASH_IN_ISSUE: (
        "Cash-in via agent not reflected in the customer balance{txn}.",
        "Confirm the agent transaction record and escalate to agent operations.",
        "We're sorry your cash-in is not yet reflected. We have recorded the details{txn} "
        "and our agent operations team will verify it. " + _OFFICIAL_NOTE,
    ),
    CaseType.REFUND_REQUEST: (
        "Customer is requesting a refund{txn}.",
        "Review refund eligibility against policy; do not promise an outcome.",
        "Thank you for reaching out about a refund. We have recorded your request{txn} "
        "and it will be reviewed for eligibility. Any eligible amount will be returned "
        "through official channels. " + _SECURITY_NOTE,
    ),
    CaseType.PHISHING_OR_SOCIAL_ENGINEERING: (
        "Possible phishing / social-engineering attempt reported by the customer{txn}.",
        "Escalate to fraud risk immediately; advise the customer to secure their account via official channels.",
        "Thank you for reporting this. It may be a scam attempt. Please do not share any "
        "codes or personal details with anyone. " + _SECURITY_NOTE + " " + _OFFICIAL_NOTE,
    ),
    CaseType.OTHER: (
        "General complaint requiring review{txn}.",
        "Review the ticket details and route to the appropriate team.",
        "Thank you for contacting us. We have received your request{txn} and our team is "
        "reviewing it. " + _SECURITY_NOTE,
    ),
}


def draft(
    case_type: CaseType,
    relevant_transaction_id: str | None,
    verdict: EvidenceVerdict,
) -> tuple[str, str, str]:
    """Return (agent_summary, recommended_next_action, customer_reply)."""
    summary_t, action_t, reply_t = _TEMPLATES.get(case_type, _TEMPLATES[CaseType.OTHER])
    txn = f" (transaction {relevant_transaction_id})" if relevant_transaction_id else ""
    summary = summary_t.format(txn=txn)
    if verdict == EvidenceVerdict.INSUFFICIENT_DATA:
        summary += " Evidence is insufficient to confirm from the provided history."
    elif verdict == EvidenceVerdict.INCONSISTENT:
        summary += " Note: transaction data appears to contradict the complaint."
    return summary, action_t, reply_t.format(txn=txn)
