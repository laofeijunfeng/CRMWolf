"""
AI Skill 配置 Schema

用于 Skill、Action、CRUD 映射、Enum 映射的 API 请求/响应
"""
from pydantic import BaseModel, Field
from typing import Optional, Dict, Any, List


# ============================================================================
# Skill Schemas
# ============================================================================

class SkillCreate(BaseModel):
    """创建 Skill"""
    skill_name: str = Field(..., description="Skill名称（如LeadSkill）")
    display_name: str = Field(..., description="显示名称（如线索管理）")
    description: str = Field(..., description="Skill描述")
    module_type: str = Field(..., description="业务模块类型（lead/customer等）")
    is_active: int = Field(default=1, description="是否启用")
    sort_order: int = Field(default=0, description="排序序号")


class SkillUpdate(BaseModel):
    """更新 Skill"""
    display_name: Optional[str] = None
    description: Optional[str] = None
    module_type: Optional[str] = None
    is_active: Optional[int] = None
    sort_order: Optional[int] = None


class SkillResponse(BaseModel):
    """Skill 响应"""
    id: int
    skill_name: str
    display_name: str
    description: str
    module_type: str
    is_active: int
    sort_order: int
    created_time: Optional[str] = None
    updated_time: Optional[str] = None


# ============================================================================
# Skill Action Schemas
# ============================================================================

class SkillActionCreate(BaseModel):
    """创建 Action"""
    action_name: str = Field(..., description="Action名称（list/detail/create）")
    display_name: str = Field(..., description="显示名称")
    description: str = Field(..., description="Action描述")
    handler_type: str = Field(..., description="Handler类型")
    handler_config: Dict[str, Any] = Field(..., description="Handler配置JSON")
    required_params: List[str] = Field(default=[], description="必填参数列表")
    optional_params: List[str] = Field(default=[], description="可选参数列表")
    permission_code: str = Field(..., description="权限码")
    result_template: Optional[str] = Field(None, description="结果输出模板")
    is_active: int = Field(default=1, description="是否启用")
    sort_order: int = Field(default=0, description="排序序号")


class SkillActionUpdate(BaseModel):
    """更新 Action"""
    display_name: Optional[str] = None
    description: Optional[str] = None
    handler_type: Optional[str] = None
    handler_config: Optional[Dict[str, Any]] = None
    required_params: Optional[List[str]] = None
    optional_params: Optional[List[str]] = None
    permission_code: Optional[str] = None
    result_template: Optional[str] = None
    is_active: Optional[int] = None
    sort_order: Optional[int] = None


class SkillActionResponse(BaseModel):
    """Action 响应"""
    id: int
    skill_id: int
    action_name: str
    display_name: str
    description: str
    handler_type: str
    handler_config: Dict[str, Any]
    required_params: List[str]
    optional_params: List[str]
    permission_code: str
    result_template: Optional[str] = None
    is_active: int
    sort_order: int


# ============================================================================
# CRUD Mapping Schemas
# ============================================================================

class CRUDMappingCreate(BaseModel):
    """创建 CRUD 映射"""
    mapping_name: str = Field(..., description="映射名称（lead/customer_follow_up）")
    crud_module: str = Field(..., description="CRUD模块路径（app.crud.lead）")
    crud_instance_name: str = Field(..., description="CRUD实例名（lead_crud）")
    model_class: str = Field(..., description="Model类名（Lead）")
    schema_create_class: Optional[str] = Field(None, description="Create Schema类名")
    schema_update_class: Optional[str] = Field(None, description="Update Schema类名")
    owner_field: Optional[str] = Field("owner_id", description="负责人字段名")
    status_field: Optional[str] = Field("status", description="状态字段名")
    name_field: Optional[str] = Field(None, description="名称字段名")


class CRUDMappingUpdate(BaseModel):
    """更新 CRUD 映射"""
    crud_module: Optional[str] = None
    crud_instance_name: Optional[str] = None
    model_class: Optional[str] = None
    schema_create_class: Optional[str] = None
    schema_update_class: Optional[str] = None
    owner_field: Optional[str] = None
    status_field: Optional[str] = None
    name_field: Optional[str] = None


class CRUDMappingResponse(BaseModel):
    """CRUD 映射响应"""
    id: int
    mapping_name: str
    crud_module: str
    crud_instance_name: str
    model_class: str
    schema_create_class: Optional[str] = None
    schema_update_class: Optional[str] = None
    owner_field: Optional[str] = None
    status_field: Optional[str] = None
    name_field: Optional[str] = None


# ============================================================================
# Enum Mapping Schemas
# ============================================================================

class EnumMappingCreate(BaseModel):
    """创建 Enum 映射"""
    enum_name: str = Field(..., description="Enum名称（lead_source/follow_up_method）")
    display_name: str = Field(..., description="显示名称")
    enum_class: str = Field(..., description="Enum类路径（app.models.lead:LeadSource）")
    values: Dict[str, str] = Field(..., description="值映射 {'电话': 'PHONE'}")


class EnumMappingUpdate(BaseModel):
    """更新 Enum 映射"""
    display_name: Optional[str] = None
    enum_class: Optional[str] = None
    values: Optional[Dict[str, str]] = None


class EnumMappingResponse(BaseModel):
    """Enum 映射响应"""
    id: int
    enum_name: str
    display_name: str
    enum_class: str
    values: Dict[str, str]


# ============================================================================
# AI Skill Generator Schemas
# ============================================================================

class SkillAnalyzeRequest(BaseModel):
    """Skill 分析请求"""
    requirement: str = Field(..., description="用户需求描述（如：产品管理，支持列表和创建）")


class SkillGenerateRequest(BaseModel):
    """Skill 生成请求"""
    config_prompt: str = Field(..., description="经过用户确认的配置 Prompt")


class SkillAnalyzeResult(BaseModel):
    """Skill 分析结果"""
    supported: bool = Field(..., description="模块是否支持")
    message: str = Field(..., description="提示信息")
    config_prompt: Optional[str] = Field(None, description="生成的配置 Prompt（仅当 supported=true 时）")


class SkillGenerateResult(BaseModel):
    """Skill 生成结果"""
    skill_id: int = Field(..., description="生成的 Skill ID")
    skill_name: str = Field(..., description="Skill 名称")
    display_name: str = Field(..., description="显示名称")
    action_count: int = Field(..., description="生成的 Action 数量")
    message: str = Field(..., description="提示信息")