import enum
from datetime import date, datetime
from enum import Enum
from typing import Any, Literal, Self, TypeVar

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.schemas.acquisition_source import AcquisitionSourceInfo
from app.schemas.product import ProductIntentRef

JsonObject = dict[str, object]


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
    primary_code: str | None = None
    primary_name: str | None = None
    secondary_name: str | None = None


class ProcurementMethodInfo(BaseModel):
    """采购方式简要信息"""
    id: int = Field(..., description="采购方式ID")
    code: str = Field(..., description="采购方式编码")
    name: str = Field(..., description="采购方式名称")
    is_active: int = Field(..., description="是否启用\uff1a1=启用, 0=停用")


class CustomerSource(str, enum.Enum):
    ONLINE_REGISTER = "线上注册"
    MARKETING_ACTIVITY = "市场活动"
    REFERRAL = "客户推荐"
    COLD_CALL = "电话营销"
    WEBSITE_INQUIRY = "网站咨询"
    EXHIBITION = "展会"
    OTHER = "其他"


class CustomerStatusEnum(str, Enum):
    FOLLOWING = "0"
    WON = "1"
    LOST = "2"
    INACTIVE = "3"
    
    @property
    def description(self) -> str:
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
    def description(self) -> str:
        return self.value


class GenderEnum(str, Enum):
    UNKNOWN = "0"
    MALE = "1"
    FEMALE = "2"
    
    @property
    def description(self) -> str:
        descriptions = {
            "0": "未知",
            "1": "男",
            "2": "女"
        }
        return descriptions.get(self.value, self.value)


class ContactBase(BaseModel):
    name: str = Field(..., min_length=1, max_length=100, description="联系人姓名")
    gender: GenderEnum = Field(..., description="性别\uff1a1:男, 2:女")
    position: str = Field(..., min_length=1, max_length=100, description="职务\uff08如\uff1aCTO、采购经理等\uff09")
    is_decision_maker: bool = Field(False, description="是否关键决策人\uff08影响销售策略\uff09")
    mobile: str = Field(..., min_length=1, max_length=20, description="手机号\uff08必填\uff0c主要联系方式\uff09")
    email: str | None = Field(None, max_length=100, description="邮箱地址")
    wechat_id: str | None = Field(None, max_length=100, description="微信ID\uff08用于微信沟通\uff09")
    remark: str | None = Field(None, description="备注信息\uff08如\uff1a沟通偏好、最佳联系时间等\uff09")
    reports_to: int | None = Field(None, description="汇报对象联系人ID\uff08用于建立组织架构\uff09")
    
    @field_validator('name')
    @classmethod
    def name_must_not_be_empty(cls, v: str) -> str:
        if v is not None and (not v or not v.strip()):
            raise ValueError('联系人姓名不能为空')
        return v.strip() if v else v
    
    @field_validator('mobile')
    @classmethod
    def mobile_must_not_be_empty(cls, v: str) -> str:
        if v is not None and (not v or not v.strip()):
            raise ValueError('手机号不能为空')
        return v.strip() if v else v

    @field_validator('position')
    @classmethod
    def position_must_not_be_empty(cls, v: str) -> str:
        if v is not None and (not v or not v.strip()):
            raise ValueError('职位不能为空')
        return v.strip() if v else v

    @field_validator('email', 'wechat_id')
    @classmethod
    def optional_text_empty_to_none(cls, v: str | None) -> str | None:
        if v is not None and not v.strip():
            return None
        return v.strip() if v else v


class ContactCreate(ContactBase):
    pass


class ContactUpdate(BaseModel):
    name: str | None = Field(None, min_length=1, max_length=100, description="联系人姓名")
    gender: GenderEnum | None = Field(None, description="性别")
    position: str | None = Field(None, min_length=1, max_length=100, description="职务")
    is_decision_maker: bool | None = Field(None, description="是否关键决策人")
    mobile: str | None = Field(None, min_length=1, max_length=20, description="手机号")
    email: str | None = Field(None, max_length=100, description="邮箱")
    wechat_id: str | None = Field(None, max_length=100, description="微信ID")
    remark: str | None = Field(None, description="备注")
    reports_to: int | None = Field(None, description="汇报对象联系人ID")
    
    @field_validator('name')
    @classmethod
    def name_must_not_be_empty(cls, v: str | None) -> str | None:
        if v is not None and (not v or not v.strip()):
            raise ValueError('联系人姓名不能为空')
        return v.strip() if v else v
    
    @field_validator('mobile')
    @classmethod
    def mobile_must_not_be_empty(cls, v: str | None) -> str | None:
        if v is not None and (not v or not v.strip()):
            raise ValueError('手机号不能为空')
        return v.strip() if v else v

    @field_validator('position')
    @classmethod
    def position_must_not_be_empty(cls, v: str | None) -> str | None:
        if v is not None and (not v or not v.strip()):
            raise ValueError('职位不能为空')
        return v.strip() if v else v

    @field_validator('email', 'wechat_id')
    @classmethod
    def optional_text_empty_to_none(cls, v: str | None) -> str | None:
        if v is not None and not v.strip():
            return None
        return v.strip() if v else v


class ContactResponse(BaseModel):
    id: int = Field(..., description="联系人ID")
    customer_id: str = Field(..., description="关联客户对外ID")
    name: str = Field(..., description="联系人姓名")
    gender: int | None = Field(None, description="性别\uff1a0:未知, 1:男, 2:女")
    position: str | None = Field(None, description="职务")
    is_decision_maker: bool = Field(..., description="是否关键决策人")
    mobile: str = Field(..., description="手机号")
    email: str | None = Field(None, description="邮箱")
    wechat_id: str | None = Field(None, description="微信ID")
    remark: str | None = Field(None, description="备注")
    reports_to: int | None = Field(None, description="汇报对象联系人ID")
    is_primary: bool = Field(..., description="是否主要联系人")
    created_time: datetime = Field(..., description="创建时间")
    
    model_config = ConfigDict(from_attributes=True)


class CustomerBase(BaseModel):
    account_name: str = Field(..., min_length=1, max_length=255, description="客户公司名称\uff08必填\uff09")
    industry: str | None = Field(None, max_length=100, description="所属行业\uff08如\uff1a互联网、金融、制造等\uff09")
    city: str = Field(..., min_length=1, max_length=100, description="所在城市\uff08必填\uff09")
    address: str | None = Field(None, max_length=500, description="公司地址\uff08详细地址\uff09")
    company_scale: str | None = Field(
        None, max_length=50,
        description="公司规模\uff08如\uff1a1-50人、51-200人、201-500人、500+人\uff09",
    )
    source: str | None = Field(None, max_length=50, description="获客来源名称\uff08兼容\uff09")
    source_public_id: str | None = Field(None, description="获客来源对外ID")
    
    @field_validator('account_name')
    @classmethod
    def account_name_must_not_be_empty(cls, v: str) -> str:
        if v is not None and (not v or not v.strip()):
            raise ValueError('客户公司名称不能为空')
        return v.strip() if v else v
    
    @field_validator('city')
    @classmethod
    def city_must_not_be_empty(cls, v: str) -> str:
        if v is not None and (not v or not v.strip()):
            raise ValueError('所在城市不能为空')
        return v.strip() if v else v


CustomerLifecycleStatus = Literal[0, 1]
CustomerLicenseType = Literal["TRIAL", "OFFICIAL"]
_AUTHORIZED_USERS_MESSAGE = "请输入大于 0 的整数"
_AUTHORIZED_USERS_MAX = 2_147_483_647
LICENSE_TYPE_REQUIRED_MESSAGE = "授权到期日期不为空时必须选择授权类型"
PERMANENT_REQUIRES_OFFICIAL_MESSAGE = "试用授权必须填写到期日\uff0c不能设为永久。"


def _validate_license_authorized_users(value: object) -> int | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(_AUTHORIZED_USERS_MESSAGE)
    if value < 1 or value > _AUTHORIZED_USERS_MAX:
        raise ValueError(_AUTHORIZED_USERS_MESSAGE)
    return value


class CustomerLicensePermanentError(ValueError):
    """A permanent customer License was requested for a non-OFFICIAL type."""


_LicenseTypeT = TypeVar("_LicenseTypeT", bound=str)


def normalize_customer_license_pair(
    license_type: _LicenseTypeT | None,
    license_expiry_date: date | None,
    license_is_permanent: bool | None,
) -> tuple[_LicenseTypeT | None, date | None, bool]:
    """Normalize a customer License snapshot to (type, expiry, permanent).

    Permanent ⇒ OFFICIAL with no expiry date. Otherwise a missing date clears the
    type and a present date requires a type.
    """
    if license_is_permanent:
        if license_type != "OFFICIAL":
            raise CustomerLicensePermanentError(PERMANENT_REQUIRES_OFFICIAL_MESSAGE)
        return license_type, None, True
    if license_expiry_date is None:
        return None, None, False
    if license_type is None:
        raise ValueError(LICENSE_TYPE_REQUIRED_MESSAGE)
    return license_type, license_expiry_date, False


class CustomerCreate(CustomerBase):
    status: CustomerLifecycleStatus = Field(0, description="客户快捷状态\uff1a0跟进中\uff0c1已成交")
    license_type: CustomerLicenseType | None = Field(None, description="客户 License 类型\uff1aTRIAL/OFFICIAL")
    license_expiry_date: date | None = Field(None, description="客户 License 最晚到期时间")
    license_is_permanent: bool | None = Field(None, description="客户 License 是否永久\uff08仅正式\uff09")
    license_authorized_users: int | None = Field(None, description="客户 License 授权人数")
    owner_id: str | None = Field(None, description="负责人系统用户ID\uff0c不传则默认为创建人")
    default_procurement_method_id: int | None = Field(None, description="默认采购方式ID")
    primary_contact: ContactCreate | None = Field(None, description="创建客户时同步创建的主联系人")
    product_public_id: str = Field(..., min_length=1, description="意向产品对外ID")

    @model_validator(mode="before")
    @classmethod
    def product_public_id_must_be_present_before(cls, data: object) -> object:
        if not isinstance(data, dict):
            return data
        value = data.get("product_public_id")
        if value is None or not str(value).strip():
            raise ValueError("缺少产品")
        data["product_public_id"] = str(value).strip()
        return data

    @field_validator("product_public_id")
    @classmethod
    def product_public_id_must_be_present(cls, v: str) -> str:
        if not v or not str(v).strip():
            raise ValueError("缺少产品")
        return v.strip()

    @field_validator("license_authorized_users", mode="before")
    @classmethod
    def license_authorized_users_must_be_positive_integer(cls, value: object) -> int | None:
        return _validate_license_authorized_users(value)

    @model_validator(mode="after")
    def normalize_license_pair(self) -> Self:
        self.license_type, self.license_expiry_date, self.license_is_permanent = (
            normalize_customer_license_pair(
                self.license_type, self.license_expiry_date, self.license_is_permanent
            )
        )
        return self


class CustomerUpdate(BaseModel):
    expected_version: int | None = Field(
        None,
        ge=1,
        description="客户端读取到的客户版本号\uff08用于乐观锁\uff0c未传入时保持兼容行为\uff09",
    )
    account_name: str | None = Field(None, min_length=1, max_length=255, description="客户公司名称")
    industry: str | None = Field(None, max_length=100, description="所属行业")
    city: str | None = Field(None, min_length=1, max_length=100, description="所在城市")
    address: str | None = Field(None, max_length=500, description="公司地址")
    company_scale: str | None = Field(None, max_length=50, description="公司规模")
    source: str | None = Field(None, max_length=50, description="获客来源名称\uff08兼容\uff09")
    source_public_id: str | None = Field(None, description="获客来源对外ID")
    default_procurement_method_id: int | None = Field(None, description="默认采购方式ID")
    status: CustomerLifecycleStatus | None = Field(None, description="客户快捷状态\uff1a0跟进中\uff0c1已成交")
    license_type: CustomerLicenseType | None = Field(None, description="客户 License 类型\uff1aTRIAL/OFFICIAL")
    license_expiry_date: date | None = Field(None, description="客户 License 最晚到期时间")
    license_is_permanent: bool | None = Field(None, description="客户 License 是否永久\uff08仅正式\uff09")
    license_authorized_users: int | None = Field(None, description="客户 License 授权人数")
    product_public_id: str | None = Field(None, description="意向产品对外ID")

    @field_validator('account_name')
    @classmethod
    def account_name_must_not_be_empty(cls, v: str | None) -> str | None:
        if v is not None and (not v or not v.strip()):
            raise ValueError('客户公司名称不能为空')
        return v.strip() if v else v

    @field_validator('city')
    @classmethod
    def city_must_not_be_empty(cls, v: str | None) -> str | None:
        if v is not None and (not v or not v.strip()):
            raise ValueError('所在城市不能为空')
        return v.strip() if v else v

    @field_validator("license_authorized_users", mode="before")
    @classmethod
    def license_authorized_users_must_be_positive_integer(cls, value: object) -> int | None:
        return _validate_license_authorized_users(value)


class CustomerStatusUpdate(BaseModel):
    status: int = Field(..., ge=0, le=3, description="客户状态\uff1a0跟进中, 1已成交, 2已输单, 3已沉寂")


class CustomerLifecycleStatusUpdate(BaseModel):
    status: Literal[0, 1] = Field(..., description="客户快捷状态\uff1a0跟进中\uff0c1已成交")
    expected_version: int = Field(..., ge=1, description="客户端读取到的客户版本号")


class CustomerLicenseSnapshotUpdate(BaseModel):
    expected_version: int = Field(..., ge=1)
    license_type: Literal["TRIAL", "OFFICIAL"] | None = None
    license_expiry_date: date | None = None
    license_is_permanent: bool | None = None

    @model_validator(mode="after")
    def normalize_license_pair(self) -> Self:
        self.license_type, self.license_expiry_date, self.license_is_permanent = (
            normalize_customer_license_pair(
                self.license_type, self.license_expiry_date, self.license_is_permanent
            )
        )
        return self


class ConvertLeadToCustomer(BaseModel):
    lead_id: str = Field(..., description="线索对外ID")
    account_name: str | None = Field(None, min_length=1, max_length=255, description="客户公司名称\uff08可覆盖\uff09")
    address: str | None = Field(None, max_length=500, description="公司地址")
    default_procurement_method_id: int | None = Field(None, description="默认采购方式ID")
    contact_name: str | None = Field(
        None,
        min_length=1,
        max_length=100,
        description="主联系人姓名\uff08兼容旧转化入口\uff09",
    )
    contact_phone: str | None = Field(
        None,
        min_length=1,
        max_length=20,
        description="主联系人手机\uff08兼容旧转化入口\uff09",
    )
    industry: str | None = Field(None, max_length=100, description="客户行业\uff08兼容旧转化入口\uff09")
    product_public_id: str | None = Field(None, description="意向产品对外ID")


class CustomerResponse(BaseModel):
    id: str = Field(..., validation_alias="public_id", description="客户对外ID")
    public_id: str = Field(..., description="客户对外ID")
    account_name: str = Field(..., description="客户公司名称")
    industry: str | None = Field(None, description="所属行业\uff08AI自动匹配\uff09")
    city: str = Field(..., description="所在城市")
    address: str | None = Field(None, description="公司地址")
    company_scale: str | None = Field(None, description="公司规模")
    source: str | None = Field(None, description="获客来源当前名称")
    source_info: AcquisitionSourceInfo | None = Field(None, description="获客来源对象")
    status: int = Field(..., description="客户状态\uff1a0:跟进中, 1:已成交, 2:已输单, 3:已沉寂\uff08公海\uff09")
    owner_id: str | None = Field(None, description="负责人系统用户ID\uff08status=3时为空\uff09")
    source_lead_id: str | None = Field(None, description="来源线索对外ID\uff08从线索转化而来时记录\uff09")
    default_procurement_method_id: int | None = Field(None, description="默认采购方式ID")
    loss_reason: str | None = Field(None, description="输单原因\uff08status=2时有值\uff09")
    return_reason: str | None = Field(None, description="退回公海原因\uff08status=3时有值\uff09")
    returned_time: datetime | None = Field(None, description="退回公海时间\uff08status=3时有值\uff09")
    creator_id: str = Field(..., description="创建人系统用户ID")
    created_time: datetime = Field(..., description="创建时间")
    last_modified_time: datetime = Field(..., description="最后修改时间")
    version: int = Field(..., description="版本号\uff08乐观锁\uff0c防止并发修改冲突\uff09")
    # License 授权字段
    license_expiry_date: date | None = Field(None, description="客户 License 最晚到期时间")
    license_is_permanent: bool = Field(False, description="客户 License 是否永久")
    license_authorized_users: int | None = Field(None, description="客户 License 授权人数")
    license_type: str | None = Field(None, description="客户 License 类型\uff1aTRIAL/OFFICIAL")
    product_public_id: str | None = Field(None, description="意向产品对外ID")
    product_name: str | None = Field(None, description="意向产品名称")
    products: list[ProductIntentRef] = Field(default_factory=list, description="意向产品列表")
    derived_status: str | None = Field(
        None,
        description=(
            "派生客户状态: not_started未启动/following跟进中/repurchasing复购中/"
            "won已成交/lost已流失/public_pool公海"
        ),
    )
    derived_status_label: str | None = Field(None, description="派生客户状态中文标签")
    derived_stage_hint: str | None = Field(
        None, description="进行中旅程进展小字,如「新购 · 初期交流」;终态为空"
    )

    model_config = ConfigDict(from_attributes=True)


class OwnerInfo(BaseModel):
    id: str = Field(..., description="系统用户ID")
    name: str = Field(..., description="用户姓名")
    avatar_url: str | None = Field(None, description="用户头像URL")
    
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
    remark: str | None = Field(None, max_length=500, description="备注")

    @field_validator('user_id')
    @classmethod
    def user_id_must_be_numeric(cls, v: str) -> str:
        if not v or not v.strip().isdigit():
            raise ValueError('成员ID无效')
        return v.strip()


class CustomerMemberUpdate(BaseModel):
    member_role: CustomerMemberRole | None = Field(None, description="成员角色")
    access_level: CustomerMemberAccessLevel | None = Field(None, description="访问级别")
    remark: str | None = Field(None, max_length=500, description="备注")


class CustomerMemberUserInfo(BaseModel):
    id: str = Field(..., description="系统用户ID")
    name: str = Field(..., description="用户姓名")
    avatar_url: str | None = Field(None, description="用户头像URL")


class CustomerMemberResponse(BaseModel):
    id: int = Field(..., description="成员记录ID")
    customer_id: str = Field(..., description="客户对外ID")
    user_id: str = Field(..., description="成员系统用户ID")
    member_role: str = Field(..., description="成员角色")
    access_level: str = Field(..., description="访问级别")
    remark: str | None = Field(None, description="备注")
    created_by: str = Field(..., description="创建人")
    created_time: datetime = Field(..., description="创建时间")
    updated_time: datetime = Field(..., description="更新时间")
    user_info: CustomerMemberUserInfo | None = Field(None, description="成员用户信息")
    can_manage: bool = Field(False, description="当前用户是否可管理成员")

    model_config = ConfigDict(from_attributes=True)


class CustomerMemberCandidate(BaseModel):
    id: str = Field(..., description="系统用户ID")
    name: str = Field(..., description="用户姓名")
    avatar_url: str | None = Field(None, description="用户头像URL")
    roles: list[str] = Field(default_factory=list, description="团队角色编码")
    already_member: bool = Field(False, description="是否已是该客户成员")


class CustomerListResponse(CustomerResponse):
    industry_info: CustomerIndustryInfo | None = Field(None, description="行业信息")
    owner_info: OwnerInfo | None = Field(None, description="负责人信息")
    collaborator_infos: list[OwnerInfo] = Field(default_factory=list, description="协作者信息")
    creator_info: OwnerInfo | None = Field(None, description="创建人信息")
    default_procurement_method_info: ProcurementMethodInfo | None = Field(None, description="默认采购方式信息")
    primary_contact_name: str | None = Field(None, description="主要联系人姓名")
    primary_contact_mobile: str | None = Field(None, description="主要联系人电话")
    derived_status: str | None = Field(
        None,
        description=(
            "派生客户状态: not_started未启动/following跟进中/repurchasing复购中/"
            "won已成交/lost已流失/public_pool公海"
        ),
    )
    derived_status_label: str | None = Field(None, description="派生客户状态中文标签")
    derived_stage_hint: str | None = Field(
        None, description="进行中旅程进展小字,如「新购 · 初期交流」;终态为空"
    )

class CustomerIdentityCandidateResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    account_name: str
    city: str | None = None
    match: JsonObject = Field(default_factory=dict)


class CustomerIdentityResolutionResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    decision: Literal[
        "auto_select",
        "ranked_auto_selectable",
        "requires_confirmation",
        "no_match",
        "semantic_related_only",
    ]
    items: list[CustomerIdentityCandidateResponse] = Field(default_factory=list)
    related_customers: list[CustomerIdentityCandidateResponse] = Field(default_factory=list)
    metadata: JsonObject = Field(default_factory=dict)


class CustomerDetailResponse(BaseModel):
    id: str = Field(..., validation_alias="public_id")
    public_id: str
    account_name: str
    industry: str | None = None
    industry_info: CustomerIndustryInfo | None = Field(None, description="行业信息")
    city: str
    address: str | None = None
    company_scale: str | None = None
    source: str | None = None
    source_info: AcquisitionSourceInfo | None = None
    status: int
    owner_id: str | None = None
    source_lead_id: str | None = None
    default_procurement_method_id: int | None = None
    default_procurement_method_info: ProcurementMethodInfo | None = Field(None, description="默认采购方式信息")
    loss_reason: str | None = None
    return_reason: str | None = None
    returned_time: datetime | None = None
    creator_id: str
    created_time: datetime
    last_modified_time: datetime
    version: int
    contacts: list[ContactResponse] = []
    owner_info: OwnerInfo | None = Field(None, description="负责人信息")
    creator_info: OwnerInfo | None = Field(None, description="创建人信息")
    customer_intelligence_has_inputs: bool = Field(False, description="是否存在可用于整理客户智能档案的业务输入")
    # License 授权字段
    license_expiry_date: date | None = Field(None, description="客户 License 最晚到期时间")
    license_is_permanent: bool = Field(False, description="客户 License 是否永久")
    license_authorized_users: int | None = Field(None, description="客户 License 授权人数")
    license_type: str | None = Field(None, description="客户 License 类型\uff1aTRIAL/OFFICIAL")
    product_public_id: str | None = Field(None, description="意向产品对外ID")
    product_name: str | None = Field(None, description="意向产品名称")
    products: list[ProductIntentRef] = Field(default_factory=list, description="意向产品列表")
    derived_status: str | None = Field(
        None,
        description=(
            "派生客户状态: not_started未启动/following跟进中/repurchasing复购中/"
            "won已成交/lost已流失/public_pool公海"
        ),
    )
    derived_status_label: str | None = Field(None, description="派生客户状态中文标签")
    derived_stage_hint: str | None = Field(
        None, description="进行中旅程进展小字,如「新购 · 初期交流」;终态为空"
    )

    model_config = ConfigDict(from_attributes=True)


class ConvertResultData(BaseModel):
    """线索转客户成功后的业务事实摘要。"""

    lead_id: str = Field(..., description="已转化线索对外ID")
    converted_lead_id: str = Field(..., description="已转化线索对外ID\uff08兼容字段\uff09")
    customer_id: str = Field(..., description="创建或复用客户的对外ID")
    customer_public_id: str = Field(..., description="客户对外ID")
    contact_id: int = Field(..., description="创建或复用主联系人的内部ID\uff08兼容字段\uff09")
    contact_public_id: str | None = Field(None, description="主联系人对外ID\uff1b旧数据暂无时为空")
    message: str = Field(..., description="响应消息")
    created_customer: bool = Field(..., description="是否新建客户")
    created_contact: bool = Field(..., description="是否新建主联系人")
    inherited_fields: list[str] = Field(default_factory=list, description="从线索继承的字段")
    source_relation: dict[str, Any] = Field(default_factory=dict, description="线索与客户的来源关系")
    warnings: list[str] = Field(default_factory=list, description="不阻断主事实的提示")


class ConvertResponse(BaseModel):
    """线索转客户的统一命令结果\uff0c兼容旧客户端的顶层字段。"""

    operation_id: str | None = Field(None, description="操作对外ID")
    status: str | None = Field(None, description="命令状态")
    # Migration compatibility: old clients read these fields directly.
    customer_id: str | None = Field(None, description="创建或复用客户的对外ID")
    contact_id: int | None = Field(None, description="创建或复用主联系人的内部ID")
    message: str | None = Field(None, description="响应消息")
    data: ConvertResultData | None = None
    resource: dict[str, Any] | None = None
    effects: list[dict[str, Any]] | None = None
    next_actions: list[dict[str, Any]] | None = None
    retryable: bool | None = None
    queryable: bool | None = None
    error: dict[str, Any] | None = None
    correlation_id: str | None = None


class MessageResponse(BaseModel):
    message: str = Field(..., description="响应消息")


class CustomerIntelligenceBatchRebuildRequest(BaseModel):
    scope: Literal["full", "partial"] = Field(
        "full",
        description="重建范围\uff1afull=完整客户档案\uff0cpartial=按业务事件更新受影响部分",
    )
    customer_ids: list[str] | None = Field(None, description="指定客户对外ID\uff1b为空时按团队批量重建")
    limit: int = Field(100, ge=1, le=500, description="本次最多调度的客户数")


class CustomerIntelligenceRegenerateRequest(BaseModel):
    scope: Literal["full", "partial"] = Field(
        "full",
        description="重建范围\uff1afull=完整客户档案\uff0cpartial=按业务事件更新受影响部分",
    )


class CustomerIntelligenceBatchRebuildResponse(BaseModel):
    message: str = Field(..., description="响应消息")
    request_id: str = Field(..., description="批量重建请求ID")
    scope: Literal["full", "partial"] = Field(..., description="重建范围")
    total: int = Field(..., description="匹配客户数")
    scheduled: int = Field(..., description="已调度客户数")
    customer_ids: list[str] = Field(..., description="已调度的客户对外ID")


class CustomerIntelligenceRunDiagnosticResponse(BaseModel):
    id: int = Field(..., description="运行记录ID")
    request_id: str = Field(..., description="请求ID")
    customer_id: str = Field(..., description="客户对外ID")
    actor_id: str | None = Field(None, description="触发人ID")
    trigger_type: str = Field(..., description="触发类型")
    scope: str = Field(..., description="刷新范围")
    status: str = Field(..., description="运行状态")
    attempt_count: int = Field(..., description="已尝试次数")
    max_attempts: int = Field(..., description="最大尝试次数")
    route_label: str | None = Field(None, description="运行类型")
    result: JsonObject = Field(default_factory=dict, description="运行结果摘要")
    visible_trace: list[JsonObject] = Field(default_factory=list, description="用户可见执行轨迹")
    trace_events: list[JsonObject] = Field(default_factory=list, description="可回放执行事件")
    error_message: str | None = Field(None, description="错误信息")
    created_time: datetime | None = Field(None, description="创建时间")
    started_time: datetime | None = Field(None, description="开始时间")
    finished_time: datetime | None = Field(None, description="结束时间")
    next_retry_at: datetime | None = Field(None, description="下次重试时间")
    last_duration_ms: int | None = Field(None, description="最近一次运行耗时毫秒")


class CustomerIntelligenceRunDiagnosticListResponse(BaseModel):
    items: list[CustomerIntelligenceRunDiagnosticResponse] = Field(default_factory=list, description="运行诊断列表")
    total: int = Field(..., description="返回数量")
    limit: int = Field(..., description="查询限制")


class CustomerIntelligenceRetryDueResponse(BaseModel):
    success: bool = Field(..., description="是否调度成功")
    total: int = Field(..., description="本次处理数量")
    succeeded: int = Field(..., description="成功数量")
    failed: int = Field(..., description="失败数量")
    results: list[JsonObject] = Field(default_factory=list, description="重试结果")



class CustomerEnrichmentJobDiagnosticResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    job_public_id: str
    customer_id: str
    purpose: Literal["INITIAL_CREATION", "HISTORICAL_BACKFILL"]
    plan_version: str
    requested_fields: list[str] = Field(default_factory=list)
    status: Literal["QUEUED", "RUNNING", "RETRY_PENDING", "COMPLETED", "SKIPPED", "EXHAUSTED"]
    attempt_count: int
    max_attempts: int
    requeue_count: int
    has_profile_refresh_receipt: bool
    available_at: datetime | None = None
    next_attempt_at: datetime | None = None
    first_attempt_finished_at: datetime | None = None
    profile_gate_timed_out_at: datetime | None = None
    created_time: datetime | None = None
    updated_time: datetime | None = None


class CustomerEnrichmentJobListResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    items: list[CustomerEnrichmentJobDiagnosticResponse] = Field(default_factory=list)
    total: int
    skip: int
    limit: int


class CustomerEnrichmentBackfillPreviewResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    industry_null: int
    existing_jobs: int
    would_schedule: int
    filled_skip: int
    invalid_non_null: int
    other_available: bool


class CustomerEnrichmentRequeueResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    job_public_id: str
    status: Literal["QUEUED"]
    requeue_count: int


class CustomerEnrichmentReconciliationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    limit: int = Field(50, ge=1, le=500)
    after_customer_id: int | None = Field(None, gt=0)
    after_orphan_job_id: int | None = Field(None, gt=0)
    dry_run: bool = False


class CustomerEnrichmentReconciliationResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    scanned: int
    jobs_created: int
    gates_released: int
    gates_cancelled: int
    refreshes_repaired: int
    errors: int
    next_customer_id: int | None = None
    next_orphan_job_id: int | None = None
    dry_run: bool

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
    detailed_reason: str | None = Field(None, max_length=500, description="详细原因说明")
    expected_version: int | None = Field(None, ge=0, description="退回时客户版本号\uff0c用于并发保护")
    
    @field_validator('detailed_reason')
    @classmethod
    def detailed_reason_must_not_be_empty(cls, v: str | None) -> str | None:
        if v is not None and (not v or not v.strip()):
            raise ValueError('详细原因不能为空')
        return v.strip() if v else v


class CustomerReturnResponse(BaseModel):
    customer_id: str = Field(..., description="客户对外ID")
    previous_owner: str = Field(..., description="原负责人姓名")
    returned_time: datetime = Field(..., description="退回时间")
    return_reason: str = Field(..., description="退回原因")
    message: str = Field(..., description="响应消息")


class CustomerClaimRequest(BaseModel):
    owner_id: str = Field(..., min_length=1, description="新负责人系统用户ID")
    expected_version: int | None = Field(None, ge=0, description="领取时客户版本号\uff0c用于并发保护")
    
    @field_validator('owner_id')
    @classmethod
    def owner_id_must_not_be_empty(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError('负责人ID不能为空')
        return v


class CustomerTransferScope(str, Enum):
    CUSTOMER_ONLY = "customer_only"
    CUSTOMER_AND_OPPORTUNITIES = "customer_and_opportunities"
    CUSTOMER_OPPORTUNITIES_AND_CONTRACTS = "customer_opportunities_and_contracts"


class CustomerAssignRequest(BaseModel):
    owner_id: str = Field(..., min_length=1, description="被分配人\uff08负责人\uff09系统用户ID")
    # Keep the historical field during the migration. New clients should use
    # transfer_scope so the contract explicitly states the affected objects.
    opportunity_transfer_scope: Literal["none", "following", "all"] | None = Field(
        None,
        description=(
            "兼容字段\uff1anone=仅客户\uff0cfollowing=跟进中商机\uff0c"
            "all=全部商机\uff1b移交商机会同步移交关联合同"
        )
    )
    transfer_scope: CustomerTransferScope | None = Field(
        None,
        description="移交范围\uff1a仅客户、客户及商机、客户/商机及合同"
    )
    expected_version: int | None = Field(None, ge=0, description="提交时客户版本号\uff0c用于并发保护")
    reason: str | None = Field(None, max_length=500, description="移交原因")
    remark: str | None = Field(None, max_length=500, description="兼容字段\uff1a分配备注\uff08说明分配原因等\uff09")
    
    @field_validator('owner_id')
    @classmethod
    def owner_id_must_not_be_empty(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError('负责人ID不能为空')
        return v.strip()

    @field_validator('reason', 'remark')
    @classmethod
    def optional_text_must_not_be_empty(cls, v: str | None) -> str | None:
        if v is not None and not v.strip():
            return None
        return v.strip() if v else v

    def normalized_transfer_scope(self) -> tuple[str, CustomerTransferScope]:
        if self.transfer_scope is not None:
            mapping = {
                CustomerTransferScope.CUSTOMER_ONLY: "none",
                CustomerTransferScope.CUSTOMER_AND_OPPORTUNITIES: "following",
                CustomerTransferScope.CUSTOMER_OPPORTUNITIES_AND_CONTRACTS: "all",
            }
            return mapping[self.transfer_scope], self.transfer_scope
        legacy_scope = self.opportunity_transfer_scope or "none"
        scope = {
            "none": CustomerTransferScope.CUSTOMER_ONLY,
            "following": CustomerTransferScope.CUSTOMER_AND_OPPORTUNITIES,
            "all": CustomerTransferScope.CUSTOMER_OPPORTUNITIES_AND_CONTRACTS,
        }[legacy_scope]
        return legacy_scope, scope

    def normalized_reason(self) -> str | None:
        return self.reason or self.remark


class CustomerAssignmentObject(BaseModel):
    public_id: str = Field(..., description="关联对象对外ID")
    object_type: Literal["opportunity", "contract"]
    status: str = Field(..., description="同步结果")
    detail: str | None = None


class CustomerAssignmentResult(BaseModel):
    customer: CustomerResponse = Field(..., description="移交后的客户信息")
    previous_owner_id: str | None = Field(None, description="原负责人ID")
    new_owner_id: str | None = Field(None, description="新负责人ID")
    transfer_scope: CustomerTransferScope = Field(..., description="实际移交范围")
    transferred_opportunities: int = Field(..., description="已同步移交的商机数量")
    transferred_contracts: int = Field(..., description="已同步移交的合同数量")
    updated_objects: list[CustomerAssignmentObject] = Field(default_factory=list, description="已同步对象")
    skipped_objects: list[CustomerAssignmentObject] = Field(default_factory=list, description="未同步对象及原因")
    message: str = Field(..., description="响应消息")


class CustomerAssignResponse(BaseModel):
    customer: CustomerResponse = Field(..., description="移交后的客户信息")
    transferred_opportunities: int = Field(..., description="已同步移交的商机数量")
    transferred_contracts: int = Field(..., description="已同步移交的合同数量")
    message: str = Field(..., description="响应消息")


class CustomerAssignmentPreviewResponse(BaseModel):
    customer_id: str = Field(..., description="客户对外ID")
    customer_version: int = Field(..., description="预览时客户版本号")
    transfer_scope: CustomerTransferScope = Field(..., description="预览移交范围")
    opportunity_count: int = Field(..., description="将同步移交的商机数量")
    contract_count: int = Field(..., description="可同步移交的合同数量")
    locked_contract_count: int = Field(..., description="因审批或签署状态不可同步的合同数量")
    locked_contracts: list[CustomerAssignmentObject] = Field(default_factory=list, description="不可同步合同明细")


class OwnerOption(BaseModel):
    id: str = Field(..., description="系统用户ID")
    name: str = Field(..., description="用户姓名")
    is_me: bool = Field(False, description="是否为当前用户")


class OwnerListResponse(BaseModel):
    data: list[OwnerOption] = Field(..., description="负责人选项列表")


class CustomerLoseRequest(BaseModel):
    loss_reason: str = Field(..., min_length=1, max_length=500, description="输单原因\uff08必填\uff09")

    @field_validator('loss_reason')
    @classmethod
    def loss_reason_must_not_be_empty(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError('输单原因不能为空')
        return v.strip()

class CustomerChartPreview(BaseModel):
    id: str
    name: str
    owner_name: str | None = None


class CustomerChartBucket(BaseModel):
    key: str
    label: str
    count: int = Field(..., ge=0)
    ratio: int = Field(..., ge=0, le=100)
    preview: list[CustomerChartPreview]
    preview_total: int = Field(..., ge=0)


class CustomerChartCard(BaseModel):
    key: Literal["status", "license", "scale", "industry", "city", "created_month"]
    title: str
    description: str
    buckets: list[CustomerChartBucket]


class CustomerChartResponse(BaseModel):
    population: int = Field(..., ge=0)
    cards: list[CustomerChartCard]


class CustomerChartBucketCustomersResponse(BaseModel):
    chart: Literal["status", "license", "scale", "industry", "city", "created_month"]
    bucket: str
    total: int = Field(..., ge=0)
    customers: list[CustomerChartPreview]
