"""Centralized FastAPI exception handlers.

Goal: every error response is a small, predictable JSON object that never
leaks stack traces, file paths, tokens, or request bodies.

Body shape (uniform across all handlers):
    {
        "detail": "<safe human-readable message>",
        "code":   "<machine-readable code>"
    }

Status-code map (per T009 spec):
    * Invalid JSON / malformed body           -> 400  (code="invalid_json")
    * Missing required field (ticket_id,
      complaint, etc.)                        -> 400  (code="missing_field")
    * Empty / whitespace-only `complaint`     -> 422  (code="empty_complaint")
    * Other Pydantic / semantic validation   -> 422  (code="validation_error")
    * Explicit `HTTPException`                -> its status code, safe message
    * Anything unexpected                     -> 500  (code="internal_error")
"""
from __future__ import annotations

import logging
from typing import Any, Iterable

from fastapi import FastAPI, HTTPException, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

logger = logging.getLogger(__name__)

# Fields that are mandatory on every ticket. Keep in sync with T003 (Navid).
# The list is checked generically so T009 works before T003 lands.
_REQUIRED_FIELDS = frozenset({"ticket_id", "complaint"})

# A conservative maximum length for any user-supplied string we echo back.
# Anything longer is truncated so we never blow up the response or leak a
# huge body. Status code strings stay well under this.
_MAX_DETAIL_LEN = 200

# Regex of common secret-shaped tokens (key=, secret=, token=, password=)
# used to scrub developer-supplied messages before they're returned to the
# caller. Compiled once at import time.
import re

_SECRET_PATTERNS = (
    re.compile(
        r"(?i)\b(api[_-]?key|secret|token|password|passwd|pwd|access[_-]?key)"
        r"\s*[:=]\s*[^\s,;]+"
    ),
    re.compile(r"(?i)\bbearer\s+[A-Za-z0-9._\-+/=]+"),
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _safe_detail(message: str) -> str:
    """Normalize a message into something safe to return to the caller.

    Strips control characters, scrubs known secret patterns, truncates to a
    fixed length, and returns an opaque fallback if the message is empty
    after normalization. Never propagates raw user input beyond a short
    sentence.
    """
    if not message:
        return "invalid request"
    text = str(message)
    for pat in _SECRET_PATTERNS:
        text = pat.sub("[REDACTED]", text)
    # Collapse whitespace; drop control chars that could break JSON or logs.
    cleaned = " ".join(text.split())
    if len(cleaned) > _MAX_DETAIL_LEN:
        cleaned = cleaned[: _MAX_DETAIL_LEN - 1] + "\u2026"
    return cleaned


def _flatten_errors(errors: Iterable[Any]) -> list[dict[str, Any]]:
    """Pull Pydantic / FastAPI error items into plain dicts.

    `errors` may contain tuples (FastAPI legacy) or dicts (current).
    We don't introspect deeply — we only need `loc`, `type`, and `msg`.
    """
    out: list[dict[str, Any]] = []
    for err in errors:
        if isinstance(err, dict):
            out.append(
                {
                    "loc": list(err.get("loc") or []),
                    "type": str(err.get("type") or ""),
                    "msg": str(err.get("msg") or ""),
                }
            )
        else:  # tuple / list fallback
            loc, type_, msg = (list(err) + [[], "", ""])[:3]
            out.append({"loc": list(loc), "type": str(type_), "msg": str(msg)})
    return out


def _is_invalid_json_error(errors: list[dict[str, Any]]) -> bool:
    """Detect Pydantic's 'Invalid JSON' / 'JSON decode' style errors."""
    for e in errors:
        etype = e.get("type", "").lower()
        # Pydantic v2: "json_invalid"; Starlette/FastAPI legacy: "value_error.jsondecode"
        if "json" in etype and ("invalid" in etype or "decode" in etype):
            return True
        # Some Starlette versions emit a bare ValueError for bad JSON
        if etype in {"value_error", "type_error"} and "json" in e.get("msg", "").lower():
            return True
    return False


def _is_missing_required_field_error(
    errors: list[dict[str, Any]], required: frozenset[str] = _REQUIRED_FIELDS
) -> tuple[bool, str | None]:
    """Return (True, field_name) if any required field is missing entirely.

    "Missing entirely" = the error's `loc` ends with the field name and the
    type indicates missing. Pydantic raises "missing" for absent fields and
    "string_too_short" / "value_error.any_str.min_length" for empty strings.
    We only treat `missing` here — empty-string complaints fall under
    `_is_empty_complaint_error`.
    """
    for e in errors:
        loc = e.get("loc") or []
        if not loc:
            continue
        field = str(loc[-1])
        etype = e.get("type", "")
        if field in required and etype == "missing":
            return True, field
    return False, None


def _is_empty_complaint_error(errors: list[dict[str, Any]]) -> bool:
    """Detect an empty / whitespace-only `complaint` after coercion."""
    for e in errors:
        loc = e.get("loc") or []
        if not loc:
            continue
        field = str(loc[-1])
        if field != "complaint":
            continue
        etype = e.get("type", "")
        msg = e.get("msg", "").lower()
        # Pydantic v2: "string_too_short" when min_length fails; also catch
        # value_error from a custom validator and legacy "value_error.any_str.min_length".
        if "string_too_short" in etype:
            return True
        if etype == "value_error" and ("empty" in msg or "min_length" in msg):
            return True
    return False


def _summarize_validation_error(
    errors: list[dict[str, Any]],
) -> tuple[int, str, str]:
    """Classify a RequestValidationError.

    Returns (status_code, code, human_detail).
    """
    if _is_invalid_json_error(errors):
        return status.HTTP_400_BAD_REQUEST, "invalid_json", "request body is not valid JSON"
    missing = _is_missing_required_field_error(errors)
    if missing[0]:
        return (
            status.HTTP_400_BAD_REQUEST,
            "missing_field",
            f"required field '{missing[1]}' is missing",
        )
    if _is_empty_complaint_error(errors):
        return (
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            "empty_complaint",
            "'complaint' must not be empty",
        )
    return (
        status.HTTP_422_UNPROCESSABLE_ENTITY,
        "validation_error",
        "request did not pass validation",
    )


# ---------------------------------------------------------------------------
# Handlers
# ---------------------------------------------------------------------------
async def _request_validation_handler(
    request: Request, exc: Exception
) -> JSONResponse:
    """Pydantic / FastAPI request-body validation errors.

    Status 400 for malformed JSON / missing required fields.
    Status 422 for semantic validation failures (including empty complaint).
    """
    raw_errors = getattr(exc, "errors", lambda: [])()  # type: ignore[attr-defined]
    errors = _flatten_errors(raw_errors)
    code_status, code, detail = _summarize_validation_error(errors)

    # Log enough for ops, never enough to leak.
    logger.info(
        "request_validation_error",
        extra={
            "path": request.url.path,
            "method": request.method,
            "code": code,
            "error_count": len(errors),
        },
    )

    return JSONResponse(
        status_code=code_status,
        content={"detail": _safe_detail(detail), "code": code},
    )


async def _http_exception_handler(
    request: Request, exc: HTTPException
) -> JSONResponse:
    """Explicit HTTPException: preserve status code, redact detail."""
    # Pick a machine code derived from the status.
    code = {
        400: "bad_request",
        401: "unauthorized",
        403: "forbidden",
        404: "not_found",
        405: "method_not_allowed",
        409: "conflict",
        413: "payload_too_large",
        415: "unsupported_media_type",
        429: "rate_limited",
    }.get(exc.status_code, f"http_{exc.status_code}")

    # exc.detail may be str, dict, or list. Coerce to a short safe string.
    detail = exc.detail if isinstance(exc.detail, str) else "request failed"

    # Headers on the original exception (e.g. WWW-Authenticate) are preserved
    # so auth flows still work; only the body is normalized.
    return JSONResponse(
        status_code=exc.status_code,
        content={"detail": _safe_detail(detail), "code": code},
        headers=getattr(exc, "headers", None),
    )


async def _unhandled_exception_handler(
    request: Request, exc: Exception  # noqa: ARG001 — exc intentionally unused in body
) -> JSONResponse:
    """Catch-all for anything unexpected. Never echo the exception back."""
    logger.exception(
        "unhandled_exception",
        extra={"path": request.url.path, "method": request.method},
    )
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={"detail": "internal server error", "code": "internal_error"},
    )


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------
def register_exception_handlers(app: FastAPI) -> None:
    """Wire all handlers onto a FastAPI app. Call once at startup."""
    app.add_exception_handler(RequestValidationError, _request_validation_handler)
    app.add_exception_handler(HTTPException, _http_exception_handler)
    app.add_exception_handler(Exception, _unhandled_exception_handler)