"""Request models for ``POST /analyze-ticket`` (spec §5).

Design choice (plan.md §5): only ``ticket_id`` and ``complaint`` are required and
strictly validated. Everything else is parsed leniently — optional metadata and
transaction entries are accepted as plain strings rather than strict enums so a
single odd value in optional context never rejects an otherwise-valid ticket
(AC-9 robustness). The reasoning engine interprets these fields itself.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, field_validator


class TransactionEntry(BaseModel):
    """One recent transaction (spec §5.2). All fields optional/tolerant on parse."""

    model_config = ConfigDict(extra="ignore")

    transaction_id: str | None = None
    timestamp: str | None = None
    type: str | None = None
    amount: float | None = None
    counterparty: str | None = None
    status: str | None = None


class TicketRequest(BaseModel):
    """One support ticket to analyze (spec §5.1)."""

    # The harness may send extra/unknown top-level fields (open-ended metadata);
    # ignore them rather than 422 (plan.md §5).
    model_config = ConfigDict(extra="ignore")

    ticket_id: str
    complaint: str
    language: str | None = None
    channel: str | None = None
    user_type: str | None = None
    campaign_context: str | None = None
    transaction_history: list[TransactionEntry] = []
    metadata: dict | None = None

    @field_validator("ticket_id")
    @classmethod
    def _ticket_id_not_blank(cls, v: str) -> str:
        # ticket_id must be echoed in the response, so it cannot be blank.
        if v is None or not str(v).strip():
            raise ValueError("ticket_id must be a non-empty string")
        return v

    @field_validator("complaint")
    @classmethod
    def _complaint_not_blank(cls, v: str) -> str:
        # Empty/whitespace complaint is semantically invalid → 422 (spec §4.1).
        if v is None or not str(v).strip():
            raise ValueError("complaint must be a non-empty string")
        return v
