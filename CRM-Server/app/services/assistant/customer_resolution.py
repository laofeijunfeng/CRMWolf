"""Resolve assistant customer names to activity-write-authorized identities."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING, Literal

from app.crud.permission import permission_crud
from app.services.customer_activity_access_policy import (
    CustomerActivityAccessDeniedError,
    CustomerActivityCustomerNotFoundError,
    customer_activity_access_policy,
)

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

    from app.models.customer import Customer

logger = logging.getLogger(__name__)

CustomerResolutionStatus = Literal[
    "RESOLVED", "NOT_FOUND", "AMBIGUOUS", "PERMISSION_DENIED", "DEPENDENCY_FAILURE"
]


@dataclass(frozen=True)
class CustomerResolution:
    status: CustomerResolutionStatus
    customer: Customer | None
    candidates: list[dict[str, object]]


def resolve_customer_candidates_for_assistant(
    db: Session, *, team_id: int, user_id: int, customer_name: str
) -> CustomerResolution:
    """Find a customer without exposing or binding identities the user cannot write to.

    A confident identity match is not authoritative when other matches exist.
    Disambiguation still requires the user to select an authorized customer.
    """
    from app.models.customer import Customer
    from app.services.customer_identity_resolution_service import customer_identity_resolution_service

    name = customer_name.strip()
    if not name:
        return CustomerResolution("NOT_FOUND", None, [])

    try:
        permission_codes = {permission.code for permission in permission_crud.get_user_permissions(db, user_id, team_id)}
        exact = db.query(Customer).filter(Customer.team_id == team_id, Customer.account_name == name).limit(2).all()
        if exact:
            identities = [customer.public_id for customer in exact]
            uniquely_identified = len(exact) == 1
        else:
            resolution = customer_identity_resolution_service.resolve(
                db, team_id=team_id, query_text=name, lexical_items=[], semantic_items=[]
            )
            identities = [item.get("id") for item in resolution.items]
            uniquely_identified = resolution.metadata.get("identity_decision") == "auto_select" and len(identities) == 1

        candidates: list[dict[str, object]] = []
        authorized: list[Customer] = []
        denied = False
        seen: set[str] = set()
        for public_id in identities:
            if not isinstance(public_id, str) or not public_id:
                raise ValueError("identity resolver returned an invalid customer identifier")
            if public_id in seen:
                continue
            seen.add(public_id)
            try:
                customer = customer_activity_access_policy.resolve_customer(
                    db,
                    customer_identifier=public_id,
                    team_id=team_id,
                    user_id=user_id,
                    permission_codes=permission_codes,
                )
            except CustomerActivityCustomerNotFoundError:
                continue
            except CustomerActivityAccessDeniedError:
                denied = True
                continue
            authorized.append(customer)
            candidates.append({"id": customer.public_id, "account_name": customer.account_name})

        if not candidates:
            return CustomerResolution("PERMISSION_DENIED" if denied else "NOT_FOUND", None, [])
        if uniquely_identified and len(authorized) == 1:
            return CustomerResolution("RESOLVED", authorized[0], candidates)
        return CustomerResolution("AMBIGUOUS", None, candidates)
    except Exception:
        logger.exception("assistant customer resolution failed")
        return CustomerResolution("DEPENDENCY_FAILURE", None, [])


def resolve_customer_for_assistant(db: Session, *, team_id: int, customer_name: str) -> Customer | None:
    """Exact match first; on miss, fall back to unambiguous identity terms."""

    from app.crud.customer import customer_crud

    name = customer_name.strip()
    if not name:
        return None
    customer = customer_crud.get_by_name(db, name, team_id=team_id)
    if customer is not None:
        return customer

    from app.services.customer_identity_resolution_service import (
        customer_identity_resolution_service,
    )

    try:
        resolution = customer_identity_resolution_service.resolve(
            db,
            team_id=team_id,
            query_text=name,
            lexical_items=[],
            semantic_items=[],
        )
    except Exception:
        logger.warning("assistant identity resolution failed for %r", name, exc_info=True)
        return None

    if resolution.metadata.get("identity_decision") != "auto_select":
        return None
    items = resolution.items
    if len(items) != 1:
        return None
    public_id = items[0].get("id")
    if not isinstance(public_id, str) or not public_id:
        return None
    resolved = customer_crud.get_by_public_id(db, public_id, team_id=team_id)
    if resolved is not None:
        logger.info(
            "assistant resolved customer %r -> %s via identity terms",
            name,
            resolved.account_name,
        )
    return resolved
