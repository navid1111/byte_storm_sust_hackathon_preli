"""Response model for ``POST /analyze-ticket`` (spec §6).

This model is the single source of truth for schema correctness: every required
field of §6.1 is present and typed, enum fields use the exact-value enums from
``enums.py``, and ``confidence`` / ``reason_codes`` are optional. A 200 response
is only returned after a value validates against this model.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from models.enums import CaseType, Department, EvidenceVerdict, Severity


class TicketAnalysis(BaseModel):
    """Structured analysis returned to the support agent (spec §6.1)."""

    model_config = ConfigDict(extra="forbid")

    ticket_id: str
    relevant_transaction_id: str | None
    evidence_verdict: EvidenceVerdict
    case_type: CaseType
    severity: Severity
    department: Department
    agent_summary: str
    recommended_next_action: str
    customer_reply: str
    human_review_required: bool

    # Optional — improve reasoning/tie-breaker signal; absence is not a violation.
    confidence: float | None = Field(default=None, ge=0.0, le=1.0)
    reason_codes: list[str] = Field(default_factory=list)
