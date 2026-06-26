"""Transaction matching → ``relevant_transaction_id`` (T012, decision-rules §1).

Scores every entry in ``transaction_history`` against cues extracted from the
complaint and returns the best entry above threshold, or ``None``. **Never
invents an ID** that is not in the provided history (AC-4).
"""

from __future__ import annotations

from dataclasses import dataclass, field

from engine import lexicon
from models.request import TransactionEntry

# Cue weights (decision-rules §1.1).
W_AMOUNT = 0.45
W_TYPE = 0.25
W_COUNTERPARTY = 0.20
W_RECENCY = 0.10

# Claim a match only above this score AND with a strong cue (amount/counterparty).
MATCH_THRESHOLD = 0.45


@dataclass
class MatchResult:
    transaction_id: str | None
    entry: TransactionEntry | None
    score: float
    cues: list[str] = field(default_factory=list)


def _detected_txn_types(norm: str) -> set[str]:
    """Transaction types implied by intent words in the complaint."""
    types: set[str] = set()
    if lexicon.contains_any(norm, lexicon.TRANSFER_CUES + lexicon.WRONG_NUMBER_CUES):
        types.add("transfer")
    if lexicon.contains_any(norm, lexicon.REFUND_CUES):
        types.add("refund")
    if lexicon.contains_any(norm, lexicon.CASH_IN_CUES):
        types.add("cash_in")
    if lexicon.contains_any(norm, lexicon.SETTLEMENT_CUES):
        types.add("settlement")
    return types


def _most_recent_index(history: list[TransactionEntry]) -> int | None:
    """Index of the entry with the latest ISO timestamp (string compare is safe
    for ISO 8601). Falls back to last entry when timestamps are missing."""
    best_i, best_ts = None, ""
    for i, e in enumerate(history):
        ts = e.timestamp or ""
        if best_i is None or ts > best_ts:
            best_i, best_ts = i, ts
    return best_i


def match(complaint: str, history: list[TransactionEntry]) -> MatchResult:
    if not history:
        return MatchResult(None, None, 0.0, ["empty_history"])

    norm = lexicon.normalize(complaint)
    amounts = lexicon.extract_amounts(norm)
    number_tails = set(lexicon.extract_number_tails(norm))
    intent_types = _detected_txn_types(norm)
    has_time_cue = lexicon.contains_any(norm, lexicon.TODAY_TIME_CUES)
    recent_i = _most_recent_index(history)

    scored: list[tuple[float, bool, str, int, TransactionEntry, list[str]]] = []
    for i, entry in enumerate(history):
        score = 0.0
        cues: list[str] = []
        amount_match = False
        counterparty_match = False

        if entry.amount is not None and any(abs(a - entry.amount) <= 1 for a in amounts):
            score += W_AMOUNT
            amount_match = True
            cues.append("amount_match")

        if entry.type and entry.type in intent_types:
            score += W_TYPE
            cues.append("type_match")

        tail = lexicon.digit_tail(entry.counterparty)
        if tail and tail in number_tails:
            score += W_COUNTERPARTY
            counterparty_match = True
            cues.append("counterparty_match")

        if has_time_cue and i == recent_i:
            score += W_RECENCY
            cues.append("recency_match")

        strong = amount_match or counterparty_match
        # Sort key components: score, strong-cue, amount-match (tie-break),
        # timestamp (recency tie-break). Negative index keeps earlier entries
        # first on a full tie (stable).
        scored.append((score, strong, amount_match, entry.timestamp or "", entry, cues, i))  # type: ignore[arg-type]

    # Tie-break order (decision-rules §1.2): score desc, then amount-matched,
    # then most recent timestamp, then first in array.
    scored.sort(key=lambda t: (t[0], t[2], t[3], -t[6]), reverse=True)
    best = scored[0]
    score, strong, _amount_match, _ts, entry, cues, _i = best

    if score >= MATCH_THRESHOLD and strong:
        return MatchResult(entry.transaction_id, entry, score, cues or ["matched"])
    return MatchResult(None, None, score, ["no_match"])
