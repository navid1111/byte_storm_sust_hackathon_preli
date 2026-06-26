"""Shared multilingual lexicon + text helpers (decision-rules §4, §5).

English / Banglish (romanized) / Bangla synonym sets used by the matcher and
classifier so they read from one source and cannot drift. All matching is done
on a normalized (lowercased) copy of the complaint; the original text is never
treated as an instruction (prompt-injection safety, S4).
"""

from __future__ import annotations

import re

# --- Intent → synonym phrases (decision-rules §4) ---------------------------

TRANSFER_CUES = [
    "send", "sent", "transfer", "paid to", "pathaisi", "pathalam", "pathaichi",
    "dilam", "transfer korsi", "পাঠাইছি", "পাঠালাম", "দিলাম", "পাঠিয়েছি",
]
REFUND_CUES = [
    "refund", "return", "money back", "refund chai", "taka ferot", "return koren",
    "ফেরত", "টাকা ফেরত", "ফিরিয়ে দিন",
]
WRONG_NUMBER_CUES = [
    "wrong number", "wrong recipient", "wrong person", "bhul number", "bhul nambar",
    "vul number", "vul nambar", "ভুল নম্বর", "ভুল নাম্বার", "ভুল লোক",
]
FAILED_CUES = [
    "failed", "declined", "deducted but failed", "deducted but not", "fail hoise",
    "kete nise but hoyni", "kete nise but hoy nai", "taka katlo", "taka kete nise",
    "ব্যর্থ", "কাটছে কিন্তু হয়নি", "টাকা কেটে নিয়েছে", "হয়নি",
]
DUPLICATE_CUES = [
    "twice", "double", "duplicate", "charged again", "two times", "duibar",
    "double katse", "abar katlo", "দুইবার", "ডবল কাটছে", "আবার কেটেছে",
]
CASH_IN_CUES = [
    "cash in", "cash-in", "deposit", "deposit via agent", "cash in korsi",
    "agent ke dilam", "ক্যাশ ইন", "এজেন্টকে দিলাম", "জমা",
]
SETTLEMENT_CUES = [
    "settlement", "payout", "not received", "settlement pai nai", "taka dhuke nai",
    "সেটেলমেন্ট", "টাকা ঢোকেনি", "পেমেন্ট পাইনি",
]
AGENT_CUES = ["agent", "এজেন্ট", "agent er", "agent point"]
MERCHANT_CUES = ["merchant", "shop", "store", "মার্চেন্ট", "দোকান"]
TODAY_TIME_CUES = [
    "today", "just now", "right now", "minutes ago", "am", "pm", "o'clock",
    "aaj", "ekhon", "ektu age", "dupur", "sokal", "rat", "আজ", "এখন", "দুপুর",
    "সকাল", "রাত", "টা",
]
NOT_RECEIVED_CUES = [
    "not received", "didn't receive", "did not receive", "haven't received",
    "pai nai", "paini", "পাইনি", "পাই নাই", "dhuke nai", "ঢোকেনি", "আসেনি",
]

# Phishing / social-engineering cues (decision-rules §5). Match a customer
# REPORTING being targeted — never a license for us to request credentials.
PHISHING_CUES = [
    "otp", "ওটিপি", "pin", "পিন", "password", "পাসওয়ার্ড", "cvv", "card number",
    "asked for my", "asked me for", "share your", "share my", "verify your account",
    "click this link", "click the link", "suspicious", "scam", "fraud", "prfotarok",
    "protarok", "প্রতারক", "চেয়েছে", "phone korse", "call dise", "claiming to be",
    "bkash theke", "bkash theke bolchi", "official call", "lottery", "lucky draw",
    "account locked", "unlock", "code dite bolse",
]

# Map a detected intent to the transaction `type` it implies (for matcher §1).
INTENT_TO_TXN_TYPE = {
    "transfer": "transfer",
    "refund": "refund",
    "cash_in": "cash_in",
    "settlement": "settlement",
}

_BN_DIGITS = str.maketrans("০১২৩৪৫৬৭৮৯", "0123456789")


def normalize(text: str) -> str:
    """Lowercase + collapse whitespace. Bangla digits → ASCII for amount parsing."""
    if not text:
        return ""
    # Neutralize prompt injection (AC-11)
    text = re.sub(
        r"ignore\s+(all\s+)?(previous\s+)?instructions\s*(and\s+\w+\s+with\s*['\"].*?['\"])?",
        "",
        text,
        flags=re.IGNORECASE
    )
    text = re.sub(r"ignore\s+instructions", "", text, flags=re.IGNORECASE)
    return re.sub(r"\s+", " ", text.translate(_BN_DIGITS).lower()).strip()


def contains_any(text: str, phrases: list[str]) -> bool:
    """True if any phrase (already lowercase) appears in the normalized text."""
    return any(p in text for p in phrases)


def extract_amounts(text: str) -> list[float]:
    """Pull numeric amounts from text (handles ``5000`` and ``5,000``).

    Ignores short 4+ digit runs that look like phone numbers (>= 7 digits with
    no comma) so a counterparty number is not mistaken for an amount.
    """
    amounts: list[float] = []
    for raw in re.findall(r"\d[\d,]*", text):
        digits = raw.replace(",", "")
        if "," not in raw and len(digits) >= 7:
            # Looks like a phone/account number, not a money amount.
            continue
        try:
            amounts.append(float(digits))
        except ValueError:  # pragma: no cover - defensive
            continue
    return amounts


def extract_number_tails(text: str, min_len: int = 4) -> list[str]:
    """Last 4 digits of each long digit run — used for counterparty matching."""
    tails: list[str] = []
    for raw in re.findall(r"\d[\d,]*", text):
        digits = raw.replace(",", "")
        if len(digits) >= min_len:
            tails.append(digits[-4:])
    return tails


def digit_tail(value: str | None, n: int = 4) -> str | None:
    """Last ``n`` digits of an arbitrary identifier (phone/merchant/agent id)."""
    if not value:
        return None
    digits = re.sub(r"\D", "", value)
    return digits[-n:] if len(digits) >= n else None
