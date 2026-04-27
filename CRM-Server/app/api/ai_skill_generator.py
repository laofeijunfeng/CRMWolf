"""
AI Skill Generator API

提供 AI 辅助生成 Skill/Action 配置的接口（SSE 流式响应）
"""
import json
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.core.database import get_db, SessionLocal
from app.core.deps import get_current_user
from app.models.user import User
from app.schemas.ai_skill_config import SkillAnalyzeRequest, SkillGenerateRequest
from app.services.skills.skill_generator_service import skill_generator_service
from app.services.permission_service import permission_service


router = APIRouter(prefix="/api/v1/ai/skills", tags=["AI Skill Generator"])


@router.post("/analyze")
async def analyze_skill_requirement(
    request: SkillAnalyzeRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    分析用户需求，判断模块是否支持（SSE 流式响应）

    SSE 事件类型：
    - progress: 分析进度
    - result: 分析结果（supported, message, config_prompt）
    - error: 错误信息

    需要权限：system:config 或 ai:manage
    """
    # 权限检查在主请求中完成（db session 有效）
    permissions = permission_service.get_user_permissions_from_db(db, current_user.id)
    if not any(p.code in ["system:config", "ai:manage"] for p in permissions):
        raise HTTPException(status_code=403, detail="无权限使用 AI Skill 生成功能")

    async def generate_sse():
        """生成 SSE 流式响应（在内部管理数据库 session）"""
        inner_db = SessionLocal()
        try:
            async for event in skill_generator_service.analyze_requirement(
                db=inner_db,
                requirement=request.requirement
            ):
                yield f"data: {json.dumps(event)}\n\n"
        finally:
            inner_db.close()

    return StreamingResponse(
        generate_sse(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no"
        }
    )


@router.post("/generate")
async def generate_skill_config(
    request: SkillGenerateRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    根据配置 Prompt 生成并保存 Skill/Action 配置（SSE 流式响应）

    SSE 事件类型：
    - progress: 生成进度
    - skill: Skill 创建成功
    - action: Action 创建成功
    - complete: 全部完成
    - error: 错误信息

    需要权限：system:config 或 ai:manage
    """
    # 权限检查在主请求中完成（db session 有效）
    permissions = permission_service.get_user_permissions_from_db(db, current_user.id)
    if not any(p.code in ["system:config", "ai:manage"] for p in permissions):
        raise HTTPException(status_code=403, detail="无权限使用 AI Skill 生成功能")

    async def generate_sse():
        """生成 SSE 流式响应（在内部管理数据库 session）"""
        inner_db = SessionLocal()
        try:
            async for event in skill_generator_service.generate_and_save(
                db=inner_db,
                config_prompt=request.config_prompt,
                user_id=current_user.id
            ):
                yield f"data: {json.dumps(event)}\n\n"
        finally:
            inner_db.close()

    return StreamingResponse(
        generate_sse(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no"
        }
    )