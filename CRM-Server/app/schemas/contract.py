from pydantic import BaseModel, Field, field_validator
from typing import Optional, List
from datetime import date, datetime
from decimal import Decimal
from enum import Enum


class ContractStatusEnum(str, Enum):
    """合同状态枚举
    
    定义合同生命周期的各种状态：
    
    - DRAFT: 草稿状态，可编辑、可删除
    - PENDING_REVIEW: 待审核，已提交审批等待审核
    - SIGNED: 已签署，双方签署完成等待生效
    - EFFECTIVE: 已生效，合同正式生效中
    - EXPIRED: 已到期，合同到期失效
    - TERMINATED: 已终止，合同提前终止
    """
    DRAFT = "DRAFT"
    PENDING_REVIEW = "PENDING_REVIEW"
    SIGNED = "SIGNED"
    EFFECTIVE = "EFFECTIVE"
    EXPIRED = "EXPIRED"
    TERMINATED = "TERMINATED"
    
    @property
    def description(self):
        descriptions = {
            "DRAFT": "草稿",
            "PENDING_REVIEW": "待审核",
            "SIGNED": "已签署",
            "EFFECTIVE": "生效中",
            "EXPIRED": "已到期",
            "TERMINATED": "已终止"
        }
        return descriptions.get(self.value, self.value)


class LicenseTypeEnum(str, Enum):
    """授权模式枚举
    
    定义软件授权的两种模式：
    
    - SUBSCRIPTION: 订阅制，按年付费，需填写订阅年限
    - PERPETUAL: 买断制，一次性付费，永久使用
    """
    SUBSCRIPTION = "SUBSCRIPTION"
    PERPETUAL = "PERPETUAL"
    
    @property
    def description(self):
        descriptions = {
            "SUBSCRIPTION": "订阅制",
            "PERPETUAL": "买断制"
        }
        return descriptions.get(self.value, self.value)


class CustomerBasicInfo(BaseModel):
    id: int = Field(..., description="客户ID")
    account_name: str = Field(..., description="客户公司名称")
    
    class Config:
        from_attributes = True


class OpportunityBasicInfo(BaseModel):
    id: int = Field(..., description="商机ID")
    opportunity_name: str = Field(..., description="商机名称")
    
    class Config:
        from_attributes = True


class ContactBasicInfo(BaseModel):
    id: int = Field(..., description="联系人ID")
    name: str = Field(..., description="联系人姓名")
    mobile: str = Field(..., description="联系人手机")
    
    class Config:
        from_attributes = True


class CreatorBasicInfo(BaseModel):
    id: str = Field(..., description="创建人飞书用户ID")
    name: str = Field(..., description="创建人姓名")
    email: Optional[str] = Field(None, description="创建人邮箱")
    mobile: Optional[str] = Field(None, description="创建人手机号")
    avatar_url: Optional[str] = Field(None, description="创建人头像URL")
    
    class Config:
        from_attributes = True


class ContractBase(BaseModel):
    contract_name: str = Field(..., min_length=1, max_length=255, description="合同名称")
    customer_id: int = Field(..., description="关联客户ID")
    opportunity_id: int = Field(..., description="关联商机ID")
    signing_contact_id: int = Field(..., description="客户签约人ID")
    user_count: int = Field(..., gt=0, description="采购用户数")
    total_amount: Decimal = Field(..., gt=0, description="合同总金额（元）")
    license_type: LicenseTypeEnum = Field(..., description="授权模式（SUBSCRIPTION:订阅制, PERPETUAL:买断制）")
    subscription_years: Optional[int] = Field(None, gt=0, description="订阅年限（订阅制时必填）")
    signing_date: Optional[date] = Field(None, description="签署日期")
    effective_date: Optional[date] = Field(None, description="生效日期")
    
    @field_validator('contract_name')
    @classmethod
    def contract_name_must_not_be_empty(cls, v):
        if not v or not v.strip():
            raise ValueError('合同名称不能为空')
        return v.strip()
    
    @field_validator('subscription_years')
    @classmethod
    def validate_subscription_years(cls, v, info):
        if info.data.get('license_type') == LicenseTypeEnum.SUBSCRIPTION:
            if v is None or v <= 0:
                raise ValueError('订阅制下订阅年限必须大于0')
        return v


class ContractCreate(ContractBase):
    pass


class ContractUpdate(BaseModel):
    contract_name: Optional[str] = Field(None, min_length=1, max_length=255, description="合同名称")
    user_count: Optional[int] = Field(None, gt=0, description="采购用户数")
    total_amount: Optional[Decimal] = Field(None, gt=0, description="合同总金额（元）")
    license_type: Optional[LicenseTypeEnum] = Field(None, description="授权模式")
    subscription_years: Optional[int] = Field(None, gt=0, description="订阅年限")
    signing_date: Optional[date] = Field(None, description="签署日期")
    effective_date: Optional[date] = Field(None, description="生效日期")


class ContractStatusUpdate(BaseModel):
    """合同状态更新请求模型
    
    用于更新合同状态，推进合同生命周期：
    
    - status: 目标状态
      - PENDING_REVIEW: 从草稿提交审批
      - SIGNED: 审核通过标记已签署
      - EFFECTIVE: 签署完成激活生效
      - EXPIRED: 合同到期
      - TERMINATED: 合同提前终止
    """
    status: ContractStatusEnum = Field(..., description="目标合同状态，参考 ContractStatusEnum 枚举值")


class ContractResponse(BaseModel):
    id: int = Field(..., description="合同ID")
    contract_number: str = Field(..., description="合同编号")
    contract_name: str = Field(..., description="合同名称")
    customer_id: int = Field(..., description="关联客户ID")
    opportunity_id: int = Field(..., description="关联商机ID")
    signing_contact_id: int = Field(..., description="客户签约人ID")
    user_count: int = Field(..., description="采购用户数")
    total_amount: Decimal = Field(..., description="合同总金额（元）")
    license_type: str = Field(..., description="授权模式")
    subscription_years: Optional[int] = Field(None, description="订阅年限")
    standard_unit_price: Decimal = Field(..., description="标准单价（系统自动计算）")
    status: str = Field(..., description="合同状态")
    signing_date: Optional[date] = Field(None, description="签署日期")
    effective_date: Optional[date] = Field(None, description="生效日期")
    expiry_date: Optional[date] = Field(None, description="到期日期")
    creator_id: str = Field(..., description="创建人飞书用户ID")
    created_time: datetime = Field(..., description="创建时间")
    last_modified_time: datetime = Field(..., description="最后修改时间")
    
    class Config:
        from_attributes = True


class ContractListResponse(ContractResponse):
    customer_info: Optional[CustomerBasicInfo] = Field(None, description="客户基本信息")
    opportunity_info: Optional[OpportunityBasicInfo] = Field(None, description="商机基本信息")
    creator_info: Optional[CreatorBasicInfo] = Field(None, description="创建人信息")
    status_info: Optional[dict] = Field(None, description="合同状态信息")


class ContractDetailResponse(ContractResponse):
    customer_info: Optional[CustomerBasicInfo] = Field(None, description="客户基本信息")
    opportunity_info: Optional[OpportunityBasicInfo] = Field(None, description="商机基本信息")
    contact_info: Optional[ContactBasicInfo] = Field(None, description="签约人信息")
    creator_info: Optional[CreatorBasicInfo] = Field(None, description="创建人信息")


class MessageResponse(BaseModel):
    message: str = Field(..., description="响应消息")
