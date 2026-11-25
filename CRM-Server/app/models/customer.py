from __future__ import annotations

import enum
from datetime import date, datetime
from enum import Enum as PyEnum
from typing import TYPE_CHECKING

from sqlalchemy import BigInteger, Boolean, Date, DateTime, ForeignKey, Index, Integer, String, Text, event
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import expression

from app.core.database import Base
from app.utils.dedupe_normalizer import mobile_dedupe_key, normalize_mobile
from app.utils.name_normalizer import build_customer_name_dedupe_key, normalize_corp_name  # R-ST-02
from app.utils.public_id import generate_public_id
from app.utils.time import business_now

if TYPE_CHECKING:
    from sqlalchemy.engine import Connection
    from sqlalchemy.orm import Mapper

    from app.models.acquisition_source import AcquisitionSource
    from app.models.contract import Contract
    from app.models.deployment import DeploymentInfo
    from app.models.invoice import InvoiceApplication, InvoiceTitle
    from app.models.license_application import LicenseApplication
    from app.models.product import Product


class CustomerIndustry(str, enum.Enum):
    FINANCE = "金融"
    INTERNET = "互联网"
    MANUFACTURING = "制造业"
    RETAIL = "零售"
    EDUCATION = "教育"
    HEALTHCARE = "医疗"
    REAL_ESTATE = "房地产"
    GOVERNMENT = "政府"
    LOGISTICS = "物流"
    ENERGY = "能源"
    TELECOMMUNICATIONS = "通信"
    CONSTRUCTION = "建筑"
    AGRICULTURE = "农业"
    ENTERTAINMENT = "娱乐"
    CONSULTING = "咨询"
    OTHER = "其他"
    
    @classmethod
    def from_string(cls, value: str) -> CustomerIndustry:
        """从字符串值获取枚举成员"""
        for member in cls:
            if member.value == value:
                return member
        raise ValueError(f"'{value}' is not a valid {cls.__name__}")


class CustomerSource(str, enum.Enum):
    ONLINE_REGISTER = "线上注册"
    MARKETING_ACTIVITY = "市场活动"
    REFERRAL = "客户推荐"
    COLD_CALL = "电话营销"
    WEBSITE_INQUIRY = "网站咨询"
    EXHIBITION = "展会"
    OTHER = "其他"
    
    @classmethod
    def from_string(cls, value: str) -> CustomerSource:
        """从字符串值获取枚举成员"""
        for member in cls:
            if member.value == value:
                return member
        raise ValueError(f"'{value}' is not a valid {cls.__name__}")


class CustomerStatus(PyEnum):
    FOLLOWING = 0
    WON = 1
    LOST = 2
    INACTIVE = 3


class Customer(Base):
    __tablename__ = "crm_customers"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True, comment="主键")
    public_id: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        unique=True,
        index=True,
        default=lambda: generate_public_id("cus"),
        comment="对外客户ID",
    )
    team_id: Mapped[int] = mapped_column(BigInteger, nullable=False, index=True, comment="团队ID")
    account_name: Mapped[str] = mapped_column(String(255), nullable=False, comment="客户公司名称")
    account_name_norm: Mapped[str | None] = mapped_column(
        String(255), nullable=True, comment="归一化客户名称\uff08去后缀/括号\uff09"
    )  # R-ST-02
    account_name_dedupe_key: Mapped[str | None] = mapped_column(
        String(512), nullable=True, comment="客户名称判重键: NFKC/去格式字符/统一空白"
    )
    industry: Mapped[str | None] = mapped_column(String(100), nullable=True, comment="所属行业")
    city: Mapped[str] = mapped_column(String(100), nullable=False, comment="所在城市")
    address: Mapped[str | None] = mapped_column(String(500), nullable=True, comment="公司地址")
    company_scale: Mapped[str | None] = mapped_column(String(50), nullable=True, comment="公司规模")
    source: Mapped[str | None] = mapped_column(String(50), nullable=True, comment="客户来源")
    source_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True, comment="获客来源ID")

    status: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, comment="客户状态\uff1a0:跟进中, 1:已赢单, 2:已输单, 3:已失效"
    )
    owner_id: Mapped[str | None] = mapped_column(String(100), nullable=True, comment="负责人系统用户ID")
    source_lead_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True, comment="来源线索ID")
    default_procurement_method_id: Mapped[int | None] = mapped_column(
        BigInteger, nullable=True, comment="默认采购方式ID"
    )
    loss_reason: Mapped[str | None] = mapped_column(String(500), nullable=True, comment="输单原因")
    return_reason: Mapped[str | None] = mapped_column(String(255), nullable=True, comment="退回公海原因")
    returned_time: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, comment="退回公海时间")

    creator_id: Mapped[str] = mapped_column(String(100), nullable=False, comment="创建人")
    created_time: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=business_now, comment="创建时间")
    last_modified_time: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=business_now, onupdate=business_now, comment="最后修改时间"
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1, comment="版本号\uff08乐观锁\uff09")

    license_expiry_date: Mapped[date | None] = mapped_column(
        Date, nullable=True, comment="客户 License 最晚到期时间\uff08自动更新\uff09"
    )
    license_type: Mapped[str | None] = mapped_column(
        String(20), nullable=True, comment="客户 License 类型\uff08自动更新\uff09\uff1aTRIAL/OFFICIAL"
    )
    license_authorized_users: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True,
        comment="客户 License 授权人数\uff08自动更新\uff09",
    )
    license_is_permanent: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        server_default=expression.false(),
        comment="客户 License 是否永久\uff08自动更新\uff0c永久时到期时间为空\uff09",
    )

    contacts: Mapped[list[Contact]] = relationship("Contact", back_populates="customer", cascade="all, delete-orphan")
    contracts: Mapped[list[Contract]] = relationship(
        "Contract", back_populates="customer", cascade="all, delete-orphan"
    )
    deployment_infos: Mapped[list[DeploymentInfo]] = relationship(
        "DeploymentInfo", back_populates="customer", cascade="all, delete-orphan"
    )
    license_applications: Mapped[list[LicenseApplication]] = relationship(
        "LicenseApplication", back_populates="customer", cascade="all, delete-orphan"
    )
    invoice_titles: Mapped[list[InvoiceTitle]] = relationship(
        "InvoiceTitle", back_populates="customer", cascade="all, delete-orphan"
    )
    invoice_applications: Mapped[list[InvoiceApplication]] = relationship(
        "InvoiceApplication", back_populates="customer", cascade="all, delete-orphan"
    )
    members: Mapped[list[CustomerMember]] = relationship(
        "CustomerMember", back_populates="customer", cascade="all, delete-orphan"
    )
    acquisition_source: Mapped[AcquisitionSource | None] = relationship(
        "AcquisitionSource",
        primaryjoin="foreign(Customer.source_id)==AcquisitionSource.id",
        viewonly=True,
    )
    product_links: Mapped[list[CustomerProduct]] = relationship(
        "CustomerProduct",
        back_populates="customer",
        cascade="all, delete-orphan",
    )
    __table_args__ = (
        Index('idx_account_name', 'account_name'),
        Index('uq_customer_team_account_name', 'team_id', 'account_name', unique=True),
        Index('uq_customer_team_name_dedupe_key', 'team_id', 'account_name_dedupe_key', unique=True),
        Index(
            'idx_account_name_norm_gin',
            'account_name_norm',
            postgresql_using='gin',
            postgresql_ops={'account_name_norm': 'gin_trgm_ops'},
        ),  # R-ST-02: pg_trgm GIN 索引
        Index('idx_industry', 'industry'),
        Index('idx_city', 'city'),
        Index('idx_status', 'status'),
        Index('idx_owner_id', 'owner_id'),
        Index('idx_source_lead_id', 'source_lead_id'),
        Index('idx_customers_source_id', 'source_id'),
        Index('idx_created_time', 'created_time'),
        Index('idx_team_id', 'team_id'),
        Index('idx_customer_public_id', 'public_id'),
        {'comment': '客户/公司表'}
    )


class CustomerProduct(Base):
    __tablename__ = "crm_customer_products"

    customer_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("crm_customers.id", ondelete="CASCADE"), primary_key=True, comment="客户ID"
    )
    product_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("crm_products.id", ondelete="RESTRICT"), primary_key=True, comment="产品ID"
    )
    team_id: Mapped[int] = mapped_column(BigInteger, nullable=False, comment="团队ID")

    customer: Mapped[Customer] = relationship("Customer", back_populates="product_links")
    product: Mapped[Product] = relationship("Product")

    __table_args__ = (
        Index("idx_customer_products_team", "team_id"),
        Index("idx_customer_products_product", "product_id"),
        {"comment": "客户意向产品"},
    )


# R-ST-02: ORM hook 自动维护 account_name_norm 与 account_name_dedupe_key
@event.listens_for(Customer, 'before_insert')
@event.listens_for(Customer, 'before_update')
def customer_update_name_norm(_mapper: Mapper[Customer], _connection: Connection, target: Customer) -> None:
    """Customer 写入时自动归一化 account_name_norm 并生成判重键"""
    if target.account_name:
        target.account_name_norm = normalize_corp_name(target.account_name)
    else:
        target.account_name_norm = None
    target.account_name_dedupe_key = build_customer_name_dedupe_key(target.account_name)


class Contact(Base):
    __tablename__ = "crm_contacts"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True, comment="主键")
    team_id: Mapped[int] = mapped_column(BigInteger, nullable=False, index=True, comment="团队ID")
    customer_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey('crm_customers.id', ondelete='CASCADE'), nullable=False, comment="所属客户ID"
    )
    name: Mapped[str] = mapped_column(String(100), nullable=False, comment="联系人姓名")
    gender: Mapped[int | None] = mapped_column(Integer, nullable=True, comment="性别\uff1a0:未知, 1:男, 2:女")
    position: Mapped[str | None] = mapped_column(String(100), nullable=True, comment="职务")
    is_decision_maker: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, comment="是否关键决策人\uff1a0:否, 1:是"
    )
    mobile: Mapped[str] = mapped_column(String(20), nullable=False, comment="手机号")
    mobile_dedupe_key: Mapped[str | None] = mapped_column(
        String(20), nullable=True, comment="手机号判重键\uff08ORM hook 维护\uff0c空手机号为 NULL\uff09"
    )
    email: Mapped[str | None] = mapped_column(String(100), nullable=True, comment="邮箱")
    wechat_id: Mapped[str | None] = mapped_column(String(100), nullable=True, comment="微信ID")
    remark: Mapped[str | None] = mapped_column(Text, nullable=True, comment="备注")
    reports_to: Mapped[int | None] = mapped_column(BigInteger, nullable=True, comment="汇报对象联系人ID")
    is_primary: Mapped[int] = mapped_column(Integer, nullable=False, default=0, comment="是否主联系人\uff1a0:否, 1:是")
    post_commit_revision: Mapped[int] = mapped_column(
        Integer, nullable=False, default=1, comment="客户智能后提交事件修订号"
    )
    created_time: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=business_now, comment="创建时间")
    updated_time: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=business_now, onupdate=business_now, comment="更新时间"
    )

    customer: Mapped[Customer] = relationship("Customer", back_populates="contacts")

    __table_args__ = (
        Index('idx_customer_id', 'customer_id'),
        Index('idx_mobile', 'mobile'),
        Index('idx_name', 'name'),
        Index('idx_is_primary', 'is_primary'),
        Index('idx_team_id', 'team_id'),
        Index('uq_contact_customer_mobile_key', 'customer_id', 'mobile_dedupe_key', unique=True),
        {'comment': '联系人表'}
    )


@event.listens_for(Contact, 'before_insert')
@event.listens_for(Contact, 'before_update')
def contact_normalize_mobile(_mapper: Mapper[Contact], _connection: Connection, target: Contact) -> None:
    """Store the normalized mobile and keep its per-customer dedupe key in sync."""
    target.mobile = normalize_mobile(target.mobile)
    target.mobile_dedupe_key = mobile_dedupe_key(target.mobile)


class CustomerMember(Base):
    __tablename__ = "crm_customer_members"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True, comment="主键")
    team_id: Mapped[int] = mapped_column(BigInteger, nullable=False, index=True, comment="团队ID")
    customer_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey('crm_customers.id', ondelete='CASCADE'), nullable=False, comment="客户ID"
    )
    user_id: Mapped[str] = mapped_column(String(100), nullable=False, comment="成员系统用户ID")
    member_role: Mapped[str] = mapped_column(
        String(20), nullable=False, default="PRESALES", comment="成员角色\uff1aSALES/PRESALES/DELIVERY/SUPPORT/OTHER"
    )
    access_level: Mapped[str] = mapped_column(
        String(20), nullable=False, default="VIEW", comment="访问级别\uff1aVIEW/FOLLOW_UP/EDIT"
    )
    remark: Mapped[str | None] = mapped_column(String(500), nullable=True, comment="备注")
    created_by: Mapped[str] = mapped_column(String(100), nullable=False, comment="创建人")
    created_time: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=business_now, comment="创建时间")
    updated_time: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=business_now, onupdate=business_now, comment="更新时间"
    )
    post_commit_revision: Mapped[int] = mapped_column(
        Integer, nullable=False, default=1, comment="客户智能后提交事件修订号"
    )
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, comment="是否有效")

    customer: Mapped[Customer] = relationship("Customer", back_populates="members")

    __table_args__ = (
        Index('idx_customer_member_customer', 'customer_id'),
        Index('idx_customer_member_user', 'user_id'),
        Index('idx_customer_member_team_customer_user_active', 'team_id', 'customer_id', 'user_id', 'is_active'),
        {'comment': '客户团队成员表'}
    )
