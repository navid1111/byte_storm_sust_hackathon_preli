"""Environment-driven settings for the QueueStorm Investigator service.

Kept dependency-light (stdlib ``os`` only) so importing this module never pulls
in an LLM client or reads a network — the ``/health`` path stays instant and the
service has no cold-start penalty (plan.md §7).

Secrets (e.g. ``GEMINI_API_KEY``) come from the environment only. Locally they
live in the git-ignored ``app/.env``; in deployment they are hosting env vars.
Never commit real values — ``.env.example`` lists names only.
"""

from __future__ import annotations

import os


def _as_bool(value: str | None, default: bool = False) -> bool:
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


class Settings:
    """Runtime configuration read once from the environment."""

    def __init__(self) -> None:
        # Optional LLM layer. It auto-activates when a GEMINI_API_KEY is present
        # (so deploying only needs that one secret env var, e.g. on Render), and
        # stays off otherwise — the deterministic rule engine is the product and
        # the LLM is a fail-safe enhancement (plan.md D4). Set LLM_ENABLED=false
        # to force it off even when a key is configured.
        self.llm_enabled: bool = _as_bool(os.getenv("LLM_ENABLED"), default=True)
        self.llm_provider: str = os.getenv("LLM_PROVIDER", "gemini")
        self.gemini_api_key: str | None = os.getenv("GEMINI_API_KEY")
        self.model_name: str = os.getenv("MODEL_NAME", "gemini-2.0-flash")

        # Server / timeouts.
        self.port: int = int(os.getenv("PORT", "8000"))
        # Hard internal budget for one /analyze-ticket call, well under the
        # 30 s harness timeout (spec §9). Used to bound any LLM call.
        self.request_timeout_s: float = float(os.getenv("REQUEST_TIMEOUT_S", "8"))

    @property
    def llm_ready(self) -> bool:
        """True when a key is configured and the layer isn't explicitly disabled.

        Effectively: presence of GEMINI_API_KEY turns the LLM on. No key → off
        (safe rule-based fallback), so the default deployment needs no secrets.
        """
        return self.llm_enabled and bool(self.gemini_api_key)


settings = Settings()
