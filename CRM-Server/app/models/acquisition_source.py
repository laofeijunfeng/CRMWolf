from sqlalchemy import (
    BigInteger,
    Column,
    DateTime,
    Index,
    Integer,
    String,
    UniqueConstraint,
)

from app.core.database import Base
from app.utils.public_id import generate_public_id
from app.utils.time import business_now


class AcquisitionSource(Base):
    """团队级获客来源配置。线索和客户共用，不提供删除。"""

    __tablename__ = "crm_acquisition_sources"

    id = Column(BigInteger, primary_key=True, autoincrement=True, comment="主键")
    public_id = Column(
        String(64),
        nullable=False,
        default=lambda: generate_public_id("acq"),
        comment="对外获客来源ID",
    )
    team_id = Column(BigInteger, nullable=False, comment="团队ID")
    code = Column(String(50), nullable=False, comment="来源编码，系统项固定，自定义项服务端生成")
    name = Column(String(50), nullable=False, comment="展示名称")
    is_system = Column(Integer, nullable=False, default=0, comment="是否系统默认项: 1是, 0否")
    is_active = Column(Integer, nullable=False, default=1, comment="是否启用: 1启用, 0停用")
    sort_order = Column(Integer, nullable=False, comment="前端排序")
    created_by = Column(String(100), nullable=False, comment="创建人系统用户ID")
    updated_by = Column(String(100), nullable=True, comment="最后更新人系统用户ID")
    created_time = Column(DateTime, default=business_now, nullable=False, comment="创建时间")
    updated_time = Column(
        DateTime,
        default=business_now,
        onupdate=business_now,
        nullable=False,
        comment="最后更新时间",
    )

    __table_args__ = (
        UniqueConstraint("public_id", name="uq_acq_source_public_id"),
        UniqueConstraint("team_id", "code", name="uq_acq_source_team_code"),
        UniqueConstraint("team_id", "name", name="uq_acq_source_team_name"),
        Index("idx_acq_source_team_active_sort", "team_id", "is_active", "sort_order"),
        Index("idx_acq_source_team_id", "team_id"),
        {"comment": "获客来源配置表"},
    )
