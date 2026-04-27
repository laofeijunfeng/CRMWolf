"""
开放接口统一响应包装器
"""
from pydantic import BaseModel, Field
from typing import Optional, Generic, TypeVar, List
from datetime import datetime
import time


T = TypeVar("T")


class OpenApiResponse(BaseModel, Generic[T]):
    """开放接口统一响应格式"""

    code: int = Field(..., description="错误码（0=成功，非0=失败）")
    message: str = Field(..., description="提示信息")
    data: Optional[T] = Field(None, description="业务数据")
    timestamp: int = Field(..., description="响应时间戳（秒级）")

    class Config:
        from_attributes = True


class OpenApiPaginatedData(BaseModel, Generic[T]):
    """分页数据格式"""

    list: List[T] = Field(default_factory=list, description="数据列表")
    total: int = Field(..., description="总条数")
    total_pages: int = Field(..., description="总页数")
    page: int = Field(..., description="当前页码")
    page_size: int = Field(..., description="当前页条数")


class OpenApiErrorResponse(BaseModel):
    """错误响应格式"""

    code: int = Field(..., description="错误码")
    message: str = Field(..., description="错误信息")
    details: Optional[str] = Field(None, description="详细信息")
    timestamp: int = Field(..., description="响应时间戳")


class OpenApiSuccessResponse(BaseModel):
    """简单成功响应（无数据）"""

    code: int = Field(default=0, description="错误码")
    message: str = Field(default="success", description="提示信息")
    timestamp: int = Field(..., description="响应时间戳")


# 工具函数
def success_response(data: Optional[T] = None, message: str = "success") -> OpenApiResponse[T]:
    """构建成功响应"""
    return OpenApiResponse(
        code=0,
        message=message,
        data=data,
        timestamp=int(time.time())
    )


def error_response(code: int, message: str, details: Optional[str] = None) -> OpenApiErrorResponse:
    """构建错误响应"""
    return OpenApiErrorResponse(
        code=code,
        message=message,
        details=details,
        timestamp=int(time.time())
    )


def paginated_response(
    items: List[T],
    total: int,
    page: int,
    page_size: int,
    message: str = "success"
) -> OpenApiResponse[OpenApiPaginatedData[T]]:
    """构建分页响应"""
    total_pages = (total + page_size - 1) // page_size if page_size > 0 else 0

    paginated_data = OpenApiPaginatedData(
        list=items,
        total=total,
        total_pages=total_pages,
        page=page,
        page_size=page_size
    )

    return OpenApiResponse(
        code=0,
        message=message,
        data=paginated_data,
        timestamp=int(time.time())
    )