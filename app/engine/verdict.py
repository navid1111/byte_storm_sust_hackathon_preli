"""Evidence verdict (T013, decision-rules §2).

Decides whether the matched transaction supports, contradicts, or cannot confirm
the complaint. Conservative by design: on a weak/no match we say
``insufficient_data`` rather than guess.
"""

from __future__ import annotations

from engine import lexicon
from engine.matcher import MatchResult
from models.enums import EvidenceVerdict


def decide(complaint: str, match: MatchResult) -> EvidenceVerdict:
    # No entry cleared the match threshold → cannot verify from history.
    if match.entry is None:
        return EvidenceVerdict.INSUFFICIENT_DATA

    norm = lexicon.normalize(complaint)
    status = (match.entry.status or "").lower()

    claims_failure = lexicon.contains_any(norm, lexicon.FAILED_CUES)
    claims_not_received = lexicon.contains_any(norm, lexicon.NOT_RECEIVED_CUES)

    # Data contradicts the claim: customer says it failed / never arrived, but
    # the matched transaction completed successfully.
    if status == "completed" and (claims_failure or claims_not_received):
        return EvidenceVerdict.INCONSISTENT

    # Data supports a failure claim: status failed/pending/reversed matches it.
    if status in {"failed", "pending", "reversed"} and claims_failure:
        return EvidenceVerdict.CONSISTENT

    # A concrete transaction matched the complaint's amount/recipient/type.
    return EvidenceVerdict.CONSISTENT
