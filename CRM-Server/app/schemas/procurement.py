from pydantic import BaseModel, Field, field_validator
from typing import Optional, List
from datetime import datetime
from enum import Enum


class ProcurementMethodOption(BaseModel):
    """采购方式选项（用于下拉选择）"""
    id: int = Field(..., description="采购方式ID")
    code: str = Field(..., description="采购方式编码")
    name: str = Field(..., description="采购方式名称")
    
    class Config:
        from_attributes = True


class ProcurementMethodCreate(BaseModel):
    """采购方式创建模型"""
    code: str = Field(..., min_length=1, max_length=50, description="采购方式编码，如: PUBLIC_BIDDING（必须是大写字母和下划线）")
    name: str = Field(..., min_length=1, max_length=100, description="采购方式名称")
    description: Optional[str] = Field(None, max_length=500, description="采购方式的详细描述说明")
    sort_order: int = Field(..., ge=0, description="排序号（数字越小越靠前）")
    is_active: int = Field(1, ge=0, le=1, description="是否启用：1=启用, 0=停用")
    
    @field_validator('code')
    @classmethod
    def code_must_be_uppercase(cls, v: str) -> str:
        if not v.isupper() and '_' not in v:
            raise ValueError('编码必须是大写字母和下划线')
        return v.upper()


class ProcurementMethodUpdate(BaseModel):
    """采购方式更新模型"""
    name: Optional[str] = Field(None, min_length=1, max_length=100, description="采购方式名称")
    description: Optional[str] = Field(None, max_length=500, description="采购方式的详细描述说明")
    sort_order: Optional[int] = Field(None, ge=0, description="排序号（数字越小越靠前）")
    is_active: Optional[int] = Field(None, ge=0, le=1, description="是否启用：1=启用, 0=停用")


class ProcurementMethodResponse(BaseModel):
    """采购方式响应模型"""
    id: int = Field(..., description="采购方式ID（主键）")
    code: str = Field(..., description="采购方式编码（唯一标识）")
    name: str = Field(..., description="采购方式名称")
    description: Optional[str] = Field(None, description="采购方式的详细描述说明")
    is_active: int = Field(..., description="是否启用：1=启用, 0=停用")
    sort_order: int = Field(..., description="排序号（数字越小越靠前）")
    created_by: Optional[str] = Field(None, description="创建人系统用户ID")
    updated_by: Optional[str] = Field(None, description="最后更新人系统用户ID")
    created_time: datetime = Field(..., description="创建时间")
    updated_time: datetime = Field(..., description="最后更新时间")
    
    class Config:
        from_attributes = True


class ProcurementStageTemplateCreate(BaseModel):
    """采购阶段模板创建模型"""
    procurement_method_id: int = Field(..., description="所属采购方式ID（关联到crm_procurement_methods表）")
    template_code: str = Field(..., min_length=1, max_length=50, description="阶段编码（同一采购方式下唯一）")
    stage_name: str = Field(..., min_length=1, max_length=100, description="阶段名称")
    win_probability: int = Field(..., ge=0, le=100, description="阶段赢率（0-100的百分数）")
    sort_order: int = Field(..., ge=0, description="阶段顺序（数字越小越靠前）")
    is_default_start: int = Field(0, ge=0, le=1, description="是否为默认起始阶段：1=是, 0=否（每个采购方式只能有一个）")
    can_skip: int = Field(0, ge=0, le=1, description="是否允许跳过该阶段：1=可以, 0=不可以")
    description: Optional[str] = Field(None, max_length=500, description="阶段的详细描述说明")


class ProcurementStageTemplateUpdate(BaseModel):
    """采购阶段模板更新模型"""
    template_code: Optional[str] = Field(None, min_length=1, max_length=50, description="阶段编码（唯一标识）")
    stage_name: Optional[str] = Field(None, min_length=1, max_length=100, description="阶段名称")
    win_probability: Optional[int] = Field(None, ge=0, le=100, description="阶段赢率（0-100的百分数）")
    sort_order: Optional[int] = Field(None, ge=0, description="阶段顺序（数字越小越靠前）")
    is_default_start: Optional[int] = Field(None, ge=0, le=1, description="是否为默认起始阶段：1=是, 0=否（每个采购方式只能有一个）")
    can_skip: Optional[int] = Field(None, ge=0, le=1, description="是否允许跳过该阶段：1=可以, 0=不可以")
    description: Optional[str] = Field(None, max_length=500, description="阶段的详细描述说明")
    version_lock: Optional[int] = Field(None, description="乐观锁版本号（防止并发修改冲突，批量更新时后端自动获取）")


class ProcurementStageTemplateResponse(BaseModel):
    """采购阶段模板响应模型"""
    id: int = Field(..., description="阶段模板ID（主键）")
    procurement_method_id: int = Field(..., description="所属采购方式ID")
    template_code: str = Field(..., description="阶段编码（唯一标识）")
    stage_name: str = Field(..., description="阶段名称")
    win_probability: int = Field(..., description="阶段赢率（0-100）")
    sort_order: int = Field(..., description="阶段顺序（数字越小越靠前）")
    is_default_start: int = Field(..., description="是否为默认起始阶段：1=是, 0=否")
    can_skip: int = Field(..., description="是否允许跳过该阶段：1=可以, 0=不可以")
    description: Optional[str] = Field(None, description="阶段的详细描述说明")
    version: int = Field(..., description="版本号（每次修改自动递增）")
    version_lock: int = Field(..., description="乐观锁版本号（用于并发控制）")
    created_by: Optional[str] = Field(None, description="创建人系统用户ID")
    updated_by: Optional[str] = Field(None, description="最后更新人系统用户ID")
    created_time: datetime = Field(..., description="创建时间")
    updated_time: datetime = Field(..., description="最后更新时间")
    
    class Config:
        from_attributes = True


class OpportunityStageSnapshotResponse(BaseModel):
    """商机阶段快照响应模型"""
    id: int = Field(..., description="快照ID（主键）")
    opportunity_id: int = Field(..., description="商机ID（关联到crm_opportunities表）")
    procurement_stage_template_id: int = Field(..., description="阶段模板ID（关联到crm_procurement_stage_templates表）")
    stage_name: str = Field(..., description="阶段名称（快照时保存）")
    win_probability: int = Field(..., description="阶段赢率（快照时保存，0-100）")
    template_sort_order: int = Field(..., description="阶段顺序（快照时保存）")
    template_code: str = Field(..., description="阶段编码（快照时保存）")
    snapshot_version: int = Field(..., description="快照版本号（模板版本）")
    entered_at: datetime = Field(..., description="进入阶段的时间")
    exited_at: Optional[datetime] = Field(None, description="退出阶段的时间（为null表示当前阶段）")
    
    class Config:
        from_attributes = True


class StageTemplateChangeLogResponse(BaseModel):
    """阶段模板变更日志响应模型"""
    id: int = Field(..., description="日志ID（主键）")
    template_id: int = Field(..., description="阶段模板ID（关联到crm_procurement_stage_templates表）")
    change_type: str = Field(..., description="变更类型：CREATE=创建, UPDATE=更新, DELETE=删除, ROLLBACK=回滚")
    old_data: Optional[str] = Field(None, description="变更前的JSON数据")
    new_data: Optional[str] = Field(None, description="变更后的JSON数据")
    changed_by: str = Field(..., description="变更人系统用户ID")
    changed_at: datetime = Field(..., description="变更时间")
    reason: Optional[str] = Field(None, description="变更原因（可选）")
    
    class Config:
        from_attributes = True


class AdvanceStageRequest(BaseModel):
    """推进商机阶段请求模型"""
    target_stage_template_id: int = Field(..., description="目标阶段模板ID（要推进到的阶段）")


class ProcurementMethodWithStagesResponse(ProcurementMethodResponse):
    """带阶段列表的采购方式响应模型"""
    stage_templates: List[ProcurementStageTemplateResponse] = Field(default_factory=list, description="该采购方式下的所有阶段模板列表")


class SetCustomerDefaultProcurementMethodRequest(BaseModel):
    """设置客户默认采购方式请求模型"""
    procurement_method_id: int = Field(..., description="要设置的默认采购方式ID")


class BatchMigrateProcurementMethodRequest(BaseModel):
    """批量迁移采购方式请求模型"""
    source_method_id: int = Field(..., description="源采购方式ID（要迁移出的方式）")
    target_method_id: int = Field(..., description="目标采购方式ID（要迁移到的方式）")
    opportunity_ids: Optional[List[int]] = Field(None, description="要迁移的商机ID列表（为空则迁移所有使用源方式的商机）")


class RollbackTemplateVersionRequest(BaseModel):
    """回滚模板版本请求模型"""
    target_version: int = Field(..., ge=1, description="要回滚到的目标版本号")


class ImpactAssessmentResponse(BaseModel):
    """影响评估响应模型"""
    template_id: int = Field(..., description="被修改的阶段模板ID")
    template_name: str = Field(..., description="被修改的阶段模板名称")
    affected_opportunities_count: int = Field(..., description="受影响的活跃商机总数")
    active_opportunities: List[dict] = Field(default_factory=list, description="受影响的活跃商机详情列表")


class MessageResponse(BaseModel):
    """通用消息响应模型"""
    message: str = Field(..., description="操作结果的响应消息")


class StageTemplateBatchUpdate(BaseModel):
    """阶段模板批量更新模型（用于批量保存）"""
    id: Optional[int] = Field(None, description="阶段模板ID（有ID=更新，无ID=新增）")
    template_code: str = Field(..., min_length=1, max_length=50, description="阶段编码")
    stage_name: str = Field(..., min_length=1, max_length=100, description="阶段名称")
    win_probability: int = Field(..., ge=0, le=100, description="阶段赢率（0-100）")
    sort_order: int = Field(..., ge=0, description="阶段顺序")
    is_default_start: int = Field(0, ge=0, le=1, description="是否为默认起始阶段：1=是, 0=否")
    can_skip: int = Field(0, ge=0, le=1, description="是否允许跳过该阶段：1=可以, 0=不可以")
    description: Optional[str] = Field(None, max_length=500, description="阶段描述")
    mark_delete: Optional[bool] = Field(False, description="是否标记删除：true=删除该阶段")


class BatchUpdateStagesRequest(BaseModel):
    """批量更新阶段请求模型"""
    stages: List[StageTemplateBatchUpdate] = Field(..., description="阶段模板列表（包含新增、更新、删除）")


class ProcurementMethodWithStagesUpdate(BaseModel):
    """采购方式及阶段批量更新请求模型"""
    method: Optional[ProcurementMethodUpdate] = Field(None, description="采购方式更新数据（为空则不更新方式）")
    stages: List[StageTemplateBatchUpdate] = Field(..., description="阶段模板列表（包含新增、更新、删除）")
