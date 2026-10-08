from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, selectinload

from app.models.customer import Customer, CustomerProduct
from app.models.opportunity import Opportunity
from app.models.product import Product, ProductModule, ProductModuleRole
from app.models.team import Team
from app.services.legacy_profile_source import advance_eligible_progress
from app.utils.public_id import generate_public_id
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

    @staticmethod
    def lock_catalog_team(db: Session, team_id: int) -> None:
        # The legacy profile publisher takes this same lock before reading the catalog.
        with db.no_autoflush:
            team = db.query(Team.id).filter(Team.id == team_id).with_for_update().one_or_none()
        if team is None:
            raise ValueError("产品团队信息无效")
    @staticmethod
    def current_catalog_product(db: Session, team_id: int, public_id: str) -> Product | None:
        # Call after the Team fence. Locking read bypasses both the RR snapshot
        # and ORM identity-map values that predate a committed catalog edit.
        with db.no_autoflush:
            return db.query(Product).filter(
                Product.team_id == team_id, Product.public_id == public_id,
            ).populate_existing().with_for_update().one_or_none()


    @staticmethod
    def _lock_team_customers(db: Session, team_id: int) -> list[int]:
        # A catalog edit can change every customer's draft grounding. Acquire
        # customer locks before any product row lock, in a stable order.
        with db.no_autoflush:
            return [int(row.id) for row in db.query(Customer.id).filter(
                Customer.team_id == team_id,
            ).order_by(Customer.id).with_for_update().all()]

    @staticmethod
    def _advance_customers(db: Session, team_id: int, customer_ids: list[int], *, deleted: bool = False) -> None:
        for customer_id in customer_ids:
            advance_eligible_progress(db, team_id=team_id, customer_id=customer_id, deleted=deleted)

    @classmethod
    def _locked_product(
        cls, db: Session, product: Product, *, lock_customers: bool = True,
    ) -> tuple[Product, list[int]]:
        if not cls._is_owned_product(product):
            raise ValueError("产品团队信息无效")
        team_id = int(product.team_id)
        cls.lock_catalog_team(db, team_id)
        customer_ids = cls._lock_team_customers(db, team_id) if lock_customers else []
        # A product passed by the API was loaded before the Team lock. Read the
        # current row under the lock rather than trusting the identity map.
        with db.no_autoflush:
            current = (
                db.query(Product)
                .filter(Product.id == product.id, Product.team_id == team_id)
                .populate_existing()
                .with_for_update()
                .one_or_none()
            )
        if current is None:
            raise ValueError("产品团队信息无效")
        return current, customer_ids

    @classmethod
    def _locked_module(cls, db: Session, module: ProductModule) -> ProductModule:
        team_id = module.team_id
        if team_id is None or int(team_id) <= 0:
            raise ValueError("产品模块团队不一致")
        cls.lock_catalog_team(db, int(team_id))
        # Both reads must be current reads under the Team lock. The caller's
        # module and its product relationship may predate another transaction.
        with db.no_autoflush:
            current = (
                db.query(ProductModule)
                .filter(ProductModule.id == module.id, ProductModule.team_id == team_id)
                .populate_existing()
                .with_for_update()
                .one_or_none()
            )
            if current is None:
                raise ValueError("产品模块团队不一致")
            product = (
                db.query(Product)
                .filter(Product.id == current.product_id, Product.team_id == team_id)
                .populate_existing()
                .with_for_update()
                .one_or_none()
            )
        if product is None:
            raise ValueError("产品模块团队不一致")
        return current

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
        self.lock_catalog_team(db, team_id)
        customer_ids = self._lock_team_customers(db, team_id)
        product = Product(
            team_id=team_id,
            created_by=creator_id,
            code=generate_public_id("PRD"),
            **data,
        )
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
            self._advance_customers(db, team_id, customer_ids)
            db.commit()
        except IntegrityError as exc:
            db.rollback()
            raise ValueError("产品编码已存在") from exc
        db.refresh(product)
        return product

    def update(self, db: Session, product: Product, obj_in: ProductUpdate, updater_id: str) -> Product:
        product, customer_ids = self._locked_product(db, product)
        data = self._dump(obj_in)
        changed = {key: value for key, value in data.items() if getattr(product, key) != value}
        old_active = bool(product.is_active)
        affected: list[int] = []
        if "name" in changed or "is_active" in changed:
            if old_active or bool(changed.get("is_active")):
                affected = customer_ids
            elif "name" in changed:
                # Inactive products can still name a linked customer intent or
                # an opportunity in the full-row context snapshot.
                with db.no_autoflush:
                    linked_ids = db.query(CustomerProduct.customer_id).filter(
                        CustomerProduct.team_id == product.team_id,
                        CustomerProduct.product_id == product.id,
                    ).with_for_update().all()
                    opportunity_ids = db.query(Opportunity.customer_id).filter(
                        Opportunity.team_id == product.team_id,
                        Opportunity.product_id == product.id,
                    ).with_for_update().all()
                affected = sorted({int(row[0]) for row in (*linked_ids, *opportunity_ids)})
        if changed:
            for key, value in changed.items():
                setattr(product, key, value)
            product.updated_by = updater_id
            product.updated_time = business_now()
            self._advance_customers(db, int(product.team_id), affected)
        db.commit()
        db.refresh(product)
        return product

    def delete(self, db: Session, product: Product) -> None:
        product, customer_ids = self._locked_product(db, product)
        # The API may have populated modules before waiting for the Team lock.
        # Read the current rows for the deletion guard, not the cached collection.
        with db.no_autoflush:
            modules = (
                db.query(ProductModule)
                .filter(ProductModule.product_id == product.id, ProductModule.team_id == product.team_id)
                .populate_existing()
                .with_for_update()
                .all()
            )
        db.expire(product, ["modules"])
        if any(module.module_role == ProductModuleRole.ADD_ON.value for module in modules):
            raise ValueError("产品包含增强模块，无法删除")  # noqa: RUF001
        if len(modules) != 1 or modules[0].module_role != ProductModuleRole.BASE.value:
            raise ValueError("产品基础模块状态不安全，无法删除")  # noqa: RUF001
        from app.crud.product_intent import PRODUCT_IN_USE_MESSAGE, assert_product_deletable

        assert_product_deletable(db, product)
        try:
            if product.is_active:
                self._advance_customers(db, int(product.team_id), customer_ids, deleted=True)
            db.delete(product)
            db.commit()
        except IntegrityError as exc:
            db.rollback()
            raise ValueError(PRODUCT_IN_USE_MESSAGE) from exc

    def create_module(
        self,
        db: Session,
        product: Product,
        obj_in: ProductModuleCreate,
        creator_id: str,
    ) -> ProductModule:
        product, _customer_ids = self._locked_product(db, product, lock_customers=False)
        data = self._dump(obj_in)
        if data.get("module_role", ProductModuleRole.ADD_ON.value) != ProductModuleRole.ADD_ON.value:
            raise ValueError("新增模块只能是增强模块")
        data.pop("module_role", None)
        module = ProductModule(
            team_id=product.team_id,
            product=product,
            created_by=creator_id,
            base_key=None,
            code=generate_public_id("PRM"),
            **data,
        )
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
        module = self._locked_module(db, module)
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
        module = self._locked_module(db, module)
        if module.module_role == ProductModuleRole.BASE.value:
            raise ValueError("基础模块不可删除")
        db.delete(module)
        db.commit()


product_crud = ProductCRUD()
