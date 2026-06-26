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


def _load_dotenv(path: str) -> None:
    """Minimal stdlib .env loader — no third-party dependency.

    Populates ``os.environ`` from a ``KEY=VALUE`` file for keys that are not
    already set, so real platform env vars (e.g. Render's Environment tab) always
    win over the file. No-op when the file is absent (the deployed case), so it
    is safe everywhere. This is why setting ``app/.env`` locally now takes effect.
    """
    try:
        with open(path, encoding="utf-8") as fh:
            for raw in fh:
                line = raw.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, _, value = line.partition("=")
                os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))
    except FileNotFoundError:
        pass


# Load app/.env (sits next to this file) before settings are read. Real
# environment variables take precedence; absent file is fine.
_load_dotenv(os.path.join(os.path.dirname(__file__), ".env"))


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
        self.model_name: str = os.getenv("MODEL_NAME", "gemini-2.5-flash-lite")

        # Server / timeouts.
        self.port: int = int(os.getenv("PORT", "8000"))
        # Hard internal budget for one /analyze-ticket call, well under the
        # 30 s harness timeout (spec §9). Used to bound any LLM call. Gemini
        # reply-polishing latency is ~6-9 s, so this is set above that with margin
        # while staying well under the 30 s hard limit.
        self.request_timeout_s: float = float(
            os.getenv("REQUEST_TIMEOUT_S") or os.getenv("REQUEST_TIMEOUT_SECONDS") or "18"
        )

    @property
    def llm_ready(self) -> bool:
        """True when a key is configured and the layer isn't explicitly disabled.

        Effectively: presence of GEMINI_API_KEY turns the LLM on. No key → off
        (safe rule-based fallback), so the default deployment needs no secrets.
        """
        return self.llm_enabled and bool(self.gemini_api_key)


settings = Settings()
