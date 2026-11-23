from datetime import datetime
from decimal import Decimal
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field, field_validator

from app.constants.business_types import ALL_BUSINESS_TYPES, is_valid_business_type


class ApprovalStatusEnum(str, Enum):
    """审批状态枚举"""
    PENDING = "PENDING"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    CANCELLED = "CANCELLED"
    
    @property
    def description(self) -> str:
        descriptions = {
            "PENDING": "审批中",
            "APPROVED": "已通过",
            "REJECTED": "已拒绝",
            "CANCELLED": "已撤回"
        }
        return descriptions.get(self.value, self.value)


class ApprovalActionEnum(str, Enum):
    """审批动作枚举"""
    SUBMIT = "SUBMIT"
    APPROVE = "APPROVE"
    REJECT = "REJECT"
    ROLLBACK = "ROLLBACK"
    
    @property
    def description(self) -> str:
        descriptions = {
            "SUBMIT": "提交",
            "APPROVE": "同意",
            "REJECT": "拒绝",
            "ROLLBACK": "回退"
        }
        return descriptions.get(self.value, self.value)


class ApprovalNodeTypeEnum(str, Enum):
    """节点类型\uff1a审批节点需有人通过\uff1b抄送节点到达即发卡片并自动流转。"""
    APPROVAL = "APPROVAL"
    CC = "CC"


class ApproverUser(BaseModel):
    """指定成员\uff1arole 为选择该成员时所在角色\uff0c提交时成员须仍属于该角色。"""
    role: str = Field(..., min_length=1, description="成员所属角色代码")
    user_id: int = Field(..., gt=0, description="成员用户ID")


class _NodeApproversMixin(BaseModel):
    approver_roles: list[str] | None = Field(
        None, description="整角色\uff1a角色内任一成员可审批/被抄送"
    )
    approver_users: list[ApproverUser] | None = Field(
        None, description="指定成员\uff1a仅这些人可审批/被抄送"
    )


def _validate_nodes(nodes: list[Any]) -> list[Any]:
    """首个节点必须是审批节点\uff1b每个节点至少选择一个角色或成员。"""
    ordered = sorted(nodes, key=lambda n: n.node_order or 0)
    if ordered and (ordered[0].node_type or ApprovalNodeTypeEnum.APPROVAL) != ApprovalNodeTypeEnum.APPROVAL:
        raise ValueError("抄送节点需位于审批节点之后")
    for index, node in enumerate(ordered, start=1):
        if node.approver_roles is None and node.approver_users is None and getattr(node, "id", None):
            continue  # 更新已有节点且未修改人员
        if not (node.approver_roles or node.approver_users):
            raise ValueError(f"第 {index} 个节点未选择审批人员")
    return nodes


class ApprovalNodeCreate(_NodeApproversMixin):
    """审批节点创建模型"""
    node_name: str = Field(
        ...,
        min_length=1,
        max_length=100,
        description="节点名称\uff0c如\uff1a部门经理审批、抄送财务"
    )
    node_code: str = Field(
        ...,
        min_length=1,
        max_length=50,
        description="节点编码\uff0c英文唯一标识\uff0c如\uff1aDEPT_MANAGER、FINANCE、GENERAL_MANAGER"
    )
    node_order: int = Field(
        ...,
        gt=0,
        description="节点顺序\uff0c从1开始连续编号\uff0c按顺序依次流转\uff0c如\uff1a1,2,3"
    )
    description: str | None = Field(
        None,
        description="节点描述\uff0c说明该节点的审批职责和要求"
    )
    node_type: ApprovalNodeTypeEnum = Field(
        ApprovalNodeTypeEnum.APPROVAL, description="节点类型\uff1aAPPROVAL 审批 / CC 抄送"
    )


class ApprovalNodeUpdate(_NodeApproversMixin):
    """审批节点更新模型"""
    id: int | None = Field(
        None,
        description="节点ID\uff0c更新已存在节点时必须提供"
    )
    node_name: str | None = Field(
        None,
        min_length=1,
        max_length=100,
        description="节点名称"
    )
    node_code: str | None = Field(
        None,
        min_length=1,
        max_length=50,
        description="节点编码"
    )
    node_order: int | None = Field(
        None,
        gt=0,
        description="节点顺序"
    )
    description: str | None = Field(
        None,
        description="节点描述"
    )
    node_type: ApprovalNodeTypeEnum | None = Field(
        None, description="节点类型\uff1aAPPROVAL 审批 / CC 抄送"
    )


class ApprovalNodeResponse(BaseModel):
    """审批节点响应模型"""
    id: int = Field(..., description="节点ID\uff0c自增主键")
    flow_id: int = Field(..., description="审批流程ID\uff0c关联到审批流程表")
    node_name: str = Field(..., description="节点名称\uff0c如\uff1a部门经理审批")
    node_code: str = Field(..., description="节点编码\uff0c英文唯一标识")
    node_order: int = Field(..., description="节点顺序\uff0c决定审批流转顺序")
    description: str | None = Field(None, description="节点描述\uff0c说明审批职责")
    node_type: str = Field("APPROVAL", description="节点类型\uff1aAPPROVAL 审批 / CC 抄送")
    approver_roles: list[str] = Field(default_factory=list, description="整角色代码列表")
    approver_users: list[ApproverUser] = Field(default_factory=list, description="指定成员列表")
    created_time: datetime = Field(..., description="创建时间\uff0c节点创建时间")

    @field_validator("approver_roles", "approver_users", mode="before")
    @classmethod
    def _none_to_list(cls, v: object) -> object:
        return v or []

    class Config:
        from_attributes = True


class ApprovalFlowCreate(BaseModel):
    """审批流程创建模型"""
    flow_name: str = Field(
        ...,
        min_length=1,
        max_length=100,
        description="审批流程名称\uff0c如\uff1a标准合同审批、大额合同审批"
    )
    flow_code: str = Field(
        ...,
        min_length=1,
        max_length=50,
        description="流程编码\uff0c英文唯一标识\uff0c如\uff1aSTANDARD、LARGE_AMOUNT"
    )
    description: str | None = Field(
        None,
        description="流程描述\uff0c说明该流程适用场景和规则"
    )
    min_amount: Decimal | None = Field(
        None,
        ge=0,
        description="最小金额\uff0c合同金额范围下限\uff08元\uff09\uff0c用于匹配流程"
    )
    max_amount: Decimal | None = Field(
        None,
        ge=0,
        description="最大金额\uff0c合同金额范围上限\uff08元\uff09\uff0c用于匹配流程"
    )
    license_type: str | None = Field(
        None,
        description="授权类型\uff0c如\uff1aSTANDARD、PROFESSIONAL、ENTERPRISE\uff0c用于匹配流程"
    )
    business_type: str = Field(
        ...,
        description="流程适用单据类型\uff1aCONTRACT/PAYMENT/INVOICE/INVOICE_REISSUE/LICENSE/OPPORTUNITY"
    )
    nodes: list[ApprovalNodeCreate] = Field(
        ...,
        min_items=1,
        description="审批节点列表\uff0c至少包含一个节点\uff0c按node_order顺序流转"
    )

    @field_validator("nodes")
    @classmethod
    def validate_nodes(cls, v: list[ApprovalNodeCreate]) -> list[ApprovalNodeCreate]:
        return _validate_nodes(v)

    @field_validator("business_type")
    @classmethod
    def validate_business_type(cls, v: str) -> str:
        """校验 business_type 合法性。"""
        if not v or not is_valid_business_type(v):
            allowed = " / ".join(ALL_BUSINESS_TYPES)
            raise ValueError(f"无效的流程适用单据类型: {v}\uff0c仅支持 {allowed}")
        return v


class ApprovalFlowUpdate(BaseModel):
    """审批流程更新模型"""
    flow_name: str | None = Field(
        None,
        min_length=1,
        max_length=100,
        description="审批流程名称"
    )
    description: str | None = Field(
        None,
        description="流程描述"
    )
    min_amount: Decimal | None = Field(
        None,
        ge=0,
        description="最小金额\uff08元\uff09"
    )
    max_amount: Decimal | None = Field(
        None,
        ge=0,
        description="最大金额\uff08元\uff09"
    )
    license_type: str | None = Field(
        None,
        description="授权类型"
    )
    is_active: int | None = Field(
        None,
        ge=0,
        le=1,
        description="是否启用\uff0c1-启用\uff0c0-禁用"
    )
    business_type: str | None = Field(
        None,
        description="流程适用单据类型\uff1aCONTRACT/PAYMENT/INVOICE/INVOICE_REISSUE/LICENSE/OPPORTUNITY"
    )
    nodes: list[ApprovalNodeUpdate] | None = Field(
        None,
        description="审批节点列表\uff0c更新时会完全替换原有节点"
    )

    @field_validator("nodes")
    @classmethod
    def validate_nodes(cls, v: list[ApprovalNodeUpdate] | None) -> list[ApprovalNodeUpdate] | None:
        # Node updates are partial; ApprovalFlowCRUD validates the merged final
        # node set after applying these patches to persisted nodes.
        return v

    @field_validator("business_type")
    @classmethod
    def validate_business_type(cls, v: str | None) -> str | None:
        """校验 business_type 合法性"""
        if v is None:
            return v  # 更新时允许不修改
        if not is_valid_business_type(v):
            allowed = " / ".join(ALL_BUSINESS_TYPES)
            raise ValueError(f"无效的流程适用单据类型: {v}\uff0c仅支持 {allowed}")
        return v


class ApprovalFlowResponse(BaseModel):
    """审批流程响应模型"""
    id: int = Field(..., description="流程ID\uff0c自增主键")
    flow_name: str = Field(..., description="流程名称")
    flow_code: str = Field(..., description="流程编码\uff0c唯一标识")
    description: str | None = Field(None, description="流程描述")
    min_amount: Decimal | None = Field(None, description="最小金额\uff08元\uff09")
    max_amount: Decimal | None = Field(None, description="最大金额\uff08元\uff09")
    license_type: str | None = Field(None, description="授权类型")
    is_active: int = Field(..., description="是否启用\uff0c1-启用\uff0c0-禁用")
    business_type: str = Field(..., description="流程适用单据类型")
    created_time: datetime = Field(..., description="创建时间")
    last_modified_time: datetime = Field(..., description="最后修改时间")
    
    class Config:
        from_attributes = True


class ApprovalFlowDetailResponse(ApprovalFlowResponse):
    """审批流程详情响应模型\uff0c包含节点列表"""
    nodes: list[ApprovalNodeResponse] = Field([], description="审批节点列表\uff0c按顺序排列")


class ApprovalSubmitRequest(BaseModel):
    """提交审批请求模型"""
    comment: str | None = Field(
        None,
        description="提交说明\uff0c提交时填写的说明信息"
    )


class ApprovalActionRequest(BaseModel):
    """审批操作请求模型"""
    action: ApprovalActionEnum = Field(
        ...,
        description="操作类型\uff1aAPPROVE\uff08同意\uff09、REJECT\uff08拒绝\uff09"
    )
    comment: str | None = Field(
        None,
        description="审批意见\uff0c必填\uff0c说明审批理由或意见"
    )
    updated_time: datetime | None = Field(
        None,
        description=(
            "审批实例最后更新时间\uff0c用于乐观锁冲突检测。"
            "前端提交审批时应传入当前审批实例的 updated_time\uff0c如果不匹配则返回 409 冲突错误"
        ),
    )


class ApprovalRecordResponse(BaseModel):
    """审批记录响应模型"""
    id: int = Field(..., description="记录ID\uff0c自增主键")
    approval_id: int = Field(..., description="审批实例ID\uff0c关联到审批实例表")
    node_id: int | None = Field(None, description="节点ID\uff0c对应的审批节点")
    node_name: str | None = Field(None, description="节点名称\uff0c如\uff1a部门经理审批")
    approver_id: str = Field(..., description="审批人系统用户ID")
    approver_name: str | None = Field(None, description="审批人姓名")
    approver_status: str | None = Field(
        None,
        description="审批人状态\uff1aactive\uff08在职\uff09、inactive\uff08离职\uff09、suspended\uff08停用\uff09"
    )
    approver_status_display: str | None = Field(
        None,
        description="审批人状态显示\uff0c如\uff1a在职、已离职、已停用"
    )
    action: str = Field(..., description="操作类型\uff1aAPPROVE、REJECT")
    comment: str | None = Field(None, description="审批意见\uff0c审批时填写的意见")
    created_time: datetime = Field(..., description="操作时间\uff0c审批操作的时间")

    class Config:
        from_attributes = True


class ApprovalResponse(BaseModel):
    """审批实例响应模型"""
    id: int = Field(..., description="审批实例ID\uff0c自增主键")
    contract_id: int = Field(..., description="合同ID\uff0c关联的合同ID")
    flow_id: int | None = Field(None, description="流程模板ID\uff0c使用的审批流程模板ID")
    flow_name: str | None = Field(None, description="流程名称\uff0c审批流程名称")
    current_node_id: int | None = Field(None, description="当前节点ID\uff0c当前待审批的节点ID")
    current_node_name: str | None = Field(None, description="当前节点名称\uff0c当前待审批的节点名称")
    status: str = Field(
        ...,
        description=(
            "审批状态\uff1aPENDING\uff08审批中\uff09"
            "、APPROVED\uff08已通过\uff09、REJECTED\uff08已拒绝\uff09"
            "、CANCELLED\uff08已撤回\uff09"
        )
    )
    submitter_id: str = Field(..., description="提交人ID\uff0c提交审批的用户ID")
    submitter_name: str | None = Field(None, description="提交人姓名")
    created_time: datetime = Field(..., description="创建时间\uff0c提交审批的时间")
    updated_time: datetime = Field(..., description="最后更新时间\uff0c最后一次操作的时间")
    
    class Config:
        from_attributes = True


class ApprovalDetailResponse(ApprovalResponse):
    """审批详情响应模型\uff0c包含流程和记录"""
    flow: ApprovalFlowDetailResponse | None = Field(
        None,
        description="审批流程详情\uff0c包含流程配置和节点信息"
    )
    flow_is_active: bool | None = Field(
        None,
        description=(
            "审批流程是否启用\uff0cTrue-启用\uff0cFalse-禁用。"
            "如果流程被禁用\uff0c已有审批实例继续执行\uff0c但新提交审批不会匹配该流程"
        )
    )
    flow_disabled_warning: str | None = Field(
        None,
        description=(
            "流程禁用提示信息。当流程被禁用时\uff0c显示提示\uff1a"
            "'审批流程已被管理员禁用\uff0c当前审批将继续执行\uff0c但新提交审批不会使用该流程'"
        )
    )
    records: list[ApprovalRecordResponse] = Field(
        [],
        description="审批记录列表\uff0c按时间顺序排列的审批历史"
    )


class ApprovalListResponse(BaseModel):
    """审批列表响应模型"""
    id: int = Field(..., description="审批实例ID")
    contract_id: int = Field(..., description="合同ID")
    contract_name: str = Field(..., description="合同名称")
    contract_number: str = Field(..., description="合同编号")
    flow_name: str | None = Field(None, description="流程名称")
    current_node_name: str | None = Field(None, description="当前节点名称")
    status: str = Field(
        ...,
        description="审批状态\uff1aPENDING、APPROVED、REJECTED、CANCELLED"
    )
    submitter_name: str | None = Field(None, description="提交人姓名")
    created_time: datetime = Field(..., description="创建时间")


class OverdueApprovalResponse(BaseModel):
    """超时审批响应模型"""
    approval_id: int = Field(..., description="审批实例ID")
    business_type: str = Field(
        ...,
        description="业务单据类型\uff1aCONTRACT/PAYMENT/INVOICE/INVOICE_REISSUE/LICENSE/OPPORTUNITY",
    )
    business_id: int | None = Field(None, description="业务单据ID\uff08与 business_type 联合定位单据\uff09")
    contract_id: int | None = Field(
        None,
        description="关联合同ID\uff08仅 CONTRACT 类非空\uff0cPAYMENT/INVOICE 为 None\uff09",
    )
    contract_name: str | None = Field(None, description="合同名称\uff08仅 CONTRACT 类由调用方按需填充\uff09")
    contract_number: str | None = Field(None, description="合同编号\uff08仅 CONTRACT 类由调用方按需填充\uff09")
    current_node_name: str | None = Field(None, description="当前审批节点名称")
    current_approver_name: str | None = Field(None, description="当前审批人姓名")
    overdue_hours: int = Field(..., description="超时小时数\uff0c当前时间减去提交时间")
    submitter_name: str | None = Field(None, description="提交人姓名")
    submit_time: datetime = Field(..., description="提交时间")
    status: str = Field(..., description="审批状态")


class OverdueApprovalListResponse(BaseModel):
    """超时审批列表响应模型"""
    items: list[OverdueApprovalResponse] = Field(..., description="超时审批列表")
    total: int = Field(..., description="总记录数")


class MessageResponse(BaseModel):
    """通用消息响应模型"""
    message: str = Field(..., description="响应消息\uff0c操作结果的描述信息")
