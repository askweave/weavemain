"""Phone numbers: E.164 normalization and log-safe masking."""

from __future__ import annotations

import re

E164_RE = re.compile(r"^\+[1-9]\d{7,14}$")


def normalize_e164(raw: str | None, default_country_code: str = "") -> str | None:
    """Return the number in E.164 (+<country><number>) or None if it cannot be one.

    Twilio already sends E.164; this also accepts '00' international prefixes and national numbers
    (a leading trunk '0' is dropped) when a default country code such as '+91' is configured."""
    if not raw:
        return None
    raw = raw.strip()
    if raw.lower().startswith("whatsapp:"):  # Twilio API for WhatsApp addresses
        raw = raw[len("whatsapp:"):]
    s = re.sub(r"[\s\-().]", "", raw.strip())
    if s.startswith("00"):
        s = "+" + s[2:]
    if not s.startswith("+"):
        cc = default_country_code.strip()
        if not cc or not s.isdigit():
            return None
        s = (cc if cc.startswith("+") else "+" + cc) + s.lstrip("0")
    return s if E164_RE.fullmatch(s) else None


def mask(phone: str | None) -> str:
    """'+919876543210' -> '+91******3210'. Used in every log line instead of the full number."""
    if not phone:
        return "-"
    return phone[:3] + "*" * max(0, len(phone) - 7) + phone[-4:]
