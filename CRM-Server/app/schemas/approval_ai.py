"""
AI 解析审批流程配置 Schema

用于 AI 辅助创建审批流程功能的请求和响应结构
"""
from pydantic import BaseModel, Field, field_validator
from typing import Optional, List
from decimal import Decimal

from app.constants.business_types import BusinessType, is_valid_business_type
from app.schemas.approval import ApprovalNodeCreate


class ApprovalAIParsedNode(BaseModel):
    """AI 解析的审批节点"""
    node_name: str = Field(..., description="节点名称，如：部门经理审批")
    node_code: str = Field(..., description="节点编码，如：DEPT_MANAGER")
    node_order: int = Field(..., gt=0, description="审批顺序，从1开始")
    approve_role: str = Field(..., description="审批角色编码，如：SALES_DIRECTOR")
    description: Optional[str] = Field(None, description="节点描述")
    is_required: int = Field(1, ge=0, le=1, description="是否必须审批，默认1")


class ApprovalAIParsedFlow(BaseModel):
    """AI 解析的审批流程

    注意：min_amount/max_amount 使用 float 类型，
    确保 JSON 序列化兼容性（不需要 SSEJsonEncoder）
    """
    flow_name: str = Field(..., description="流程名称")
    flow_code: str = Field(..., description="流程编码")
    description: Optional[str] = Field(None, description="流程描述")
    # 改为 float 类型（不再使用 Decimal），确保 SSE JSON 序列化兼容
    min_amount: Optional[float] = Field(None, ge=0, description="最小金额（元）")
    max_amount: Optional[float] = Field(None, ge=0, description="最大金额（元）")
    license_type: Optional[str] = Field(None, description="授权类型，如：STANDARD")
    # B3：单据类型 CONTRACT/PAYMENT/INVOICE/LICENSE，默认 CONTRACT（兼容既有合同解析行为）
    business_type: str = Field(
        BusinessType.CONTRACT,
        description="流程适用单据类型：CONTRACT（合同，默认）/PAYMENT（回款）/INVOICE（发票）/LICENSE（License申请）",
    )
    nodes: List[ApprovalAIParsedNode] = Field(..., min_length=1, description="审批节点列表")

    @field_validator("business_type")
    @classmethod
    def validate_business_type(cls, v):
        """非法或缺失 business_type 回退 CONTRACT，保证模型始终有效。"""
        if not v or not is_valid_business_type(v):
            return BusinessType.CONTRACT
        return v

    def to_sse_dict(self) -> dict:
        """转换为 SSE 可序列化的字典

        使用 model_dump(mode='json') 确保所有类型兼容 JSON
        """
        return self.model_dump(mode='json')


class ApprovalAIParseRequest(BaseModel):
    """AI 解析请求"""
    content: str = Field(..., min_length=1, description="用户自然语言描述")


class ApprovalAIParseResponse(BaseModel):
    """AI 解析响应"""
    flow: ApprovalAIParsedFlow
    thinking_process: str = Field(..., description="AI 思考过程")


class ApprovalAICreateRequest(BaseModel):
    """创建审批流程请求（用户确认后）

    复用现有 ApprovalNodeCreate Schema，确保与 CRUD 接口兼容
    """
    flow_name: str = Field(..., description="流程名称")
    flow_code: str = Field(..., description="流程编码")
    description: Optional[str] = Field(None, description="流程描述")
    min_amount: Optional[Decimal] = Field(None, ge=0, description="最小金额（元）")
    max_amount: Optional[Decimal] = Field(None, ge=0, description="最大金额（元）")
    license_type: Optional[str] = Field(None, description="授权类型")
    # B3：落库 ApprovalFlow.business_type（A5 已加该列），默认 CONTRACT
    business_type: str = Field(
        BusinessType.CONTRACT,
        description="流程适用单据类型：CONTRACT/PAYMENT/INVOICE/LICENSE，默认 CONTRACT",
    )
    nodes: List[ApprovalNodeCreate] = Field(..., min_length=1, description="审批节点列表")

    @field_validator("business_type")
    @classmethod
    def validate_business_type(cls, v):
        if not v or not is_valid_business_type(v):
            return BusinessType.CONTRACT
        return v

    @field_validator('max_amount')
    @classmethod
    def validate_amount_range(cls, v, info):
        """可选校验：金额范围逻辑"""
        min_amount = info.data.get('min_amount')
        if v is not None and min_amount is not None and v <= min_amount:
            # 提示警告但不阻止（用户可能故意只设下限）
            pass
        return v