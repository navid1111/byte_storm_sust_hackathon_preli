"""Investigation orchestrator (T016).

Phase 1: a safe, schema-valid placeholder so the ``/analyze-ticket`` endpoint
works end-to-end and Gate G1 is met. Phase 2 (T012–T016) replaces the body with
the real pipeline: normalize → match → verdict → classify → route → draft →
sanitize. The function signature is stable so the endpoint never changes.
"""

from __future__ import annotations

from models.request import TicketRequest
from models.response import TicketAnalysis


def analyze(ticket: TicketRequest) -> TicketAnalysis:
    """Analyze one ticket and return a structured, safe response.

    Phase 1 stub — conservative defaults: nothing is asserted from evidence yet,
    the case is flagged for human review, and the reply is safe by construction
    (no credential request, no refund promise).
    """
    return TicketAnalysis(
        ticket_id=ticket.ticket_id,
        relevant_transaction_id=None,
        evidence_verdict="insufficient_data",
        case_type="other",
        severity="low",
        department="customer_support",
        agent_summary="Ticket received and queued for analysis.",
        recommended_next_action="Review the ticket details with the customer through official channels.",
        customer_reply=(
            "Thank you for contacting us. We have received your request and our "
            "team is reviewing it. Please note we will never ask for your PIN, "
            "OTP, or password."
        ),
        human_review_required=True,
        reason_codes=["pending_analysis"],
    )
