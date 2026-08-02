from __future__ import annotations

import enum
from datetime import date, datetime
from enum import Enum
from typing import Dict, List, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator

JsonObject = Dict[str, object]


class CustomerIndustryOption(BaseModel):
    """客户所属行业选项"""
    value: str = Field(..., description="行业值")
    label: str = Field(..., description="行业名称")
    
    class Config:
        from_attributes = True


class CustomerIndustryInfo(BaseModel):
    """客户所属行业信息"""
    code: str = Field(..., description="行业代码")
    name: str = Field(..., description="行业名称")


class ProcurementMethodInfo(BaseModel):
    """采购方式简要信息"""
    id: int = Field(..., description="采购方式ID")
    code: str = Field(..., description="采购方式编码")
    name: str = Field(..., description="采购方式名称")
    is_active: int = Field(..., description="是否启用：1=启用, 0=停用")


class CustomerSource(str, enum.Enum):
    ONLINE_REGISTER = "线上注册"
    MARKETING_ACTIVITY = "市场活动"
    REFERRAL = "客户推荐"
    COLD_CALL = "电话营销"
    WEBSITE_INQUIRY = "网站咨询"
    EXHIBITION = "展会"
    OTHER = "其他"
    LEAD_CONVERSION = "线索转化"


class CustomerStatusEnum(str, Enum):
    FOLLOWING = "0"
    WON = "1"
    LOST = "2"
    INACTIVE = "3"
    
    @property
    def description(self):
        descriptions = {
            "0": "跟进中",
            "1": "已成交",
            "2": "已流失",
            "3": "非激活"
        }
        return descriptions.get(self.value, self.value)


class ReturnReasonEnum(str, Enum):
    LOST_DEAL = "丢单"
    NO_INTEREST = "无意向"
    WRONG_INFO = "信息错误"
    LONG_NO_FOLLOW_UP = "长期未跟进"
    BUDGET_ISSUE = "预算不足"
    OTHER = "其他"
    
    @property
    def description(self):
        return self.value


class GenderEnum(str, Enum):
    UNKNOWN = "0"
    MALE = "1"
    FEMALE = "2"
    
    @property
    def description(self):
        descriptions = {
            "0": "未知",
            "1": "男",
            "2": "女"
        }
        return descriptions.get(self.value, self.value)


class ContactBase(BaseModel):
    name: str = Field(..., min_length=1, max_length=100, description="联系人姓名")
    gender: GenderEnum = Field(..., description="性别：1:男, 2:女")
    position: str = Field(..., min_length=1, max_length=100, description="职务（如：CTO、采购经理等）")
    is_decision_maker: bool = Field(False, description="是否关键决策人（影响销售策略）")
    mobile: str = Field(..., min_length=1, max_length=20, description="手机号（必填，主要联系方式）")
    email: Optional[str] = Field(None, max_length=100, description="邮箱地址")
    wechat_id: Optional[str] = Field(None, max_length=100, description="微信ID（用于微信沟通）")
    remark: Optional[str] = Field(None, description="备注信息（如：沟通偏好、最佳联系时间等）")
    reports_to: Optional[int] = Field(None, description="汇报对象联系人ID（用于建立组织架构）")
    
    @field_validator('name')
    @classmethod
    def name_must_not_be_empty(cls, v):
        if v is not None and (not v or not v.strip()):
            raise ValueError('联系人姓名不能为空')
        return v.strip() if v else v
    
    @field_validator('mobile')
    @classmethod
    def mobile_must_not_be_empty(cls, v):
        if v is not None and (not v or not v.strip()):
            raise ValueError('手机号不能为空')
        return v.strip() if v else v

    @field_validator('position')
    @classmethod
    def position_must_not_be_empty(cls, v):
        if v is not None and (not v or not v.strip()):
            raise ValueError('职位不能为空')
        return v.strip() if v else v

    @field_validator('email', 'wechat_id')
    @classmethod
    def optional_text_empty_to_none(cls, v):
        if v is not None and not v.strip():
            return None
        return v.strip() if v else v


class ContactCreate(ContactBase):
    pass


class ContactUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=100, description="联系人姓名")
    gender: Optional[GenderEnum] = Field(None, description="性别")
    position: Optional[str] = Field(None, min_length=1, max_length=100, description="职务")
    is_decision_maker: Optional[bool] = Field(None, description="是否关键决策人")
    mobile: Optional[str] = Field(None, min_length=1, max_length=20, description="手机号")
    email: Optional[str] = Field(None, max_length=100, description="邮箱")
    wechat_id: Optional[str] = Field(None, max_length=100, description="微信ID")
    remark: Optional[str] = Field(None, description="备注")
    reports_to: Optional[int] = Field(None, description="汇报对象联系人ID")
    
    @field_validator('name')
    @classmethod
    def name_must_not_be_empty(cls, v):
        if v is not None and (not v or not v.strip()):
            raise ValueError('联系人姓名不能为空')
        return v.strip() if v else v
    
    @field_validator('mobile')
    @classmethod
    def mobile_must_not_be_empty(cls, v):
        if v is not None and (not v or not v.strip()):
            raise ValueError('手机号不能为空')
        return v.strip() if v else v

    @field_validator('position')
    @classmethod
    def position_must_not_be_empty(cls, v):
        if v is not None and (not v or not v.strip()):
            raise ValueError('职位不能为空')
        return v.strip() if v else v

    @field_validator('email', 'wechat_id')
    @classmethod
    def optional_text_empty_to_none(cls, v):
        if v is not None and not v.strip():
            return None
        return v.strip() if v else v


class ContactResponse(BaseModel):
    id: int = Field(..., description="联系人ID")
    customer_id: int = Field(..., description="关联客户ID")
    name: str = Field(..., description="联系人姓名")
    gender: Optional[int] = Field(None, description="性别：0:未知, 1:男, 2:女")
    position: Optional[str] = Field(None, description="职务")
    is_decision_maker: bool = Field(..., description="是否关键决策人")
    mobile: str = Field(..., description="手机号")
    email: Optional[str] = Field(None, description="邮箱")
    wechat_id: Optional[str] = Field(None, description="微信ID")
    remark: Optional[str] = Field(None, description="备注")
    reports_to: Optional[int] = Field(None, description="汇报对象联系人ID")
    is_primary: bool = Field(..., description="是否主要联系人")
    created_time: datetime = Field(..., description="创建时间")
    
    model_config = ConfigDict(from_attributes=True)


class CustomerBase(BaseModel):
    account_name: str = Field(..., min_length=1, max_length=255, description="客户公司名称（必填）")
    industry: Optional[str] = Field(None, max_length=100, description="所属行业（如：互联网、金融、制造等）")
    city: str = Field(..., min_length=1, max_length=100, description="所在城市（必填）")
    address: Optional[str] = Field(None, max_length=500, description="公司地址（详细地址）")
    company_scale: Optional[str] = Field(None, max_length=50, description="公司规模（如：1-50人、51-200人、201-500人、500+人）")
    source: Optional[CustomerSource] = Field(None, description="客户来源")
    
    @field_validator('account_name')
    @classmethod
    def account_name_must_not_be_empty(cls, v):
        if v is not None and (not v or not v.strip()):
            raise ValueError('客户公司名称不能为空')
        return v.strip() if v else v
    
    @field_validator('city')
    @classmethod
    def city_must_not_be_empty(cls, v):
        if v is not None and (not v or not v.strip()):
            raise ValueError('所在城市不能为空')
        return v.strip() if v else v


class CustomerCreate(CustomerBase):
    owner_id: Optional[str] = Field(None, description="负责人系统用户ID，不传则默认为创建人")
    default_procurement_method_id: Optional[int] = Field(None, description="默认采购方式ID")
    primary_contact: Optional[ContactCreate] = Field(None, description="创建客户时同步创建的主联系人")


class CustomerUpdate(BaseModel):
    account_name: Optional[str] = Field(None, min_length=1, max_length=255, description="客户公司名称")
    industry: Optional[str] = Field(None, max_length=100, description="所属行业")
    city: Optional[str] = Field(None, min_length=1, max_length=100, description="所在城市")
    address: Optional[str] = Field(None, max_length=500, description="公司地址")
    company_scale: Optional[str] = Field(None, max_length=50, description="公司规模")
    source: Optional[CustomerSource] = Field(None, description="客户来源")
    default_procurement_method_id: Optional[int] = Field(None, description="默认采购方式ID")

    @field_validator('account_name')
    @classmethod
    def account_name_must_not_be_empty(cls, v):
        if v is not None and (not v or not v.strip()):
            raise ValueError('客户公司名称不能为空')
        return v.strip() if v else v

    @field_validator('city')
    @classmethod
    def city_must_not_be_empty(cls, v):
        if v is not None and (not v or not v.strip()):
            raise ValueError('所在城市不能为空')
        return v.strip() if v else v


class CustomerStatusUpdate(BaseModel):
    status: int = Field(..., ge=0, le=3, description="客户状态：0跟进中, 1已成交, 2已输单, 3已沉寂")


class ConvertLeadToCustomer(BaseModel):
    lead_id: int = Field(..., description="线索ID")
    account_name: Optional[str] = Field(None, min_length=1, max_length=255, description="客户公司名称（可覆盖）")
    address: Optional[str] = Field(None, max_length=500, description="公司地址")
    default_procurement_method_id: Optional[int] = Field(None, description="默认采购方式ID")


class CustomerResponse(BaseModel):
    id: int = Field(..., description="客户ID（主键）")
    account_name: str = Field(..., description="客户公司名称")
    industry: Optional[str] = Field(None, description="所属行业（AI自动匹配）")
    city: str = Field(..., description="所在城市")
    address: Optional[str] = Field(None, description="公司地址")
    company_scale: Optional[str] = Field(None, description="公司规模")
    source: Optional[str] = Field(None, description="客户来源")
    status: int = Field(..., description="客户状态：0:跟进中, 1:已成交, 2:已输单, 3:已沉寂（公海）")
    owner_id: Optional[str] = Field(None, description="负责人系统用户ID（status=3时为空）")
    source_lead_id: Optional[int] = Field(None, description="来源线索ID（从线索转化而来时记录）")
    default_procurement_method_id: Optional[int] = Field(None, description="默认采购方式ID")
    loss_reason: Optional[str] = Field(None, description="输单原因（status=2时有值）")
    return_reason: Optional[str] = Field(None, description="退回公海原因（status=3时有值）")
    returned_time: Optional[datetime] = Field(None, description="退回公海时间（status=3时有值）")
    creator_id: str = Field(..., description="创建人系统用户ID")
    created_time: datetime = Field(..., description="创建时间")
    last_modified_time: datetime = Field(..., description="最后修改时间")
    version: int = Field(..., description="版本号（乐观锁，防止并发修改冲突）")
    # 档案字段
    company_background: Optional[str] = Field(None, description="企业背景")
    company_website: Optional[str] = Field(None, description="公司官网")
    main_business: Optional[str] = Field(None, description="主营业务")
    similar_customers: Optional[str] = Field(None, description="同行业客户")
    project_background: Optional[str] = Field(None, description="项目需求背景")
    profile_status: Optional[str] = Field(None, description="档案生成状态")
    profile_generated_time: Optional[datetime] = Field(None, description="档案生成完成时间")
    profile_error_message: Optional[str] = Field(None, description="档案生成失败原因")
    # 热力值字段
    score: Optional[int] = Field(None, description="热力值分数（0-100）")
    score_updated_at: Optional[datetime] = Field(None, description="热力值最后更新时间")
    # License 授权字段
    license_expiry_date: Optional[date] = Field(None, description="客户 License 最晚到期时间")
    license_type: Optional[str] = Field(None, description="客户 License 类型：TRIAL/OFFICIAL")

    model_config = ConfigDict(from_attributes=True)


class OwnerInfo(BaseModel):
    id: str = Field(..., description="系统用户ID")
    name: str = Field(..., description="用户姓名")
    avatar_url: Optional[str] = Field(None, description="用户头像URL")
    
    model_config = ConfigDict(from_attributes=True)


class CustomerMemberRole(str, Enum):
    SALES = "SALES"
    PRESALES = "PRESALES"
    DELIVERY = "DELIVERY"
    SUPPORT = "SUPPORT"
    OTHER = "OTHER"


class CustomerMemberAccessLevel(str, Enum):
    VIEW = "VIEW"
    FOLLOW_UP = "FOLLOW_UP"
    EDIT = "EDIT"


class CustomerMemberCreate(BaseModel):
    user_id: str = Field(..., min_length=1, description="成员系统用户ID")
    member_role: CustomerMemberRole = Field(CustomerMemberRole.PRESALES, description="成员角色")
    access_level: CustomerMemberAccessLevel = Field(CustomerMemberAccessLevel.VIEW, description="访问级别")
    remark: Optional[str] = Field(None, max_length=500, description="备注")

    @field_validator('user_id')
    @classmethod
    def user_id_must_be_numeric(cls, v):
        if not v or not v.strip().isdigit():
            raise ValueError('成员ID无效')
        return v.strip()


class CustomerMemberUpdate(BaseModel):
    member_role: Optional[CustomerMemberRole] = Field(None, description="成员角色")
    access_level: Optional[CustomerMemberAccessLevel] = Field(None, description="访问级别")
    remark: Optional[str] = Field(None, max_length=500, description="备注")


class CustomerMemberUserInfo(BaseModel):
    id: str = Field(..., description="系统用户ID")
    name: str = Field(..., description="用户姓名")
    avatar_url: Optional[str] = Field(None, description="用户头像URL")


class CustomerMemberResponse(BaseModel):
    id: int = Field(..., description="成员记录ID")
    customer_id: int = Field(..., description="客户ID")
    user_id: str = Field(..., description="成员系统用户ID")
    member_role: str = Field(..., description="成员角色")
    access_level: str = Field(..., description="访问级别")
    remark: Optional[str] = Field(None, description="备注")
    created_by: str = Field(..., description="创建人")
    created_time: datetime = Field(..., description="创建时间")
    updated_time: datetime = Field(..., description="更新时间")
    user_info: Optional[CustomerMemberUserInfo] = Field(None, description="成员用户信息")
    can_manage: bool = Field(False, description="当前用户是否可管理成员")

    model_config = ConfigDict(from_attributes=True)


class CustomerMemberCandidate(BaseModel):
    id: str = Field(..., description="系统用户ID")
    name: str = Field(..., description="用户姓名")
    avatar_url: Optional[str] = Field(None, description="用户头像URL")
    roles: List[str] = Field(default_factory=list, description="团队角色编码")
    already_member: bool = Field(False, description="是否已是该客户成员")


class CustomerListResponse(CustomerResponse):
    industry_info: Optional[CustomerIndustryInfo] = Field(None, description="行业信息")
    owner_info: Optional[OwnerInfo] = Field(None, description="负责人信息")
    collaborator_infos: List[OwnerInfo] = Field(default_factory=list, description="协作者信息")
    creator_info: Optional[OwnerInfo] = Field(None, description="创建人信息")
    default_procurement_method_info: Optional[ProcurementMethodInfo] = Field(None, description="默认采购方式信息")


class CustomerDetailResponse(BaseModel):
    id: int
    account_name: str
    industry: Optional[str] = None
    industry_info: Optional[CustomerIndustryInfo] = Field(None, description="行业信息")
    city: str
    address: Optional[str] = None
    company_scale: Optional[str] = None
    source: Optional[str] = None
    status: int
    owner_id: Optional[str] = None
    source_lead_id: Optional[int] = None
    default_procurement_method_id: Optional[int] = None
    default_procurement_method_info: Optional[ProcurementMethodInfo] = Field(None, description="默认采购方式信息")
    loss_reason: Optional[str] = None
    return_reason: Optional[str] = None
    returned_time: Optional[datetime] = None
    creator_id: str
    created_time: datetime
    last_modified_time: datetime
    version: int
    contacts: List[ContactResponse] = []
    owner_info: Optional[OwnerInfo] = Field(None, description="负责人信息")
    creator_info: Optional[OwnerInfo] = Field(None, description="创建人信息")
    # 档案字段
    company_background: Optional[str] = None
    company_website: Optional[str] = None
    main_business: Optional[str] = None
    similar_customers: Optional[str] = None
    project_background: Optional[str] = None
    profile_status: Optional[str] = None
    profile_generated_time: Optional[datetime] = None
    profile_error_message: Optional[str] = None
    # 客户概况字段
    customer_brief_json: Optional[str] = None
    customer_brief_markdown: Optional[str] = None
    customer_brief_citations: Optional[str] = None
    customer_brief_status: Optional[str] = None
    customer_brief_generated_time: Optional[datetime] = None
    customer_brief_error_message: Optional[str] = None
    customer_intelligence_has_inputs: bool = Field(False, description="是否存在可用于整理客户智能档案的业务输入")
    # 热力值字段
    score: Optional[int] = Field(None, description="热力值分数（0-100）")
    score_updated_at: Optional[datetime] = Field(None, description="热力值最后更新时间")
    # License 授权字段
    license_expiry_date: Optional[date] = Field(None, description="客户 License 最晚到期时间")
    license_type: Optional[str] = Field(None, description="客户 License 类型：TRIAL/OFFICIAL")

    model_config = ConfigDict(from_attributes=True)


class ConvertResponse(BaseModel):
    customer_id: int = Field(..., description="创建的客户ID")
    contact_id: int = Field(..., description="创建的联系人ID")
    message: str = Field(..., description="响应消息")


class MessageResponse(BaseModel):
    message: str = Field(..., description="响应消息")


class CustomerIntelligenceBatchRebuildRequest(BaseModel):
    scope: Literal["full", "brief"] = Field("full", description="重建范围：full=客户档案和客户概况，brief=客户概况")
    customer_ids: Optional[List[int]] = Field(None, description="指定客户ID；为空时按团队批量重建")
    limit: int = Field(100, ge=1, le=500, description="本次最多调度的客户数")


class CustomerIntelligenceBatchRebuildResponse(BaseModel):
    message: str = Field(..., description="响应消息")
    request_id: str = Field(..., description="批量重建请求ID")
    scope: Literal["full", "brief"] = Field(..., description="重建范围")
    total: int = Field(..., description="匹配客户数")
    scheduled: int = Field(..., description="已调度客户数")
    customer_ids: List[int] = Field(..., description="已调度的客户ID")


class CustomerIntelligenceRunDiagnosticResponse(BaseModel):
    id: int = Field(..., description="运行记录ID")
    request_id: str = Field(..., description="请求ID")
    customer_id: int = Field(..., description="客户ID")
    actor_id: Optional[str] = Field(None, description="触发人ID")
    trigger_type: str = Field(..., description="触发类型")
    scope: str = Field(..., description="刷新范围")
    status: str = Field(..., description="运行状态")
    attempt_count: int = Field(..., description="已尝试次数")
    max_attempts: int = Field(..., description="最大尝试次数")
    route_label: Optional[str] = Field(None, description="运行类型")
    result: JsonObject = Field(default_factory=dict, description="运行结果摘要")
    visible_trace: List[JsonObject] = Field(default_factory=list, description="用户可见执行轨迹")
    trace_events: List[JsonObject] = Field(default_factory=list, description="可回放执行事件")
    error_message: Optional[str] = Field(None, description="错误信息")
    created_time: Optional[datetime] = Field(None, description="创建时间")
    started_time: Optional[datetime] = Field(None, description="开始时间")
    finished_time: Optional[datetime] = Field(None, description="结束时间")
    next_retry_at: Optional[datetime] = Field(None, description="下次重试时间")
    last_duration_ms: Optional[int] = Field(None, description="最近一次运行耗时毫秒")


class CustomerIntelligenceRunDiagnosticListResponse(BaseModel):
    items: List[CustomerIntelligenceRunDiagnosticResponse] = Field(default_factory=list, description="运行诊断列表")
    total: int = Field(..., description="返回数量")
    limit: int = Field(..., description="查询限制")


class CustomerIntelligenceRetryDueResponse(BaseModel):
    success: bool = Field(..., description="是否调度成功")
    total: int = Field(..., description="本次处理数量")
    succeeded: int = Field(..., description="成功数量")
    failed: int = Field(..., description="失败数量")
    results: List[JsonObject] = Field(default_factory=list, description="重试结果")


class StatisticsResponse(BaseModel):
    total: int = Field(..., description="总客户数")
    following: int = Field(..., description="跟进中客户数")
    won: int = Field(..., description="已成交客户数")
    lost: int = Field(..., description="已输单客户数")
    inactive: int = Field(..., description="已沉寂客户数")


class TrendResponse(BaseModel):
    date: str = Field(..., description="日期")
    count: int = Field(..., description="数量")


class CustomerReturnRequest(BaseModel):
    return_reason: ReturnReasonEnum = Field(..., description="退回公海原因")
    detailed_reason: Optional[str] = Field(None, max_length=500, description="详细原因说明")
    
    @field_validator('detailed_reason')
    @classmethod
    def detailed_reason_must_not_be_empty(cls, v):
        if v is not None and (not v or not v.strip()):
            raise ValueError('详细原因不能为空')
        return v.strip() if v else v


class CustomerReturnResponse(BaseModel):
    customer_id: int = Field(..., description="客户ID")
    previous_owner: str = Field(..., description="原负责人姓名")
    returned_time: datetime = Field(..., description="退回时间")
    return_reason: str = Field(..., description="退回原因")
    message: str = Field(..., description="响应消息")


class CustomerClaimRequest(BaseModel):
    owner_id: str = Field(..., min_length=1, description="新负责人系统用户ID")
    
    @field_validator('owner_id')
    @classmethod
    def owner_id_must_not_be_empty(cls, v):
        if not v or not v.strip():
            raise ValueError('负责人ID不能为空')
        return v


class CustomerAssignRequest(BaseModel):
    owner_id: str = Field(..., min_length=1, description="被分配人（负责人）系统用户ID")
    opportunity_transfer_scope: Literal["none", "following", "all"] = Field(
        "none",
        description="关联商机移交范围：none=仅客户，following=跟进中商机，all=全部商机；移交商机会同步移交关联合同"
    )
    remark: Optional[str] = Field(None, max_length=500, description="分配备注（说明分配原因等）")
    
    @field_validator('owner_id')
    @classmethod
    def owner_id_must_not_be_empty(cls, v):
        if not v or not v.strip():
            raise ValueError('负责人ID不能为空')
        return v


class CustomerAssignResponse(BaseModel):
    customer: CustomerResponse = Field(..., description="移交后的客户信息")
    transferred_opportunities: int = Field(..., description="已同步移交的商机数量")
    transferred_contracts: int = Field(..., description="已同步移交的合同数量")
    message: str = Field(..., description="响应消息")


class OwnerOption(BaseModel):
    id: str = Field(..., description="系统用户ID")
    name: str = Field(..., description="用户姓名")
    is_me: bool = Field(False, description="是否为当前用户")


class OwnerListResponse(BaseModel):
    data: List[OwnerOption] = Field(..., description="负责人选项列表")


class CustomerLoseRequest(BaseModel):
    loss_reason: str = Field(..., min_length=1, max_length=500, description="输单原因（必填）")

    @field_validator('loss_reason')
    @classmethod
    def loss_reason_must_not_be_empty(cls, v):
        if not v or not v.strip():
            raise ValueError('输单原因不能为空')
        return v.strip()
