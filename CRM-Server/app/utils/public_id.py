from __future__ import annotations

import re
from uuid import uuid4

OPPORTUNITY_PUBLIC_ID_PATTERN = re.compile(r"^opp_[0-9a-f]{32}$")


def generate_public_id(prefix: str) -> str:
    return f"{prefix}_{uuid4().hex}"


def is_opportunity_public_id(value: object) -> bool:
    if not isinstance(value, str):
        return False
    return bool(OPPORTUNITY_PUBLIC_ID_PATTERN.fullmatch(value))
