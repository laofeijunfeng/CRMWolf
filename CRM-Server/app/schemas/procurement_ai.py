"""
AI 解析采购方式配置 Schema

用于 AI 辅助创建采购方式功能的请求和响应结构
"""
from pydantic import BaseModel, Field
from typing import Optional, List


class ProcurementAIParseRequest(BaseModel):
    """AI 解析采购方式配置请求"""
    content: str = Field(..., min_length=1, description="用户输入的自然语言描述")


class ProcurementAIParsedStage(BaseModel):
    """AI 解析出的阶段配置"""
    stage_name: str = Field(..., description="阶段名称")
    template_code: str = Field(..., description="阶段编码（英文大写+下划线）")
    win_probability: int = Field(..., ge=10, le=100, description="赢率 10-100")
    sort_order: int = Field(..., ge=1, description="阶段顺序号")
    is_default_start: bool = Field(default=False, description="是否默认起始阶段")
    can_skip: bool = Field(default=False, description="是否可跳过")
    description: Optional[str] = Field(None, description="阶段描述")


class ProcurementAIParsedMethod(BaseModel):
    """AI 解析出的采购方式配置"""
    name: str = Field(..., description="采购方式名称")
    code: str = Field(..., description="采购方式编码（英文大写+下划线）")
    description: Optional[str] = Field(None, description="采购方式描述")
    stages: List[ProcurementAIParsedStage] = Field(..., min_length=1, description="阶段配置列表")


class ProcurementAIParseResponse(BaseModel):
    """AI 解析采购方式配置响应"""
    method: ProcurementAIParsedMethod = Field(..., description="解析出的采购方式配置")
    thinking_process: Optional[str] = Field(None, description="AI 思考过程")


class ProcurementAICreateRequest(BaseModel):
    """AI 创建采购方式请求（用户确认后提交）"""
    name: str = Field(..., description="采购方式名称")
    code: str = Field(..., description="采购方式编码")
    description: Optional[str] = Field(None, description="采购方式描述")
    stages: List[ProcurementAIParsedStage] = Field(..., description="阶段配置列表")
    team_id: Optional[int] = Field(None, description="团队ID（NULL表示系统默认）")