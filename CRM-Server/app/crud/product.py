from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, selectinload

from app.models.product import Product, ProductModule, ProductModuleRole
from app.utils.time import business_now

if TYPE_CHECKING:
    from app.schemas.product import ProductCreate, ProductModuleCreate, ProductModuleUpdate, ProductUpdate


class ProductCRUD:
    @staticmethod
    def _dump(obj: object) -> dict[str, object]:
        if hasattr(obj, "model_dump"):
            return obj.model_dump(exclude_unset=True)
        return dict(obj)

    @staticmethod
    def _is_owned_product(product: Product) -> bool:
        return product.team_id is not None and int(product.team_id) > 0

    def list(self, db: Session, team_id: int, is_active: bool | None = None) -> list[Product]:
        query = db.query(Product).options(selectinload(Product.modules)).filter(Product.team_id == team_id)
        if is_active is not None:
            query = query.filter(Product.is_active == is_active)
        return query.order_by(Product.id).all()

    def get_by_public_id(self, db: Session, public_id: str, team_id: int) -> Product | None:
        return (
            db.query(Product)
            .options(selectinload(Product.modules))
            .filter(Product.public_id == public_id, Product.team_id == team_id)
            .first()
        )

    def get_module_by_public_id(
        self,
        db: Session,
        public_id: str,
        team_id: int,
        product_id: int | None = None,
    ) -> ProductModule | None:
        query = db.query(ProductModule).filter(ProductModule.public_id == public_id, ProductModule.team_id == team_id)
        if product_id is not None:
            query = query.filter(ProductModule.product_id == product_id)
        return query.first()

    def create(self, db: Session, team_id: int, obj_in: ProductCreate, creator_id: str) -> Product:
        data = self._dump(obj_in)
        if db.query(Product.id).filter(Product.team_id == team_id, Product.code == data["code"]).first() is not None:
            raise ValueError("产品编码已存在")
        product = Product(team_id=team_id, created_by=creator_id, **data)
        db.add(product)
        try:
            db.flush()
            base_module = ProductModule(
                team_id=team_id,
                product=product,
                code="BASE",
                name="基础版",
                module_role=ProductModuleRole.BASE.value,
                base_key="BASE",
                is_active=True,
                sort_order=0,
                created_by=creator_id,
            )
            db.add(base_module)
            db.commit()
        except IntegrityError as exc:
            db.rollback()
            raise ValueError("产品编码已存在") from exc
        db.refresh(product)
        return product

    def update(self, db: Session, product: Product, obj_in: ProductUpdate, updater_id: str) -> Product:
        if not self._is_owned_product(product):
            raise ValueError("产品团队信息无效")
        for key, value in self._dump(obj_in).items():
            setattr(product, key, value)
        product.updated_by = updater_id
        product.updated_time = business_now()
        db.commit()
        db.refresh(product)
        return product

    def delete(self, db: Session, product: Product) -> None:
        if not self._is_owned_product(product):
            raise ValueError("产品团队信息无效")
        modules = list(product.modules or [])
        if any(module.module_role == ProductModuleRole.ADD_ON.value for module in modules):
            raise ValueError("产品包含增强模块，无法删除")  # noqa: RUF001
        if len(modules) != 1 or modules[0].module_role != ProductModuleRole.BASE.value:
            raise ValueError("产品基础模块状态不安全，无法删除")  # noqa: RUF001
        db.delete(product)
        db.commit()

    def create_module(
        self,
        db: Session,
        product: Product,
        obj_in: ProductModuleCreate,
        creator_id: str,
    ) -> ProductModule:
        if not self._is_owned_product(product):
            raise ValueError("产品团队信息无效")
        data = self._dump(obj_in)
        if data.get("module_role", ProductModuleRole.ADD_ON.value) != ProductModuleRole.ADD_ON.value:
            raise ValueError("新增模块只能是增强模块")
        if (
            db.query(ProductModule.id)
            .filter(ProductModule.product_id == product.id, ProductModule.code == data["code"])
            .first()
        ):
            raise ValueError("模块编码已存在")
        data.pop("module_role", None)
        module = ProductModule(team_id=product.team_id, product=product, created_by=creator_id, base_key=None, **data)
        db.add(module)
        try:
            db.commit()
        except IntegrityError as exc:
            db.rollback()
            raise ValueError("模块编码已存在") from exc
        db.refresh(module)
        return module

    def update_module(
        self,
        db: Session,
        module: ProductModule,
        obj_in: ProductModuleUpdate,
        updater_id: str,
    ) -> ProductModule:
        if module.product is not None and module.team_id != module.product.team_id:
            raise ValueError("产品模块团队不一致")
        data = self._dump(obj_in)
        if module.module_role == ProductModuleRole.BASE.value and data.get("is_active") is False:
            raise ValueError("基础模块不可停用")
        for key, value in data.items():
            setattr(module, key, value)
        module.updated_by = updater_id
        module.updated_time = business_now()
        db.commit()
        db.refresh(module)
        return module

    def delete_module(self, db: Session, module: ProductModule) -> None:
        if module.product is not None and module.team_id != module.product.team_id:
            raise ValueError("产品模块团队不一致")
        if module.module_role == ProductModuleRole.BASE.value:
            raise ValueError("基础模块不可删除")
        db.delete(module)
        db.commit()


product_crud = ProductCRUD()
