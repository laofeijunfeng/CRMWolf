from sqlalchemy import Column, BigInteger, String, Integer, DateTime, func, Index, ForeignKey, Text
from sqlalchemy.orm import relationship
from enum import Enum as PyEnum
from app.core.database import Base
import enum


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
    def from_string(cls, value: str):
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
    def from_string(cls, value: str):
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

    id = Column(BigInteger, primary_key=True, autoincrement=True, comment="主键")
    account_name = Column(String(255), nullable=False, unique=True, comment="客户公司名称")
    industry = Column(String(100), nullable=True, comment="所属行业")
    city = Column(String(100), nullable=False, comment="所在城市")
    address = Column(String(500), nullable=True, comment="公司地址")
    company_scale = Column(String(50), nullable=True, comment="公司规模")
    source = Column(String(50), nullable=True, comment="客户来源")
    
    status = Column(Integer, nullable=False, default=0, comment="客户状态：0:跟进中, 1:已赢单, 2:已输单, 3:已失效")
    owner_id = Column(String(100), nullable=True, comment="负责人（飞书用户ID）")
    source_lead_id = Column(BigInteger, nullable=True, comment="来源线索ID")
    default_procurement_method_id = Column(BigInteger, nullable=True, comment="默认采购方式ID")
    return_reason = Column(String(255), nullable=True, comment="退回公海原因")
    returned_time = Column(DateTime, nullable=True, comment="退回公海时间")
    
    creator_id = Column(String(100), nullable=False, comment="创建人")
    created_time = Column(DateTime, nullable=False, default=func.now(), comment="创建时间")
    last_modified_time = Column(DateTime, nullable=False, default=func.now(), onupdate=func.now(), comment="最后修改时间")
    version = Column(Integer, nullable=False, default=1, comment="版本号（乐观锁）")
    
    contacts = relationship("Contact", back_populates="customer", cascade="all, delete-orphan")
    invoice_titles = relationship("InvoiceTitle", back_populates="customer", cascade="all, delete-orphan")
    invoice_applications = relationship("InvoiceApplication", back_populates="customer", cascade="all, delete-orphan")
    
    __table_args__ = (
        Index('idx_account_name', 'account_name'),
        Index('idx_industry', 'industry'),
        Index('idx_city', 'city'),
        Index('idx_status', 'status'),
        Index('idx_owner_id', 'owner_id'),
        Index('idx_source_lead_id', 'source_lead_id'),
        Index('idx_created_time', 'created_time'),
        {'comment': '客户/公司表'}
    )


class Contact(Base):
    __tablename__ = "crm_contacts"

    id = Column(BigInteger, primary_key=True, autoincrement=True, comment="主键")
    customer_id = Column(BigInteger, ForeignKey('crm_customers.id', ondelete='CASCADE'), nullable=False, comment="所属客户ID")
    name = Column(String(100), nullable=False, comment="联系人姓名")
    gender = Column(Integer, nullable=True, comment="性别：0:未知, 1:男, 2:女")
    position = Column(String(100), nullable=True, comment="职务")
    is_decision_maker = Column(Integer, nullable=False, default=0, comment="是否关键决策人：0:否, 1:是")
    mobile = Column(String(20), nullable=False, unique=True, comment="手机号")
    email = Column(String(100), nullable=True, comment="邮箱")
    wechat_id = Column(String(100), nullable=True, comment="微信ID")
    remark = Column(Text, nullable=True, comment="备注")
    reports_to = Column(BigInteger, nullable=True, comment="汇报对象联系人ID")
    is_primary = Column(Integer, nullable=False, default=0, comment="是否主联系人：0:否, 1:是")
    created_time = Column(DateTime, nullable=False, default=func.now(), comment="创建时间")
    
    customer = relationship("Customer", back_populates="contacts")
    
    __table_args__ = (
        Index('idx_customer_id', 'customer_id'),
        Index('idx_mobile', 'mobile'),
        Index('idx_name', 'name'),
        Index('idx_is_primary', 'is_primary'),
        {'comment': '联系人表'}
    )
