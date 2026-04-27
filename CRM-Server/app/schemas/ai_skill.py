"""
AI Skill Schema

定义 AI 解析意图和执行结果的数据结构
Skill 定义从数据库动态加载（见 dynamic_prompt_service）
"""
from pydantic import BaseModel, Field
from typing import Optional, Dict, Any, List


class AIParsedIntent(BaseModel):
    """AI 解析后的意图结果"""
    skill: Optional[str] = Field(None, description="Skill名称，null表示无匹配或参数缺失")
    action: Optional[str] = Field(None, description="Action名称")
    params: Dict[str, Any] = Field(default_factory=dict, description="参数字典")
    reply_text: str = Field(..., description="必填：追问内容或执行提示")


class SkillExecutionResult(BaseModel):
    """Skill 执行结果"""
    success: bool = Field(..., description="是否成功")
    message: str = Field(..., description="提示信息")
    data: Optional[Dict[str, Any]] = Field(None, description="业务数据")


class SkillActionDefinition(BaseModel):
    """Skill 动作定义"""
    action: str = Field(..., description="动作名称")
    description: str = Field(..., description="动作描述")
    required_params: List[str] = Field(default_factory=list, description="必填参数列表")
    optional_params: List[str] = Field(default_factory=list, description="可选参数列表")
    permission_code: str = Field(..., description="权限码")


class SkillDefinition(BaseModel):
    """Skill 定义"""
    skill_name: str = Field(..., description="Skill名称")
    description: str = Field(..., description="Skill描述")
    actions: List[SkillActionDefinition] = Field(..., description="支持的动作列表")