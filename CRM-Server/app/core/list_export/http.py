"""Convert list-export catalog errors into HTTP 400 responses."""

from collections.abc import Callable
from typing import TypeVar

from fastapi import HTTPException

from app.core.list_export.errors import ListExportError

T = TypeVar("T")


def run_list_export_or_400(func: Callable[[], T]) -> T:
    try:
        return func()
    except ListExportError as exc:
        raise HTTPException(status_code=400, detail=exc.detail) from exc
