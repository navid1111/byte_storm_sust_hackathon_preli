"""Safety guardrails sanitizer (T019, T020).

Implements:
  - S1: credential request scrub
  - S2: refund confirmation rewrite
  - S3: third-party/suspicious link strip
"""

from __future__ import annotations

import re

# S1 credential regexes
CREDENTIAL_RE = re.compile(
    r"\b(pin|otp|password|cvv|card\s*number|card\s*no|পিন|ওটিপি|পাসওয়ার্ড)\b",
    re.IGNORECASE
)

# S2 refund confirmations and their authority-safe replacements
REFUND_PATTERNS = [
    (re.compile(r"we\s+will\s+refund\s+you", re.IGNORECASE), "any eligible amount will be returned through official channels"),
    (re.compile(r"we\s+have\s+refunded", re.IGNORECASE), "any eligible amount will be returned through official channels"),
    (re.compile(r"your\s+refund\s+has\s+been\s+processed", re.IGNORECASE), "any eligible amount will be returned through official channels"),
    (re.compile(r"your\s+money\s+has\s+been\s+returned", re.IGNORECASE), "any eligible amount will be returned through official channels"),
    (re.compile(r"refund\s+is\s+confirmed", re.IGNORECASE), "any eligible amount will be returned through official channels"),
    (re.compile(r"we\s+will\s+reverse\s+the\s+transaction", re.IGNORECASE), "any eligible amount will be returned through official channels"),
    (re.compile(r"transaction\s+has\s+been\s+reversed", re.IGNORECASE), "any eligible amount will be returned through official channels"),
    (re.compile(r"we\s+have\s+reversed", re.IGNORECASE), "any eligible amount will be returned through official channels"),
    (re.compile(r"your\s+account\s+has\s+been\s+unblocked", re.IGNORECASE), "any eligible amount will be returned through official channels"),
    (re.compile(r"we\s+have\s+unblocked", re.IGNORECASE), "any eligible amount will be returned through official channels"),
    (re.compile(r"you\s+will\s+receive\s+the\s+refund\s+immediately", re.IGNORECASE), "any eligible amount will be returned through official channels"),
    (re.compile(r"refund\s+processed\s+successfully", re.IGNORECASE), "any eligible amount will be returned through official channels"),
    (re.compile(r"100%\s+refund\s+guaranteed", re.IGNORECASE), "any eligible amount will be returned through official channels"),
    (re.compile(r"\brefunded\b", re.IGNORECASE), "returned through official channels"),
    (re.compile(r"\brefund\s+processed\b", re.IGNORECASE), "processed through official channels"),
]

# S3 forbidden third-party pattern lists
S3_PATTERNS = [
    re.compile(r"contact\s+this\s+number", re.IGNORECASE),
    re.compile(r"call\s+this\s+person", re.IGNORECASE),
    re.compile(r"send\s+money\s+to", re.IGNORECASE),
    re.compile(r"transfer\s+to\s+this\s+agent", re.IGNORECASE),
    re.compile(r"share\s+your\s+details\s+with", re.IGNORECASE),
    re.compile(r"forward\s+your\s+otp\s+to", re.IGNORECASE),
    re.compile(r"click\s+this\s+link", re.IGNORECASE),
    re.compile(r"visit\s+this\s+site", re.IGNORECASE),
    re.compile(r"telegram\.me/\S*", re.IGNORECASE),
    re.compile(r"whatsapp\s+me", re.IGNORECASE),
    re.compile(r"facebook\.com/\S*", re.IGNORECASE),
]

# URL matching regex
URL_RE = re.compile(r"https?://\S*", re.IGNORECASE)


def sanitize_customer_reply(text: str) -> str:
    """Sanitizes customer replies to guarantee S1, S2, and S3 compliance."""
    if not text:
        return ""

    # S2: Rewrite refund/reversal confirmations
    for pattern, replacement in REFUND_PATTERNS:
        text = pattern.sub(replacement, text)

    # S3: Strip suspicious third-party directives
    for pattern in S3_PATTERNS:
        text = pattern.sub("", text)

    # S3: Filter URLs to allow only official support domains
    def url_replacer(match):
        url = match.group(0)
        if any(domain in url.lower() for domain in ["support", "help", "official"]):
            return url
        return ""  # strip suspicious URLs

    text = URL_RE.sub(url_replacer, text)

    # S1: Scrub credential requests (e.g. asking for PIN/OTP)
    # If the text is asking for credentials, replace it with a warning.
    # Note: A warning like "We will never ask for your PIN/OTP" is safe because "never ask" is present.
    # But if the text says "Please send your PIN", that is a request, so we replace it.
    if CREDENTIAL_RE.search(text):
        # If it already warns about never asking, let it be
        text_lower = text.lower()
        has_warning = (
            "never ask" in text_lower
            or "will not ask" in text_lower
            or "do not share" in text_lower
            or "never request" in text_lower
            or "never share" in text_lower
            or "চাইবে না" in text_lower
        )
        if not has_warning:
            # Replace credential request sentence or terms
            text = CREDENTIAL_RE.sub("[redacted]", text)

    # Clean up double spaces from replacements
    text = re.sub(r"\s+", " ", text).strip()
    return text


def sanitize_recommended_next_action(text: str) -> str:
    """Sanitizes recommendations for agent actions to ensure safety (e.g., no credential asking)."""
    if not text:
        return ""

    # Next action: ensure agent is never told to ask for client credentials
    if CREDENTIAL_RE.search(text):
        text_lower = text.lower()
        has_warning = (
            "never ask" in text_lower
            or "do not ask" in text_lower
            or "never request" in text_lower
        )
        if not has_warning:
            text = CREDENTIAL_RE.sub("[redacted]", text)

    # S3: Strip suspicious links/directives
    for pattern in S3_PATTERNS:
        text = pattern.sub("", text)

    text = URL_RE.sub("", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text
