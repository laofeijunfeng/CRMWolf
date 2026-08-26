"""Canonical authorization policy for customer activity and follow-up writes."""

from __future__ import annotations

from typing import TYPE_CHECKING

from app.crud.customer import customer_crud
from app.crud.customer_member import customer_member_crud

if TYPE_CHECKING:
    from collections.abc import Collection

    from sqlalchemy.orm import Session

    from app.models.customer import Customer


class CustomerActivityAccessError(RuntimeError):
    """Base authorization error for customer activity operations."""


class CustomerActivityCustomerNotFoundError(CustomerActivityAccessError):
    """The customer does not exist in the requested team."""


class CustomerActivityAccessDeniedError(CustomerActivityAccessError):
    """The user cannot create activity or follow-up records for the customer."""


class CustomerActivityAccessPolicy:
    """Resolve one team-owned customer and enforce the canonical activity-write rule."""

    def resolve_customer(
        self,
        db: Session,
        *,
        customer_identifier: int | str,
        team_id: int,
        user_id: int,
        permission_codes: Collection[str],
    ) -> Customer:
        customer = (
            customer_crud.get_by_id(db, customer_identifier, team_id)
            if isinstance(customer_identifier, int)
            else customer_crud.get_by_public_id(db, str(customer_identifier), team_id)
        )
        if customer is None:
            raise CustomerActivityCustomerNotFoundError("customer not found")

        if "customer:edit:all" in permission_codes:
            return customer
        if customer_member_crud.has_access(
            db=db,
            team_id=team_id,
            customer_id=customer.id,
            user_id=str(user_id),
            required_level="FOLLOW_UP",
        ):
            return customer
        if customer.owner_id == str(user_id) and bool(
            set(permission_codes)
            & {
                "customer:activity:create",
                "customer:follow_up:create",
                "customer:edit:own",
            }
        ):
            return customer

        raise CustomerActivityAccessDeniedError("customer activity access denied")


customer_activity_access_policy = CustomerActivityAccessPolicy()
