from pydantic import BaseModel, EmailStr, Field
from typing import Optional
from app.schemas.user import UserResponse


class SendCodeRequest(BaseModel):
    """发送验证码请求"""
    email: EmailStr
    purpose: str = Field(default="login", pattern="^(register|login|reset_password)$")


class RegisterRequest(BaseModel):
    """注册请求（验证码方式）"""
    email: EmailStr
    code: str = Field(..., min_length=6, max_length=6)
    name: str = Field(..., min_length=1, max_length=100)
    password: Optional[str] = Field(None, min_length=6, max_length=50)


class RegisterPasswordRequest(BaseModel):
    """注册请求（密码方式）"""
    email: EmailStr
    name: str = Field(..., min_length=1, max_length=100)
    password: str = Field(..., min_length=6, max_length=50)


class LoginCodeRequest(BaseModel):
    """验证码登录请求"""
    email: EmailStr
    code: str = Field(..., min_length=6, max_length=6)


class LoginPasswordRequest(BaseModel):
    """密码登录请求"""
    email: EmailStr
    password: str = Field(..., min_length=1)


class LoginResponse(BaseModel):
    """登录响应"""
    access_token: str
    token_type: str = "bearer"
    user: UserResponse