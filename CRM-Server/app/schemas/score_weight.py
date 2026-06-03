"""热力值权重配置 Schema

定义权重配置和热力值相关的请求/响应模型。
"""
from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import datetime


# ============== 权重配置 Schema ==============

class WeightConfigBase(BaseModel):
    """权重配置基础模型"""
    factor_key: str = Field(..., description="因子键名")
    factor_name: str = Field(..., description="因子显示名称")
    weight_value: int = Field(..., ge=-50, le=50, description="权重值（-50到50）")
    is_enabled: int = Field(1, ge=0, le=1, description="是否启用：1启用，0禁用")
    condition_rules: Optional[str] = Field(None, description="条件规则JSON")
    sort_order: int = Field(0, description="排序序号")


class WeightConfigCreate(WeightConfigBase):
    """权重配置创建模型"""
    module_type: str = Field(..., description="模块类型：LEAD/CUSTOMER")


class WeightConfigUpdate(BaseModel):
    """权重配置更新模型"""
    weight_value: Optional[int] = Field(None, ge=-50, le=50, description="权重值")
    is_enabled: Optional[int] = Field(None, ge=0, le=1, description="是否启用")
    condition_rules: Optional[str] = Field(None, description="条件规则")


class WeightConfigResponse(WeightConfigBase):
    """权重配置响应模型"""
    id: int = Field(..., description="配置ID")
    team_id: Optional[int] = Field(None, description="团队ID（NULL表示系统默认）")
    module_type: str = Field(..., description="模块类型")
    created_by: str = Field(..., description="创建人")
    created_time: datetime = Field(..., description="创建时间")
    updated_by: Optional[str] = Field(None, description="更新人")
    updated_time: datetime = Field(..., description="更新时间")

    class Config:
        from_attributes = True


class WeightConfigList(BaseModel):
    """权重配置列表响应"""
    module_type: str = Field(..., description="模块类型")
    weights: List[WeightConfigResponse] = Field(default_factory=list, description="权重配置列表")
    is_system_default: bool = Field(..., description="是否使用系统默认配置")


# ============== 热力值明细 Schema ==============

class ScoreDetailBase(BaseModel):
    """热力值明细基础模型"""
    factor_key: str = Field(..., description="因子键名")
    factor_name: str = Field(..., description="因子名称")
    weight_value: int = Field(..., description="权重值")
    actual_value: Optional[str] = Field(None, description="实际值")
    score_change: int = Field(..., description="分数变化")
    reason: Optional[str] = Field(None, description="原因说明")


class ScoreDetailResponse(ScoreDetailBase):
    """热力值明细响应模型"""
    id: int = Field(..., description="明细ID")
    calculated_time: datetime = Field(..., description="计算时间")

    class Config:
        from_attributes = True


# ============== 热力值响应 Schema ==============

class ScoreResponse(BaseModel):
    """热力值响应模型"""
    score: Optional[int] = Field(None, description="热力值分数（0-100）")
    score_level: Optional[str] = Field(None, description="热力值等级：高/中/低/危险")
    updated_at: Optional[datetime] = Field(None, description="最后更新时间")
    details: List[ScoreDetailResponse] = Field(default_factory=list, description="计算明细")


class ScoreLevelInfo(BaseModel):
    """热力值等级信息"""
    score: int = Field(..., description="分数")
    level: str = Field(..., description="等级：高/中/低/危险")
    icon: str = Field(..., description="图标")
    color: str = Field(..., description="颜色")


def get_score_level_info(score: Optional[int]) -> ScoreLevelInfo:
    """根据分数获取等级信息"""
    if score is None:
        return ScoreLevelInfo(score=0, level="未知", icon="❓", color="#d9d9d9")

    if score >= 80:
        return ScoreLevelInfo(score=score, level="高", icon="🔥", color="#ff4d4f")
    elif score >= 60:
        return ScoreLevelInfo(score=score, level="中", icon="⚡", color="#faad14")
    elif score >= 40:
        return ScoreLevelInfo(score=score, level="低", icon="✅", color="#52c41a")
    else:
        return ScoreLevelInfo(score=score, level="危险", icon="❄️", color="#d9d9d9")