from datetime import date, datetime
from decimal import Decimal
from enum import Enum

from pydantic import BaseModel, Field, ValidationInfo, field_validator


class ContractStatusEnum(str, Enum):
    """合同状态枚举
    
    定义合同生命周期的各种状态\uff1a
    
    - DRAFT: 草稿状态\uff0c可编辑、可删除
    - PENDING_REVIEW: 待审核\uff0c已提交审批等待审核
    - SIGNED: 已签署\uff0c双方签署完成
    - EFFECTIVE: 历史兼容状态\uff0c按已签署处理
    - EXPIRED: 已到期\uff0c合同到期失效
    - TERMINATED: 已终止\uff0c合同提前终止
    """
    DRAFT = "DRAFT"
    PENDING_REVIEW = "PENDING_REVIEW"
    SIGNED = "SIGNED"
    EFFECTIVE = "EFFECTIVE"
    EXPIRED = "EXPIRED"
    TERMINATED = "TERMINATED"
    
    @property
    def description(self) -> str:
        descriptions = {
            "DRAFT": "草稿",
            "PENDING_REVIEW": "待审核",
            "SIGNED": "已签署",
            "EFFECTIVE": "已签署",
            "EXPIRED": "已到期",
            "TERMINATED": "已终止"
        }
        return descriptions.get(self.value, self.value)


class LicenseTypeEnum(str, Enum):
    """授权模式枚举
    
    定义软件授权的两种模式\uff1a
    
    - SUBSCRIPTION: 订阅制\uff0c按年付费\uff0c需填写订阅年限
    - PERPETUAL: 买断制\uff0c一次性付费\uff0c永久使用
    """
    SUBSCRIPTION = "SUBSCRIPTION"
    PERPETUAL = "PERPETUAL"
    
    @property
    def description(self) -> str:
        descriptions = {
            "SUBSCRIPTION": "订阅制",
            "PERPETUAL": "买断制"
        }
        return descriptions.get(self.value, self.value)


class CustomerBasicInfo(BaseModel):
    id: str = Field(..., description="客户对外ID")
    public_id: str = Field(..., description="客户对外ID")
    account_name: str = Field(..., description="客户公司名称")
    
    class Config:
        from_attributes = True


class OpportunityBasicInfo(BaseModel):
    id: str = Field(..., description="商机对外ID")
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
    id: str = Field(..., description="创建人系统用户ID")
    name: str = Field(..., description="创建人姓名")
    email: str | None = Field(None, description="创建人邮箱")
    mobile: str | None = Field(None, description="创建人手机号")
    avatar_url: str | None = Field(None, description="创建人头像URL")
    
    class Config:
        from_attributes = True


class OwnerBasicInfo(CreatorBasicInfo):
    id: str = Field(..., description="负责人系统用户ID")
    name: str = Field(..., description="负责人姓名")


class ContractBase(BaseModel):
    contract_name: str = Field(..., min_length=1, max_length=255, description="合同名称")
    customer_id: str = Field(..., description="关联客户对外ID")
    opportunity_id: str = Field(..., description="关联商机对外ID")
    signing_contact_id: int = Field(..., description="客户签约人ID")
    user_count: int = Field(..., gt=0, description="采购用户数")
    total_amount: Decimal = Field(..., gt=0, description="合同总金额\uff08元\uff09")
    license_type: LicenseTypeEnum = Field(..., description="授权模式\uff08SUBSCRIPTION:订阅制, PERPETUAL:买断制\uff09")
    subscription_years: int | None = Field(None, gt=0, description="订阅年限\uff08订阅制时必填\uff09")
    signing_date: date | None = Field(None, description="签署日期")
    effective_date: date | None = Field(None, description="生效日期")
    
    @field_validator('contract_name')
    @classmethod
    def contract_name_must_not_be_empty(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError('合同名称不能为空')
        return v.strip()
    
    @field_validator('subscription_years')
    @classmethod
    def validate_subscription_years(cls, v: int | None, info: ValidationInfo) -> int | None:
        if info.data.get('license_type') == LicenseTypeEnum.SUBSCRIPTION and (v is None or v <= 0):
            raise ValueError('订阅制下订阅年限必须大于0')
        return v


class ContractCreate(ContractBase):
    owner_id: str | None = Field(None, description="合同负责人系统用户ID\uff0c不传则继承商机/客户负责人")


class ContractInternalCreate(ContractBase):
    """Internal contract creation model using database foreign-key IDs."""
    customer_id: int = Field(..., description="关联客户内部ID")
    opportunity_id: int = Field(..., description="关联商机内部ID")
    owner_id: str | None = Field(None, description="合同负责人系统用户ID")


class ContractUpdate(BaseModel):
    contract_name: str | None = Field(None, min_length=1, max_length=255, description="合同名称")
    user_count: int | None = Field(None, gt=0, description="采购用户数")
    total_amount: Decimal | None = Field(None, gt=0, description="合同总金额\uff08元\uff09")
    license_type: LicenseTypeEnum | None = Field(None, description="授权模式")
    subscription_years: int | None = Field(None, gt=0, description="订阅年限")
    signing_date: date | None = Field(None, description="签署日期")
    effective_date: date | None = Field(None, description="生效日期")


class ContractChangeItem(BaseModel):
    key: str = Field(..., description="变更字段")
    old_value: str = Field(..., description="变更前值")
    new_value: str = Field(..., description="变更后值")


class ContractChangeCreate(BaseModel):
    new_amount: Decimal = Field(..., gt=0, description="变更后合同金额")
    reason: str = Field(..., min_length=1, max_length=2000, description="变更原因")


class ContractFinancialSnapshotResponse(BaseModel):
    paid_amount: Decimal
    invoiced_amount: Decimal
    planned_amount: Decimal
    floor_amount: Decimal


class ContractChangeResponse(BaseModel):
    id: int
    contract_id: int
    creator_id: str
    change_items: list[ContractChangeItem]
    reason: str
    approval_phase: str
    attachment_name: str | None = None
    attachment_size: int | None = None
    attachment_mime_type: str | None = None
    created_time: datetime
    updated_time: datetime

    class Config:
        from_attributes = True


def contract_change_response(change) -> ContractChangeResponse:
    return ContractChangeResponse(
        id=change.id,
        contract_id=change.contract_id,
        creator_id=change.creator_id,
        change_items=change.change_items_json,
        reason=change.reason,
        approval_phase=change.approval_phase,
        attachment_name=change.attachment_name,
        attachment_size=change.attachment_size,
        attachment_mime_type=change.attachment_mime_type,
        created_time=change.created_time,
        updated_time=change.updated_time,
    )


class ContractResponse(BaseModel):
    id: int = Field(..., description="合同ID")
    contract_number: str = Field(..., description="合同编号")
    contract_name: str = Field(..., description="合同名称")
    customer_id: str = Field(..., description="关联客户对外ID")
    opportunity_id: str | None = Field(None, description="关联商机对外ID\uff0c可为空")
    signing_contact_id: int = Field(..., description="客户签约人ID")
    user_count: int = Field(..., description="采购用户数")
    total_amount: Decimal = Field(..., description="合同总金额\uff08元\uff09")
    license_type: str = Field(..., description="授权模式")
    subscription_years: int | None = Field(None, description="订阅年限")
    standard_unit_price: Decimal = Field(..., description="标准单价\uff08系统自动计算\uff09")
    status: str = Field(..., description="合同状态")
    approval_phase: str | None = Field(None, description="审批流程状态\uff1adraft/pending_review/approved/rejected")
    signing_date: date | None = Field(None, description="签署日期")
    effective_date: date | None = Field(None, description="生效日期")
    expiry_date: date | None = Field(None, description="到期日期")
    owner_id: str = Field(..., description="负责人系统用户ID")
    creator_id: str = Field(..., description="创建人系统用户ID")
    created_time: datetime = Field(..., description="创建时间")
    last_modified_time: datetime = Field(..., description="最后修改时间")
    contract_file_path: str | None = Field(None, description="合同附件路径\uff08相对路径\uff09")
    contract_file_name: str | None = Field(None, description="合同附件原始文件名")
    contract_file_size: int | None = Field(None, description="合同附件大小\uff08字节\uff09")
    contract_file_mime_type: str | None = Field(None, description="合同附件 MIME 类型")
    
    class Config:
        from_attributes = True


class ContractListResponse(ContractResponse):
    customer_name: str | None = Field(None, description="客户名称")
    opportunity_name: str | None = Field(None, description="商机名称")
    purchase_type: str | None = Field(None, description="采购类型\uff1aNEW/RENEWAL/EXPANSION")
    license_authorized_users: int | None = Field(
        None,
        description="最新正式 License 授权数量\uff1b无 License 时回退合同采购用户数",
    )
    license_expiry_date: date | None = Field(None, description="最新正式 License 到期日期")
    license_is_permanent: bool = Field(False, description="最新正式 License 是否永久")
    customer_info: CustomerBasicInfo | None = Field(None, description="客户基本信息")
    opportunity_info: OpportunityBasicInfo | None = Field(None, description="商机基本信息")
    owner_info: OwnerBasicInfo | None = Field(None, description="负责人信息")
    creator_info: CreatorBasicInfo | None = Field(None, description="创建人信息")
    status_info: dict | None = Field(None, description="合同状态信息")


class ContractDetailResponse(ContractResponse):
    customer_info: CustomerBasicInfo | None = Field(None, description="客户基本信息")
    opportunity_info: OpportunityBasicInfo | None = Field(None, description="商机基本信息")
    contact_info: ContactBasicInfo | None = Field(None, description="签约人信息")
    owner_info: OwnerBasicInfo | None = Field(None, description="负责人信息")
    creator_info: CreatorBasicInfo | None = Field(None, description="创建人信息")
    can_request_change: bool = Field(False, description="当前用户是否可发起合同变更")
    change_disabled_reason: str | None = Field(None, description="不能发起合同变更的原因")
    pending_change: ContractChangeResponse | None = None
    change_history: list[ContractChangeResponse] = Field(default_factory=list)
    financial_snapshot: ContractFinancialSnapshotResponse | None = None


class MessageResponse(BaseModel):
    message: str = Field(..., description="响应消息")


class ContractChartPreview(BaseModel):
    id: int
    name: str
    customer_name: str | None = None
    owner_name: str | None = None
    amount: float
    signing_date: date | None = None


class ContractChartBucket(BaseModel):
    key: str
    label: str
    count: int
    amount: float
    ratio: int
    amount_ratio: int
    preview: list[ContractChartPreview]
    preview_total: int


class ContractChartCard(BaseModel):
    key: str
    title: str
    description: str
    buckets: list[ContractChartBucket]


class ContractChartResponse(BaseModel):
    population: int
    total_amount: float
    cards: list[ContractChartCard]


class ContractChartBucketContracts(BaseModel):
    chart: str
    bucket: str
    total: int
    contracts: list[ContractChartPreview]
