from sqlalchemy import Column, BigInteger, String, Integer, DateTime, Text, Enum, Index
from sqlalchemy.orm import relationship
from app.core.database import Base
from app.utils.time import business_now
from app.utils.public_id import generate_public_id
import enum


class LeadSource(str, enum.Enum):
    ONLINE_REGISTER = "线上注册"
    MARKETING_ACTIVITY = "市场活动"
    REFERRAL = "客户推荐"
    COLD_CALL = "电话营销"
    WEBSITE_INQUIRY = "网站咨询"
    EXHIBITION = "展会"
    OTHER = "其他"


class LeadStatus(int, enum.Enum):
    NEW = 0
    FOLLOWING = 1
    CONVERTED = 2
    INVALID = 3


class CompanyScale(str, enum.Enum):
    SCALE_1_50 = "1-50人"
    SCALE_51_200 = "51-200人"
    SCALE_201_500 = "201-500人"
    SCALE_501_1000 = "501-1000人"
    SCALE_1000_PLUS = "1000人以上"


class FollowUpMethod(str, enum.Enum):
    PHONE = "电话"
    WECHAT = "微信"
    VISIT = "拜访"
    EMAIL = "邮件"
    OTHER = "其他"


class Lead(Base):
    __tablename__ = "crm_leads"

    id = Column(BigInteger, primary_key=True, autoincrement=True, comment="主键")
    public_id = Column(String(64), nullable=False, unique=True, index=True, default=lambda: generate_public_id("lead"), comment="对外线索ID")
    team_id = Column(BigInteger, nullable=False, index=True, comment="团队ID")
    lead_name = Column(String(255), nullable=False, comment="线索名称")
    source = Column(String(50), nullable=False, comment="线索来源名称（跟读配置表，双写兼容）")
    source_id = Column(BigInteger, nullable=True, comment="获客来源ID")
    city = Column(String(100), nullable=False, comment="所在城市")
    contact_name = Column(String(100), nullable=False, comment="联系人姓名")
    contact_phone = Column(String(20), nullable=False, comment="联系人手机")
    company_scale = Column(Enum(CompanyScale), nullable=True, comment="团队规模")

    owner_id = Column(String(100), nullable=True, comment="负责人系统用户ID")
    status = Column(Enum(LeadStatus), nullable=False, default=LeadStatus.NEW, comment="线索状态")
    invalid_reason = Column(String(500), nullable=True, comment="无效原因")
    pool_id = Column(BigInteger, nullable=True, comment="所属线索池ID")

    creator_id = Column(String(100), nullable=False, comment="创建人系统用户ID")
    created_time = Column(DateTime, nullable=False, default=business_now, comment="创建时间")
    last_modified_time = Column(DateTime, nullable=False, default=business_now, onupdate=business_now, comment="最后修改时间")
    version = Column(Integer, nullable=False, default=1, comment="版本号（乐观锁）")

    acquisition_source = relationship(
        "AcquisitionSource",
        primaryjoin="foreign(Lead.source_id)==AcquisitionSource.id",
        viewonly=True,
    )

    __table_args__ = (
        Index('uq_lead_team_lead_name', 'team_id', 'lead_name', unique=True),
        Index('idx_owner_id', 'owner_id'),
        Index('idx_status', 'status'),
        Index('idx_source', 'source'),
        Index('idx_leads_source_id', 'source_id'),
        Index('idx_city', 'city'),
        Index('idx_created_time', 'created_time'),
        Index('idx_team_id', 'team_id'),
        Index('idx_lead_public_id', 'public_id'),
        {'comment': '线索表'}
    )


class LeadFollowUp(Base):
    __tablename__ = "crm_lead_follow_ups"

    id = Column(BigInteger, primary_key=True, autoincrement=True, comment="主键")
    team_id = Column(BigInteger, nullable=False, index=True, comment="团队ID")
    lead_id = Column(BigInteger, nullable=False, comment="关联线索ID")
    content = Column(Text, nullable=False, comment="跟进内容")
    method = Column(Enum(FollowUpMethod), nullable=False, comment="跟进方式")
    next_follow_time = Column(DateTime, nullable=True, comment="计划下次跟进时间")
    next_action = Column(Text, nullable=True, comment="下一步动作内容")

    creator_id = Column(String(100), nullable=False, comment="创建人系统用户ID")
    created_time = Column(DateTime, nullable=False, default=business_now, comment="创建时间")

    __table_args__ = (
        Index('idx_lead_id', 'lead_id'),
        Index('idx_creator_id', 'creator_id'),
        Index('idx_created_time', 'created_time'),
        Index('idx_team_id', 'team_id'),
        {'comment': '线索跟进记录表'}
    )
