from pydantic import BaseModel, Field, field_validator
from typing import Optional, List
from datetime import datetime
from decimal import Decimal
from enum import Enum


class ApprovalStatusEnum(str, Enum):
    """审批状态枚举"""
    PENDING = "PENDING"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    CANCELLED = "CANCELLED"
    
    @property
    def description(self):
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
    def description(self):
        descriptions = {
            "SUBMIT": "提交",
            "APPROVE": "同意",
            "REJECT": "拒绝",
            "ROLLBACK": "回退"
        }
        return descriptions.get(self.value, self.value)


class ApprovalNodeCreate(BaseModel):
    """审批节点创建模型"""
    node_name: str = Field(
        ...,
        min_length=1,
        max_length=100,
        description="审批节点名称，如：部门经理审批、财务审批、总经理审批"
    )
    node_code: str = Field(
        ...,
        min_length=1,
        max_length=50,
        description="节点编码，英文唯一标识，如：DEPT_MANAGER、FINANCE、GENERAL_MANAGER"
    )
    node_order: int = Field(
        ...,
        gt=0,
        description="审批顺序，从1开始连续编号，按顺序依次流转，如：1,2,3"
    )
    description: Optional[str] = Field(
        None,
        description="节点描述，说明该节点的审批职责和要求"
    )
    approve_role: str = Field(
        ...,
        description="审批角色代码，拥有该角色的用户才能审批，如：SALES_MANAGER、FINANCE、GENERAL_MANAGER"
    )
    is_required: int = Field(
        1,
        ge=0,
        le=1,
        description="是否必须审批，1-必须，0-可选（预留字段，当前版本默认为必须）"
    )


class ApprovalNodeUpdate(BaseModel):
    """审批节点更新模型"""
    id: Optional[int] = Field(
        None,
        description="节点ID，更新已存在节点时必须提供"
    )
    node_name: Optional[str] = Field(
        None,
        min_length=1,
        max_length=100,
        description="审批节点名称"
    )
    node_code: Optional[str] = Field(
        None,
        min_length=1,
        max_length=50,
        description="节点编码"
    )
    node_order: Optional[int] = Field(
        None,
        gt=0,
        description="审批顺序"
    )
    description: Optional[str] = Field(
        None,
        description="节点描述"
    )
    approve_role: Optional[str] = Field(
        None,
        description="审批角色代码"
    )
    is_required: Optional[int] = Field(
        None,
        ge=0,
        le=1,
        description="是否必须审批"
    )


class ApprovalNodeResponse(BaseModel):
    """审批节点响应模型"""
    id: int = Field(..., description="节点ID，自增主键")
    flow_id: int = Field(..., description="审批流程ID，关联到审批流程表")
    node_name: str = Field(..., description="节点名称，如：部门经理审批")
    node_code: str = Field(..., description="节点编码，英文唯一标识")
    node_order: int = Field(..., description="节点顺序，决定审批流转顺序")
    description: Optional[str] = Field(None, description="节点描述，说明审批职责")
    approve_role: str = Field(..., description="审批角色代码，如：SALES_MANAGER")
    is_required: int = Field(..., description="是否必须审批，1-必须，0-可选")
    created_time: datetime = Field(..., description="创建时间，节点创建时间")
    
    class Config:
        from_attributes = True


class ApprovalFlowCreate(BaseModel):
    """审批流程创建模型"""
    flow_name: str = Field(
        ...,
        min_length=1,
        max_length=100,
        description="审批流程名称，如：标准合同审批、大额合同审批"
    )
    flow_code: str = Field(
        ...,
        min_length=1,
        max_length=50,
        description="流程编码，英文唯一标识，如：STANDARD、LARGE_AMOUNT"
    )
    description: Optional[str] = Field(
        None,
        description="流程描述，说明该流程适用场景和规则"
    )
    min_amount: Optional[Decimal] = Field(
        None,
        ge=0,
        description="最小金额，合同金额范围下限（元），用于匹配流程"
    )
    max_amount: Optional[Decimal] = Field(
        None,
        ge=0,
        description="最大金额，合同金额范围上限（元），用于匹配流程"
    )
    license_type: Optional[str] = Field(
        None,
        description="授权类型，如：STANDARD、PROFESSIONAL、ENTERPRISE，用于匹配流程"
    )
    nodes: List[ApprovalNodeCreate] = Field(
        ...,
        min_items=1,
        description="审批节点列表，至少包含一个节点，按node_order顺序流转"
    )


class ApprovalFlowUpdate(BaseModel):
    """审批流程更新模型"""
    flow_name: Optional[str] = Field(
        None,
        min_length=1,
        max_length=100,
        description="审批流程名称"
    )
    description: Optional[str] = Field(
        None,
        description="流程描述"
    )
    min_amount: Optional[Decimal] = Field(
        None,
        ge=0,
        description="最小金额（元）"
    )
    max_amount: Optional[Decimal] = Field(
        None,
        ge=0,
        description="最大金额（元）"
    )
    license_type: Optional[str] = Field(
        None,
        description="授权类型"
    )
    is_active: Optional[int] = Field(
        None,
        ge=0,
        le=1,
        description="是否启用，1-启用，0-禁用"
    )
    nodes: Optional[List[ApprovalNodeUpdate]] = Field(
        None,
        description="审批节点列表，更新时会完全替换原有节点"
    )


class ApprovalFlowResponse(BaseModel):
    """审批流程响应模型"""
    id: int = Field(..., description="流程ID，自增主键")
    flow_name: str = Field(..., description="流程名称")
    flow_code: str = Field(..., description="流程编码，唯一标识")
    description: Optional[str] = Field(None, description="流程描述")
    min_amount: Optional[Decimal] = Field(None, description="最小金额（元）")
    max_amount: Optional[Decimal] = Field(None, description="最大金额（元）")
    license_type: Optional[str] = Field(None, description="授权类型")
    is_active: int = Field(..., description="是否启用，1-启用，0-禁用")
    created_time: datetime = Field(..., description="创建时间")
    last_modified_time: datetime = Field(..., description="最后修改时间")
    
    class Config:
        from_attributes = True


class ApprovalFlowDetailResponse(ApprovalFlowResponse):
    """审批流程详情响应模型，包含节点列表"""
    nodes: List[ApprovalNodeResponse] = Field([], description="审批节点列表，按顺序排列")


class ApprovalSubmitRequest(BaseModel):
    """提交审批请求模型"""
    comment: Optional[str] = Field(
        None,
        description="提交说明，提交时填写的说明信息"
    )


class ApprovalActionRequest(BaseModel):
    """审批操作请求模型"""
    action: ApprovalActionEnum = Field(
        ...,
        description="操作类型：APPROVE（同意）、REJECT（拒绝）"
    )
    comment: Optional[str] = Field(
        None,
        description="审批意见，必填，说明审批理由或意见"
    )


class ApprovalRecordResponse(BaseModel):
    """审批记录响应模型"""
    id: int = Field(..., description="记录ID，自增主键")
    approval_id: int = Field(..., description="审批实例ID，关联到审批实例表")
    node_id: Optional[int] = Field(None, description="节点ID，对应的审批节点")
    node_name: Optional[str] = Field(None, description="节点名称，如：部门经理审批")
    approver_id: str = Field(..., description="审批人ID，飞书用户ID")
    approver_name: Optional[str] = Field(None, description="审批人姓名")
    action: str = Field(..., description="操作类型：APPROVE、REJECT")
    comment: Optional[str] = Field(None, description="审批意见，审批时填写的意见")
    created_time: datetime = Field(..., description="操作时间，审批操作的时间")
    
    class Config:
        from_attributes = True


class ApprovalResponse(BaseModel):
    """审批实例响应模型"""
    id: int = Field(..., description="审批实例ID，自增主键")
    contract_id: int = Field(..., description="合同ID，关联的合同ID")
    flow_id: Optional[int] = Field(None, description="流程模板ID，使用的审批流程模板ID")
    flow_name: Optional[str] = Field(None, description="流程名称，审批流程名称")
    current_node_id: Optional[int] = Field(None, description="当前节点ID，当前待审批的节点ID")
    current_node_name: Optional[str] = Field(None, description="当前节点名称，当前待审批的节点名称")
    status: str = Field(
        ...,
        description="审批状态：PENDING（审批中）、APPROVED（已通过）、REJECTED（已拒绝）、CANCELLED（已撤回）"
    )
    submitter_id: str = Field(..., description="提交人ID，提交审批的用户ID")
    submitter_name: Optional[str] = Field(None, description="提交人姓名")
    created_time: datetime = Field(..., description="创建时间，提交审批的时间")
    updated_time: datetime = Field(..., description="最后更新时间，最后一次操作的时间")
    
    class Config:
        from_attributes = True


class ApprovalDetailResponse(ApprovalResponse):
    """审批详情响应模型，包含流程和记录"""
    flow: Optional[ApprovalFlowDetailResponse] = Field(
        None,
        description="审批流程详情，包含流程配置和节点信息"
    )
    records: List[ApprovalRecordResponse] = Field(
        [],
        description="审批记录列表，按时间顺序排列的审批历史"
    )


class ApprovalListResponse(BaseModel):
    """审批列表响应模型"""
    id: int = Field(..., description="审批实例ID")
    contract_id: int = Field(..., description="合同ID")
    contract_name: str = Field(..., description="合同名称")
    contract_number: str = Field(..., description="合同编号")
    flow_name: Optional[str] = Field(None, description="流程名称")
    current_node_name: Optional[str] = Field(None, description="当前节点名称")
    status: str = Field(
        ...,
        description="审批状态：PENDING、APPROVED、REJECTED、CANCELLED"
    )
    submitter_name: Optional[str] = Field(None, description="提交人姓名")
    created_time: datetime = Field(..., description="创建时间")


class MessageResponse(BaseModel):
    """通用消息响应模型"""
    message: str = Field(..., description="响应消息，操作结果的描述信息")
