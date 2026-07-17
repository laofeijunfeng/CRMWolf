"""License 申请 Schema 模块

定义 License 申请相关的 Pydantic 模型。
"""
from pydantic import BaseModel, Field, field_validator, model_validator, ConfigDict
from typing import Optional
from datetime import date, datetime
from enum import Enum


class LicenseApplicationStatus(str, Enum):
    """License 申请状态枚举"""
    DRAFT = "DRAFT"
    PENDING_REVIEW = "PENDING_REVIEW"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    ISSUED = "ISSUED"

    @property
    def description(self):
        descriptions = {
            "DRAFT": "草稿",
            "PENDING_REVIEW": "待审批",
            "APPROVED": "已批准",
            "REJECTED": "已拒绝",
            "ISSUED": "已发放"
        }
        return descriptions.get(self.value, self.value)


class LicenseType(str, Enum):
    """License 类型枚举"""
    TRIAL = "TRIAL"
    OFFICIAL = "OFFICIAL"

    @property
    def description(self):
        descriptions = {
            "TRIAL": "试用版",
            "OFFICIAL": "正式版"
        }
        return descriptions.get(self.value, self.value)


class LicenseApplicationBase(BaseModel):
    """License 申请基础模型"""
    customer_id: int = Field(..., description="关联客户ID")
    deployment_info_id: Optional[int] = Field(None, description="关联部署信息ID")
    license_type: LicenseType = Field(..., description="License 类型")
    expiry_date: date = Field(..., description="到期时间")
    remark: Optional[str] = Field(None, description="备注（申请时填写）")

    @field_validator('expiry_date')
    @classmethod
    def validate_expiry_date(cls, v: date) -> date:
        """验证到期时间必须晚于今天"""
        if v <= date.today():
            raise ValueError('到期时间必须晚于今天')
        return v

    @field_validator('license_type')
    @classmethod
    def validate_license_type(cls, v: LicenseType) -> LicenseType:
        """验证 License 类型"""
        if v not in [LicenseType.TRIAL, LicenseType.OFFICIAL]:
            raise ValueError('License 类型必须是 TRIAL 或 OFFICIAL')
        return v


class LicenseApplicationCreate(LicenseApplicationBase):
    """创建 License 申请请求模型"""
    contract_id: Optional[int] = Field(None, description="关联合同ID（正式版必填）")

    @model_validator(mode='after')
    def validate_contract_for_official(self):
        """验证正式版必须关联合同"""
        if self.license_type == LicenseType.OFFICIAL and not self.contract_id:
            raise ValueError('正式版 License 必须关联合同')
        return self


class LicenseApplicationUpdate(BaseModel):
    """更新 License 申请请求模型"""
    deployment_info_id: Optional[int] = Field(None, description="关联部署信息ID")
    contract_id: Optional[int] = Field(None, description="关联合同ID")
    expiry_date: Optional[date] = Field(None, description="到期时间")
    remark: Optional[str] = Field(None, description="备注")

    @field_validator('expiry_date')
    @classmethod
    def validate_expiry_date(cls, v: Optional[date]) -> Optional[date]:
        """验证到期时间必须晚于今天"""
        if v is not None and v <= date.today():
            raise ValueError('到期时间必须晚于今天')
        return v


class LicenseApplicationApprove(BaseModel):
    """审批 License 申请请求模型 - 简化版本"""
    license_code: str = Field(..., min_length=1, description="授权码（审批人回填）")


class LicenseApplicationApproveFull(BaseModel):
    """审批 License 申请请求模型 - 完整版本"""
    license_info: str = Field(..., min_length=1, description="完整的 License 信息文本")
    comment: Optional[str] = Field(None, description="审批意见")


class LicenseApplicationResponse(BaseModel):
    """License 申请响应模型"""
    id: int = Field(..., description="申请ID")
    team_id: int = Field(..., description="团队ID")
    application_number: str = Field(..., description="申请单号")
    customer_id: int = Field(..., description="关联客户ID")
    deployment_info_id: Optional[int] = Field(None, description="关联部署信息ID")
    contract_id: Optional[int] = Field(None, description="关联合同ID")
    expiry_date: date = Field(..., description="到期时间")
    license_type: str = Field(..., description="License 类型")
    # 补充需求字段
    enterprise_id: Optional[str] = Field(None, description="企业编号")
    supported_modules: Optional[str] = Field(None, description="支持模块")
    server_license_code: Optional[str] = Field(None, description="服务端 License")
    client_license_code: Optional[str] = Field(None, description="客户端 License")
    remark: Optional[str] = Field(None, description="备注")
    # 原有字段
    license_code: Optional[str] = Field(None, description="授权码（旧字段）")
    status: str = Field(..., description="申请状态")
    applicant_id: str = Field(..., description="申请人飞书用户ID")
    approver_id: Optional[str] = Field(None, description="审批人飞书用户ID")
    approved_time: Optional[datetime] = Field(None, description="审批时间")
    # 审批关联字段
    approval_id: Optional[int] = Field(None, description="审批实例ID")
    created_time: datetime = Field(..., description="创建时间")
    last_modified_time: datetime = Field(..., description="最后修改时间")

    # 关联信息（用于前端展示）
    customer_name: Optional[str] = Field(None, description="客户名称")
    deployment_name: Optional[str] = Field(None, description="部署名称")
    contract_name: Optional[str] = Field(None, description="合同名称")
    applicant_name: Optional[str] = Field(None, description="申请人姓名")
    approver_name: Optional[str] = Field(None, description="审批人姓名")

    model_config = ConfigDict(from_attributes=True)


class LicenseApplicationListResponse(BaseModel):
    """License 申请列表响应模型"""
    items: list[LicenseApplicationResponse] = Field(..., description="申请列表")
    total: int = Field(..., description="总数")
    page: int = Field(default=1, description="当前页码")
    page_size: int = Field(default=100, description="每页记录数")


class MessageResponse(BaseModel):
    """消息响应模型"""
    message: str = Field(..., description="响应消息")
