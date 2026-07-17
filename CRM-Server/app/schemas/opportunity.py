from pydantic import BaseModel, Field, field_validator, ConfigDict, model_validator
from typing import Optional, List
from datetime import date, datetime
from enum import Enum
from app.schemas.customer import ProcurementMethodInfo


class CurrentStageSnapshotInfo(BaseModel):
    """当前阶段快照信息"""
    id: int = Field(..., description="快照ID")
    procurement_stage_template_id: int = Field(..., description="阶段模板ID（与采购阶段列表的id对应）")
    stage_name: str = Field(..., description="阶段名称")
    win_probability: int = Field(..., description="阶段赢率（0-100）")
    template_sort_order: int = Field(..., description="阶段顺序（记录进入时模板的sort_order）")
    template_code: Optional[str] = Field(None, description="阶段模板编码")
    entered_at: datetime = Field(..., description="进入时间")
    exited_at: Optional[datetime] = Field(None, description="退出时间")
    procurement_method: Optional[ProcurementMethodInfo] = Field(None, description="采购方式信息")


class PurchaseTypeEnum(str, Enum):
    NEW = "NEW"
    RENEWAL = "RENEWAL"
    EXPANSION = "EXPANSION"
    
    @property
    def description(self):
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
    def description(self):
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
    def description(self):
        descriptions = {
            "0": "跟进中",
            "1": "赢单",
            "2": "输单"
        }
        return descriptions.get(self.value, self.value)


class OpportunityStageBase(BaseModel):
    stage_code: str = Field(..., min_length=1, max_length=100, description="阶段编码")
    stage_name: str = Field(..., min_length=1, max_length=100, description="阶段名称")
    win_probability: int = Field(..., ge=0, le=100, description="赢率（0-100）")
    sort_order: int = Field(..., ge=0, description="排序序号")
    description: Optional[str] = Field(None, max_length=500, description="阶段描述")


class OpportunityStageCreate(OpportunityStageBase):
    pass


class OpportunityStageUpdate(BaseModel):
    stage_name: Optional[str] = Field(None, min_length=1, max_length=100, description="阶段名称")
    win_probability: Optional[int] = Field(None, ge=0, le=100, description="赢率（0-100）")
    sort_order: Optional[int] = Field(None, ge=0, description="排序序号")
    description: Optional[str] = Field(None, max_length=500, description="阶段描述")
    is_active: Optional[int] = Field(None, ge=0, le=1, description="是否启用")


class OpportunityStageResponse(BaseModel):
    id: int = Field(..., description="销售阶段ID")
    stage_code: str = Field(..., description="阶段编码")
    stage_name: str = Field(..., description="阶段名称")
    win_probability: int = Field(..., description="赢率（0-100）")
    sort_order: int = Field(..., description="排序序号")
    description: Optional[str] = Field(None, description="阶段描述")
    is_active: int = Field(..., description="是否启用：0:否, 1:是")
    created_time: datetime = Field(..., description="创建时间")
    last_modified_time: datetime = Field(..., description="最后修改时间")
    
    model_config = ConfigDict(from_attributes=True)


class OpportunityBase(BaseModel):
    opportunity_name: str = Field(..., min_length=1, max_length=255, description="商机名称（项目名称）")
    total_amount: float = Field(..., gt=0, description="预计总金额（元）")
    user_count: int = Field(..., gt=0, description="采购用户数（ licenses 数量）")
    license_type: LicenseTypeEnum = Field(..., description="授权模式：SUBSCRIPTION:订阅制, PERPETUAL:买断制")
    subscription_years: Optional[int] = Field(None, gt=0, description="订阅年限（订阅制时必填，默认1年）")
    purchase_type: PurchaseTypeEnum = Field(..., description="采购类型：NEW:新购, RENEWAL:续购, EXPANSION:增购")
    decision_maker_count: Optional[int] = Field(None, ge=1, description="采购决策人数（影响销售策略）")
    expected_closing_date: date = Field(..., description="预计成交日期")
    
    @model_validator(mode='after')
    def validate_license_fields(cls, values):
        license_type = values.license_type
        subscription_years = values.subscription_years
        
        if license_type == LicenseTypeEnum.SUBSCRIPTION:
            if subscription_years is None or subscription_years <= 0:
                raise ValueError('订阅制下订阅年限必须大于0')
        
        return values
    
    @field_validator('opportunity_name')
    @classmethod
    def opportunity_name_must_not_be_empty(cls, v):
        if v is not None and (not v or not v.strip()):
            raise ValueError('商机名称不能为空')
        return v.strip() if v else v


class OpportunityCreate(OpportunityBase):
    customer_id: int = Field(..., description="关联客户ID（关联到 crm_customers 表）")
    procurement_method_id: Optional[int] = Field(None, description="采购方式ID（关联到 crm_procurement_methods 表），如果不指定则使用客户的默认采购方式")
    stage_id: Optional[int] = Field(None, description="初始销售阶段ID（关联到 crm_procurement_stage_templates 表），如果不指定则使用采购方式的默认起始阶段")
    owner_id: Optional[str] = Field(None, description="负责人系统用户ID，如果不指定则默认为创建人")


class OpportunityUpdate(BaseModel):
    opportunity_name: Optional[str] = Field(None, min_length=1, max_length=255, description="商机名称（项目名称）")
    total_amount: Optional[float] = Field(None, gt=0, description="预计总金额（元）")
    user_count: Optional[int] = Field(None, gt=0, description="采购用户数（ licenses 数量）")
    license_type: Optional[LicenseTypeEnum] = Field(None, description="授权模式：SUBSCRIPTION:订阅制, PERPETUAL:买断制")
    subscription_years: Optional[int] = Field(None, gt=0, description="订阅年限（订阅制时必填，默认1年）")
    purchase_type: Optional[PurchaseTypeEnum] = Field(None, description="采购类型：NEW:新购, RENEWAL:续购, EXPANSION:增购")
    decision_maker_count: Optional[int] = Field(None, ge=1, description="采购决策人数（影响销售策略）")
    expected_closing_date: Optional[date] = Field(None, description="预计成交日期")
    procurement_method_id: Optional[int] = Field(None, description="采购方式ID（关联到 crm_procurement_methods 表）")
    owner_id: Optional[str] = Field(None, description="负责人系统用户ID")
    
    @model_validator(mode='after')
    def validate_license_fields(cls, values):
        license_type = values.license_type
        subscription_years = values.subscription_years
        
        if license_type == LicenseTypeEnum.SUBSCRIPTION:
            if subscription_years is None or subscription_years <= 0:
                raise ValueError('订阅制下订阅年限必须大于0')
        
        return values


class OpportunityStageUpdate(BaseModel):
    stage_template_id: int = Field(..., description="目标采购阶段模板ID（推进到下一阶段）")


class OpportunityMoveToStage(BaseModel):
    stage_template_id: int = Field(..., description="目标采购阶段模板ID（推进到下一阶段）")


class OpportunityWin(BaseModel):
    actual_amount: float = Field(..., gt=0, description="实际成交金额（元）")
    actual_closing_date: date = Field(..., description="实际成交日期")


class OpportunityLose(BaseModel):
    loss_reason: str = Field(..., min_length=1, max_length=500, description="输单原因（必填，用于后续分析）")
    
    @field_validator('loss_reason')
    @classmethod
    def loss_reason_must_not_be_empty(cls, v):
        if v is not None and (not v or not v.strip()):
            raise ValueError('输单原因不能为空')
        return v.strip() if v else v


class OpportunityResponse(BaseModel):
    id: int = Field(..., description="商机ID（主键）")
    opportunity_name: str = Field(..., description="商机名称（项目名称）")
    customer_id: int = Field(..., description="关联客户ID")
    procurement_method_id: Optional[int] = Field(None, description="采购方式ID")
    procurement_method_info: Optional[ProcurementMethodInfo] = Field(None, description="采购方式详细信息")
    total_amount: float = Field(..., description="预计总金额（元）")
    user_count: int = Field(..., description="采购用户数（ licenses 数量）")
    unit_price: float = Field(..., description="标准单价（系统自动计算：订阅制=总金额/用户数/年数，买断制=总金额/用户数/5）")
    license_type: str = Field(..., description="授权模式：SUBSCRIPTION:订阅, PERPETUAL:买断")
    subscription_years: Optional[int] = Field(None, description="订阅年限（订阅制时必填）")
    purchase_type: str = Field(..., description="采购类型：NEW:新购, RENEWAL:续购, EXPANSION:增购")
    decision_maker_count: Optional[int] = Field(None, description="采购决策人数（影响销售策略）")
    expected_closing_date: date = Field(..., description="预计成交日期")
    stage_id: Optional[int] = Field(None, description="当前销售阶段ID（已废弃，保留用于兼容）")
    win_probability: int = Field(..., description="当前阶段赢率（0-100，继承自销售阶段配置）")
    owner_id: str = Field(..., description="负责人系统用户ID")
    status: int = Field(..., description="商机状态：0:跟进中, 1:已赢单, 2:已输单")
    loss_reason: Optional[str] = Field(None, description="输单原因（status=2时有值）")
    actual_amount: Optional[float] = Field(None, description="实际成交金额（status=1时有值）")
    actual_closing_date: Optional[date] = Field(None, description="实际成交日期（status=1时有值）")
    creator_id: str = Field(..., description="创建人系统用户ID")
    created_time: datetime = Field(..., description="创建时间")
    last_modified_time: datetime = Field(..., description="最后修改时间")
    version: int = Field(..., description="版本号（乐观锁，防止并发修改冲突）")
    current_stage_snapshot: Optional[CurrentStageSnapshotInfo] = Field(None, description="当前阶段快照信息")
    
    model_config = ConfigDict(from_attributes=True)


class CustomerInfo(BaseModel):
    id: int = Field(..., description="客户ID")
    account_name: str = Field(..., description="客户公司名称")
    industry: Optional[str] = Field(None, description="所属行业")
    city: str = Field(..., description="所在城市")
    address: Optional[str] = Field(None, description="公司地址")
    company_scale: Optional[str] = Field(None, description="公司规模")
    status: int = Field(..., description="客户状态")
    owner_id: Optional[str] = Field(None, description="负责人系统用户ID")
    
    model_config = ConfigDict(from_attributes=True)


class OwnerInfo(BaseModel):
    id: str = Field(..., description="系统用户ID")
    name: str = Field(..., description="用户姓名")
    avatar_url: Optional[str] = Field(None, description="用户头像URL")
    
    model_config = ConfigDict(from_attributes=True)


class OpportunityProcurementStageInfo(BaseModel):
    """商机采购阶段信息"""
    id: int = Field(..., description="阶段模板ID")
    stage_name: str = Field(..., description="阶段名称")
    win_probability: int = Field(..., description="阶段赢率（0-100）")
    sort_order: int = Field(..., description="阶段顺序")
    is_current: bool = Field(..., description="是否为当前商机的阶段")
    is_default_start: bool = Field(..., description="是否为默认起始阶段")
    can_skip: bool = Field(..., description="是否可跳过")


class OpportunityDetailResponse(OpportunityResponse):
    current_stage_snapshot: Optional[CurrentStageSnapshotInfo] = Field(None, description="当前阶段快照信息")
    procurement_stages: Optional[List[OpportunityProcurementStageInfo]] = Field(None, description="该采购方式的所有阶段列表")
    customer_name: Optional[str] = Field(None, description="客户名称")
    customer_info: Optional['CustomerInfo'] = Field(None, description="客户详细信息")
    owner_info: Optional[OwnerInfo] = Field(None, description="负责人信息")
    creator_info: Optional[OwnerInfo] = Field(None, description="创建人信息")


class OpportunityListResponse(OpportunityResponse):
    stage: Optional[OpportunityStageResponse] = Field(None, description="销售阶段信息")
    customer_name: Optional[str] = Field(None, description="客户名称")
    owner_info: Optional[OwnerInfo] = Field(None, description="负责人信息")


class MessageResponse(BaseModel):
    message: str = Field(..., description="响应消息")


class SalesFunnelResponse(BaseModel):
    stage_id: int = Field(..., description="销售阶段ID")
    stage_code: str = Field(..., description="阶段编码")
    stage_name: str = Field(..., description="阶段名称")
    win_probability: int = Field(..., description="赢率（0-100）")
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
    owner_id: Optional[str] = Field(None, description="负责人ID")
    start_date: Optional[date] = Field(None, description="开始日期")
    end_date: Optional[date] = Field(None, description="结束日期")
