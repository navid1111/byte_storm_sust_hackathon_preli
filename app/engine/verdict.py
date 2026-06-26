"""Evidence verdict (T013, decision-rules §2).

Decides whether the matched transaction supports, contradicts, or cannot confirm
the complaint. Conservative by design: on a weak/no match we say
``insufficient_data`` rather than guess.
"""

from __future__ import annotations

from engine import lexicon
from engine.matcher import MatchResult
from models.enums import EvidenceVerdict


def decide(complaint: str, match: MatchResult, history: list[TransactionEntry]) -> EvidenceVerdict:
    # No entry cleared the match threshold → cannot verify from history.
    if match.entry is None:
        return EvidenceVerdict.INSUFFICIENT_DATA

    norm = lexicon.normalize(complaint)
    status = (match.entry.status or "").lower()

    claims_failure = lexicon.contains_any(norm, lexicon.FAILED_CUES)
    claims_not_received = lexicon.contains_any(norm, lexicon.NOT_RECEIVED_CUES)

    # 1. Establish contradiction for Wrong Transfer:
    # If the user claims wrong transfer, but has successfully sent money
    # to this exact same counterparty in the past, it's an established
    # recipient pattern, which contradicts the wrong transfer claim.
    is_wrong_transfer = lexicon.contains_any(norm, lexicon.WRONG_NUMBER_CUES) or (
        lexicon.contains_any(norm, lexicon.TRANSFER_CUES)
        and (
            lexicon.contains_any(norm, ["brother", "friend", "sister", "mother", "father", "he says"])
            or lexicon.contains_any(norm, lexicon.NOT_RECEIVED_CUES)
            or "didn't get" in norm
            or "did not get" in norm
        )
    )
    if is_wrong_transfer and match.entry.type == "transfer":
        same_counterparty_txns = [
            t for t in history 
            if t.transaction_id != match.entry.transaction_id 
            and t.type == "transfer"
            and t.status == "completed"
            and t.counterparty == match.entry.counterparty
        ]
        if len(same_counterparty_txns) > 0:
            return EvidenceVerdict.INCONSISTENT

    # 2. Data contradicts the claim: customer says it failed / never arrived, but
    # the matched transaction completed successfully.
    if status == "completed" and (claims_failure or claims_not_received):
        return EvidenceVerdict.INCONSISTENT

    # 3. Data supports a failure claim: status failed/pending/reversed matches it.
    if status in {"failed", "pending", "reversed"} and claims_failure:
        return EvidenceVerdict.CONSISTENT

    # A concrete transaction matched the complaint's amount/recipient/type.
    return EvidenceVerdict.CONSISTENT
