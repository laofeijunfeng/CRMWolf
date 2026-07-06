from pydantic import BaseModel, Field, field_validator, ConfigDict
from typing import Optional, List
from datetime import datetime


class DeploymentInfoBase(BaseModel):
    """部署信息基础模型"""
    deployment_name: str = Field(..., min_length=1, max_length=100, description="部署名称（如：生产环境、测试环境）")
    server_address: str = Field(..., max_length=500, description="服务器地址（http:// 或 https:// 开头）")
    authorized_users: int = Field(..., gt=0, description="授权人数（必须大于0）")
    is_default: bool = Field(default=False, description="是否默认部署")

    @field_validator('deployment_name')
    @classmethod
    def deployment_name_must_not_be_empty(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError('部署名称不能为空')
        return v.strip()

    @field_validator('server_address')
    @classmethod
    def validate_server_address(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError('服务器地址不能为空')
        v = v.strip()
        if not v.startswith('http://') and not v.startswith('https://'):
            raise ValueError('服务器地址必须以 http:// 或 https:// 开头')
        return v


class DeploymentInfoCreate(DeploymentInfoBase):
    """创建部署信息请求模型"""
    customer_id: int = Field(..., description="关联客户ID")


class DeploymentInfoUpdate(BaseModel):
    """更新部署信息请求模型"""
    deployment_name: Optional[str] = Field(None, min_length=1, max_length=100, description="部署名称")
    server_address: Optional[str] = Field(None, max_length=500, description="服务器地址")
    authorized_users: Optional[int] = Field(None, gt=0, description="授权人数（必须大于0）")
    is_default: Optional[bool] = Field(None, description="是否默认部署")

    @field_validator('deployment_name')
    @classmethod
    def deployment_name_must_not_be_empty(cls, v: Optional[str]) -> Optional[str]:
        if v is not None:
            if not v or not v.strip():
                raise ValueError('部署名称不能为空')
            return v.strip()
        return v

    @field_validator('server_address')
    @classmethod
    def validate_server_address(cls, v: Optional[str]) -> Optional[str]:
        if v is not None:
            if not v or not v.strip():
                raise ValueError('服务器地址不能为空')
            v = v.strip()
            if not v.startswith('http://') and not v.startswith('https://'):
                raise ValueError('服务器地址必须以 http:// 或 https:// 开头')
        return v


class DeploymentInfoResponse(DeploymentInfoBase):
    """部署信息响应模型"""
    id: int = Field(..., description="部署信息ID")
    customer_id: int = Field(..., description="关联客户ID")
    team_id: int = Field(..., description="团队ID")
    created_time: datetime = Field(..., description="创建时间")
    last_modified_time: datetime = Field(..., description="最后修改时间")

    model_config = ConfigDict(from_attributes=True)


class DeploymentInfoListResponse(BaseModel):
    """部署信息列表响应模型"""
    data: List[DeploymentInfoResponse] = Field(..., description="部署信息列表")
    total: int = Field(..., description="总数")

    model_config = ConfigDict(from_attributes=True)


class DeploymentInfoMessageResponse(BaseModel):
    """部署信息消息响应模型"""
    message: str = Field(..., description="响应消息")
    data: Optional[DeploymentInfoResponse] = Field(None, description="部署信息数据")