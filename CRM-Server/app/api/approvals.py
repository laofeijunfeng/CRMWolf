from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session
from sqlalchemy import text
from typing import List, Optional

from app.core.database import get_db
from app.core.deps import get_current_active_user, get_current_user_team
from app.core.logging import get_logger, log_with_fields
from app.crud.contract import contract_crud
from app.crud.approval import approval_flow_crud, approval_crud
from app.crud.role import role_crud
from app.crud.user import user_crud
from app.models.approval import ApprovalStatus, ApprovalAction
from app.models.contract import ContractStatus
from app.schemas.approval import (
    ApprovalFlowCreate, ApprovalFlowUpdate, ApprovalFlowResponse, ApprovalFlowDetailResponse,
    ApprovalSubmitRequest, ApprovalActionRequest, ApprovalDetailResponse, ApprovalListResponse,
    ApprovalRecordResponse, MessageResponse, OverdueApprovalResponse, OverdueApprovalListResponse
)
from app.services.notification import notification_service_factory


router = APIRouter(prefix="/v1/approvals", tags=["审批管理"])

# 审批操作日志记录器
logger = get_logger(__name__)


def log_approval_operation(
    operation: str,
    approval_id: Optional[int] = None,
    contract_id: Optional[int] = None,
    flow_name: Optional[str] = None,
    node_name: Optional[str] = None,
    operator: Optional[str] = None,
    next_node: Optional[str] = None,
    flow_direction: Optional[str] = None,
    notification_status: Optional[str] = None,
    reason: Optional[str] = None,
    level: int = 20  # INFO
):
    """
    记录审批操作日志

    Args:
        operation: 操作类型（Submit/Approve/Reject/Cancel）
        approval_id: 审批实例ID
        contract_id: 合同ID
        flow_name: 审批流程名称
        node_name: 当前节点名称
        operator: 操作人姓名
        next_node: 下一节点名称
        flow_direction: 流转方向（next_node/terminated/completed）
        notification_status: 通知发送状态（success/failed/skipped）
        reason: 拒绝/撤回原因
        level: 日志级别（默认 INFO）
    """
    message = f"[Approval] {operation}"

    fields = {}
    if contract_id:
        fields["contract_id"] = contract_id
    if approval_id:
        fields["approval_id"] = approval_id
    if flow_name:
        fields["flow"] = flow_name
    if node_name:
        fields["node"] = node_name
    if operator:
        fields["operator"] = operator
    if next_node:
        fields["next_node"] = next_node
    if flow_direction:
        fields["direction"] = flow_direction
    if notification_status:
        fields["notification"] = notification_status
    if reason:
        fields["reason"] = reason

    log_with_fields(logger, level, message, **fields)


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


@router.get("/overdue", response_model=OverdueApprovalListResponse, summary="获取超时审批列表", description="""
获取所有超时的审批实例列表，供管理员进行应急处理。

**功能说明：**
- 查询所有状态为 PENDING 且超过指定小时数的审批
- 默认查询超过 48 小时的审批
- 支持按超时程度筛选（24h/48h/72h）
- 超时时间最长的排在最前面

**业务场景：**
- 管理员查看超时审批进行应急处理
- 批量发送催办通知
- 介入处理卡住的审批流程

**请求参数：**
- min_hours: 最小超时小时数（默认48小时）
- skip: 跳过记录数（默认0）
- limit: 每页记录数（默认100）

**返回字段：**
- items: 超时审批列表
  - approval_id: 审批实例ID
  - contract_id: 合同ID
  - contract_name: 合同名称
  - contract_number: 合同编号
  - current_node_name: 当前审批节点名称
  - current_approver_name: 当前审批人姓名
  - overdue_hours: 超时小时数
  - submitter_name: 提交人姓名
  - submit_time: 提交时间
  - status: 审批状态
- total: 总记录数

**权限要求：**
- 需要管理员权限或 approval:flow:view 权限
""")
def get_overdue_approvals(
    min_hours: int = Query(48, ge=1, le=720, description="最小超时小时数，默认48小时，可选24/48/72"),
    skip: int = Query(0, ge=0, description="跳过记录数"),
    limit: int = Query(100, ge=1, le=100, description="每页记录数"),
    team_id: int = Depends(get_current_user_team),
    current_user = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """
    获取超时审批列表

    管理员应急操作指南：
    1. 查看超时审批列表，了解哪些审批卡住了
    2. 批量发送催办通知给审批人
    3. 或联系审批人/提交人进行处理
    4. 必要时可撤回审批让提交人重新提交
    """
    overdue_list, total = approval_crud.get_overdue_approvals(
        db,
        team_id,
        min_hours,
        skip,
        limit
    )

    return OverdueApprovalListResponse(
        items=[OverdueApprovalResponse(**item) for item in overdue_list],
        total=total
    )


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
    team_id: int = Depends(get_current_user_team),
    current_user = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    flow = approval_flow_crud.get_by_id(db, flow_id, team_id)
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
    team_id: int = Depends(get_current_user_team),
    current_user = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    from app.core.deps import require_permission

    permission_checker = require_permission("approval:flow:update")
    permission_checker(current_user, db)

    flow = approval_flow_crud.get_by_id(db, flow_id, team_id)
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
    team_id: int = Depends(get_current_user_team),
    current_user = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    contract = contract_crud.get_by_id(db, contract_id, team_id)
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

    existing_approval = approval_crud.get_by_contract_id(db, contract_id, team_id)
    if existing_approval and existing_approval.status == ApprovalStatus.PENDING:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="该合同已有审批流程，请等待审批完成"
        )
    
    flow, error_msg = approval_flow_crud.match_flow(db, contract, contract.team_id)
    if not flow:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=error_msg or "未找到匹配的审批流程，请联系管理员配置"
        )

    # 检查第一个审批节点是否有审批人
    from app.models.approval import ApprovalNode
    first_node = db.query(ApprovalNode).filter(
        ApprovalNode.flow_id == flow.id,
        ApprovalNode.node_order == 1
    ).first()

    if first_node:
        has_approvers = approval_flow_crud.check_node_has_approvers(db, first_node.id, team_id)
        if not has_approvers:
            # 记录系统告警日志
            log_with_fields(
                logger,
                level=30,  # WARNING
                message="[Approval Config Error] 审批节点无审批人",
                flow_id=flow.id,
                flow_name=flow.flow_name,
                node_id=first_node.id,
                node_name=first_node.node_name,
                approve_role=first_node.approve_role or "",
                team_id=team_id,
                contract_id=contract_id
            )
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"审批流程配置错误：节点「{first_node.node_name}」无审批人，请联系管理员"
            )

    try:
        approval = approval_crud.create_approval(
            db,
            contract,
            flow,
            str(current_user.id),
            current_user.name
        )

        # 记录提交日志
        log_approval_operation(
            operation="Submit",
            approval_id=approval.id,
            contract_id=contract_id,
            flow_name=flow.flow_name,
            node_name=approval.current_node.node_name if approval.current_node else None,
            operator=current_user.name,
            flow_direction="submitted"
        )

        notification_service = notification_service_factory(db, team_id)
        notification_status = "skipped"

        if approval.current_node:
            approvers = get_approvers_by_role(db, approval.current_node.approve_role)
            try:
                for approver in approvers:
                    await notification_service.notify_approval_pending(
                        contract_name=contract.contract_name,
                        flow_name=flow.flow_name,
                        node_name=approval.current_node.node_name,
                        approver_open_id=approver.feishu_open_id or "",
                        approver_name=approver.name,
                        contract_id=contract_id
                    )
                notification_status = "success" if approvers else "skipped"
            except Exception as notify_error:
                notification_status = "failed"
                logger.error(
                    f"[Approval] Submit notification failed: contract_id={contract_id}, error={str(notify_error)}"
                )

            # 更新日志补充通知状态
            log_approval_operation(
                operation="Submit",
                approval_id=approval.id,
                contract_id=contract_id,
                flow_name=flow.flow_name,
                node_name=approval.current_node.node_name,
                operator=current_user.name,
                flow_direction="submitted",
                notification_status=notification_status
            )

        db.refresh(approval)
        return approval

    except ValueError as e:
        log_approval_operation(
            operation="Submit",
            contract_id=contract_id,
            operator=current_user.name,
            reason=str(e),
            level=40  # ERROR
        )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except Exception as e:
        log_approval_operation(
            operation="Submit",
            contract_id=contract_id,
            operator=current_user.name,
            reason=str(e),
            level=40  # ERROR
        )
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
- 如审批自己创建的合同，需要额外权限：contract:approve:own

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
    approval = approval_crud.get_by_contract_id(db, contract_id, team_id)
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
    
    contract = contract_crud.get_by_id(db, contract_id, team_id)
    if contract and contract.creator_id == str(current_user.id):
        from app.crud.permission import permission_crud
        user_permissions = permission_crud.get_user_permissions(db, current_user.id, team_id)
        permission_codes = {p.code for p in user_permissions}
        
        if "contract:approve:own" not in permission_codes:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="您没有权限审批自己创建的合同"
            )

    # 如果是审批通过操作，检查下一节点是否有审批人
    if action_request.action.value == ApprovalAction.APPROVE:
        from app.models.approval import ApprovalNode
        next_node = db.query(ApprovalNode).filter(
            ApprovalNode.flow_id == approval.flow_id,
            ApprovalNode.node_order == approval.current_node.node_order + 1
        ).first()

        if next_node:
            has_approvers = approval_flow_crud.check_node_has_approvers(db, next_node.id, team_id)
            if not has_approvers:
                # 记录系统告警日志
                log_with_fields(
                    logger,
                    level=30,  # WARNING
                    message="[Approval Config Error] 审批节点无审批人",
                    flow_id=approval.flow_id,
                    flow_name=approval.flow.flow_name if approval.flow else "",
                    node_id=next_node.id,
                    node_name=next_node.node_name,
                    approve_role=next_node.approve_role or "",
                    team_id=team_id,
                    contract_id=contract_id,
                    current_node=approval.current_node.node_name
                )
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"无法流转到下一节点：审批角色「{next_node.node_name}」无成员，系统已通知管理员"
                )

    try:
        approval = approval_crud.approve(
            db,
            approval,
            action_request,
            str(current_user.id),
            current_user.name
        )

        notification_service = notification_service_factory(db, team_id)

        if action_request.action.value == ApprovalAction.APPROVE:
            if approval.status == ApprovalStatus.APPROVED:
                # 获取提交人的 feishu_open_id
                submitter = user_crud.get_by_id(db, int(approval.submitter_id))
                submitter_open_id = submitter.feishu_open_id if submitter else ""
                await notification_service.notify_approval_approved(
                    submitter_open_id=submitter_open_id,
                    contract_name=contract.contract_name,
                    contract_id=contract_id
                )
            elif approval.current_node:
                approvers = get_approvers_by_role(db, approval.current_node.approve_role)
                for approver in approvers:
                    await notification_service.notify_approval_pending(
                        contract_name=contract.contract_name,
                        flow_name=approval.flow.flow_name if approval.flow else "",
                        node_name=approval.current_node.node_name,
                        approver_open_id=approver.feishu_open_id or "",
                        approver_name=approver.name,
                        contract_id=contract_id
                    )
        elif action_request.action.value == ApprovalAction.REJECT:
            # 获取提交人的 feishu_open_id
            submitter = user_crud.get_by_id(db, int(approval.submitter_id))
            submitter_open_id = submitter.feishu_open_id if submitter else ""
            await notification_service.notify_approval_rejected(
                submitter_open_id=submitter_open_id,
                contract_name=contract.contract_name,
                reject_reason=action_request.comment or "无",
                contract_id=contract_id
            )

        db.refresh(approval)
        return approval

    except ValueError as e:
        # 乐观锁冲突返回 409
        if "审批已被其他用户处理" in str(e):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="该审批已被处理，请刷新页面查看最新状态"
            )
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
    team_id: int = Depends(get_current_user_team),
    current_user = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    approval = approval_crud.get_by_contract_id(db, contract_id, team_id)
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
    team_id: int = Depends(get_current_user_team),
    current_user = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    approval = approval_crud.get_by_contract_id(db, contract_id, team_id)
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
