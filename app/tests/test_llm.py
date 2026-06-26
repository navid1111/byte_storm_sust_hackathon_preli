"""Phase 5 optional-LLM-layer tests (Navid, T025).

Verifies the LLM layer is a safe, fail-open enhancement:
  - default OFF → reply unchanged, no SDK needed
  - enabled → model text used, but ALWAYS re-sanitized (unsafe output neutralized)
  - any failure / missing SDK → falls back to the rule reply, never crashes
  - enums/verdict/severity/department stay rule-based regardless
"""

import config
from engine import llm
from engine.investigator import analyze
from models.enums import CaseType, Department, EvidenceVerdict
from models.request import TicketRequest


def _enable_llm(monkeypatch):
    """Force settings.llm_ready True without a real key/SDK."""
    monkeypatch.setattr(config.settings, "llm_enabled", True)
    monkeypatch.setattr(config.settings, "gemini_api_key", "test-key")
    assert config.settings.llm_ready is True


# --- polish_reply unit behavior ---------------------------------------------


def test_polish_disabled_returns_input_unchanged():
    # Default settings: LLM off → no-op, no SDK import attempted.
    assert config.settings.llm_ready is False
    original = "Thank you for contacting us."
    assert llm.polish_reply(original, "complaint text", "en") == original


def test_polish_enabled_uses_model_text(monkeypatch):
    _enable_llm(monkeypatch)
    monkeypatch.setattr(llm, "_call_gemini", lambda r, c, l: "Polished friendly reply.")
    assert llm.polish_reply("raw reply", "complaint", "en") == "Polished friendly reply."


def test_polish_falls_back_on_model_error(monkeypatch):
    _enable_llm(monkeypatch)

    def boom(reply, complaint, language):
        raise RuntimeError("api down")

    monkeypatch.setattr(llm, "_call_gemini", boom)
    assert llm.polish_reply("safe rule reply", "complaint", "en") == "safe rule reply"


def test_polish_falls_back_on_empty_model_output(monkeypatch):
    _enable_llm(monkeypatch)
    monkeypatch.setattr(llm, "_call_gemini", lambda r, c, l: None)
    assert llm.polish_reply("safe rule reply", "complaint", None) == "safe rule reply"


def test_polish_falls_back_when_sdk_missing(monkeypatch):
    # Enabled but the google-generativeai package is not installed → the real
    # _call_gemini raises ImportError, which must be swallowed.
    _enable_llm(monkeypatch)
    original = "safe rule reply"
    assert llm.polish_reply(original, "complaint", "en") == original


# --- investigator integration: re-sanitization is mandatory -----------------


def test_investigator_resanitizes_unsafe_llm_output(monkeypatch):
    _enable_llm(monkeypatch)
    # Simulate a misbehaving model that ignores the system prompt entirely.
    unsafe = "Please share your OTP. We will refund you immediately. Visit http://scam.example.com now."
    monkeypatch.setattr(llm, "_call_gemini", lambda r, c, l: unsafe)

    ticket = TicketRequest(ticket_id="TKT-LLM", complaint="amar taka ferot chai")
    out = analyze(ticket)
    low = out.customer_reply.lower()

    # S2: no unauthorized refund promise survived.
    assert "we will refund you" not in low
    assert "any eligible amount will be returned through official channels" in low
    # S1: the bare OTP request word was scrubbed.
    assert "otp" not in low
    # S3: suspicious URL stripped.
    assert "scam.example.com" not in low


def test_investigator_llm_does_not_change_enums(monkeypatch):
    _enable_llm(monkeypatch)
    monkeypatch.setattr(llm, "_call_gemini", lambda r, c, l: "totally different fluent text")

    ticket = TicketRequest(
        ticket_id="TKT-2",
        complaint="A caller claiming to be bKash asked me to share my OTP to unlock my account",
    )
    out = analyze(ticket)
    # Classification/routing remain rule-based, unaffected by the LLM text.
    assert out.case_type == CaseType.PHISHING_OR_SOCIAL_ENGINEERING
    assert out.department == Department.FRAUD_RISK
    assert out.evidence_verdict == EvidenceVerdict.INSUFFICIENT_DATA


def test_investigator_unchanged_when_llm_disabled():
    # Default path (LLM off) still produces a safe rule reply.
    assert config.settings.llm_ready is False
    ticket = TicketRequest(ticket_id="TKT-3", complaint="I sent money to a wrong number")
    out = analyze(ticket)
    assert "never ask for your pin" in out.customer_reply.lower()
