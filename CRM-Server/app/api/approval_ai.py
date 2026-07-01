"""
AI 解析审批流程配置接口

用于 AI 辅助创建审批流程功能
"""
import json
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError

from app.core.database import SessionLocal, get_db
from app.core.deps import get_current_active_user, get_current_user_team, require_permission
from app.models.user import User
from app.models.approval import ApprovalFlow, ApprovalNode
from app.schemas.approval_ai import ApprovalAIParseRequest, ApprovalAICreateRequest
from app.services.approval_ai_parser import approval_ai_parser_service
from app.crud.approval import approval_flow_crud
from app.constants.approval_roles import ALLOWED_APPROVAL_ROLES


router = APIRouter(prefix="/v1/approval-ai", tags=["AI 审批流程解析"])


@router.post("/parse")
async def parse_approval_flow(
    request: ApprovalAIParseRequest,
    current_user: User = Depends(get_current_active_user),
    team_id: int = Depends(get_current_user_team)
):
    """
    AI 解析审批流程配置（SSE 流式响应）

    SSE 事件类型：
    - status: 状态更新
    - content: AI 思考过程内容片段
    - parsed: 解析完成，返回结构化配置
    - error: 错误信息
    """
    async def generate_sse():
        db = SessionLocal()
        try:
            async for event in approval_ai_parser_service.parse_approval_flow_stream(
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
async def create_approval_flow_from_ai(
    request: ApprovalAICreateRequest,
    current_user: User = Depends(require_permission("approval:flow:create")),
    team_id: int = Depends(get_current_user_team),
    db: Session = Depends(get_db)
):
    """
    从 AI 解析结果创建审批流程（用户确认后提交）

    创建审批流程及其所有节点配置（事务保护）

    校验规则：
    1. flow_code 不能重复
    2. nodes 至少包含 1 个节点
    3. approve_role 必须是预定义角色
    4. node_order 自动修正为连续
    """
    # 检查 team_id 是否有效
    if team_id is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="无法获取用户团队信息，请重新登录"
        )

    # 检查编码是否已存在
    existing = approval_flow_crud.get_by_code(db, request.flow_code, team_id)
    if existing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"审批流程编码「{request.flow_code}」已存在，请修改编码"
        )

    # 验证节点配置
    if not request.nodes:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="审批节点不能为空"
        )

    # 验证角色编码
    for node in request.nodes:
        if node.approve_role not in ALLOWED_APPROVAL_ROLES:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"审批角色「{node.approve_role}」无效，请使用预定义角色：{', '.join(ALLOWED_APPROVAL_ROLES)}"
            )

    # 检查节点编码唯一性
    node_codes = [n.node_code for n in request.nodes]
    if len(node_codes) != len(set(node_codes)):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="节点编码不能重复"
        )

    # 使用事务创建审批流程和节点
    try:
        # 创建审批流程
        flow_data = request.model_dump(exclude={'nodes'})
        flow_data['team_id'] = team_id
        flow_data['is_active'] = 1

        flow = ApprovalFlow(**flow_data)
        db.add(flow)
        db.flush()  # 获取 flow.id 但不提交

        # 创建审批节点
        created_nodes = []
        for i, node in enumerate(request.nodes):
            # 自动修正 node_order 为连续
            node_obj = ApprovalNode(
                flow_id=flow.id,
                team_id=team_id,
                node_name=node.node_name,
                node_code=node.node_code,
                node_order=i + 1,  # 强制连续
                description=node.description,
                approve_role=node.approve_role,
                is_required=node.is_required if hasattr(node, 'is_required') else 1
            )
            db.add(node_obj)
            created_nodes.append(node_obj)

        # 提交事务
        db.commit()
        db.refresh(flow)
        for n in created_nodes:
            db.refresh(n)

        return {
            "success": True,
            "message": f"审批流程「{flow.flow_name}」创建成功，包含 {len(created_nodes)} 个审批节点",
            "data": {
                "flow": {
                    "id": flow.id,
                    "flow_name": flow.flow_name,
                    "flow_code": flow.flow_code,
                    "description": flow.description,
                    "min_amount": float(flow.min_amount) if flow.min_amount else None,
                    "max_amount": float(flow.max_amount) if flow.max_amount else None,
                    "license_type": flow.license_type
                },
                "nodes": [
                    {
                        "id": n.id,
                        "node_name": n.node_name,
                        "node_code": n.node_code,
                        "node_order": n.node_order,
                        "approve_role": n.approve_role
                    }
                    for n in created_nodes
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