"""Persistence boundary for the customer profile projection read model."""

from __future__ import annotations

from typing import TYPE_CHECKING

from app.models.customer_profile_projection import (
    CUSTOMER_PROFILE_READABLE_PUBLICATION_STATUSES,
    CustomerProfileCurrent,
    CustomerProfileProjectionVersion,
)

if TYPE_CHECKING:
    from sqlalchemy.orm import Session


class CustomerProfileProjectionCRUD:
    """Keep projection queries out of APIs and orchestration services."""

    def get_current(
        self,
        db: Session,
        *,
        team_id: int,
        customer_id: int,
        for_update: bool = False,
    ) -> CustomerProfileCurrent | None:
        query = db.query(CustomerProfileCurrent).filter(
            CustomerProfileCurrent.team_id == team_id,
            CustomerProfileCurrent.customer_id == customer_id,
        )
        if for_update:
            query = query.with_for_update()
        return query.one_or_none()

    def get_version(
        self,
        db: Session,
        *,
        team_id: int,
        customer_id: int,
        profile_version: int | None = None,
        public_id: str | None = None,
        version_id: int | None = None,
    ) -> CustomerProfileProjectionVersion | None:
        query = db.query(CustomerProfileProjectionVersion).filter(
            CustomerProfileProjectionVersion.team_id == team_id,
            CustomerProfileProjectionVersion.customer_id == customer_id,
        )
        if profile_version is not None:
            query = query.filter(CustomerProfileProjectionVersion.profile_version == profile_version)
        if public_id is not None:
            query = query.filter(CustomerProfileProjectionVersion.public_id == public_id)
        if version_id is not None:
            query = query.filter(CustomerProfileProjectionVersion.id == version_id)
        return query.one_or_none()

    def get_current_version(
        self,
        db: Session,
        *,
        team_id: int,
        customer_id: int,
        current: CustomerProfileCurrent,
    ) -> CustomerProfileProjectionVersion | None:
        if current.current_profile_version_id is None:
            return None
        return (
            db.query(CustomerProfileProjectionVersion)
            .filter(
                CustomerProfileProjectionVersion.id == current.current_profile_version_id,
                CustomerProfileProjectionVersion.team_id == team_id,
                CustomerProfileProjectionVersion.customer_id == customer_id,
                CustomerProfileProjectionVersion.publication_status.in_(CUSTOMER_PROFILE_READABLE_PUBLICATION_STATUSES),
            )
            .one_or_none()
        )

    def find_duplicate(
        self,
        db: Session,
        *,
        team_id: int,
        customer_id: int,
        content_hash: str,
        source_watermark_hash: str,
    ) -> CustomerProfileProjectionVersion | None:
        return (
            db.query(CustomerProfileProjectionVersion)
            .filter(
                CustomerProfileProjectionVersion.team_id == team_id,
                CustomerProfileProjectionVersion.customer_id == customer_id,
                CustomerProfileProjectionVersion.content_hash == content_hash,
                CustomerProfileProjectionVersion.source_watermark_hash == source_watermark_hash,
                CustomerProfileProjectionVersion.publication_status.in_(CUSTOMER_PROFILE_READABLE_PUBLICATION_STATUSES),
            )
            .order_by(CustomerProfileProjectionVersion.profile_version.desc())
            .first()
        )

    def get_previous_version(
        self,
        db: Session,
        *,
        team_id: int,
        customer_id: int,
        profile_version: int,
    ) -> CustomerProfileProjectionVersion | None:
        """Return the immediately preceding published projection version."""

        return (
            db.query(CustomerProfileProjectionVersion)
            .filter(
                CustomerProfileProjectionVersion.team_id == team_id,
                CustomerProfileProjectionVersion.customer_id == customer_id,
                CustomerProfileProjectionVersion.profile_version < profile_version,
                CustomerProfileProjectionVersion.publication_status.in_(CUSTOMER_PROFILE_READABLE_PUBLICATION_STATUSES),
            )
            .order_by(CustomerProfileProjectionVersion.profile_version.desc())
            .first()
        )

    def list_versions(
        self,
        db: Session,
        *,
        team_id: int,
        customer_id: int,
        limit: int = 20,
        before_version: int | None = None,
    ) -> tuple[list[CustomerProfileProjectionVersion], int | None]:
        safe_limit = min(max(limit, 1), 100)
        query = db.query(CustomerProfileProjectionVersion).filter(
            CustomerProfileProjectionVersion.team_id == team_id,
            CustomerProfileProjectionVersion.customer_id == customer_id,
        )
        if before_version is not None:
            query = query.filter(CustomerProfileProjectionVersion.profile_version < before_version)
        rows = query.order_by(CustomerProfileProjectionVersion.profile_version.desc()).limit(safe_limit + 1).all()
        next_cursor = rows[safe_limit].profile_version if len(rows) > safe_limit else None
        return rows[:safe_limit], next_cursor


customer_profile_projection_crud = CustomerProfileProjectionCRUD()
