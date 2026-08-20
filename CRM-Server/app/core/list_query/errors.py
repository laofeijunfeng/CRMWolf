from __future__ import annotations


class ListQueryError(ValueError):
    """Raised when list filters or sorts cannot be applied."""

    def __init__(self, detail: str, error_code: str = "LIST_QUERY_INVALID") -> None:
        super().__init__(detail)
        self.detail = detail
        self.error_code = error_code
