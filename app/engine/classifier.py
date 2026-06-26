"""Case-type classification (T014, decision-rules §3.1).

First-match-wins ordering, with phishing/social-engineering checked first so a
fraud report is never mislabeled as an ordinary transaction issue (§5).
"""

from __future__ import annotations

from engine import lexicon
from engine.matcher import MatchResult
from models.enums import CaseType


def _looks_duplicate(norm: str, match: MatchResult, history) -> bool:
    if not lexicon.contains_any(norm, lexicon.DUPLICATE_CUES):
        return False
    # Corroborate with two history entries sharing amount + counterparty.
    seen: set[tuple] = set()
    for e in history:
        key = (e.amount, e.counterparty)
        if e.amount is not None and key in seen:
            return True
        seen.add(key)
    # Keyword alone is still enough to flag a duplicate complaint.
    return True


def classify(complaint: str, match: MatchResult, history, user_type: str | None) -> CaseType:
    norm = lexicon.normalize(complaint)
    status = (match.entry.status or "").lower() if match.entry else ""

    # 1. Phishing / social engineering — overrides everything (§5).
    if lexicon.contains_any(norm, lexicon.PHISHING_CUES):
        return CaseType.PHISHING_OR_SOCIAL_ENGINEERING

    # 2. Duplicate payment.
    if _looks_duplicate(norm, match, history):
        return CaseType.DUPLICATE_PAYMENT

    # 3. Wrong transfer.
    if lexicon.contains_any(norm, lexicon.WRONG_NUMBER_CUES):
        return CaseType.WRONG_TRANSFER

    # 4. Payment failed / deducted but failed.
    is_agent = lexicon.contains_any(norm, lexicon.CASH_IN_CUES) or (
        lexicon.contains_any(norm, lexicon.AGENT_CUES) and (
            user_type == "agent" or "cash" in norm or "balance" in norm or "deposit" in norm
        )
    )
    is_merchant = lexicon.contains_any(norm, lexicon.SETTLEMENT_CUES) or (
        lexicon.contains_any(norm, lexicon.MERCHANT_CUES) and user_type == "merchant"
    )
    if not is_agent and not is_merchant:
        if lexicon.contains_any(norm, lexicon.FAILED_CUES) or status in {"failed", "pending"}:
            return CaseType.PAYMENT_FAILED

    # 5. Agent cash-in issue.
    if is_agent:
        return CaseType.AGENT_CASH_IN_ISSUE

    # 6. Merchant settlement delay.
    if is_merchant:
        return CaseType.MERCHANT_SETTLEMENT_DELAY

    # 7. Refund request (no fraud cue).
    if lexicon.contains_any(norm, lexicon.REFUND_CUES):
        return CaseType.REFUND_REQUEST

    # 8. Anything else.
    return CaseType.OTHER
