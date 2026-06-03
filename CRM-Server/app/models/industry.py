"""
行业分级模型

支持一级行业和二级行业的分层管理
"""
from sqlalchemy import Column, Integer, String, DateTime, func, ForeignKey
from sqlalchemy.orm import relationship
from app.core.database import Base


class Industry(Base):
    """行业分级表"""
    __tablename__ = "crm_industries"

    id = Column(Integer, primary_key=True, autoincrement=True, comment="主键")
    level = Column(Integer, nullable=False, comment="层级：1=一级行业，2=二级行业")
    parent_id = Column(Integer, ForeignKey('crm_industries.id'), nullable=True, comment="父行业ID（二级行业关联一级行业）")
    code = Column(String(50), nullable=False, unique=True, comment="行业编码")
    name = Column(String(100), nullable=False, comment="行业名称")
    sort_order = Column(Integer, default=0, comment="排序")
    is_active = Column(Integer, default=1, comment="是否启用：1=启用，0=停用")
    created_time = Column(DateTime, nullable=False, default=func.now(), comment="创建时间")

    # 自关联关系
    # parent: 多对一，返回单个父行业对象
    # children: 一对多，返回子行业列表
    parent = relationship("Industry", remote_side=[id], foreign_keys=[parent_id], uselist=False)
    children = relationship("Industry", foreign_keys=[parent_id], overlaps="parent")

    __table_args__ = (
        {'comment': '行业分级表'}
    )

    @property
    def is_primary(self) -> bool:
        """是否是一级行业"""
        return self.level == 1

    @property
    def is_secondary(self) -> bool:
        """是否是二级行业"""
        return self.level == 2

    @property
    def parent_industry(self) -> str:
        """获取父行业名称（仅二级行业有效）"""
        if self.parent:
            return self.parent.name
        return None