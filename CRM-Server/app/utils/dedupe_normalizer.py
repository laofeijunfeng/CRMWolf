"""Normalizers for customer child-record duplicate detection (CRM-164).

Each ``normalize_*`` returns the canonical stored/compared form; each
``*_dedupe_key`` returns ``None`` for empty input so blank values never collide
in the per-customer unique indexes.
"""

import re
from urllib.parse import urlsplit, urlunsplit

_MOBILE_SEPARATORS = re.compile(r"[\s\-]+")
_WHITESPACE = re.compile(r"\s+")


def normalize_mobile(value: str | None) -> str:
    """Strip whitespace and ``-`` plus a China ``+86``/``86`` prefix."""
    mobile = _MOBILE_SEPARATORS.sub("", value or "")
    if mobile.startswith("+86"):
        return mobile[3:]
    if mobile.startswith("86") and len(mobile) == 13:
        return mobile[2:]
    return mobile


def normalize_taxpayer_id(value: str | None) -> str:
    """Remove all whitespace and uppercase."""
    return _WHITESPACE.sub("", value or "").upper()


def normalize_server_address(value: str | None) -> str:
    """Trim, drop trailing ``/`` and lowercase scheme and host; keep port, path and query."""
    address = (value or "").strip().rstrip("/")
    if not address:
        return ""
    parts = urlsplit(address)
    userinfo, at, hostport = parts.netloc.rpartition("@")
    netloc = f"{userinfo}{at}{hostport.lower()}"
    return urlunsplit((parts.scheme.lower(), netloc, parts.path, parts.query, parts.fragment))


def mobile_dedupe_key(value: str | None) -> str | None:
    return normalize_mobile(value) or None


def taxpayer_dedupe_key(value: str | None) -> str | None:
    return normalize_taxpayer_id(value) or None


def server_address_dedupe_key(value: str | None) -> str | None:
    return normalize_server_address(value) or None
