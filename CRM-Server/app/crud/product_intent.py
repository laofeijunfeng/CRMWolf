from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from app.crud.product import product_crud
from app.models.customer import CustomerProduct
from app.models.lead import LeadProduct
from app.models.opportunity import Opportunity
from app.models.product import Product, ProductModuleRole

EMPTY_CATALOG_MESSAGE = "团队还没有可用产品，请联系管理员在「设置 → 产品管理」创建"
MISSING_PRODUCT_MESSAGE = "请选择产品"
INACTIVE_PRODUCT_MESSAGE = "请选择启用中的产品"
PRODUCT_NOT_FOUND_MESSAGE = "产品不存在"
PRODUCT_IN_USE_MESSAGE = "产品仍被线索、客户或商机引用，无法删除"


class ProductNotFoundError(ValueError):
    """Raised when a product public id is missing or belongs to another team."""


def _is_blank(product_public_id: str | None) -> bool:
    return product_public_id is None or not str(product_public_id).strip()


def first_active_product(db: Session, team_id: int) -> Product | None:
    products = product_crud.list(db, team_id, is_active=True)
    return products[0] if products else None


def resolve_writable_product(db: Session, team_id: int, product_public_id: str | None) -> Product:
    if _is_blank(product_public_id):
        if first_active_product(db, team_id) is None:
            raise ValueError(EMPTY_CATALOG_MESSAGE)
        raise ValueError(MISSING_PRODUCT_MESSAGE)

    product = product_crud.get_by_public_id(db, str(product_public_id).strip(), team_id)
    if product is None:
        raise ProductNotFoundError(PRODUCT_NOT_FOUND_MESSAGE)
    if not product.is_active:
        raise ValueError(INACTIVE_PRODUCT_MESSAGE)
    return product


def replace_product_links(
    db: Session,
    *,
    team_id: int,
    link_cls: type[Any],
    owner_id: int,
    owner_fk: str,
    product: Product,
) -> None:
    del team_id
    owner_column = getattr(link_cls, owner_fk)
    db.query(link_cls).filter(owner_column == owner_id).delete(synchronize_session=False)
    db.add(
        link_cls(
            **{
                owner_fk: owner_id,
                "product_id": product.id,
                "team_id": product.team_id,
            }
        )
    )
    db.flush()


def product_intent_payload(links: list[Any] | tuple[Any, ...] | None) -> dict[str, Any]:
    rows = list(links or [])

    def _product_id(link: Any) -> int:
        product_id = getattr(link, "product_id", None)
        if product_id is not None:
            return int(product_id)
        product = getattr(link, "product", None)
        if product is not None and getattr(product, "id", None) is not None:
            return int(product.id)
        return 0

    rows.sort(key=_product_id)
    if not rows:
        return {
            "product_public_id": None,
            "product_name": None,
            "products": [],
        }

    product = rows[0].product
    return {
        "product_public_id": product.public_id,
        "product_name": product.name,
        "products": [{"public_id": product.public_id, "name": product.name}],
    }


def base_module_public_id(product: Product) -> str | None:
    modules = list(product.modules or [])
    active_base = next(
        (
            module
            for module in modules
            if module.module_role == ProductModuleRole.BASE.value and module.is_active
        ),
        None,
    )
    if active_base is not None:
        return active_base.public_id
    active_module = next((module for module in modules if module.is_active), None)
    if active_module is not None:
        return active_module.public_id
    return None


def assert_product_deletable(db: Session, product: Product) -> None:
    if (
        db.query(LeadProduct).filter(LeadProduct.product_id == product.id).first() is not None
        or db.query(CustomerProduct).filter(CustomerProduct.product_id == product.id).first() is not None
        or db.query(Opportunity).filter(Opportunity.product_id == product.id).first() is not None
    ):
        raise ValueError(PRODUCT_IN_USE_MESSAGE)
