from pydantic import BaseModel, Field, field_validator
from typing import Optional
import re


class MockLoginRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=100, description="用户姓名")
    email: str = Field(..., pattern=r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$', description="用户邮箱")
    mobile: str = Field(..., pattern=r'^\+?[1-9]\d{1,14}$', description="用户手机号")
    region: str = Field(..., min_length=1, max_length=50, description="所属地区")
    
    @field_validator('name')
    @classmethod
    def name_must_not_be_empty(cls, v):
        if not v or not v.strip():
            raise ValueError('用户姓名不能为空')
        return v.strip()
    
    @field_validator('email')
    @classmethod
    def email_must_not_be_empty(cls, v):
        if not v or not v.strip():
            raise ValueError('邮箱不能为空')
        return v.strip()
    
    @field_validator('mobile')
    @classmethod
    def mobile_must_not_be_empty(cls, v):
        if not v or not v.strip():
            raise ValueError('手机号不能为空')
        return v.strip()
    
    @field_validator('region')
    @classmethod
    def region_must_not_be_empty(cls, v):
        if not v or not v.strip():
            raise ValueError('地区不能为空')
        return v.strip()


class CreateAdminRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=100, description="管理员姓名")
    email: str = Field(..., pattern=r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$', description="管理员邮箱")
    
    @field_validator('name')
    @classmethod
    def name_must_not_be_empty(cls, v):
        if not v or not v.strip():
            raise ValueError('管理员姓名不能为空')
        return v.strip()
    
    @field_validator('email')
    @classmethod
    def email_must_not_be_empty(cls, v):
        if not v or not v.strip():
            raise ValueError('邮箱不能为空')
        return v.strip()


class CreateSalesDirectorRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=100, description="销售总监姓名")
    email: str = Field(..., pattern=r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$', description="销售总监邮箱")
    region: str = Field(..., min_length=1, max_length=50, description="所属地区")
    
    @field_validator('name')
    @classmethod
    def name_must_not_be_empty(cls, v):
        if not v or not v.strip():
            raise ValueError('销售总监姓名不能为空')
        return v.strip()
    
    @field_validator('email')
    @classmethod
    def email_must_not_be_empty(cls, v):
        if not v or not v.strip():
            raise ValueError('邮箱不能为空')
        return v.strip()
    
    @field_validator('region')
    @classmethod
    def region_must_not_be_empty(cls, v):
        if not v or not v.strip():
            raise ValueError('地区不能为空')
        return v.strip()


class CreateSalesMemberRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=100, description="销售成员姓名")
    email: str = Field(..., pattern=r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$', description="销售成员邮箱")
    region: str = Field(..., min_length=1, max_length=50, description="所属地区")
    
    @field_validator('name')
    @classmethod
    def name_must_not_be_empty(cls, v):
        if not v or not v.strip():
            raise ValueError('销售成员姓名不能为空')
        return v.strip()
    
    @field_validator('email')
    @classmethod
    def email_must_not_be_empty(cls, v):
        if not v or not v.strip():
            raise ValueError('邮箱不能为空')
        return v.strip()
    
    @field_validator('region')
    @classmethod
    def region_must_not_be_empty(cls, v):
        if not v or not v.strip():
            raise ValueError('地区不能为空')
        return v.strip()
