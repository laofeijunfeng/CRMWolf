"""
AI Skill 数据库模型
"""
from sqlalchemy import Column, BigInteger, String, Integer, DateTime, Text, JSON, Index
from sqlalchemy.sql import func
from app.core.database import Base


class AISkill(Base):
    """Skill 主表"""
    __tablename__ = "crm_ai_skills"

    id = Column(BigInteger, primary_key=True, autoincrement=True, comment="主键")
    skill_name = Column(String(100), nullable=False, unique=True, comment="Skill名称（如LeadSkill）")
    display_name = Column(String(100), nullable=False, comment="显示名称（如线索管理）")
    description = Column(String(500), nullable=False, comment="Skill描述")
    module_type = Column(String(50), nullable=False, comment="业务模块类型（lead/customer等）")
    is_active = Column(Integer, nullable=False, default=1, comment="是否启用（1启用0禁用）")
    sort_order = Column(Integer, nullable=False, default=0, comment="排序序号")
    created_time = Column(DateTime, nullable=False, default=func.now(), comment="创建时间")
    updated_time = Column(DateTime, nullable=False, default=func.now(), onupdate=func.now(), comment="更新时间")

    __table_args__ = (
        Index('idx_skill_name', 'skill_name'),
        Index('idx_module_type', 'module_type'),
        Index('idx_is_active', 'is_active'),
        {'comment': 'AI Skill配置表'}
    )


class AISkillAction(Base):
    """Action 子表"""
    __tablename__ = "crm_ai_skill_actions"

    id = Column(BigInteger, primary_key=True, autoincrement=True, comment="主键")
    skill_id = Column(BigInteger, nullable=False, comment="关联Skill ID")
    action_name = Column(String(100), nullable=False, comment="Action名称（list/detail/create）")
    display_name = Column(String(100), nullable=False, comment="显示名称")
    description = Column(String(500), nullable=False, comment="Action描述")
    handler_type = Column(String(50), nullable=False, comment="Handler类型（QueryListHandler等）")
    handler_config = Column(JSON, nullable=False, comment="Handler配置JSON")
    required_params = Column(JSON, nullable=False, default=[], comment="必填参数列表")
    optional_params = Column(JSON, nullable=True, default=[], comment="可选参数列表")
    permission_code = Column(String(100), nullable=False, comment="权限码")
    result_template = Column(String(1000), nullable=True, comment="结果输出模板")
    is_active = Column(Integer, nullable=False, default=1, comment="是否启用")
    sort_order = Column(Integer, nullable=False, default=0, comment="排序序号")
    created_time = Column(DateTime, nullable=False, default=func.now(), comment="创建时间")
    updated_time = Column(DateTime, nullable=False, default=func.now(), onupdate=func.now(), comment="更新时间")

    __table_args__ = (
        Index('idx_skill_id', 'skill_id'),
        Index('idx_action_name', 'action_name'),
        Index('idx_handler_type', 'handler_type'),
        Index('idx_is_active', 'is_active'),
        {'comment': 'AI Skill Action配置表'}
    )


class AICRUDMapping(Base):
    """CRUD 映射表"""
    __tablename__ = "crm_ai_crud_mappings"

    id = Column(BigInteger, primary_key=True, autoincrement=True, comment="主键")
    mapping_name = Column(String(100), nullable=False, unique=True, comment="映射名称（lead/customer_follow_up）")
    crud_module = Column(String(100), nullable=False, comment="CRUD模块路径（app.crud.lead）")
    crud_instance_name = Column(String(100), nullable=False, comment="CRUD实例名（lead_crud）")
    model_class = Column(String(100), nullable=False, comment="Model类名（Lead）")
    schema_create_class = Column(String(100), nullable=True, comment="Create Schema类名")
    schema_update_class = Column(String(100), nullable=True, comment="Update Schema类名")
    owner_field = Column(String(50), nullable=True, default="owner_id", comment="负责人字段名")
    status_field = Column(String(50), nullable=True, default="status", comment="状态字段名")
    name_field = Column(String(50), nullable=True, comment="名称字段名（用于模糊搜索）")
    created_time = Column(DateTime, nullable=False, default=func.now(), comment="创建时间")
    updated_time = Column(DateTime, nullable=False, default=func.now(), onupdate=func.now(), comment="更新时间")

    __table_args__ = (
        Index('idx_mapping_name', 'mapping_name'),
        {'comment': 'AI CRUD映射表'}
    )


class AIEnumMapping(Base):
    """Enum 映射表"""
    __tablename__ = "crm_ai_enum_mappings"

    id = Column(BigInteger, primary_key=True, autoincrement=True, comment="主键")
    enum_name = Column(String(100), nullable=False, unique=True, comment="Enum名称（lead_source/follow_up_method）")
    display_name = Column(String(100), nullable=False, comment="显示名称")
    enum_class = Column(String(100), nullable=False, comment="Enum类路径（app.models.lead:LeadSource）")
    values = Column(JSON, nullable=False, comment="值映射 {'电话': 'PHONE', '微信': 'WECHAT'}")
    created_time = Column(DateTime, nullable=False, default=func.now(), comment="创建时间")
    updated_time = Column(DateTime, nullable=False, default=func.now(), onupdate=func.now(), comment="更新时间")

    __table_args__ = (
        Index('idx_enum_name', 'enum_name'),
        {'comment': 'AI Enum映射表'}
    )