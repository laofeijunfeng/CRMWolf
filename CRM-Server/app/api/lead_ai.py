"""
AI 解析线索信息接口

用于智能创建线索功能
"""
import json
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.core.database import SessionLocal
from app.core.deps import get_current_active_user, get_current_user_team, get_db
from app.models.user import User
from app.models.lead import LeadSource, CompanyScale, Lead, LeadStatus
from app.schemas.lead_ai import LeadAIParseRequest, LeadAICreateRequest
from app.schemas.lead import LeadCreate, LeadResponse
from app.services.ai_parser.factory import EntityAIParserFactory
from app.services.follow_up_parser import follow_up_parser_service
from app.crud.lead import lead_crud, lead_follow_up_crud
from app.schemas.lead import LeadFollowUpCreate
from app.models.lead import FollowUpMethod


router = APIRouter(prefix="/v1/leads/ai", tags=["AI 线索解析"])


# 枚举值映射
SOURCE_ENUM_MAP = {
    "线上注册": LeadSource.ONLINE_REGISTER,
    "市场活动": LeadSource.MARKETING_ACTIVITY,
    "客户推荐": LeadSource.REFERRAL,
    "电话营销": LeadSource.COLD_CALL,
    "网站咨询": LeadSource.WEBSITE_INQUIRY,
    "展会": LeadSource.EXHIBITION,
    "其他": LeadSource.OTHER
}

COMPANY_SCALE_ENUM_MAP = {
    "1-50人": CompanyScale.SCALE_1_50,
    "51-200人": CompanyScale.SCALE_51_200,
    "201-500人": CompanyScale.SCALE_201_500,
    "501-1000人": CompanyScale.SCALE_501_1000,
    "1000人以上": CompanyScale.SCALE_1000_PLUS
}


@router.post("/parse")
async def parse_lead_info(
    request: LeadAIParseRequest,
    current_user: User = Depends(get_current_active_user),
    team_id: int = Depends(get_current_user_team)
):
    """
    AI 解析线索信息（SSE 流式响应）

    SSE 事件类型：
    - status: 状态更新
    - content: AI 思考过程内容片段
    - parsed: 解析完成，返回结构化信息
    - error: 错误信息
    """
    async def generate_sse():
        db = SessionLocal()
        try:
            async for event in lead_ai_parser_service.parse_lead_info_stream(
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


@router.post("/create", response_model=LeadResponse, status_code=status.HTTP_201_CREATED)
async def create_lead_from_ai(
    request: LeadAICreateRequest,
    current_user: User = Depends(get_current_active_user),
    team_id: int = Depends(get_current_user_team),
    db: Session = Depends(get_db)
):
    """
    从 AI 解析结果创建线索（用户确认后提交）

    如果有跟进信息（follow_up_content），会自动创建一条跟进记录，
    并处理 next_action 和 next_follow_time
    """
    # 枚举值转换
    source_enum = SOURCE_ENUM_MAP.get(request.source)
    if not source_enum:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"无效的线索来源：{request.source}"
        )

    company_scale_enum = None
    if request.company_scale:
        company_scale_enum = COMPANY_SCALE_ENUM_MAP.get(request.company_scale)
        if not company_scale_enum:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"无效的公司规模：{request.company_scale}"
            )

    # 创建线索
    lead_create = LeadCreate(
        lead_name=request.lead_name,
        source=source_enum,
        city=request.city,
        contact_name=request.contact_name,
        contact_phone=request.contact_phone,
        company_scale=company_scale_enum
    )

    lead = lead_crud.create(db, lead_create, str(current_user.id), team_id)

    # 如果有跟进信息，创建跟进记录
    if request.follow_up_content or request.next_action:
        # 构建跟进内容
        follow_up_content_parts = []
        if request.follow_up_content:
            follow_up_content_parts.append(request.follow_up_content)

        content = follow_up_content_parts[0] if follow_up_content_parts else None
        if content is None:
            content = "【AI 创建线索时提取的信息】"

        # 解析下次跟进时间（使用共享服务）
        next_follow_time_dt = None
        if request.next_follow_time:
            next_follow_time_dt = follow_up_parser_service.parse_relative_time(
                request.next_follow_time,
                base_date=datetime.now()
            )

        follow_up_create = LeadFollowUpCreate(
            content=content,
            method=FollowUpMethod.OTHER,
            next_action=request.next_action,
            next_follow_time=next_follow_time_dt
        )
        lead_follow_up_crud.create(
            db=db,
            obj_in=follow_up_create,
            lead_id=lead.id,
            creator_id=str(current_user.id),
            team_id=team_id,
            operator_name=current_user.name if hasattr(current_user, 'name') else None
        )

    return lead