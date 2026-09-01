"""Authorized customer identity resolution for API and Agent consumers."""

from __future__ import annotations

from collections.abc import Collection

from sqlalchemy.orm import Session

from app.crud.customer import customer_crud
from app.crud.customer_member import customer_member_crud
from app.models.customer import Customer
from app.services.customer_identity_resolution_service import (
    CustomerIdentityResolution,
    CustomerIdentityResolutionService,
    customer_identity_resolution_service,
)
from app.services.customer_knowledge_candidate_service import (
    CustomerKnowledgeCandidateService,
    CustomerVisibilityPredicate,
    customer_knowledge_candidate_service,
)


class CustomerIdentityResolutionApplicationService:
    """Resolve a user phrase to visible, authoritative CRM customers."""

    def __init__(
        self,
        *,
        identity_service: CustomerIdentityResolutionService | None = None,
        knowledge_service: CustomerKnowledgeCandidateService | None = None,
    ) -> None:
        self._identity_service = identity_service or customer_identity_resolution_service
        self._knowledge_service = knowledge_service or customer_knowledge_candidate_service

    def resolve(
        self,
        db: Session,
        *,
        team_id: int,
        user_id: int,
        permission_codes: Collection[str],
        query_text: str,
        limit: int = 10,
    ) -> CustomerIdentityResolution:
        visibility = self._visibility_predicate(
            db,
            team_id=team_id,
            user_id=user_id,
            permission_codes=permission_codes,
        )
        has_view_all = "customer:view:all" in permission_codes
        customers, _ = customer_crud.get_multi(
            db=db,
            team_id=team_id,
            skip=0,
            limit=limit,
            keyword=query_text,
            scope="accessible",
            current_user_id=str(user_id),
            include_collaborated=not has_view_all,
        )
        lexical_items = [
            {
                "id": customer.public_id,
                "account_name": customer.account_name,
                "city": customer.city,
            }
            for customer in customers
        ]
        semantic = self._knowledge_service.recall(
            db,
            team_id=team_id,
            query_text=query_text,
            limit=limit,
            source_types=[
                "customer",
                "follow_up",
                "business_flow",
                "opportunity",
                "contract",
                "payment",
                "contact",
            ],
            visibility_predicate=visibility,
        )
        return self._identity_service.resolve(
            db,
            team_id=team_id,
            query_text=query_text,
            lexical_items=lexical_items,
            semantic_items=semantic.candidates,
            limit=limit,
            visibility_predicate=visibility,
        )

    @staticmethod
    def _visibility_predicate(
        db: Session,
        *,
        team_id: int,
        user_id: int,
        permission_codes: Collection[str],
    ) -> CustomerVisibilityPredicate:
        user_key = str(user_id)
        can_view_all = "customer:view:all" in permission_codes

        def can_view(customer: Customer) -> bool:
            if can_view_all or customer.owner_id == user_key:
                return True
            return customer_member_crud.get_active_member(
                db,
                team_id=team_id,
                customer_id=customer.id,
                user_id=user_key,
            ) is not None

        return can_view


customer_identity_resolution_application_service = CustomerIdentityResolutionApplicationService()
