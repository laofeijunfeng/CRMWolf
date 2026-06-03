from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session
from sqlalchemy import text
from typing import List, Optional

from app.core.database import get_db
from app.core.deps import get_current_active_user, get_current_user_team
from app.crud.contract import contract_crud
from app.crud.approval import approval_flow_crud, approval_crud
from app.crud.role import role_crud
from app.models.approval import ApprovalStatus, ApprovalAction
from app.models.contract import ContractStatus
from app.schemas.approval import (
    ApprovalFlowCreate, ApprovalFlowUpdate, ApprovalFlowResponse, ApprovalFlowDetailResponse,
    ApprovalSubmitRequest, ApprovalActionRequest, ApprovalDetailResponse, ApprovalListResponse,
    ApprovalRecordResponse, MessageResponse
)


router = APIRouter(prefix="/v1/approvals", tags=["审批管理"])


@router.get("/flows", response_model=List[ApprovalFlowResponse], summary="获取审批流程列表", description="""
获取所有审批流程模板列表，支持分页查询和按启用状态筛选。

**功能说明：**
- 支持分页查询，默认每页100条
- 可按启用/禁用状态筛选
- 返回流程基本信息，不包含节点详情

**业务场景：**
- 管理员查看所有审批流程配置
- 匹配合同对应的审批流程

**返回字段：**
- flow_id: 流程ID
- flow_name: 流程名称
- flow_code: 流程编码
- flow_type: 流程类型（CONTRACT-合同审批）
- is_active: 是否启用
- description: 流程描述
""")
def get_approval_flows(
    skip: int = Query(0, ge=0, description="跳过记录数"),
    limit: int = Query(100, ge=1, le=100, description="每页记录数"),
    is_active: Optional[bool] = Query(None, description="是否启用"),
    team_id: int = Depends(get_current_user_team),
    current_user = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    flows, total = approval_flow_crud.get_multi(db, team_id, skip, limit, is_active)
    return flows


@router.get("/flows/{flow_id}", response_model=ApprovalFlowDetailResponse, summary="获取审批流程详情", description="""
获取指定审批流程的详细信息，包括流程配置和所有审批节点。

**功能说明：**
- 返回流程完整配置信息
- 包含所有审批节点列表
- 显示每个节点的审批角色、顺序等信息

**业务场景：**
- 管理员查看流程配置详情
- 了解审批链路和节点设置

**路径参数：**
- flow_id: 审批流程ID

**返回字段：**
- 基本信息：流程ID、名称、编码、类型、状态等
- nodes: 审批节点列表
  - node_id: 节点ID
  - node_name: 节点名称
  - approve_role: 审批角色
  - node_order: 节点顺序
  - is_active: 是否启用
""")
def get_approval_flow(
    flow_id: int,
    current_user = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    flow = approval_flow_crud.get_by_id(db, flow_id)
    if not flow:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="审批流程不存在"
        )
    
    return flow


@router.post("/flows", response_model=ApprovalFlowResponse, status_code=status.HTTP_201_CREATED, summary="创建审批流程", description="""
创建新的审批流程模板，支持配置多节点审批链路。

**功能说明：**
- 创建新的审批流程模板
- 可配置多个审批节点
- 节点按顺序依次审批

**业务场景：**
- 管理员配置新的审批流程
- 定义不同类型合同的审批规则

**权限要求：**
- 需要权限：approval:flow:create

**请求体字段：**
- flow_name: 流程名称（必填）
- flow_code: 流程编码，唯一标识（必填）
- flow_type: 流程类型，如CONTRACT（必填）
- description: 流程描述
- is_active: 是否启用
- nodes: 审批节点列表
  - node_name: 节点名称
  - approve_role: 审批角色
  - node_order: 节点顺序

**注意事项：**
- flow_code必须唯一
- 节点顺序应连续且从1开始
""")
def create_approval_flow(
    flow_data: ApprovalFlowCreate,
    team_id: int = Depends(get_current_user_team),
    current_user = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    from app.core.deps import require_permission

    permission_checker = require_permission("approval:flow:create")
    permission_checker(current_user, db)

    existing_flow = approval_flow_crud.get_by_code(db, flow_data.flow_code, team_id)
    if existing_flow:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"审批流程编码 {flow_data.flow_code} 已存在"
        )

    try:
        flow = approval_flow_crud.create(db, flow_data, team_id)
        return flow
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"创建审批流程失败: {str(e)}"
        )


@router.put("/flows/{flow_id}", response_model=ApprovalFlowResponse, summary="更新审批流程", description="""
更新现有审批流程模板的配置信息。

**功能说明：**
- 更新流程基本信息
- 调整审批节点配置
- 修改流程启用状态

**业务场景：**
- 调整审批规则
- 增加或减少审批节点
- 暂停/启用某个流程

**权限要求：**
- 需要权限：approval:flow:update

**路径参数：**
- flow_id: 审批流程ID

**请求体字段：**
- 所有字段均为可选
- flow_name: 流程名称
- description: 流程描述
- is_active: 是否启用
- nodes: 审批节点列表（完整替换）

**注意事项：**
- 更新节点时会完全替换现有节点
- 正在使用的流程谨慎修改
""")
def update_approval_flow(
    flow_id: int,
    flow_data: ApprovalFlowUpdate,
    current_user = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    from app.core.deps import require_permission
    
    permission_checker = require_permission("approval:flow:update")
    permission_checker(current_user, db)
    
    flow = approval_flow_crud.get_by_id(db, flow_id)
    if not flow:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="审批流程不存在"
        )
    
    try:
        updated_flow = approval_flow_crud.update(db, flow, flow_data)
        return updated_flow
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"更新审批流程失败: {str(e)}"
        )


@router.post("/contracts/{contract_id}/submit", response_model=ApprovalDetailResponse, status_code=status.HTTP_201_CREATED, summary="提交合同审批", description="""
将草稿状态的合同提交到审批流程，系统会自动匹配对应的审批流程。

**功能说明：**
- 只有草稿状态的合同可以提交审批
- 系统自动匹配对应的审批流程
- 创建审批实例并流转到第一个节点
- 向首个节点的审批人发送通知

**业务场景：**
- 销售人员完成合同后提交审批
- 启动合同审批流程

**路径参数：**
- contract_id: 合同ID

**请求体字段：**
- flow_id: 指定审批流程ID（可选，不指定则自动匹配）
- comment: 提交说明（可选）

**业务规则：**
- 只能提交草稿（DRAFT）状态的合同
- 自动根据合同类型匹配审批流程
- 首个节点的审批人会收到飞书通知

**错误情况：**
- 合同不存在
- 合同状态不是草稿
- 未找到匹配的审批流程
- 该合同已有待审批流程
""")
async def submit_contract_approval(
    contract_id: int,
    submit_data: ApprovalSubmitRequest,
    current_user = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    contract = contract_crud.get_by_id(db, contract_id)
    if not contract:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="合同不存在"
        )
    
    if contract.status != ContractStatus.DRAFT:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"只有草稿状态的合同可以提交审批，当前状态: {contract.status}"
        )
    
    existing_approval = approval_crud.get_by_contract_id(db, contract_id)
    if existing_approval and existing_approval.status == ApprovalStatus.PENDING:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="该合同已有审批流程，请等待审批完成"
        )
    
    flow = approval_flow_crud.match_flow(db, contract, contract.team_id)
    if not flow:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="未找到匹配的审批流程，请联系管理员配置"
        )
    
    try:
        approval = approval_crud.create_approval(
            db,
            contract,
            flow,
            str(current_user.id),
            current_user.name
        )
        
        from app.services.feishu import feishu_service
        if approval.current_node:
            approvers = get_approvers_by_role(db, approval.current_node.approve_role)
            for approver in approvers:
                await feishu_service.notify_approval_pending(
                    approver.feishu_open_id,
                    contract.contract_name,
                    flow.flow_name,
                    approval.current_node.node_name
                )
        
        db.refresh(approval)
        return approval
        
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"提交审批失败: {str(e)}"
        )


@router.post("/contracts/{contract_id}/approve", response_model=ApprovalDetailResponse, summary="审批通过/拒绝", description="""
对当前待审批的合同进行审批操作，支持通过或拒绝。

**功能说明：**
- 审批人可以对当前节点的合同进行审批
- 支持通过（APPROVE）和拒绝（REJECT）两种操作
- 通过后自动流转到下一节点或结束审批
- 拒绝后流程终止，合同需要重新提交

**业务场景：**
- 审批人对合同进行审批
- 多级审批链路逐级流转

**路径参数：**
- contract_id: 合同ID

**请求体字段：**
- action: 审批动作，APPROVE（通过）或REJECT（拒绝）
- comment: 审批意见（必填）

**权限要求：**
- 必须是当前审批节点的审批角色
- 如审批自己创建的合同，需要额外权限：contract:approve_own

**业务规则：**
- 只有当前节点对应的审批角色才能操作
- 通过后流转到下一审批节点
- 全部节点通过后合同状态变为已审批
- 拒绝后流程终止，合同回到草稿状态

**通知机制：**
- 通过且有下一节点：下一节点审批人收到通知
- 全部通过：合同创建人收到通过通知
- 拒绝：合同创建人收到拒绝通知及理由
""")
async def approve_contract(
    contract_id: int,
    action_request: ApprovalActionRequest,
    team_id: int = Depends(get_current_user_team),
    current_user = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    approval = approval_crud.get_by_contract_id(db, contract_id)
    if not approval:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="审批流程不存在"
        )

    if not approval.current_node:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="当前审批节点不存在"
        )

    user_roles = role_crud.get_user_roles(db, current_user.id, team_id)
    role_codes = {r.code for r in user_roles}
    
    if approval.current_node.approve_role not in role_codes:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"您没有权限进行此操作，需要角色: {approval.current_node.approve_role}"
        )
    
    contract = contract_crud.get_by_id(db, contract_id)
    if contract and contract.creator_id == str(current_user.id):
        from app.crud.permission import permission_crud
        user_permissions = permission_crud.get_user_permissions(db, current_user.id, team_id)
        permission_codes = {p.code for p in user_permissions}
        
        if "contract:approve_own" not in permission_codes:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="您没有权限审批自己创建的合同"
            )
    
    try:
        approval = approval_crud.approve(
            db,
            approval,
            action_request,
            str(current_user.id),
            current_user.name
        )
        
        from app.services.feishu import feishu_service
        
        if action_request.action.value == ApprovalAction.APPROVE:
            if approval.status == ApprovalStatus.APPROVED:
                await feishu_service.notify_approval_approved(
                    approval.submitter_id,
                    contract.contract_name
                )
            elif approval.current_node:
                approvers = get_approvers_by_role(db, approval.current_node.approve_role)
                for approver in approvers:
                    await feishu_service.notify_approval_pending(
                        approver.feishu_open_id,
                        contract.contract_name,
                        approval.flow.flow_name if approval.flow else "",
                        approval.current_node.node_name
                    )
        elif action_request.action.value == ApprovalAction.REJECT:
            await feishu_service.notify_approval_rejected(
                approval.submitter_id,
                contract.contract_name,
                action_request.comment or "无"
            )
        
        db.refresh(approval)
        return approval
        
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"审批操作失败: {str(e)}"
        )


@router.post("/contracts/{contract_id}/cancel", response_model=MessageResponse, summary="撤回审批", description="""
撤回正在审批中的合同，终止审批流程。

**功能说明：**
- 只有审批提交人可以撤回
- 只能撤回待审批状态的流程
- 撤回后合同回到草稿状态
- 可以修改后重新提交

**业务场景：**
- 发现提交的合同有误，需要修改
- 暂时不需要审批，撤回后稍后再提交

**路径参数：**
- contract_id: 合同ID

**业务规则：**
- 只有审批创建者（提交人）可以撤回
- 只能撤回待审批（PENDING）状态的流程
- 已审批完成或已拒绝的流程无法撤回

**返回信息：**
- 成功：返回"审批已撤回"
- 失败：返回具体错误信息
""")
def cancel_approval(
    contract_id: int,
    current_user = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    approval = approval_crud.get_by_contract_id(db, contract_id)
    if not approval:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="审批流程不存在"
        )
    
    try:
        approval = approval_crud.cancel(db, approval, str(current_user.id))
        return MessageResponse(message="审批已撤回")
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"撤回审批失败: {str(e)}"
        )


@router.get("/contracts/{contract_id}/detail", response_model=ApprovalDetailResponse, summary="获取审批详情", description="""
获取合同审批流程的完整详情，包括所有审批记录和当前状态。

**功能说明：**
- 查看合同的完整审批链路
- 显示所有节点的审批记录
- 显示当前审批进度和状态
- 包含每个审批人的意见和操作时间

**业务场景：**
- 审批人查看合同审批历史
- 了解当前审批进度
- 查看其他审批人的意见

**路径参数：**
- contract_id: 合同ID

**返回字段：**
- 基本信息：审批ID、状态、提交时间等
- flow: 审批流程信息
- current_node: 当前待审批节点
- records: 审批记录列表
  - node_name: 节点名称
  - approver_name: 审批人姓名
  - action: 审批动作（APPROVE/REJECT）
  - comment: 审批意见
  - created_at: 审批时间

**状态说明：**
- PENDING: 待审批
- APPROVED: 已通过
- REJECTED: 已拒绝
- CANCELLED: 已撤回
""")
def get_approval_detail(
    contract_id: int,
    current_user = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    approval = approval_crud.get_by_contract_id(db, contract_id)
    if not approval:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="审批流程不存在"
        )
    
    return approval


def get_approvers_by_role(db: Session, role_code: str):
    from app.crud.user import user_crud
    from app.crud.role import role_crud
    
    role = role_crud.get_by_code(db, role_code)
    if not role:
        return []
    
    users = role_crud.get_role_users(db, role.id)
    return users
