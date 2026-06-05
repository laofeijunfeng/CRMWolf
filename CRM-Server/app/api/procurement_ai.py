"""
AI 解析采购方式配置接口

用于 AI 辅助创建采购方式功能
"""
import json
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError

from app.core.database import SessionLocal
from app.core.deps import get_current_active_user, get_current_user_team, get_db
from app.models.user import User
from app.models.procurement import ProcurementMethod, ProcurementStageTemplate
from app.schemas.procurement_ai import ProcurementAIParseRequest, ProcurementAICreateRequest
from app.schemas.procurement import ProcurementMethodCreate, ProcurementStageTemplateCreate
from app.services.procurement_ai_parser import procurement_ai_parser_service
from app.crud.procurement import procurement_method_crud, procurement_stage_template_crud


router = APIRouter(prefix="/v1/procurement-ai", tags=["AI 采购方式解析"])


@router.post("/parse")
async def parse_procurement_method(
    request: ProcurementAIParseRequest,
    current_user: User = Depends(get_current_active_user),
    team_id: int = Depends(get_current_user_team)
):
    """
    AI 解析采购方式配置（SSE 流式响应）

    SSE 事件类型：
    - status: 状态更新
    - content: AI 思考过程内容片段
    - parsed: 解析完成，返回结构化配置
    - error: 错误信息
    """
    async def generate_sse():
        db = SessionLocal()
        try:
            async for event in procurement_ai_parser_service.parse_procurement_method_stream(
                db=db,
                user_message=request.content,
                team_id=team_id
            ):
                yield f"data: {json.dumps(event)}\n\n"
        finally:
            db.close()

    return StreamingResponse(
        generate_sse(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no"
        }
    )


@router.post("/create", status_code=status.HTTP_201_CREATED)
async def create_procurement_method_from_ai(
    request: ProcurementAICreateRequest,
    current_user: User = Depends(get_current_active_user),
    team_id: int = Depends(get_current_user_team),
    db: Session = Depends(get_db)
):
    """
    从 AI 解析结果创建采购方式（用户确认后提交）

    创建采购方式及其所有阶段模板配置（事务保护）
    """
    # 检查 team_id 是否有效
    if team_id is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="无法获取用户团队信息，请重新登录"
        )

    # 检查编码是否已存在
    existing = procurement_method_crud.get_by_code(db, request.code, team_id)
    if existing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"采购方式编码「{request.code}」已存在，请修改编码"
        )

    # 检查名称是否已存在
    existing_name = procurement_method_crud.get_by_name(db, request.name, team_id)
    if existing_name:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"采购方式名称「{request.name}」已存在，请修改名称"
        )

    # 验证阶段配置
    if not request.stages:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="阶段配置不能为空"
        )

    # 检查是否有且只有一个默认起始阶段
    default_start_count = sum(1 for s in request.stages if s.is_default_start)
    if default_start_count == 0:
        # 如果没有设置，默认第一个阶段为起始阶段
        request.stages[0].is_default_start = True
    elif default_start_count > 1:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="只能有一个默认起始阶段"
        )

    # 检查最后阶段赢率是否为 100
    last_stage = request.stages[-1]
    if last_stage.win_probability != 100:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="最后阶段的赢率必须为 100%"
        )

    # 检查阶段编码唯一性
    stage_codes = [s.template_code for s in request.stages]
    if len(stage_codes) != len(set(stage_codes)):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="阶段编码不能重复"
        )

    # 使用事务创建采购方式和阶段模板
    try:
        # 创建采购方式
        method = ProcurementMethod(
            name=request.name,
            code=request.code,
            description=request.description,
            is_active=1,
            sort_order=0,
            team_id=team_id,
            created_by=str(current_user.id)
        )
        db.add(method)
        db.flush()  # 获取 method.id 但不提交

        # 创建阶段模板
        created_stages = []
        for stage in request.stages:
            stage_obj = ProcurementStageTemplate(
                procurement_method_id=method.id,
                template_code=stage.template_code,
                stage_name=stage.stage_name,
                win_probability=stage.win_probability,
                sort_order=stage.sort_order,
                is_default_start=1 if stage.is_default_start else 0,
                can_skip=1 if stage.can_skip else 0,
                description=stage.description,
                version=1,
                version_lock=0,
                team_id=team_id,
                created_by=str(current_user.id)
            )
            db.add(stage_obj)
            created_stages.append(stage_obj)

        # 提交事务
        db.commit()
        db.refresh(method)
        for s in created_stages:
            db.refresh(s)

        return {
            "success": True,
            "message": f"采购方式「{method.name}」创建成功，包含 {len(created_stages)} 个阶段",
            "data": {
                "method": {
                    "id": method.id,
                    "name": method.name,
                    "code": method.code,
                    "description": method.description
                },
                "stages": [
                    {
                        "id": s.id,
                        "stage_name": s.stage_name,
                        "template_code": s.template_code,
                        "win_probability": s.win_probability,
                        "sort_order": s.sort_order,
                        "is_default_start": s.is_default_start
                    }
                    for s in created_stages
                ]
            }
        }

    except IntegrityError as e:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"数据库约束错误：{str(e)}"
        )
    except Exception as e:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"创建失败：{str(e)}"
        )