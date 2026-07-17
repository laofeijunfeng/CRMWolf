from pydantic import BaseModel, Field, field_validator, ConfigDict
from typing import Optional, List
from datetime import date, datetime
from enum import Enum
import enum


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
    gender: Optional[GenderEnum] = Field(None, description="性别：0:未知, 1:男, 2:女")
    position: Optional[str] = Field(None, max_length=100, description="职务（如：CTO、采购经理等）")
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


class ContactCreate(ContactBase):
    pass


class ContactUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=100, description="联系人姓名")
    gender: Optional[GenderEnum] = Field(None, description="性别")
    position: Optional[str] = Field(None, max_length=100, description="职务")
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


class CustomerUpdate(BaseModel):
    account_name: Optional[str] = Field(None, min_length=1, max_length=255, description="客户公司名称")
    industry: Optional[str] = Field(None, max_length=100, description="所属行业")
    city: Optional[str] = Field(None, min_length=1, max_length=100, description="所在城市")
    address: Optional[str] = Field(None, max_length=500, description="公司地址")
    company_scale: Optional[str] = Field(None, max_length=50, description="公司规模")
    source: Optional[CustomerSource] = Field(None, description="客户来源")
    default_procurement_method_id: Optional[int] = Field(None, description="默认采购方式ID")
    # 档案字段（支持编辑）
    company_background: Optional[str] = Field(None, description="企业背景")
    company_website: Optional[str] = Field(None, description="公司官网")
    main_business: Optional[str] = Field(None, description="主营业务")
    project_background: Optional[str] = Field(None, description="项目需求背景")

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


class CustomerListResponse(CustomerResponse):
    industry_info: Optional[CustomerIndustryInfo] = Field(None, description="行业信息")
    owner_info: Optional[OwnerInfo] = Field(None, description="负责人信息")
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
    remark: Optional[str] = Field(None, max_length=500, description="分配备注（说明分配原因等）")
    
    @field_validator('owner_id')
    @classmethod
    def owner_id_must_not_be_empty(cls, v):
        if not v or not v.strip():
            raise ValueError('负责人ID不能为空')
        return v


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
