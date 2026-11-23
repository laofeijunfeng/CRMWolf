"""
AI 解析审批流程配置 Schema

用于 AI 辅助创建审批流程功能的请求和响应结构
"""
from decimal import Decimal

from pydantic import BaseModel, Field, ValidationInfo, field_validator, model_validator

from app.constants.business_types import BusinessType, is_valid_business_type
from app.schemas.approval import ApprovalNodeCreate


class ApprovalAIParsedNode(ApprovalNodeCreate):
    """AI 解析的审批节点\uff08沿用标准审批节点配置\uff09。"""

    @model_validator(mode="before")
    @classmethod
    def normalize_legacy_role(cls, value: object) -> object:
        if isinstance(value, dict) and "approver_roles" not in value:
            legacy_role = value.get("approve_role")
            if isinstance(legacy_role, str):
                return {**value, "approver_roles": [legacy_role]}
        return value


class ApprovalAIParsedFlow(BaseModel):
    """AI 解析的审批流程

    注意\uff1amin_amount/max_amount 使用 float 类型\uff0c
    确保 JSON 序列化兼容性\uff08不需要 SSEJsonEncoder\uff09
    """
    flow_name: str = Field(..., description="流程名称")
    flow_code: str = Field(..., description="流程编码")
    description: str | None = Field(None, description="流程描述")
    # 改为 float 类型(不再使用 Decimal),确保 SSE JSON 序列化兼容
    min_amount: float | None = Field(None, ge=0, description="最小金额\uff08元\uff09")
    max_amount: float | None = Field(None, ge=0, description="最大金额\uff08元\uff09")
    license_type: str | None = Field(None, description="授权类型\uff0c如\uff1aSTANDARD")
    # B3:单据类型 CONTRACT/PAYMENT/INVOICE/INVOICE_REISSUE/LICENSE/OPPORTUNITY,默认 CONTRACT(兼容既有合同解析行为)
    business_type: str = Field(
        BusinessType.CONTRACT,
        description=(
            "流程适用单据类型\uff1aCONTRACT\uff08合同\uff0c默认\uff09"
            "/PAYMENT\uff08回款\uff09/INVOICE\uff08发票\uff09"
            "/LICENSE\uff08License申请\uff09/OPPORTUNITY\uff08商机\uff09"
        ),
    )
    nodes: list[ApprovalAIParsedNode] = Field(..., min_length=1, description="审批节点列表")

    @field_validator("business_type")
    @classmethod
    def validate_business_type(cls, v: str) -> str:
        """非法或缺失 business_type 回退 CONTRACT\uff0c保证模型始终有效。"""
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
    """创建审批流程请求\uff08用户确认后\uff09

    复用现有 ApprovalNodeCreate Schema\uff0c确保与 CRUD 接口兼容
    """
    flow_name: str = Field(..., description="流程名称")
    flow_code: str = Field(..., description="流程编码")
    description: str | None = Field(None, description="流程描述")
    min_amount: Decimal | None = Field(None, ge=0, description="最小金额\uff08元\uff09")
    max_amount: Decimal | None = Field(None, ge=0, description="最大金额\uff08元\uff09")
    license_type: str | None = Field(None, description="授权类型")
    # B3:落库 ApprovalFlow.business_type(A5 已加该列),默认 CONTRACT
    business_type: str = Field(
        BusinessType.CONTRACT,
        description=(
            "流程适用单据类型\uff1aCONTRACT/PAYMENT/INVOICE"
            "/INVOICE_REISSUE/LICENSE/OPPORTUNITY\uff0c默认 CONTRACT"
        ),
    )
    nodes: list[ApprovalAIParsedNode] = Field(..., min_length=1, description="审批节点列表")

    @field_validator("business_type")
    @classmethod
    def validate_business_type(cls, v: str) -> str:
        if not v or not is_valid_business_type(v):
            return BusinessType.CONTRACT
        return v

    @field_validator('max_amount')
    @classmethod
    def validate_amount_range(cls, v: Decimal | None, info: ValidationInfo) -> Decimal | None:
        """可选校验\uff1a金额范围逻辑"""
        min_amount = info.data.get('min_amount')
        if v is not None and min_amount is not None and v <= min_amount:
            # 提示警告但不阻止(用户可能故意只设下限)
            pass
        return v
