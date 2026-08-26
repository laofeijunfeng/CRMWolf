"""Opaque cursor helpers owned by the deterministic CRM query module."""

from __future__ import annotations

import base64
import json


class CRMQueryCursorError(ValueError):
    pass


def encode_offset_cursor(offset: int) -> str:
    if offset < 0:
        raise ValueError("cursor offset must be non-negative")
    payload = json.dumps({"offset": offset}, separators=(",", ":"), sort_keys=True).encode()
    return base64.urlsafe_b64encode(payload).decode().rstrip("=")


def decode_offset_cursor(cursor: str | None) -> int:
    if cursor is None:
        return 0
    try:
        padded = cursor + "=" * (-len(cursor) % 4)
        payload = json.loads(base64.urlsafe_b64decode(padded.encode()).decode())
        offset = payload["offset"]
    except (KeyError, TypeError, ValueError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise CRMQueryCursorError("invalid CRM query cursor") from exc
    if not isinstance(offset, int) or isinstance(offset, bool) or offset < 0:
        raise CRMQueryCursorError("invalid CRM query cursor")
    return offset
