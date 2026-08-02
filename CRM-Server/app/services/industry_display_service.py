"""User-facing industry display helpers."""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.crud.industry import industry_crud


class IndustryDisplayService:
    """Resolve internal industry codes into names suitable for UI and AI output."""

    def display_name(self, db: Session, industry_code: str | None) -> str | None:
        code = str(industry_code or "").strip()
        if not code:
            return None

        industry = industry_crud.get_by_code_with_parent(db, code)
        if industry is None:
            return code

        if industry.level == 2 and industry.parent:
            return f"{industry.parent.name}/{industry.name}"
        return str(industry.name or "").strip() or code

    def sanitize_markdown(
        self,
        db: Session,
        markdown: str | None,
        *,
        industry_code: str | None,
    ) -> str | None:
        if markdown is None:
            return None
        sanitized = markdown.replace("### 行业与同行客户", "### 同行业客户")
        code = str(industry_code or "").strip()
        if not code:
            return sanitized
        display_name = self.display_name(db, code)
        if display_name and display_name != code:
            sanitized = sanitized.replace(code, display_name)
        return sanitized


industry_display_service = IndustryDisplayService()
