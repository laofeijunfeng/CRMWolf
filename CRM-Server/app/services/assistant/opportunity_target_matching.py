"""Conservative proposal target matching, never CRM command-success attribution."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Literal, TypeVar

if TYPE_CHECKING:
    from sqlalchemy.orm import Query, Session

    from app.schemas.opportunity import OpportunityCreate


OpportunityTargetStatus = Literal["DISTINCT", "DUPLICATE", "AMBIGUOUS"]
_QueryRow = TypeVar("_QueryRow")


@dataclass(frozen=True)
class OpportunityTargetMatch:
    status: OpportunityTargetStatus
    target_public_ids: tuple[str, ...] = ()


def match_opportunity_target(
    db: Session,
    *,
    team_id: int,
    customer_id: int,
    data: OpportunityCreate,
    current_read: bool = False,
) -> OpportunityTargetMatch:
    """Classify a validated create proposal against this customer's current targets.

    A duplicate requires one exact, nonblank name and a fully resolved, identical
    product, module set, purchase type and license type/term. Names are not fuzzy
    matched; different names may describe separate purchases of the same product.
    Amount, seat count and closing date are mutable commercial terms, not target
    identifiers. No business similarity threshold or approval is implied.

    An unresolved catalog reference or same-name legacy identity is ambiguous.
    With an auto-generated name, inspect all scoped targets without a NULL-name
    predicate: a compatible or unresolved target is ambiguous, and no possible
    target is distinct. Multiple possible targets are always ambiguous.

    This only reads persisted state (including suppressing autoflush). Set
    current_read for the final execution check while holding the team catalog
    fence: MySQL locking reads see writes committed after this transaction's
    repeatable-read snapshot. DISTINCT is not write authorization and DUPLICATE
    is not proof any command succeeded.
    """
    from sqlalchemy import and_

    from app.models.opportunity import Opportunity, OpportunityProductModule
    from app.models.product import Product, ProductModule
    from app.schemas.opportunity import LicenseTypeEnum, PurchaseTypeEnum

    locking_read = current_read and db.get_bind().dialect.name in {"mysql", "mariadb"}

    def read_query(query: Query[_QueryRow]) -> Query[_QueryRow]:
        return query.with_for_update() if locking_read else query

    name = (data.opportunity_name or "").strip()
    module_public_ids = set(data.product_module_public_ids)
    if (
        not data.product_public_id.strip()
        or not module_public_ids
        or any(not public_id.strip() for public_id in module_public_ids)
    ):
        return OpportunityTargetMatch("AMBIGUOUS")

    with db.no_autoflush:
        product = read_query(
            db.query(Product.id)
            .filter(
                Product.public_id == data.product_public_id,
                Product.team_id == team_id,
                Product.is_active.is_(True),
            )
        ).one_or_none()
        if product is None:
            return OpportunityTargetMatch("AMBIGUOUS")
        modules = read_query(
            db.query(ProductModule.id, ProductModule.public_id)
            .filter(
                ProductModule.public_id.in_(module_public_ids),
                ProductModule.team_id == team_id,
                ProductModule.product_id == product.id,
                ProductModule.is_active.is_(True),
            )
        ).all()
        if {module.public_id for module in modules} != module_public_ids:
            return OpportunityTargetMatch("AMBIGUOUS")
        candidate_modules: set[int] = {module.id for module in modules}

        targets_query = db.query(
            Opportunity.id,
            Opportunity.public_id,
            Opportunity.opportunity_name,
            Opportunity.product_id,
            Opportunity.purchase_type,
            Opportunity.license_type,
            Opportunity.subscription_years,
        ).filter(
            Opportunity.team_id == team_id,
            Opportunity.customer_id == customer_id,
        )
        targets = read_query(targets_query.order_by(Opportunity.id)).all()
        # Python strip defines exact name identity, including legacy whitespace;
        # SQL equality or TRIM would exclude names before that normalization.
        if name:
            targets = [target for target in targets if target.opportunity_name.strip() == name]
        if not targets:
            return OpportunityTargetMatch("DISTINCT")

        target_ids = [target.id for target in targets]
        product_ids = {target.product_id for target in targets if target.product_id is not None}
        products_query = db.query(Product.id).filter(
            Product.team_id == team_id,
            Product.id.in_(product_ids),
        )
        resolved_products = {identifier for (identifier,) in read_query(products_query).all()}
        module_sets: dict[int, set[int]] = {}
        unresolved_module_targets: set[int] = set()
        target_products = {target.id: target.product_id for target in targets}
        links = read_query(
            db.query(
                OpportunityProductModule.opportunity_id,
                OpportunityProductModule.product_module_id,
                OpportunityProductModule.team_id,
                ProductModule.id,
                ProductModule.product_id,
            )
            .join(Opportunity, Opportunity.id == OpportunityProductModule.opportunity_id)
            .outerjoin(
                ProductModule,
                and_(
                    ProductModule.id == OpportunityProductModule.product_module_id,
                    ProductModule.team_id == team_id,
                ),
            )
            .filter(
                Opportunity.team_id == team_id,
                Opportunity.customer_id == customer_id,
                OpportunityProductModule.opportunity_id.in_(target_ids),
            )
        ).all()
        for target_id, module_id, link_team_id, resolved_id, product_id in links:
            if link_team_id != team_id or resolved_id is None or product_id != target_products[target_id]:
                unresolved_module_targets.add(target_id)
            module_sets.setdefault(target_id, set()).add(module_id)

        possible: list[str] = []
        unresolved = False
        valid_purchase_types = {value.value for value in PurchaseTypeEnum}
        valid_license_types = {value.value for value in LicenseTypeEnum}
        for target in targets:
            target_modules = module_sets.get(target.id)
            identity_resolved = (
                target.product_id in resolved_products
                and bool(target_modules)
                and target.id not in unresolved_module_targets
                and target.purchase_type in valid_purchase_types
                and target.license_type in valid_license_types
                and (
                    target.license_type != LicenseTypeEnum.SUBSCRIPTION.value
                    or (target.subscription_years is not None and target.subscription_years > 0)
                )
            )
            if not identity_resolved:
                possible.append(target.public_id)
                unresolved = True
                continue
            if (
                target.product_id == product.id
                and target_modules == candidate_modules
                and target.purchase_type == data.purchase_type.value
                and target.license_type == data.license_type.value
                and (
                    data.license_type != LicenseTypeEnum.SUBSCRIPTION
                    or target.subscription_years == data.subscription_years
                )
            ):
                possible.append(target.public_id)

        if not possible:
            return OpportunityTargetMatch("DISTINCT")
        if unresolved or not name or len(possible) != 1:
            return OpportunityTargetMatch("AMBIGUOUS", tuple(possible))
        return OpportunityTargetMatch("DUPLICATE", tuple(possible))
