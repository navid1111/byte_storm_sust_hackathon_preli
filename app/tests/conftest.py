"""Shared pytest fixtures.

Force the optional LLM layer OFF for every test, regardless of any local
``app/.env`` that may hold a real ``GEMINI_API_KEY`` (which ``config`` now loads
automatically). This keeps the suite fast, deterministic, and free of real
network / API calls. Tests that exercise the LLM opt back in by setting
``config.settings.gemini_api_key`` themselves (see test_llm.py).
"""

import pytest

import config


@pytest.fixture(autouse=True)
def _llm_off_by_default(monkeypatch):
    monkeypatch.setattr(config.settings, "gemini_api_key", None, raising=False)
