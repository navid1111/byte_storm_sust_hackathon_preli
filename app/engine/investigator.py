"""Investigation orchestrator (T016).

Runs the deterministic pipeline (plan.md §4) for one ticket:
normalize → match → verdict → classify → route → draft → assemble.
Every numeric boundary lives in ``decision-rules.md`` and is implemented in the
stage modules; this file only wires them together and never crashes the request.

Safety note: reply templates are safe by construction. Shadman's sanitizer
(safety.py, T019/T020) will be layered in front of the assembled text in Phase 3.
"""

from __future__ import annotations

from engine import classifier, matcher, reply, router, verdict
from models.request import TicketRequest
from models.response import TicketAnalysis


def analyze(ticket: TicketRequest) -> TicketAnalysis:
    history = ticket.transaction_history or []

    # 1–2. Match the complaint to a transaction.
    match_result = matcher.match(ticket.complaint, history)

    # 3. Evidence verdict.
    evidence_verdict = verdict.decide(ticket.complaint, match_result)

    # 4. Case type.
    case_type = classifier.classify(
        ticket.complaint, match_result, history, ticket.user_type
    )

    # 5. Route: severity → department → human review.
    amount = match_result.entry.amount if match_result.entry else None
    severity = router.severity(case_type, amount, evidence_verdict)
    department = router.department(case_type, severity)
    human_review = router.human_review_required(
        case_type, severity, evidence_verdict, amount, ticket.user_type
    )

    # 6. Draft safe agent + customer text.
    agent_summary, next_action, customer_reply = reply.draft(
        case_type, match_result.transaction_id, evidence_verdict
    )
    from engine.safety import sanitize_customer_reply, sanitize_recommended_next_action
    customer_reply = sanitize_customer_reply(customer_reply)
    next_action = sanitize_recommended_next_action(next_action)

    # Optional LLM fluency pass (T025) — default OFF. Only the customer reply text
    # is polished; enums/verdict/safety stay rule-based. The result is re-sanitized
    # so the model can never introduce an unsafe reply.
    from config import settings as _settings

    if _settings.llm_ready:
        from engine import llm

        customer_reply = sanitize_customer_reply(
            llm.polish_reply(customer_reply, ticket.complaint, ticket.language)
        )

    # 7. Reason codes + confidence.
    reason_codes = [case_type.value, *match_result.cues, evidence_verdict.value]
    confidence = _confidence(match_result.score, evidence_verdict)

    return TicketAnalysis(
        ticket_id=ticket.ticket_id,
        relevant_transaction_id=match_result.transaction_id,
        evidence_verdict=evidence_verdict,
        case_type=case_type,
        severity=severity,
        department=department,
        agent_summary=agent_summary,
        recommended_next_action=next_action,
        customer_reply=customer_reply,
        human_review_required=human_review,
        confidence=confidence,
        reason_codes=reason_codes,
    )


def _confidence(score: float, evidence_verdict) -> float:
    """Rough confidence: strong match → higher; insufficient data → low."""
    from models.enums import EvidenceVerdict

    if evidence_verdict == EvidenceVerdict.INSUFFICIENT_DATA:
        return round(min(0.5, 0.3 + score), 2)
    return round(min(0.95, 0.6 + score), 2)
