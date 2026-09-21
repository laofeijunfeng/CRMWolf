from __future__ import annotations

from typing import Any, Sequence

from sqlalchemy import inspect as sa_inspect
from sqlalchemy.orm import Session

from app.crud.product import product_crud
from app.models.customer import Customer, CustomerProduct
from app.models.lead import Lead, LeadProduct
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


def format_active_product_catalog(db: Session | None, team_id: int | None) -> tuple[str, str]:
    if db is None or team_id is None or not hasattr(db, "query"):
        return "无", ""
    products = product_crud.list(db, int(team_id), is_active=True)
    if not products:
        return "无", ""
    catalog_text = "、".join(f"{product.name}({product.public_id})" for product in products)
    names_enum = "|".join(product.name for product in products)
    return catalog_text, names_enum


def match_catalog_product(products: Sequence[Any], raw: object) -> Any | None:
    text = str(raw).strip() if raw is not None else ""
    if not text:
        return None
    folded = text.casefold()
    active = [item for item in products if bool(getattr(item, "is_active", True))]
    by_id = [item for item in active if str(getattr(item, "public_id", "")) == text]
    if len(by_id) == 1:
        return by_id[0]
    exact = [item for item in active if str(getattr(item, "name", "")).casefold() == folded]
    if len(exact) == 1:
        return exact[0]
    contained = [
        item
        for item in active
        if (name := str(getattr(item, "name", "")).casefold())
        and (name in folded or folded in name)
    ]
    if len(contained) == 1:
        return contained[0]
    return None


def match_active_product(db: Session, team_id: int, raw: object) -> Product | None:
    text = str(raw).strip() if raw is not None else ""
    if not text:
        return None
    by_id = product_crud.get_by_public_id(db, text, team_id)
    if by_id is not None and bool(by_id.is_active):
        return by_id
    return match_catalog_product(product_crud.list(db, team_id, is_active=True), raw)


def resolve_writable_product(db: Session, team_id: int, product_public_id: str | None) -> Product:
    if _is_blank(product_public_id):
        if first_active_product(db, team_id) is None:
            raise ValueError(EMPTY_CATALOG_MESSAGE)
        raise ValueError(MISSING_PRODUCT_MESSAGE)

    matched = match_active_product(db, team_id, product_public_id)
    if matched is not None:
        return matched
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
    db.query(link_cls).filter(owner_column == owner_id).delete(synchronize_session="fetch")
    _expire_loaded_product_links(db, owner_fk, owner_id)
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


def _expire_loaded_product_links(db: Session, owner_fk: str, owner_id: int) -> None:
    owner_cls = {"lead_id": Lead, "customer_id": Customer}.get(owner_fk)
    if owner_cls is None:
        return
    owner = db.identity_map.get(sa_inspect(owner_cls).identity_key_from_primary_key((owner_id,)))
    if owner is not None:
        db.expire(owner, ["product_links"])


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


def product_intent_payloads_by_owner(
    db: Session,
    *,
    link_model: type[CustomerProduct] | type[LeadProduct],
    owner_fk: str,
    owner_ids: Sequence[int],
) -> dict[int, dict[str, Any]]:
    """Load product links for owner ids on this session; never touch stream-session relationships."""
    if not owner_ids:
        return {}
    links = (
        db.query(link_model)
        .filter(getattr(link_model, owner_fk).in_(list(owner_ids)))
        .all()
    )
    product_ids = {int(link.product_id) for link in links if getattr(link, "product_id", None) is not None}
    products = {
        product.id: product
        for product in db.query(Product).filter(Product.id.in_(product_ids)).all()
    } if product_ids else {}
    links_by_owner: dict[int, list] = {}
    for link in links:
        owner_id = int(getattr(link, owner_fk))
        product = products.get(int(link.product_id)) if getattr(link, "product_id", None) is not None else None
        if product is not None:
            link.product = product
        links_by_owner.setdefault(owner_id, []).append(link)
    return {
        owner_id: product_intent_payload(owner_links)
        for owner_id, owner_links in links_by_owner.items()
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
