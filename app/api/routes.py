"""API routes: ``GET /health`` and ``POST /analyze-ticket`` (T007, T008)."""

from __future__ import annotations

from fastapi import APIRouter

from engine.investigator import analyze
from models.request import TicketRequest
from models.response import TicketAnalysis

router = APIRouter()


@router.get("/health")
def health() -> dict[str, str]:
    """Liveness probe — dependency-free so it answers within 60 s of start (AC-1)."""
    return {"status": "ok"}


@router.post("/analyze-ticket", response_model=TicketAnalysis)
def analyze_ticket(ticket: TicketRequest) -> TicketAnalysis:
    """Investigate one ticket and return a structured analysis (spec §6).

    ``response_model`` guarantees the body validates and enums serialize to their
    exact string values before a 200 is returned.
    """
    return analyze(ticket)
