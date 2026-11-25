from datetime import date, datetime
from enum import Enum
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.schemas.customer import ProcurementMethodInfo


def _split_public_ids(value: object) -> object:
    if isinstance(value, str):
        return [item.strip() for item in value.split(",") if item.strip()]
    return value




class CurrentStageSnapshotInfo(BaseModel):
    """当前阶段快照信息"""
    id: int = Field(..., description="快照ID")
    procurement_stage_template_id: int = Field(..., description="阶段模板ID\uff08与采购阶段列表的id对应\uff09")
    stage_name: str = Field(..., description="阶段名称")
    win_probability: int = Field(..., description="阶段赢率\uff080-100\uff09")
    template_sort_order: int = Field(..., description="阶段顺序\uff08记录进入时模板的sort_order\uff09")
    template_code: str | None = Field(None, description="阶段模板编码")
    entered_at: datetime = Field(..., description="进入时间")
    exited_at: datetime | None = Field(None, description="退出时间")
    procurement_method: ProcurementMethodInfo | None = Field(None, description="采购方式信息")


class PurchaseTypeEnum(str, Enum):
    NEW = "NEW"
    RENEWAL = "RENEWAL"
    EXPANSION = "EXPANSION"
    
    @property
    def description(self) -> str:
        descriptions = {
            "NEW": "新购",
            "RENEWAL": "续购",
            "EXPANSION": "增购"
        }
        return descriptions.get(self.value, self.value)


class LicenseTypeEnum(str, Enum):
    SUBSCRIPTION = "SUBSCRIPTION"
    PERPETUAL = "PERPETUAL"
    
    @property
    def description(self) -> str:
        descriptions = {
            "SUBSCRIPTION": "订阅制",
            "PERPETUAL": "买断制"
        }
        return descriptions.get(self.value, self.value)


class OpportunityStatusEnum(str, Enum):
    FOLLOWING = "0"
    WON = "1"
    LOST = "2"
    
    @property
    def description(self) -> str:
        descriptions = {
            "0": "跟进中",
            "1": "赢单",
            "2": "输单"
        }
        return descriptions.get(self.value, self.value)


class OpportunityStageBase(BaseModel):
    stage_code: str = Field(..., min_length=1, max_length=100, description="阶段编码")
    stage_name: str = Field(..., min_length=1, max_length=100, description="阶段名称")
    win_probability: int = Field(..., ge=0, le=100, description="赢率\uff080-100\uff09")
    sort_order: int = Field(..., ge=0, description="排序序号")
    description: str | None = Field(None, max_length=500, description="阶段描述")


class OpportunityStageCreate(OpportunityStageBase):
    pass


class OpportunityStageResponse(BaseModel):
    id: int = Field(..., description="销售阶段ID")
    stage_code: str = Field(..., description="阶段编码")
    stage_name: str = Field(..., description="阶段名称")
    win_probability: int = Field(..., description="赢率\uff080-100\uff09")
    sort_order: int = Field(..., description="排序序号")
    description: str | None = Field(None, description="阶段描述")
    is_active: int = Field(..., description="是否启用\uff1a0:否, 1:是")
    created_time: datetime = Field(..., description="创建时间")
    last_modified_time: datetime = Field(..., description="最后修改时间")
    
    model_config = ConfigDict(from_attributes=True)


class OpportunityBase(BaseModel):
    opportunity_name: str | None = Field(
        None, min_length=1, max_length=255,
        description="商机名称\uff08项目名称\uff09\uff0c创建时不传则由后端自动生成",
    )
    total_amount: float = Field(..., gt=0, description="预计总金额\uff08元\uff09")
    user_count: int = Field(..., gt=0, description="采购用户数\uff08 licenses 数量\uff09")
    license_type: LicenseTypeEnum = Field(..., description="授权模式\uff1aSUBSCRIPTION:订阅制, PERPETUAL:买断制")
    subscription_years: int | None = Field(None, gt=0, description="订阅年限\uff08订阅制时必填\uff0c默认1年\uff09")
    purchase_type: PurchaseTypeEnum = Field(..., description="采购类型\uff1aNEW:新购, RENEWAL:续购, EXPANSION:增购")
    decision_maker_count: int | None = Field(None, ge=1, description="采购决策人数\uff08影响销售策略\uff09")
    expected_closing_date: date = Field(..., description="预计成交日期")
    
    @model_validator(mode='after')
    def validate_license_fields(self) -> "OpportunityBase":
        license_type = self.license_type
        subscription_years = self.subscription_years

        if license_type == LicenseTypeEnum.SUBSCRIPTION and (subscription_years is None or subscription_years <= 0):
            raise ValueError('订阅制下订阅年限必须大于0')

        return self
    
    @field_validator('opportunity_name')
    @classmethod
    def opportunity_name_must_not_be_empty(cls, v: str | None) -> str | None:
        if v is not None and (not v or not v.strip()):
            raise ValueError('商机名称不能为空')
        return v.strip() if v else v


class OpportunityCreate(OpportunityBase):
    customer_id: str = Field(..., description="关联客户对外ID")
    procurement_method_id: int | None = Field(
        None,
        description="采购方式ID\uff08关联到 crm_procurement_methods 表\uff09\uff0c如果不指定则使用客户的默认采购方式",
    )
    stage_id: int | None = Field(
        None,
        description=(
            "初始销售阶段ID\uff08关联到 crm_procurement_stage_templates 表\uff09\uff0c"
            "如果不指定则使用采购方式的默认起始阶段"
        ),
    )
    owner_id: str | None = Field(None, description="负责人系统用户ID\uff0c如果不指定则默认为创建人")
    product_public_id: str = Field(..., min_length=1, description="关联产品对外ID")
    product_module_public_ids: list[str] = Field(..., min_length=1, description="关联产品模块对外ID列表")

    @field_validator("product_module_public_ids", mode="before")
    @classmethod
    def split_create_module_public_ids(cls, value: object) -> object:
        return _split_public_ids(value)



class OpportunityUpdate(BaseModel):
    opportunity_name: str | None = Field(None, min_length=1, max_length=255, description="商机名称\uff08项目名称\uff09")
    total_amount: float | None = Field(None, gt=0, description="预计总金额\uff08元\uff09")
    user_count: int | None = Field(None, gt=0, description="采购用户数\uff08 licenses 数量\uff09")
    license_type: LicenseTypeEnum | None = Field(
        None,
        description="授权模式\uff1aSUBSCRIPTION:订阅制, PERPETUAL:买断制",
    )
    subscription_years: int | None = Field(None, gt=0, description="订阅年限\uff08订阅制时必填\uff0c默认1年\uff09")
    purchase_type: PurchaseTypeEnum | None = Field(
        None,
        description="采购类型\uff1aNEW:新购, RENEWAL:续购, EXPANSION:增购",
    )
    decision_maker_count: int | None = Field(None, ge=1, description="采购决策人数\uff08影响销售策略\uff09")
    expected_closing_date: date | None = Field(None, description="预计成交日期")
    procurement_method_id: int | None = Field(
        None,
        description="采购方式ID\uff08关联到 crm_procurement_methods 表\uff09",
    )
    owner_id: str | None = Field(None, description="负责人系统用户ID")
    product_public_id: str | None = Field(None, min_length=1, description="关联产品对外ID")
    product_module_public_ids: list[str] | None = Field(None, description="关联产品模块对外ID列表")

    @field_validator("product_module_public_ids", mode="before")
    @classmethod
    def split_update_module_public_ids(cls, value: object) -> object:
        return _split_public_ids(value)


    @model_validator(mode="after")
    def validate_license_fields(self) -> "OpportunityUpdate":
        license_type = self.license_type
        subscription_years = self.subscription_years

        if license_type == LicenseTypeEnum.SUBSCRIPTION and (subscription_years is None or subscription_years <= 0):
            raise ValueError("订阅制下订阅年限必须大于0")

        product_public_id = self.product_public_id
        module_public_ids = self.product_module_public_ids
        if product_public_id is not None or module_public_ids is not None:
            if not product_public_id:
                raise ValueError("请选择产品")
            if not module_public_ids:
                raise ValueError("请至少选择一个产品模块")

        return self


class OpportunityDealJourneyUpdate(BaseModel):
    """显式调整商机当前业务旅程\uff1b传 null 表示解除关联。"""

    deal_journey_id: str | None = Field(
        ...,
        description="目标业务旅程对外ID\uff1b传 null 表示解除当前关联",
    )
    expected_version: int | None = Field(
        None,
        ge=1,
        description="客户端读取到的商机版本\uff1b用于避免并发操作覆盖\uff0c省略则由服务端行锁保护",
    )


class OpportunityStageUpdate(BaseModel):
    stage_template_id: int = Field(..., description="目标采购阶段模板ID\uff08推进到下一阶段\uff09")


class OpportunityMoveToStage(BaseModel):
    stage_template_id: int = Field(..., description="目标采购阶段模板ID\uff08推进到下一阶段\uff09")


class OpportunityWin(BaseModel):
    actual_amount: float = Field(..., gt=0, description="实际成交金额\uff08元\uff09")
    actual_closing_date: date = Field(..., description="实际成交日期")


class OpportunityLose(BaseModel):
    loss_reason: str = Field(
        ...,
        min_length=1,
        max_length=500,
        description="输单原因\uff08必填\uff0c用于后续分析\uff09",
    )
    
    @field_validator('loss_reason')
    @classmethod
    def loss_reason_must_not_be_empty(cls, v: str | None) -> str | None:
        if v is not None and (not v or not v.strip()):
            raise ValueError('输单原因不能为空')
        return v.strip() if v else v


class OpportunityProductModuleInfo(BaseModel):
    public_id: str = Field(..., description="产品模块对外ID")
    name: str = Field(..., description="产品模块名称")
    module_role: str = Field(..., description="模块角色\uff1aBASE/ADD_ON")


class OpportunityResponse(BaseModel):
    id: str = Field(..., description="商机对外ID")
    deal_journey_id: str | None = Field(None, description="当前业务旅程对外ID")
    public_id: str = Field(..., description="商机对外ID")
    opportunity_number: str = Field(..., description="商机编号")
    opportunity_name: str = Field(..., description="商机名称\uff08项目名称\uff09")
    customer_id: str = Field(..., description="关联客户对外ID")
    procurement_method_id: int | None = Field(None, description="采购方式ID")
    procurement_method_info: ProcurementMethodInfo | None = Field(None, description="采购方式详细信息")
    product_public_id: str | None = Field(None, description="关联产品对外ID")
    product_name: str | None = Field(None, description="关联产品名称")
    product_module_public_ids: list[str] = Field(default_factory=list, description="关联产品模块对外ID列表")
    product_modules: list[OpportunityProductModuleInfo] = Field(default_factory=list, description="关联产品模块摘要")
    total_amount: float = Field(..., description="预计总金额\uff08元\uff09")
    user_count: int = Field(..., description="采购用户数\uff08 licenses 数量\uff09")
    unit_price: float = Field(
        ...,
        description="标准单价\uff08系统自动计算\uff1a订阅制=总金额/用户数/年数\uff0c买断制=总金额/用户数/5\uff09",
    )
    license_type: str = Field(..., description="授权模式\uff1aSUBSCRIPTION:订阅, PERPETUAL:买断")
    subscription_years: int | None = Field(None, description="订阅年限\uff08订阅制时必填\uff09")
    purchase_type: str = Field(..., description="采购类型\uff1aNEW:新购, RENEWAL:续购, EXPANSION:增购")
    decision_maker_count: int | None = Field(None, description="采购决策人数\uff08影响销售策略\uff09")
    expected_closing_date: date = Field(..., description="预计成交日期")
    stage_id: int | None = Field(None, description="当前销售阶段ID\uff08已废弃\uff0c保留用于兼容\uff09")
    procurement_stage_id: int | None = Field(None, description="当前采购阶段ID")
    win_probability: int = Field(..., description="当前阶段赢率\uff080-100\uff0c继承自销售阶段配置\uff09")
    owner_id: str = Field(..., description="负责人系统用户ID")
    status: int = Field(..., description="商机状态\uff1a0:跟进中, 1:已赢单, 2:已输单")
    approval_phase: str = Field(..., description="审批流程状态\uff1adraft/pending_review/approved/rejected")
    loss_reason: str | None = Field(None, description="输单原因\uff08status=2时有值\uff09")
    actual_amount: float | None = Field(None, description="实际成交金额\uff08status=1时有值\uff09")
    actual_closing_date: date | None = Field(None, description="实际成交日期\uff08status=1时有值\uff09")
    creator_id: str = Field(..., description="创建人系统用户ID")
    created_time: datetime = Field(..., description="创建时间")
    last_modified_time: datetime = Field(..., description="最后修改时间")
    updated_time: datetime | None = Field(None, description="最后修改时间\uff0c兼容前端字段")
    version: int = Field(..., description="版本号\uff08乐观锁\uff0c防止并发修改冲突\uff09")
    current_stage_snapshot: CurrentStageSnapshotInfo | None = Field(None, description="当前阶段快照信息")
    loss_unavailable_reason: str | None = Field(None, description="已赢单但存在未删除合同时不可标记输单的原因")

    model_config = ConfigDict(from_attributes=True)


class CustomerInfo(BaseModel):
    id: str = Field(..., description="客户对外ID")
    public_id: str = Field(..., description="客户对外ID")
    account_name: str = Field(..., description="客户公司名称")
    industry: str | None = Field(None, description="所属行业")
    city: str = Field(..., description="所在城市")
    address: str | None = Field(None, description="公司地址")
    company_scale: str | None = Field(None, description="公司规模")
    status: int = Field(..., description="客户状态")
    owner_id: str | None = Field(None, description="负责人系统用户ID")
    
    model_config = ConfigDict(from_attributes=True)


class OwnerInfo(BaseModel):
    id: str = Field(..., description="系统用户ID")
    name: str = Field(..., description="用户姓名")
    avatar_url: str | None = Field(None, description="用户头像URL")
    
    model_config = ConfigDict(from_attributes=True)


class OpportunityProcurementStageInfo(BaseModel):
    """商机采购阶段信息"""
    id: int = Field(..., description="阶段模板ID")
    stage_name: str = Field(..., description="阶段名称")
    win_probability: int = Field(..., description="阶段赢率\uff080-100\uff09")
    sort_order: int = Field(..., description="阶段顺序")
    is_current: bool = Field(..., description="是否为当前商机的阶段")
    is_default_start: bool = Field(..., description="是否为默认起始阶段")
    can_skip: bool = Field(..., description="是否可跳过")


class OpportunityStageInfo(BaseModel):
    id: int = Field(..., description="阶段快照ID")
    stage_name: str = Field(..., description="阶段名称")
    win_probability: int = Field(..., description="阶段赢率")
    is_default: int = Field(0, description="是否默认阶段\uff0c兼容旧前端字段")


class OpportunityDetailResponse(OpportunityResponse):
    current_stage_snapshot: CurrentStageSnapshotInfo | None = Field(None, description="当前阶段快照信息")
    procurement_stages: list[OpportunityProcurementStageInfo] | None = Field(
        None,
        description="该采购方式的所有阶段列表",
    )
    customer_name: str | None = Field(None, description="客户名称")
    customer_info: Optional['CustomerInfo'] = Field(None, description="客户详细信息")
    owner_info: OwnerInfo | None = Field(None, description="负责人信息")
    creator_info: OwnerInfo | None = Field(None, description="创建人信息")


class OpportunityListResponse(OpportunityResponse):
    stage: OpportunityStageResponse | None = Field(None, description="销售阶段信息")
    stage_info: OpportunityStageInfo | None = Field(None, description="当前阶段信息\uff0c兼容旧前端字段")
    customer_name: str | None = Field(None, description="客户名称")
    owner_info: OwnerInfo | None = Field(None, description="负责人信息")
    contract_unavailable_reason: str | None = Field(None, description="新建合同时不可选的原因。可创建时为空")


class OpportunityChartPreview(BaseModel):
    id: str
    name: str
    customer_name: str | None = None
    owner_name: str | None = None
    amount: float
    expected_closing_date: date | None = None


class OpportunityChartBucket(BaseModel):
    key: str
    label: str
    count: int
    amount: float
    ratio: float
    amount_ratio: float
    preview: list[OpportunityChartPreview]
    preview_total: int


class OpportunityChartCard(BaseModel):
    key: str
    buckets: list[OpportunityChartBucket]


class OpportunityChartResponse(BaseModel):
    population: int
    total_amount: float
    cards: list[OpportunityChartCard]


class OpportunityChartBucketOpportunities(BaseModel):
    chart: str
    bucket: str
    total: int
    opportunities: list[OpportunityChartPreview]



class MessageResponse(BaseModel):
    message: str = Field(..., description="响应消息")


class SalesFunnelResponse(BaseModel):
    stage_id: int = Field(..., description="销售阶段ID")
    stage_code: str = Field(..., description="阶段编码")
    stage_name: str = Field(..., description="阶段名称")
    win_probability: int = Field(..., description="赢率\uff080-100\uff09")
    opportunity_count: int = Field(..., description="商机数量")
    total_amount: float = Field(..., description="总金额")
    average_amount: float = Field(..., description="平均金额")


class StageDurationResponse(BaseModel):
    stage_id: int = Field(..., description="销售阶段ID")
    stage_code: str = Field(..., description="阶段编码")
    stage_name: str = Field(..., description="阶段名称")
    average_days: float = Field(..., description="平均停留天数")
    min_days: float = Field(..., description="最短停留天数")
    max_days: float = Field(..., description="最长停留天数")
    opportunity_count: int = Field(..., description="商机数量")


class AnalyticsFilter(BaseModel):
    owner_id: str | None = Field(None, description="负责人ID")
    start_date: date | None = Field(None, description="开始日期")
    end_date: date | None = Field(None, description="结束日期")
