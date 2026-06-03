from pydantic import BaseModel, Field, field_validator
from typing import Optional, List
from datetime import datetime
from app.models.lead import LeadSource, LeadStatus, CompanyScale, FollowUpMethod


class OwnerInfo(BaseModel):
    id: str = Field(..., description="用户飞书Open ID")
    name: str = Field(..., description="用户姓名")
    avatar_url: Optional[str] = Field(None, description="用户头像URL")
    
    class Config:
        from_attributes = True


class LeadBase(BaseModel):
    lead_name: str = Field(..., min_length=1, max_length=255, description="线索名称（项目名称或公司名称）")
    source: LeadSource = Field(..., description="线索来源：如：WEBSITE:官网, REFERRAL:转介绍, EVENT:活动等")
    city: str = Field(..., min_length=1, max_length=100, description="所在城市（必填）")
    contact_name: str = Field(..., min_length=1, max_length=100, description="联系人姓名（必填）")
    contact_phone: str = Field(..., min_length=1, max_length=20, description="联系人手机（必填，主要联系方式）")
    company_scale: Optional[CompanyScale] = Field(None, description="团队规模：如：1-10人、11-50人、51-200人、201-500人、500+人")
    
    @field_validator('lead_name')
    @classmethod
    def lead_name_must_not_be_empty(cls, v):
        if not v or not v.strip():
            raise ValueError('线索名称不能为空')
        return v.strip()
    
    @field_validator('city')
    @classmethod
    def city_must_not_be_empty(cls, v):
        if not v or not v.strip():
            raise ValueError('所在城市不能为空')
        return v.strip()
    
    @field_validator('contact_name')
    @classmethod
    def contact_name_must_not_be_empty(cls, v):
        if not v or not v.strip():
            raise ValueError('联系人姓名不能为空')
        return v.strip()
    
    @field_validator('contact_phone')
    @classmethod
    def contact_phone_must_not_be_empty(cls, v):
        if not v or not v.strip():
            raise ValueError('联系人手机不能为空')
        return v.strip()


class LeadCreate(LeadBase):
    pass


class LeadUpdate(BaseModel):
    lead_name: Optional[str] = Field(None, min_length=1, max_length=255, description="线索名称")
    source: Optional[LeadSource] = Field(None, description="线索来源")
    city: Optional[str] = Field(None, min_length=1, max_length=100, description="所在城市")
    contact_name: Optional[str] = Field(None, min_length=1, max_length=100, description="联系人姓名")
    contact_phone: Optional[str] = Field(None, min_length=1, max_length=20, description="联系人手机")
    company_scale: Optional[CompanyScale] = Field(None, description="团队规模")
    status: Optional[LeadStatus] = Field(None, description="线索状态")
    
    @field_validator('lead_name')
    @classmethod
    def lead_name_must_not_be_empty(cls, v):
        if v is not None and (not v or not v.strip()):
            raise ValueError('线索名称不能为空')
        return v.strip() if v else v
    
    @field_validator('city')
    @classmethod
    def city_must_not_be_empty(cls, v):
        if v is not None and (not v or not v.strip()):
            raise ValueError('所在城市不能为空')
        return v.strip() if v else v
    
    @field_validator('contact_name')
    @classmethod
    def contact_name_must_not_be_empty(cls, v):
        if v is not None and (not v or not v.strip()):
            raise ValueError('联系人姓名不能为空')
        return v.strip() if v else v
    
    @field_validator('contact_phone')
    @classmethod
    def contact_phone_must_not_be_empty(cls, v):
        if v is not None and (not v or not v.strip()):
            raise ValueError('联系人手机不能为空')
        return v.strip() if v else v


class LeadResponse(LeadBase):
    id: int = Field(..., description="线索ID（主键）")
    owner_id: Optional[str] = Field(None, description="负责人飞书用户ID")
    status: LeadStatus = Field(..., description="线索状态：NEW:新线索, CONTACTED:已联系, QUALIFIED:已确认, CONVERTED:已转化, INVALID:无效")
    invalid_reason: Optional[str] = Field(None, description="无效原因")
    pool_id: Optional[int] = Field(None, description="线索池ID（公海池）")
    creator_id: str = Field(..., description="创建人飞书用户ID")
    created_time: datetime = Field(..., description="创建时间")
    last_modified_time: datetime = Field(..., description="最后修改时间")
    version: int = Field(..., description="版本号（乐观锁，防止并发修改冲突）")
    score: Optional[int] = Field(None, description="热力值分数（0-100）")
    score_updated_at: Optional[datetime] = Field(None, description="热力值最后更新时间")

    class Config:
        from_attributes = True


class LeadListResponse(LeadResponse):
    owner_info: Optional[OwnerInfo] = Field(None, description="负责人信息")
    
    class Config:
        from_attributes = True


class LeadDetailResponse(LeadResponse):
    follow_ups: List['LeadFollowUpResponse'] = []
    owner_info: Optional[OwnerInfo] = Field(None, description="负责人信息")
    creator_info: Optional[OwnerInfo] = Field(None, description="创建人信息")
    
    class Config:
        from_attributes = True


class LeadFollowUpBase(BaseModel):
    content: str = Field(..., min_length=1, description="跟进内容")
    method: FollowUpMethod = Field(..., description="跟进方式")
    next_follow_time: Optional[datetime] = Field(None, description="计划下次跟进时间")
    next_action: Optional[str] = Field(None, max_length=200, description="下一步动作")

    @field_validator('content')
    @classmethod
    def content_must_not_be_empty(cls, v):
        if not v or not v.strip():
            raise ValueError('跟进内容不能为空')
        return v.strip()


class LeadFollowUpCreate(LeadFollowUpBase):
    pass


class LeadFollowUpResponse(LeadFollowUpBase):
    id: int = Field(..., description="跟进记录ID")
    lead_id: int = Field(..., description="线索ID")
    creator_id: str = Field(..., description="创建人飞书用户ID")
    created_time: datetime = Field(..., description="创建时间")
    creator_info: Optional[OwnerInfo] = Field(None, description="跟进人信息")

    class Config:
        from_attributes = True


class LeadAssignRequest(BaseModel):
    owner_id: str = Field(..., description="负责人ID（飞书用户ID）")


class LeadConvertRequest(BaseModel):
    customer_name: str = Field(..., min_length=1, max_length=255, description="客户名称")
    customer_contact_name: str = Field(..., min_length=1, max_length=100, description="客户联系人姓名")
    customer_contact_phone: str = Field(..., min_length=1, max_length=20, description="客户联系人手机")
    customer_address: Optional[str] = Field(None, max_length=500, description="客户地址")
    customer_industry: Optional[str] = Field(None, max_length=100, description="客户行业")
    
    @field_validator('customer_name')
    @classmethod
    def customer_name_must_not_be_empty(cls, v):
        if not v or not v.strip():
            raise ValueError('客户名称不能为空')
        return v.strip()
    
    @field_validator('customer_contact_name')
    @classmethod
    def customer_contact_name_must_not_be_empty(cls, v):
        if not v or not v.strip():
            raise ValueError('客户联系人姓名不能为空')
        return v.strip()
    
    @field_validator('customer_contact_phone')
    @classmethod
    def customer_contact_phone_must_not_be_empty(cls, v):
        if not v or not v.strip():
            raise ValueError('客户联系人手机不能为空')
        return v.strip()


class LeadBatchImportRequest(BaseModel):
    leads: List[LeadCreate] = Field(..., min_length=1, max_length=100, description="线索列表（最多100条）")


class LeadBatchImportResponse(BaseModel):
    total: int = Field(..., description="总数")
    success: int = Field(..., description="成功数量")
    failed: int = Field(..., description="失败数量")
    failed_items: List[dict] = Field(default_factory=list, description="失败项详情")


class LeadTrendResponse(BaseModel):
    date: str = Field(..., description="日期")
    count: int = Field(..., description="数量")


class LeadConversionResponse(BaseModel):
    source: str = Field(..., description="来源")
    total: int = Field(..., description="总数")
    converted: int = Field(..., description="转化数")
    conversion_rate: float = Field(..., description="转化率（%）")


class LeadMarkInvalidRequest(BaseModel):
    reason: str = Field(..., min_length=1, max_length=500, description="无效原因（必填）")

    @field_validator('reason')
    @classmethod
    def reason_must_not_be_empty(cls, v):
        if not v or not v.strip():
            raise ValueError('无效原因不能为空')
        return v.strip()


LeadDetailResponse.model_rebuild()
