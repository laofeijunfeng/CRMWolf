"""
AI 对话历史接口

用于获取和管理用户的 AI 助手对话历史记录
"""
from datetime import datetime
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from pydantic import BaseModel, Field

from app.core.database import SessionLocal
from app.core.deps import get_current_active_user, get_current_user_team
from app.models.user import User
from app.crud.ai_conversation_history_crud import ai_conversation_history_crud


router = APIRouter(prefix="/v1/assistant/conversations", tags=["AI 对话历史"])


# ========== Pydantic Schemas ==========

class MessageItem(BaseModel):
    """消息项"""
    role: str = Field(..., description="角色：user 或 assistant")
    content: str = Field(..., description="消息内容")
    timestamp: str = Field(..., description="时间戳")


class ConversationHistoryItem(BaseModel):
    """对话历史项"""
    id: int
    title: str
    action_type: Optional[str] = None
    entity_type: Optional[str] = None
    entity_id: Optional[int] = None
    created_at: datetime

    class Config:
        from_attributes = True


class ConversationDetail(BaseModel):
    """对话详情"""
    id: int
    title: str
    summary: Optional[str] = None
    action_type: Optional[str] = None
    entity_type: Optional[str] = None
    entity_id: Optional[int] = None
    messages: List[MessageItem]
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class ConversationGroup(BaseModel):
    """按日期分组的对话列表"""
    today: List[ConversationHistoryItem]
    yesterday: List[ConversationHistoryItem]
    earlier: List[ConversationHistoryItem]


class HistoryListResponse(BaseModel):
    """历史列表响应"""
    groups: ConversationGroup
    total: int


class HistoryListParams(BaseModel):
    """历史列表请求参数"""
    page: int = Field(default=1, ge=1, description="页码")
    pageSize: int = Field(default=20, ge=1, le=100, description="每页数量")


class ConversationCreateParams(BaseModel):
    """创建对话请求参数"""
    title: str = Field(..., max_length=200, description="对话标题")
    messages: List[MessageItem] = Field(..., description="对话消息列表")
    action_type: Optional[str] = Field(default=None, description="操作类型")
    entity_type: Optional[str] = Field(default=None, description="实体类型")
    entity_id: Optional[int] = Field(default=None, description="实体ID")


# ========== Helper Functions ==========

def get_db():
    """获取数据库会话"""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def format_conversation_history(conv) -> dict:
    """格式化对话历史项"""
    return {
        "id": conv.id,
        "title": conv.title,
        "action_type": conv.action_type,
        "entity_type": conv.entity_type,
        "entity_id": conv.entity_id,
        "created_at": conv.created_at.isoformat() if conv.created_at else None
    }


def format_conversation_detail(conv) -> dict:
    """格式化对话详情"""
    return {
        "id": conv.id,
        "title": conv.title,
        "summary": conv.summary,
        "action_type": conv.action_type,
        "entity_type": conv.entity_type,
        "entity_id": conv.entity_id,
        "messages": conv.messages or [],
        "created_at": conv.created_at.isoformat() if conv.created_at else None,
        "updated_at": conv.updated_at.isoformat() if conv.updated_at else None
    }


# ========== API Endpoints ==========

@router.get("", response_model=HistoryListResponse)
def get_conversation_history(
    page: int = Query(default=1, ge=1),
    pageSize: int = Query(default=20, ge=1, le=100),
    db: Session = Depends(get_db),
    team_id: int = Depends(get_current_user_team),
    current_user: User = Depends(get_current_active_user)
):
    """
    获取对话历史列表（按日期分组）

    返回今天、昨天、更早三个分组的对话历史
    """
    # 按日期分组获取
    groups = ai_conversation_history_crud.get_by_date_groups(
        db,
        team_id=team_id,
        user_id=current_user.id,
        limit=pageSize
    )

    # 格式化响应
    formatted_groups = {
        "today": [format_conversation_history(c) for c in groups["today"]],
        "yesterday": [format_conversation_history(c) for c in groups["yesterday"]],
        "earlier": [format_conversation_history(c) for c in groups["earlier"]]
    }

    # 统计总数
    total = ai_conversation_history_crud.count(
        db,
        team_id=team_id,
        user_id=current_user.id
    )

    return {
        "groups": formatted_groups,
        "total": total
    }


@router.post("", response_model=ConversationDetail)
def create_conversation(
    params: ConversationCreateParams,
    db: Session = Depends(get_db),
    team_id: int = Depends(get_current_user_team),
    current_user: User = Depends(get_current_active_user)
):
    """
    创建对话记录

    保存用户的 AI 对话到数据库，用于后续查阅和上下文恢复
    """
    # 转换消息格式
    messages = [
        {
            "role": m.role,
            "content": m.content,
            "timestamp": m.timestamp
        }
        for m in params.messages
    ]

    # 创建对话记录
    conv = ai_conversation_history_crud.create(
        db,
        team_id=team_id,
        user_id=current_user.id,
        title=params.title,
        messages=messages,
        action_type=params.action_type,
        entity_type=params.entity_type,
        entity_id=params.entity_id
    )

    return format_conversation_detail(conv)


@router.put("/{id}", response_model=ConversationDetail)
def update_conversation(
    id: int,
    params: ConversationCreateParams,
    db: Session = Depends(get_db),
    team_id: int = Depends(get_current_user_team),
    current_user: User = Depends(get_current_active_user)
):
    """
    更新对话记录（实时保存）

    用于 ChatGPT 模式的实时保存：每次发送消息、AI 流式响应时实时更新
    """
    # 检查对话是否存在
    existing_conv = ai_conversation_history_crud.get_by_id(db, id, team_id)
    if not existing_conv:
        raise HTTPException(status_code=404, detail="对话不存在")

    # 检查对话是否属于当前用户
    if existing_conv.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="无权限修改此对话")

    # 转换消息格式
    messages = [
        {
            "role": m.role,
            "content": m.content,
            "timestamp": m.timestamp
        }
        for m in params.messages
    ]

    # 更新对话记录
    conv = ai_conversation_history_crud.update(
        db,
        id=id,
        team_id=team_id,
        title=params.title,
        messages=messages,
        action_type=params.action_type,
        entity_type=params.entity_type,
        entity_id=params.entity_id
    )

    if not conv:
        raise HTTPException(status_code=500, detail="更新失败")

    return format_conversation_detail(conv)


@router.get("/{id}", response_model=ConversationDetail)
def get_conversation_detail(
    id: int,
    db: Session = Depends(get_db),
    team_id: int = Depends(get_current_user_team),
    current_user: User = Depends(get_current_active_user)
):
    """
    获取单个对话详情

    返回完整的对话消息列表
    """
    conv = ai_conversation_history_crud.get_by_id(db, id, team_id)

    if not conv:
        raise HTTPException(status_code=404, detail="对话不存在")

    return format_conversation_detail(conv)


@router.delete("/{id}")
def delete_conversation(
    id: int,
    db: Session = Depends(get_db),
    team_id: int = Depends(get_current_user_team),
    current_user: User = Depends(get_current_active_user)
):
    """
    删除对话历史（软删除）

    将对话状态标记为 deleted
    """
    success = ai_conversation_history_crud.delete(db, id, team_id)

    if not success:
        raise HTTPException(status_code=404, detail="对话不存在")

    return {"message": "删除成功"}


@router.get("/search")
def search_conversations(
    keyword: str = Query(..., min_length=1, max_length=50),
    limit: int = Query(default=10, ge=1, le=50),
    db: Session = Depends(get_db),
    team_id: int = Depends(get_current_user_team),
    current_user: User = Depends(get_current_active_user)
):
    """
    搜索对话历史

    根据关键词搜索对话标题
    """
    results = ai_conversation_history_crud.search(
        db,
        team_id=team_id,
        user_id=current_user.id,
        keyword=keyword,
        limit=limit
    )

    return [format_conversation_history(c) for c in results]