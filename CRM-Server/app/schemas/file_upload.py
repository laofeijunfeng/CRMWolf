# app/schemas/file_upload.py

from pydantic import BaseModel, Field
from typing import Optional

class FileUploadResponse(BaseModel):
    """文件上传响应"""
    file_path: str = Field(..., description="文件相对路径（用于存储到数据库）")
    file_name: str = Field(..., description="原始文件名")
    file_size: int = Field(..., description="文件大小（字节）")
    message: str = Field(default="上传成功", description="响应消息")