from __future__ import annotations

from enum import StrEnum

from sqlalchemy import BigInteger, Boolean, CheckConstraint, Column, DateTime, ForeignKeyConstraint, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import relationship

from app.core.database import Base
from app.utils.public_id import generate_public_id
from app.utils.time import business_now


class ProductModuleRole(StrEnum):
    BASE = "BASE"
    ADD_ON = "ADD_ON"


_SQLITE_BIGINT = BigInteger().with_variant(Integer, "sqlite")


class Product(Base):
    __tablename__ = "crm_products"

    id = Column(_SQLITE_BIGINT, primary_key=True, autoincrement=True, comment="主键")
    public_id = Column(String(64), nullable=False, default=lambda: generate_public_id("prd"), comment="产品对外ID")
    team_id = Column(_SQLITE_BIGINT, nullable=False, comment="团队ID")
    code = Column(String(50), nullable=False, comment="团队内产品编码")
    name = Column(String(100), nullable=False, comment="产品名称")
    description = Column(Text, nullable=True, comment="产品描述")
    is_active = Column(Boolean, nullable=False, default=True, comment="是否启用")
    created_by = Column(String(100), nullable=False, comment="创建人")
    updated_by = Column(String(100), nullable=True, comment="最后更新人")
    created_time = Column(DateTime, nullable=False, default=business_now, comment="创建时间")
    updated_time = Column(DateTime, nullable=False, default=business_now, onupdate=business_now, comment="更新时间")

    modules = relationship(
        "ProductModule",
        back_populates="product",
        cascade="all, delete-orphan",
        order_by="(ProductModule.sort_order, ProductModule.id)",
    )

    __table_args__ = (
        UniqueConstraint("public_id", name="uq_crm_products_public_id"),
        UniqueConstraint("team_id", "code", name="uq_crm_products_team_code"),
        UniqueConstraint("id", "team_id", name="uq_crm_products_id_team"),
        Index("idx_crm_products_team_active", "team_id", "is_active"),
        Index("idx_crm_products_team_id", "team_id"),
        Index("idx_crm_products_code", "code"),
        {"comment": "团队级产品目录"},
    )


class ProductModule(Base):
    __tablename__ = "crm_product_modules"

    id = Column(_SQLITE_BIGINT, primary_key=True, autoincrement=True, comment="主键")
    public_id = Column(String(64), nullable=False, default=lambda: generate_public_id("prm"), comment="模块对外ID")
    team_id = Column(_SQLITE_BIGINT, nullable=False, comment="团队ID")
    product_id = Column(_SQLITE_BIGINT, nullable=False, comment="所属产品ID")
    code = Column(String(50), nullable=False, comment="产品内模块编码")
    name = Column(String(100), nullable=False, comment="模块名称")
    description = Column(Text, nullable=True, comment="模块描述")
    module_role = Column(String(20), nullable=False, default=ProductModuleRole.ADD_ON.value, comment="模块角色")
    base_key = Column(String(10), nullable=True, comment="基础模块唯一键；增强模块为空")
    is_active = Column(Boolean, nullable=False, default=True, comment="是否启用")
    sort_order = Column(Integer, nullable=False, default=0, comment="展示顺序")
    created_by = Column(String(100), nullable=False, comment="创建人")
    updated_by = Column(String(100), nullable=True, comment="最后更新人")
    created_time = Column(DateTime, nullable=False, default=business_now, comment="创建时间")
    updated_time = Column(DateTime, nullable=False, default=business_now, onupdate=business_now, comment="更新时间")

    product = relationship("Product", back_populates="modules")

    __table_args__ = (
        ForeignKeyConstraint(
            ["product_id", "team_id"],
            ["crm_products.id", "crm_products.team_id"],
            ondelete="CASCADE",
            name="fk_crm_product_modules_product_team",
        ),
        UniqueConstraint("public_id", name="uq_crm_product_modules_public_id"),
        UniqueConstraint("product_id", "code", name="uq_crm_product_modules_product_code"),
        UniqueConstraint("product_id", "base_key", name="uq_crm_product_modules_product_base_key"),
        CheckConstraint("module_role IN ('BASE', 'ADD_ON')", name="ck_crm_product_modules_role"),
        CheckConstraint(
            "(module_role = 'BASE' AND base_key = 'BASE') OR (module_role = 'ADD_ON' AND base_key IS NULL)",
            name="ck_crm_product_modules_base_key",
        ),
        Index("idx_crm_product_modules_team_product", "team_id", "product_id"),
        Index("idx_crm_product_modules_team_active", "team_id", "is_active"),
        Index("idx_crm_product_modules_product_role", "product_id", "module_role"),
        {"comment": "产品模块目录"},
    )
