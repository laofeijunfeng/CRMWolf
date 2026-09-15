# ruff: noqa: B008

from __future__ import annotations

from typing import TYPE_CHECKING, Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import get_current_user_team, require_permission
from app.crud.product import product_crud
from app.schemas.product import (
    ProductCreate,
    ProductModuleCreate,
    ProductModuleResponse,
    ProductModuleUpdate,
    ProductResponse,
    ProductUpdate,
)

if TYPE_CHECKING:
    from app.models.product import Product, ProductModule
    from app.models.user import User

router = APIRouter(prefix="/v1/products", tags=["产品管理"])

TeamId = Annotated[int, Depends(get_current_user_team)]
DbSession = Annotated[Session, Depends(get_db)]


def _not_found(detail: str = "产品不存在") -> HTTPException:
    return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=detail)


def _domain_error(exc: ValueError) -> HTTPException:
    message = str(exc)
    if "编码已存在" in message or "引用" in message:
        return HTTPException(status_code=status.HTTP_409_CONFLICT, detail=message)
    return HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=message)


def _module_response(module: ProductModule) -> ProductModuleResponse:
    return ProductModuleResponse.model_validate(module)


def _product_response(product: Product) -> ProductResponse:
    modules = sorted(product.modules or [], key=lambda module: (module.sort_order, module.id))
    payload = ProductResponse.model_validate(product)
    payload.modules = [_module_response(module) for module in modules]
    return payload


def _get_product(db: Session, public_id: str, team_id: int) -> Product:
    product = product_crud.get_by_public_id(db, public_id, team_id)
    if product is None:
        raise _not_found()
    return product


def _get_module(db: Session, product: Product, module_public_id: str, team_id: int) -> ProductModule:
    module = product_crud.get_module_by_public_id(
        db,
        module_public_id,
        team_id,
        product_id=product.id,
    )
    if module is None:
        raise _not_found("产品模块不存在")
    return module


@router.get(
    "/",
    response_model=list[ProductResponse],
    summary="获取产品列表",
)
def list_products(
    is_active: bool | None = Query(None, description="是否启用"),
    *,
    team_id: TeamId,
    db: DbSession,
    current_user: User = Depends(require_permission("product:view")),
) -> list[ProductResponse]:
    del current_user
    return [_product_response(product) for product in product_crud.list(db, team_id, is_active)]


@router.get(
    "/{public_id}",
    response_model=ProductResponse,
    summary="获取产品详情",
)
def get_product(
    public_id: str,
    team_id: TeamId,
    db: DbSession,
    current_user: User = Depends(require_permission("product:view")),
) -> ProductResponse:
    del current_user
    return _product_response(_get_product(db, public_id, team_id))


@router.post(
    "/",
    response_model=ProductResponse,
    status_code=status.HTTP_201_CREATED,
    summary="创建产品",
)
def create_product(
    payload: ProductCreate,
    team_id: TeamId,
    db: DbSession,
    current_user: User = Depends(require_permission("product:create")),
) -> ProductResponse:
    try:
        product = product_crud.create(db, team_id, payload, str(current_user.id))
    except ValueError as exc:
        raise _domain_error(exc) from exc
    return _product_response(product)


@router.put(
    "/{public_id}",
    response_model=ProductResponse,
    summary="更新产品",
)
def update_product(
    public_id: str,
    payload: ProductUpdate,
    team_id: TeamId,
    db: DbSession,
    current_user: User = Depends(require_permission("product:edit")),
) -> ProductResponse:
    product = _get_product(db, public_id, team_id)
    try:
        return _product_response(product_crud.update(db, product, payload, str(current_user.id)))
    except ValueError as exc:
        raise _domain_error(exc) from exc


@router.delete(
    "/{public_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="删除产品",
)
def delete_product(
    public_id: str,
    team_id: TeamId,
    db: DbSession,
    current_user: User = Depends(require_permission("product:delete")),
) -> Response:
    del current_user
    product = _get_product(db, public_id, team_id)
    try:
        product_crud.delete(db, product)
    except ValueError as exc:
        raise _domain_error(exc) from exc
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post(
    "/{public_id}/modules",
    response_model=ProductModuleResponse,
    status_code=status.HTTP_201_CREATED,
    summary="创建产品模块",
)
def create_product_module(
    public_id: str,
    payload: ProductModuleCreate,
    team_id: TeamId,
    db: DbSession,
    current_user: User = Depends(require_permission("product:edit")),
) -> ProductModuleResponse:
    product = _get_product(db, public_id, team_id)
    try:
        module = product_crud.create_module(db, product, payload, str(current_user.id))
    except ValueError as exc:
        raise _domain_error(exc) from exc
    return _module_response(module)


@router.put(
    "/{public_id}/modules/{module_public_id}",
    response_model=ProductModuleResponse,
    summary="更新产品模块",
)
def update_product_module(
    public_id: str,
    module_public_id: str,
    payload: ProductModuleUpdate,
    team_id: TeamId,
    db: DbSession,
    current_user: User = Depends(require_permission("product:edit")),
) -> ProductModuleResponse:
    product = _get_product(db, public_id, team_id)
    module = _get_module(db, product, module_public_id, team_id)
    try:
        return _module_response(product_crud.update_module(db, module, payload, str(current_user.id)))
    except ValueError as exc:
        raise _domain_error(exc) from exc


@router.delete(
    "/{public_id}/modules/{module_public_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="删除产品模块",
)
def delete_product_module(
    public_id: str,
    module_public_id: str,
    team_id: TeamId,
    db: DbSession,
    current_user: User = Depends(require_permission("product:edit")),
) -> Response:
    del current_user
    product = _get_product(db, public_id, team_id)
    module = _get_module(db, product, module_public_id, team_id)
    try:
        product_crud.delete_module(db, module)
    except ValueError as exc:
        raise _domain_error(exc) from exc
    return Response(status_code=status.HTTP_204_NO_CONTENT)
