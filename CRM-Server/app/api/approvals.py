from fastapi import APIRouter, Depends, HTTPException, status, Query, File, UploadFile, Form
from sqlalchemy.orm import Session
from sqlalchemy import text, func
from typing import List, Optional

from app.core.database import get_db
from app.core.deps import get_current_active_user, get_current_user_team, require_permission
from app.core.logging import get_logger, log_with_fields
from app.crud.contract import contract_crud
from app.crud.approval import approval_flow_crud, approval_crud
from app.crud.role import role_crud
from app.crud.user import user_crud
from app.models.approval import Approval, ApprovalStatus, ApprovalAction, ApprovalRecord
from app.models.contract import ContractStatus
from app.models.invoice import InvoiceApplicationStatus
from app.models.user import User
from app.schemas.approval import (
    ApprovalFlowCreate, ApprovalFlowUpdate, ApprovalFlowResponse, ApprovalFlowDetailResponse,
    ApprovalSubmitRequest, ApprovalActionRequest, ApprovalDetailResponse, ApprovalListResponse,
    ApprovalRecordResponse, MessageResponse, OverdueApprovalResponse, OverdueApprovalListResponse
)
from app.schemas.approval_generic import (
    ApprovalSubmitRequest as GenericApprovalSubmitRequest,
    GenericApprovalSubmitResponse,
    BulkApproveRequest,
    BulkApproveResponse,
    BulkApproveFailedItem,
    ApprovalListItemResponse,
    ApprovalGenericListResponse,
)
from app.constants.business_types import is_valid_business_type, BusinessType
from app.services.approval_adapter import get_adapter
from app.services.notification import notification_service_factory
from app.services.file_storage import file_storage_service, FileStorageError
from datetime import datetime as _datetime


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
    level: int = 20,  # INFO
    business_type: Optional[str] = None,
    business_id: Optional[int] = None,
):
    """
    记录审批操作日志

    Args:
        operation: 操作类型（Submit/Approve/Reject/Cancel/BulkApprove）
        approval_id: 审批实例ID
        contract_id: 合同ID（CONTRACT 类型沿用，向下兼容）
        flow_name: 审批流程名称
        node_name: 当前节点名称
        operator: 操作人姓名
        next_node: 下一节点名称
        flow_direction: 流转方向（next_node/terminated/completed）
        notification_status: 通知发送状态（success/failed/skipped）
        reason: 拒绝/撤回原因
        level: 日志级别（默认 INFO）
        business_type: 业务单据类型（A6 通用端点：CONTRACT/PAYMENT/INVOICE）
        business_id: 业务单据ID（A6 通用端点）
    """
    message = f"[Approval] {operation}"

    fields = {}
    # A6 通用端点用 business_type / business_id；CONTRACT 旧端点仍写 contract_id
    if business_type:
        fields["business_type"] = business_type
    if business_id:
        fields["business_id"] = business_id
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
    current_user = Depends(require_permission("approval:flow:create")),
    db: Session = Depends(get_db)
):
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
- 需要 TEAM_ADMIN 角色 **或** approval:flow:edit 权限

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
    # 权限检查：TEAM_ADMIN 或 approval:flow:edit
    from app.crud.role import role_crud
    from app.crud.permission import permission_crud

    user_roles = role_crud.get_user_roles(db, current_user.id, team_id)
    role_codes = {r.code for r in user_roles}

    # 检查是否为 TEAM_ADMIN
    if "TEAM_ADMIN" not in role_codes:
        # 检查是否有 approval:flow:edit 权限
        user_permissions = permission_crud.get_user_permissions(db, current_user.id, team_id)
        permission_codes = {p.code for p in user_permissions}

        if "approval:flow:edit" not in permission_codes:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="您没有权限更新审批流程（需要 TEAM_ADMIN 角色或 approval:flow:edit 权限）"
            )
    flow = approval_flow_crud.get_by_id(db, flow_id, team_id)
    if not flow:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="审批流程不存在"
        )

    # 记录禁用流程操作日志
    if flow_data.is_active is not None:
        old_is_active = flow.is_active
        new_is_active = flow_data.is_active

        # 禁用流程时记录日志
        if old_is_active == 1 and new_is_active == 0:
            log_with_fields(
                logger,
                level=20,  # INFO
                message="[Approval Flow Disabled] 管理员禁用审批流程",
                flow_id=flow_id,
                flow_name=flow.flow_name,
                flow_code=flow.flow_code,
                operator=current_user.name,
                operator_id=current_user.id,
                team_id=team_id,
                old_status="启用",
                new_status="禁用",
                note="已有审批实例继续执行，新提交审批不会匹配该流程"
            )
        # 启用流程时记录日志
        elif old_is_active == 0 and new_is_active == 1:
            log_with_fields(
                logger,
                level=20,  # INFO
                message="[Approval Flow Enabled] 管理员启用审批流程",
                flow_id=flow_id,
                flow_name=flow.flow_name,
                flow_code=flow.flow_code,
                operator=current_user.name,
                operator_id=current_user.id,
                team_id=team_id,
                old_status="禁用",
                new_status="启用",
                note="新提交审批立即可以使用该流程"
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
                        entity_type=BusinessType.CONTRACT,
                        entity_name=contract.contract_name,
                        flow_name=flow.flow_name,
                        node_name=approval.current_node.node_name,
                        approver_open_id=approver.feishu_open_id or "",
                        approver_name=approver.name,
                        business_id=contract_id,
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

    _check_approve_permissions(
        db, approval, current_user, team_id,
        entity_type=BusinessType.CONTRACT, entity_id=contract_id,
    )

    # 如果是审批通过操作，检查下一节点是否有审批人
    if action_request.action.value == ApprovalAction.APPROVE:
        _check_next_node_has_approvers(
            db, approval, team_id,
            detail_suffix="无成员，系统已通知管理员",
            log_extra={
                "contract_id": contract_id,
                "current_node": approval.current_node.node_name,
            },
        )

    try:
        # 记录当前节点（审批前的状态）
        current_node_name = approval.current_node.node_name if approval.current_node else ""
        flow_name = approval.flow.flow_name if approval.flow else ""

        approval = approval_crud.approve(
            db,
            approval,
            action_request,
            str(current_user.id),
            current_user.name
        )

        notification_service = notification_service_factory(db, team_id)
        notification_status = "skipped"

        if action_request.action.value == ApprovalAction.APPROVE:
            if approval.status == ApprovalStatus.APPROVED:
                # 全部节点通过
                flow_direction = "completed"
                next_node = None
                # 获取提交人的 feishu_open_id
                submitter = user_crud.get_by_id(db, int(approval.submitter_id))
                submitter_open_id = submitter.feishu_open_id if submitter else ""
                try:
                    await notification_service.notify_approval_approved(
                        submitter_open_id=submitter_open_id,
                        entity_type=BusinessType.CONTRACT,
                        entity_name=contract.contract_name,
                        business_id=contract_id,
                    )
                    notification_status = "success"
                except Exception as notify_error:
                    notification_status = "failed"
                    logger.error(
                        f"[Approval] Approve notification failed: contract_id={contract_id}, error={str(notify_error)}"
                    )
            elif approval.current_node:
                # 流转到下一节点
                flow_direction = "next_node"
                next_node = approval.current_node.node_name
                approvers = get_approvers_by_role(db, approval.current_node.approve_role)
                try:
                    for approver in approvers:
                        await notification_service.notify_approval_pending(
                            entity_type=BusinessType.CONTRACT,
                            entity_name=contract.contract_name,
                            flow_name=approval.flow.flow_name if approval.flow else "",
                            node_name=approval.current_node.node_name,
                            approver_open_id=approver.feishu_open_id or "",
                            approver_name=approver.name,
                            business_id=contract_id,
                        )
                    notification_status = "success" if approvers else "skipped"
                except Exception as notify_error:
                    notification_status = "failed"
                    logger.error(
                        f"[Approval] Approve notification failed: contract_id={contract_id}, error={str(notify_error)}"
                    )
            else:
                flow_direction = "completed"
                next_node = None

            # 记录审批通过日志
            log_approval_operation(
                operation="Approve",
                approval_id=approval.id,
                contract_id=contract_id,
                flow_name=flow_name,
                node_name=current_node_name,
                operator=current_user.name,
                next_node=next_node,
                flow_direction=flow_direction,
                notification_status=notification_status
            )

        elif action_request.action.value == ApprovalAction.REJECT:
            # 拒绝审批
            flow_direction = "terminated"
            # 获取提交人的 feishu_open_id
            submitter = user_crud.get_by_id(db, int(approval.submitter_id))
            submitter_open_id = submitter.feishu_open_id if submitter else ""
            try:
                await notification_service.notify_approval_rejected(
                    submitter_open_id=submitter_open_id,
                    entity_type=BusinessType.CONTRACT,
                    entity_name=contract.contract_name,
                    reject_reason=action_request.comment or "无",
                    business_id=contract_id,
                )
                notification_status = "success"
            except Exception as notify_error:
                notification_status = "failed"
                logger.error(
                    f"[Approval] Reject notification failed: contract_id={contract_id}, error={str(notify_error)}"
                )

            # 记录审批拒绝日志
            log_approval_operation(
                operation="Reject",
                approval_id=approval.id,
                contract_id=contract_id,
                flow_name=flow_name,
                node_name=current_node_name,
                operator=current_user.name,
                flow_direction=flow_direction,
                notification_status=notification_status,
                reason=action_request.comment or "无"
            )

        db.refresh(approval)
        return approval

    except ValueError as e:
        # 乐观锁冲突返回 409
        if "审批已被其他用户处理" in str(e):
            log_approval_operation(
                operation="Approve",
                approval_id=approval.id if approval else None,
                contract_id=contract_id,
                operator=current_user.name,
                reason="乐观锁冲突：审批已被其他用户处理",
                level=40  # ERROR
            )
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="该审批已被处理，请刷新页面查看最新状态"
            )
        log_approval_operation(
            operation="Approve",
            approval_id=approval.id if approval else None,
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
            operation="Approve",
            approval_id=approval.id if approval else None,
            contract_id=contract_id,
            operator=current_user.name,
            reason=str(e),
            level=40  # ERROR
        )
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

    # 记录撤回前的状态
    current_node_name = approval.current_node.node_name if approval.current_node else ""
    flow_name = approval.flow.flow_name if approval.flow else ""

    try:
        approval = approval_crud.cancel(db, approval, str(current_user.id))

        # 记录撤回日志
        log_approval_operation(
            operation="Cancel",
            approval_id=approval.id,
            contract_id=contract_id,
            flow_name=flow_name,
            node_name=current_node_name,
            operator=current_user.name,
            flow_direction="cancelled"
        )

        return MessageResponse(message="审批已撤回")
    except ValueError as e:
        log_approval_operation(
            operation="Cancel",
            approval_id=approval.id if approval else None,
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
            operation="Cancel",
            approval_id=approval.id if approval else None,
            contract_id=contract_id,
            operator=current_user.name,
            reason=str(e),
            level=40  # ERROR
        )
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
- 显示审批流程是否被禁用的状态提示
- 显示审批人是否离职的状态标记

**业务场景：**
- 审批人查看合同审批历史
- 了解当前审批进度
- 查看其他审批人的意见
- 查看流程是否被禁用

**路径参数：**
- contract_id: 合同ID

**返回字段：**
- 基本信息：审批ID、状态、提交时间等
- flow: 审批流程信息
- flow_is_active: 审批流程是否启用（True-启用，False-禁用）
- flow_disabled_warning: 流程禁用提示信息（仅当流程被禁用时显示）
- current_node: 当前待审批节点
- records: 审批记录列表
  - node_name: 节点名称
  - approver_name: 审批人姓名（离职人员显示「姓名（已离职）」）
  - approver_status: 审批人状态（active/inactive/suspended）
  - approver_status_display: 审批人状态显示（在职/已离职/已停用）
  - action: 审批动作（APPROVE/REJECT）
  - comment: 审批意见
  - created_at: 审批时间

**状态说明：**
- PENDING: 待审批
- APPROVED: 已通过
- REJECTED: 已拒绝
- CANCELLED: 已撤回

**流程禁用处理（场景六）：**
- 已有审批实例继续执行现有流程（不受影响）
- 新提交审批不匹配已禁用流程
- 流程恢复启用后立即生效
""")
def get_approval_detail(
    contract_id: int,
    team_id: int = Depends(get_current_user_team),
    current_user = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    from app.models.user import User, UserStatus

    approval = approval_crud.get_by_contract_id(db, contract_id, team_id)
    if not approval:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="审批流程不存在"
        )

    # 获取审批记录并填充审批人状态信息
    records = approval_crud.get_records(db, approval.id)

    # 收集所有审批人ID，批量查询用户状态
    approver_ids = [int(r.approver_id) for r in records if r.approver_id]
    users = {}
    if approver_ids:
        user_list = db.query(User).filter(User.id.in_(approver_ids)).all()
        users = {str(u.id): u for u in user_list}

    # 构建审批记录响应（含审批人状态）
    record_responses = []
    for record in records:
        user = users.get(record.approver_id)
        approver_status = None
        approver_status_display = None
        approver_name = record.approver_name

        if user:
            approver_status = user.status.value if user.status else None
            # 状态显示：active=在职，inactive=已离职，suspended=已停用
            status_display_map = {
                UserStatus.ACTIVE: "在职",
                UserStatus.INACTIVE: "已离职",
                UserStatus.SUSPENDED: "已停用"
            }
            approver_status_display = status_display_map.get(user.status)
            # 如果审批人已离职，显示姓名时添加「已离职」标记
            if user.status == UserStatus.INACTIVE and approver_name:
                approver_name = f"{approver_name}（已离职）"

        record_responses.append(
            ApprovalRecordResponse(
                id=record.id,
                approval_id=record.approval_id,
                node_id=record.node_id,
                node_name=record.node.node_name if record.node else None,
                approver_id=record.approver_id,
                approver_name=approver_name,
                approver_status=approver_status,
                approver_status_display=approver_status_display,
                action=record.action,
                comment=record.comment,
                created_time=record.created_time
            )
        )

    # 检查流程是否被禁用，添加提示信息
    flow_is_active = None
    flow_disabled_warning = None

    if approval.flow:
        flow_is_active = approval.flow.is_active == 1
        if not flow_is_active:
            flow_disabled_warning = "审批流程已被管理员禁用，当前审批将继续执行，但新提交审批不会使用该流程"

    # 构建审批详情响应
    return ApprovalDetailResponse(
        id=approval.id,
        contract_id=approval.contract_id,
        flow_id=approval.flow_id,
        flow_name=approval.flow.flow_name if approval.flow else None,
        current_node_id=approval.current_node_id,
        current_node_name=approval.current_node.node_name if approval.current_node else None,
        status=approval.status,
        submitter_id=approval.submitter_id,
        submitter_name=approval.submitter_name,
        created_time=approval.created_time,
        updated_time=approval.updated_time,
        flow=approval.flow,
        flow_is_active=flow_is_active,
        flow_disabled_warning=flow_disabled_warning,
        records=record_responses
    )


def get_approvers_by_role(db: Session, role_code: str):
    from app.crud.user import user_crud
    from app.crud.role import role_crud

    role = role_crud.get_by_code(db, role_code)
    if not role:
        return []

    users = role_crud.get_role_users(db, role.id)
    return users


# 自审追加权限校验失败文案（按 entity_type 分发）。
# CONTRACT 文案与改造前逐字一致（E1 合同回归）；PAYMENT/INVOICE 按 M-3 规范。
_SELF_APPROVE_DENY_MSG = {
    BusinessType.CONTRACT: "您没有权限审批自己创建的合同",
    BusinessType.PAYMENT: "您没有权限审批自己创建的回款",
    BusinessType.INVOICE: "您没有权限审批自己创建的发票",
}


def _check_self_approval_permission(
    db: Session,
    current_user,
    team_id: int,
    entity_type: str,
    entity_id: int,
) -> None:
    """自审追加权限校验：审批人 == 单据提交人时需 `<resource>:approve:own` 权限码。

    泛化自原 CONTRACT 自审校验（contract.creator_id + contract:approve:own），
    按 entity_type 分发到 A4 适配器取实体 / 提交人，避免在 API 层硬编码各模型
    字段名（CONTRACT/PAYMENT→creator_id，INVOICE→applicant_id）。

    - entity 为 None（单据已删 / 跨 team）时跳过（对齐原 `if contract and ...` 语义）
    - 提交人 id == str(current_user.id) 视为自审，查用户权限码，
      缺 `<resource>:approve:own`（contract/payment/invoice）→ 403
    - 重复查 DB（approve 端点已取过 entity）可接受——审批非高频，留 M-1 一并优化
    """
    adapter = get_adapter(entity_type)
    entity = adapter.get_entity(db, entity_id, team_id)
    if entity is None:
        return
    submitter_id, _ = adapter.get_submitter(entity)
    if submitter_id != str(current_user.id):
        return
    from app.crud.permission import permission_crud
    user_permissions = permission_crud.get_user_permissions(
        db, current_user.id, team_id
    )
    permission_codes = {p.code for p in user_permissions}
    required_code = f"{entity_type.lower()}:approve:own"
    if required_code not in permission_codes:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=_SELF_APPROVE_DENY_MSG[entity_type],
        )


def _check_approve_permissions(
    db: Session,
    approval: Approval,
    current_user,
    team_id: int,
    *,
    entity_type: Optional[str] = None,
    entity_id: Optional[int] = None,
) -> None:
    """审批权限校验（旧 `/contracts/{id}/approve` 与新 generic approve 共用）。

    - 角色校验：current_node.approve_role 不在 current_user 角色集 → 403
    - 自审追加：current_user 是单据提交人时需 `<resource>:approve:own` 权限 → 403
      （CONTRACT/PAYMENT/INVOICE 均校验，泛化自原 CONTRACT-only 逻辑，M-3）

    旧合同端点传 entity_type=BusinessType.CONTRACT / entity_id=contract_id；
    新通用端点传路由参数 entity_type / entity_id。
    """
    user_roles = role_crud.get_user_roles(db, current_user.id, team_id)
    role_codes = {r.code for r in user_roles}

    if approval.current_node.approve_role not in role_codes:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"您没有权限进行此操作，需要角色: {approval.current_node.approve_role}",
        )

    # 自审追加权限校验（CONTRACT/PAYMENT/INVOICE 通用，M-3 泛化）
    if entity_type is not None and entity_id is not None:
        _check_self_approval_permission(
            db, current_user, team_id, entity_type, entity_id
        )


def _check_next_node_has_approvers(
    db: Session,
    approval: Approval,
    team_id: int,
    *,
    detail_suffix: str = "无成员",
    log_extra: Optional[dict] = None,
) -> None:
    """APPROVE 时检查下一节点是否有审批人（旧 `approve_contract` 与新 generic approve 共用）。

    查询 node_order+1 的下一节点；若存在但无审批成员 → 记 WARNING 日志 + 400。
    log_extra 用于补充两处调用方各自的上下文字段（旧端点写 contract_id/current_node，
    新端点写 business_type/business_id）。
    """
    from app.models.approval import ApprovalNode

    next_node = db.query(ApprovalNode).filter(
        ApprovalNode.flow_id == approval.flow_id,
        ApprovalNode.node_order == approval.current_node.node_order + 1,
    ).first()

    if not next_node:
        return

    if approval_flow_crud.check_node_has_approvers(db, next_node.id, team_id):
        return

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
        **(log_extra or {}),
    )
    raise HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST,
        detail=f"无法流转到下一节点：审批角色「{next_node.node_name}」{detail_suffix}",
    )


# ============================================================================
# Task A6：通用审批 API 端点（CONTRACT / PAYMENT / INVOICE 统一入口）
# ============================================================================
# 设计要点：
# - 新端点 prefix 沿用既有 router 的 `/v1/approvals`
# - entity_type 用 is_valid_business_type（A1）校验，非法 → 400
# - submit：取 adapter.get_entity → None 时 404；match_flow_generic
#   （决策1：CONTRACT 未匹配报错 / PAYMENT·INVOICE 未匹配直通即免审批）；
#   建 Approval（create_approval_generic）；通知留 TODO 由 Task A8 泛化
# - approve：get_by_entity 取审批实例 → 复用既有 :611-619 角色校验逻辑
#   → approval_crud.approve(...) → D3 端点回写：business_type==INVOICE 时
#   由端点补写 reviewer_id / review_comment 两字段（不扩适配器签名）
# - cancel：approval_crud.cancel 内部校验 submitter_id==user_id
# - detail：get_by_entity → 序列化返回
# - /bulk-approve（E6）：逐条独立事务，部分成功汇总，不整体事务
# - 旧 `/contracts/{contract_id}/submit|approve|cancel|detail` 保留为 wrapper，
#   合同回归契约（E1）由此保证。
# ============================================================================


def _serialize_generic_approval(approval: Approval, db: Session) -> dict:
    """通用审批实例序列化 —— 不依赖 contract_id（INVOICE/PAYMENT 该字段为 None）。

    复刻 `/contracts/{contract_id}/detail`（:950-1039）关键字段，但 contract_id 可空、
    并补 business_type / business_id。审批人状态展示（在职/离职）由 A8 通知泛化时
    统一加，此处先返回基础字段，保证前端通用审批页可用。
    """
    from app.models.user import User, UserStatus

    records = approval_crud.get_records(db, approval.id)

    approver_ids = []
    for r in records:
        if r.approver_id and str(r.approver_id).isdigit():
            approver_ids.append(int(r.approver_id))
    users: dict = {}
    if approver_ids:
        user_list = db.query(User).filter(User.id.in_(approver_ids)).all()
        users = {str(u.id): u for u in user_list}

    status_display_map = {
        UserStatus.ACTIVE: "在职",
        UserStatus.INACTIVE: "已离职",
        UserStatus.SUSPENDED: "已停用",
    }

    record_list = []
    for record in records:
        user = users.get(str(record.approver_id)) if record.approver_id else None
        approver_name = record.approver_name
        approver_status = None
        approver_status_display = None
        if user:
            approver_status = user.status.value if user.status else None
            approver_status_display = status_display_map.get(user.status)
            if user.status == UserStatus.INACTIVE and approver_name:
                approver_name = f"{approver_name}（已离职）"
        record_list.append({
            "id": record.id,
            "approval_id": record.approval_id,
            "node_id": record.node_id,
            "node_name": record.node.node_name if record.node else None,
            "approver_id": record.approver_id,
            "approver_name": approver_name,
            "approver_status": approver_status,
            "approver_status_display": approver_status_display,
            "action": record.action,
            "comment": record.comment,
            "created_time": record.created_time,
        })

    flow_is_active = None
    flow_disabled_warning = None
    if approval.flow:
        flow_is_active = approval.flow.is_active == 1
        if not flow_is_active:
            flow_disabled_warning = (
                "审批流程已被管理员禁用，当前审批将继续执行，但新提交审批不会使用该流程"
            )

    return {
        "id": approval.id,
        "business_type": approval.business_type,
        "business_id": approval.business_id,
        "contract_id": approval.contract_id,
        "flow_id": approval.flow_id,
        "flow_name": approval.flow.flow_name if approval.flow else None,
        "current_node_id": approval.current_node_id,
        "current_node_name": approval.current_node.node_name if approval.current_node else None,
        "status": approval.status,
        "submitter_id": approval.submitter_id,
        "submitter_name": approval.submitter_name,
        "created_time": approval.created_time,
        "updated_time": approval.updated_time,
        "flow_is_active": flow_is_active,
        "flow_disabled_warning": flow_disabled_warning,
        "records": record_list,
    }


def _validate_entity_type(entity_type: str) -> None:
    """entity_type 校验：非法 → 400。统一守卫，避免每个端点重复。"""
    if not is_valid_business_type(entity_type):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"无效的业务单据类型: {entity_type}，仅支持 CONTRACT / PAYMENT / INVOICE",
        )


@router.post(
    "/{entity_type}/{entity_id}/submit",
    response_model=GenericApprovalSubmitResponse,
    summary="提交审批（通用）",
    description="""
将草稿状态的业务单据（合同/回款/发票）提交到审批流程，统一入口。

**功能说明：**
- 按 entity_type 走对应适配器取实体；不存在 → 404
- match_flow_generic 匹配审批流程：
  - CONTRACT：未匹配报错（沿用合同原语义）
  - PAYMENT/INVOICE：未匹配直通（决策1：免审批）
- 创建审批实例（create_approval_generic），状态置 PENDING
- 通知由 Task A8 泛化，本端点暂不发送

**路径参数：**
- entity_type: CONTRACT / PAYMENT / INVOICE
- entity_id: 业务单据 ID
""",
)
async def submit_generic_approval(
    entity_type: str,
    entity_id: int,
    submit_data: GenericApprovalSubmitRequest,
    db: Session = Depends(get_db),
    team_id: int = Depends(get_current_user_team),
    current_user=Depends(get_current_active_user),
):
    _validate_entity_type(entity_type)

    adapter = get_adapter(entity_type)
    entity = adapter.get_entity(db, entity_id, team_id)
    if entity is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="业务单据不存在",
        )

    flow, err = approval_flow_crud.match_flow_generic(
        db, entity_type, team_id, **adapter.match_kwargs(entity)
    )
    if flow is None and err:
        # CONTRACT 未匹配分支：err 非空 → 报错阻断
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=err or "未匹配到审批流程",
        )
    if flow is None:
        # PAYMENT/INVOICE 未匹配分支：决策1 直通，无审批流程即免审批
        # 返回 approval_id=0 + status=APPROVED 标识"免审批直通"语义；
        # 业务侧据 business_id 与 status 自行处理单据后续状态（由适配器 on_submit
        # 在 create_approval_generic 中已切，本分支不切单据状态，保留原 DRAFT）。
        return GenericApprovalSubmitResponse(approval_id=0, status="APPROVED")

    submitter_id, submitter_name = adapter.get_submitter(entity)

    try:
        ap = approval_crud.create_approval_generic(
            db, entity_type, entity_id, team_id, flow,
            submitter_id, submitter_name,
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )

    log_approval_operation(
        operation="Submit",
        approval_id=ap.id,
        flow_name=flow.flow_name,
        node_name=ap.current_node.node_name if ap.current_node else None,
        operator=current_user.name,
        flow_direction="submitted",
        business_type=entity_type,
        business_id=entity_id,
    )

    # 通知泛化（A8）：按 entity_type 走适配器取展示名，分发给当前节点审批人
    notification_service = notification_service_factory(db, team_id)
    notification_status = "skipped"
    if ap.current_node:
        approvers = get_approvers_by_role(db, ap.current_node.approve_role)
        try:
            entity_name = adapter.get_name(entity)
            for approver in approvers:
                await notification_service.notify_approval_pending(
                    entity_type=entity_type,
                    entity_name=entity_name,
                    flow_name=flow.flow_name,
                    node_name=ap.current_node.node_name,
                    approver_open_id=approver.feishu_open_id or "",
                    approver_name=approver.name,
                    business_id=entity_id,
                )
            notification_status = "success" if approvers else "skipped"
        except Exception as notify_error:
            notification_status = "failed"
            logger.error(
                f"[Approval] Submit notification failed: entity_type={entity_type}, "
                f"business_id={entity_id}, error={str(notify_error)}"
            )
        log_approval_operation(
            operation="Submit",
            approval_id=ap.id,
            flow_name=flow.flow_name,
            node_name=ap.current_node.node_name,
            operator=current_user.name,
            flow_direction="submitted",
            notification_status=notification_status,
            business_type=entity_type,
            business_id=entity_id,
        )

    return GenericApprovalSubmitResponse(approval_id=ap.id, status=ap.status)


@router.post(
    "/{entity_type}/{entity_id}/approve",
    summary="审批通过/拒绝（通用）",
    description="""
对当前待审批的业务单据（合同/回款/发票）进行审批操作。

**功能说明：**
- get_by_entity 取审批实例；不存在 → 404
- 复用既有 :611-619 角色校验：current_node.approve_role 不在用户角色集 → 403
- approval_crud.approve(...) 内部已调适配器 on_approved/on_rejected 切单据状态
  （INVOICE 写 status / reviewed_time；PAYMENT 写 confirmation_status；CONTRACT 写 status）
- **D3 端点回写**：business_type==INVOICE 时，由本端点补写 reviewer_id / review_comment
  两字段（不扩适配器签名，Pre-Flight 定案）
- 通知由 Task A8 泛化，本端点暂不发送
""",
)
async def approve_generic_approval(
    entity_type: str,
    entity_id: int,
    action_request: ApprovalActionRequest,
    db: Session = Depends(get_db),
    team_id: int = Depends(get_current_user_team),
    current_user=Depends(get_current_active_user),
):
    _validate_entity_type(entity_type)

    approval = approval_crud.get_by_entity(db, entity_type, entity_id, team_id)
    if not approval:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="审批流程不存在",
        )
    if not approval.current_node:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="当前审批节点不存在",
        )

    # 角色校验 + CONTRACT 自审追加权限校验（与既有 approve_contract 共用 helper）
    _check_approve_permissions(
        db, approval, current_user, team_id,
        entity_type=entity_type, entity_id=entity_id,
    )

    # APPROVE 时检查下一节点是否有审批人（与既有 approve_contract 共用 helper）
    if action_request.action.value == ApprovalAction.APPROVE:
        _check_next_node_has_approvers(
            db, approval, team_id,
            detail_suffix="无成员",
            log_extra={"business_type": entity_type, "business_id": entity_id},
        )

    current_node_name = approval.current_node.node_name if approval.current_node else ""
    flow_name = approval.flow.flow_name if approval.flow else ""

    try:
        approval = approval_crud.approve(
            db,
            approval,
            action_request,
            str(current_user.id),
            current_user.name,
        )
    except ValueError as e:
        if "审批已被其他用户处理" in str(e):
            log_approval_operation(
                operation="Approve",
                approval_id=approval.id,
                business_type=entity_type,
                business_id=entity_id,
                operator=current_user.name,
                reason="乐观锁冲突：审批已被其他用户处理",
                level=40,
            )
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="该审批已被处理，请刷新页面查看最新状态",
            )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )

    # ---- D3 端点回写：INVOICE 补 reviewer_id / review_comment（不扩适配器）----
    # approval_crud.approve 已调 InvoiceApplicationAdapter.on_approved/on_rejected
    # 写 invoice.status / reviewed_time；此处仅补 reviewer_id / review_comment 两字段。
    # 对 APPROVE 与 REJECT 都写：审批人即 reviewer，意见即 review_comment。
    # D3 时序：approval_crud.approve 内部已 commit 落审批状态；此处是第二次 commit，
    # 失败时仅记 ERROR 日志——审批已生效不可回滚，reviewer 是审计信息可后补。
    if entity_type == BusinessType.INVOICE:
        inv_adapter = get_adapter(BusinessType.INVOICE)
        invoice = inv_adapter.get_entity(db, approval.business_id, approval.team_id)
        if invoice is not None:
            try:
                invoice.reviewer_id = str(current_user.id)
                invoice.review_comment = action_request.comment
                db.commit()
            except Exception as reviewer_err:
                logger.error(
                    "reviewer 回写失败 approval_id=%s: %s",
                    approval.id, reviewer_err
                )
                db.rollback()

    flow_direction_str = ("completed" if approval.status == ApprovalStatus.APPROVED else
                     "next_node" if approval.current_node else "terminated")

    # 通知泛化（A8）：按 entity_type 走适配器取展示名，分发 pending/approved/rejected
    notification_service = notification_service_factory(db, team_id)
    notification_status = "skipped"
    adapter = get_adapter(entity_type)
    entity = adapter.get_entity(db, approval.business_id, approval.team_id)
    entity_name = adapter.get_name(entity) if entity is not None else f"{entity_type}#{entity_id}"
    submitter = user_crud.get_by_id(db, int(approval.submitter_id)) if approval.submitter_id else None
    submitter_open_id = submitter.feishu_open_id if submitter else ""

    try:
        if action_request.action.value == ApprovalAction.APPROVE:
            if approval.status == ApprovalStatus.APPROVED:
                # 全部节点通过：通知提交人
                await notification_service.notify_approval_approved(
                    submitter_open_id=submitter_open_id,
                    entity_type=entity_type,
                    entity_name=entity_name,
                    business_id=entity_id,
                )
                notification_status = "success"
            elif approval.current_node:
                # 流转到下一节点：通知下一节点审批人
                approvers = get_approvers_by_role(db, approval.current_node.approve_role)
                for approver in approvers:
                    await notification_service.notify_approval_pending(
                        entity_type=entity_type,
                        entity_name=entity_name,
                        flow_name=approval.flow.flow_name if approval.flow else "",
                        node_name=approval.current_node.node_name,
                        approver_open_id=approver.feishu_open_id or "",
                        approver_name=approver.name,
                        business_id=entity_id,
                    )
                notification_status = "success" if approvers else "skipped"
        elif action_request.action.value == ApprovalAction.REJECT:
            await notification_service.notify_approval_rejected(
                submitter_open_id=submitter_open_id,
                entity_type=entity_type,
                entity_name=entity_name,
                reject_reason=action_request.comment or "无",
                business_id=entity_id,
            )
            notification_status = "success"
    except Exception as notify_error:
        notification_status = "failed"
        logger.error(
            f"[Approval] Generic notification failed: entity_type={entity_type}, "
            f"business_id={entity_id}, error={str(notify_error)}"
        )

    log_approval_operation(
        operation="Approve" if action_request.action.value == ApprovalAction.APPROVE else "Reject",
        approval_id=approval.id,
        flow_name=flow_name,
        node_name=current_node_name,
        operator=current_user.name,
        flow_direction=flow_direction_str,
        notification_status=notification_status,
        business_type=entity_type,
        business_id=entity_id,
    )

    db.refresh(approval)
    return _serialize_generic_approval(approval, db)


@router.post(
    "/{entity_type}/{entity_id}/cancel",
    response_model=MessageResponse,
    summary="撤回审批（通用）",
    description="""
撤回审批中的业务单据审批流程。只有提交人本人可撤回，且仅限 PENDING 状态。
""",
)
def cancel_generic_approval(
    entity_type: str,
    entity_id: int,
    db: Session = Depends(get_db),
    team_id: int = Depends(get_current_user_team),
    current_user=Depends(get_current_active_user),
):
    _validate_entity_type(entity_type)

    approval = approval_crud.get_by_entity(db, entity_type, entity_id, team_id)
    if not approval:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="审批流程不存在",
        )

    current_node_name = approval.current_node.node_name if approval.current_node else ""
    flow_name = approval.flow.flow_name if approval.flow else ""

    try:
        approval = approval_crud.cancel(db, approval, str(current_user.id))
    except ValueError as e:
        log_approval_operation(
            operation="Cancel",
            approval_id=approval.id,
            business_type=entity_type,
            business_id=entity_id,
            operator=current_user.name,
            reason=str(e),
            level=40,
        )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )

    log_approval_operation(
        operation="Cancel",
        approval_id=approval.id,
        flow_name=flow_name,
        node_name=current_node_name,
        operator=current_user.name,
        flow_direction="cancelled",
        business_type=entity_type,
        business_id=entity_id,
    )
    return MessageResponse(message="审批已撤回")


@router.get(
    "/{entity_type}/{entity_id}/detail",
    summary="获取审批详情（通用）",
    description="""
按业务单据类型+ID 查询最新一条审批实例的完整详情，包括所有审批记录和当前状态。
""",
)
def detail_generic_approval(
    entity_type: str,
    entity_id: int,
    db: Session = Depends(get_db),
    team_id: int = Depends(get_current_user_team),
    current_user=Depends(get_current_active_user),
):
    _validate_entity_type(entity_type)

    approval = approval_crud.get_by_entity(db, entity_type, entity_id, team_id)
    if not approval:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="审批流程不存在",
        )
    return _serialize_generic_approval(approval, db)


@router.post(
    "/bulk-approve",
    response_model=BulkApproveResponse,
    summary="批量审批（E6）",
    description="""
对多条同类型业务单据批量执行审批操作。

**E6 拍板**：逐条独立事务，部分成功汇总，不整体事务——避免一条失败全回滚让审批人白做。

**返回字段：**
- success_count: 成功审批的条数
- failed: 失败条目列表 `[{id, reason}]`，乐观锁冲突单列 reason="已被他人处理"
""",
)
async def bulk_approve(
    payload: BulkApproveRequest,
    db: Session = Depends(get_db),
    team_id: int = Depends(get_current_user_team),
    current_user=Depends(get_current_active_user),
):
    _validate_entity_type(payload.entity_type)

    from app.schemas.approval import ApprovalActionRequest as _ApprovalActionReq

    success_count = 0
    failed: list[BulkApproveFailedItem] = []

    for bid in payload.ids:
        # 逐条独立事务：approve 内部 db.commit()，单条失败 db.rollback() 不影响他条
        try:
            approval = approval_crud.get_by_entity(
                db, payload.entity_type, bid, team_id
            )
            if not approval:
                raise ValueError("审批实例不存在")
            if not approval.current_node:
                raise ValueError("当前审批节点不存在")

            # 角色校验（与单条 approve 端点一致）
            user_roles = role_crud.get_user_roles(db, current_user.id, team_id)
            role_codes = {r.code for r in user_roles}
            if approval.current_node.approve_role not in role_codes:
                raise ValueError(f"需要角色: {approval.current_node.approve_role}")

            # 自审追加权限校验（CONTRACT/PAYMENT/INVOICE 通用，M-3 泛化）
            # 复用 _check_self_approval_permission；helper 抛 HTTPException，
            # 这里转 ValueError 由 bulk 失败汇总逻辑计入 failed（reason=detail 文案）。
            try:
                _check_self_approval_permission(
                    db, current_user, team_id, payload.entity_type, bid
                )
            except HTTPException as e:
                raise ValueError(str(e.detail)) from None

            # 取该条的乐观锁时间戳
            ut_raw = None
            if payload.updated_times:
                v = payload.updated_times.get(str(bid))
                if v:
                    try:
                        ut_raw = _datetime.fromisoformat(v)
                    except (ValueError, TypeError):
                        ut_raw = None

            req = _ApprovalActionReq(
                action=payload.action,
                comment=payload.comment,
                updated_time=ut_raw,
            )

            approval_crud.approve(
                db, approval, req, str(current_user.id), current_user.name
            )

            # D3 端点回写（INVOICE）——审批已生效，reviewer 写失败仅记日志不影响成功计数
            if payload.entity_type == BusinessType.INVOICE:
                inv_adapter = get_adapter(BusinessType.INVOICE)
                invoice = inv_adapter.get_entity(db, approval.business_id, approval.team_id)
                if invoice is not None:
                    try:
                        invoice.reviewer_id = str(current_user.id)
                        invoice.review_comment = payload.comment
                        db.commit()
                    except Exception as reviewer_err:
                        logger.error(
                            "reviewer 回写失败 approval_id=%s: %s",
                            approval.id, reviewer_err
                        )
                        db.rollback()

            success_count += 1
        except ValueError as e:
            db.rollback()
            msg = str(e)
            if "审批已被其他用户处理" in msg:
                reason = "已被他人处理"
            else:
                reason = msg
            failed.append(BulkApproveFailedItem(id=bid, reason=reason))
        except Exception as e:  # noqa: BLE001
            db.rollback()
            failed.append(BulkApproveFailedItem(id=bid, reason=str(e)))

    log_approval_operation(
        operation="BulkApprove",
        operator=current_user.name,
        flow_direction=f"success={success_count}, failed={len(failed)}",
        reason=payload.entity_type,
        business_type=payload.entity_type,
        level=20,
    )

    return BulkApproveResponse(success_count=success_count, failed=failed)


# ============================================================================
# Task C3：通用审批列表端点 GET /v1/approvals
# ============================================================================
# 设计要点：
# - E2 越权过滤（P0）：tab=pending/processed/submitted 分别按角色/记录/提交人过滤，
#   team_id 由 get_current_user_team 注入，前端无法跨 team 抓数据。
# - 角色获取：复用既有 role_crud.get_user_roles(db, user_id, team_id) → 取 code 集合，
#   传给 approval_crud.list_approvals 做 pending tab 的 IN 过滤。
# - 权限：Depends(get_current_user_team) + get_current_active_user 即可，无需额外
#   require_permission——能看到的都是自己相关（待我审批/我已处理/我提交的）。
# - E9 N+1：approval_crud.list_approvals 内部分组批量预取实体摘要。
# - 响应：{items, total, pending_count}（pending_count=pending tab total，任意 tab 附）。
# ============================================================================


@router.get(
    "",
    response_model=ApprovalGenericListResponse,
    summary="获取审批列表（通用，Task C3）",
    description="""
按 tab 维度查询当前用户相关审批列表，团队隔离 + 角色驱动过滤。

**功能说明：**
- tab=pending：当前节点审批角色属于我的角色集 + 状态 PENDING
- tab=processed：我作为审批人留下过 APPROVE/REJECT 记录的审批
- tab=submitted：我提交的所有审批（含已通过/驳回/撤回）
- 任意 tab 响应都附 `pending_count`（当前用户待我审批总数，供侧边栏徽章）

**查询参数：**
- tab: pending / processed / submitted
- business_type: 可选 CONTRACT / PAYMENT / INVOICE 维度过滤
- page / page_size: 分页

**返回字段：**
- items: 审批列表项，含按 business_type 内存 join 出的 application_number /
  entity_name / entity_amount 三摘要（避免 N+1）
- total: 当前 tab+business_type 过滤后的总数
- pending_count: 当前用户待我审批总数（任意 tab 都附）
""",
)
def list_approvals(
    tab: str = Query("pending", description="过滤维度：pending/processed/submitted"),
    business_type: Optional[str] = Query(None, description="业务类型过滤 CONTRACT/PAYMENT/INVOICE"),
    page: int = Query(1, ge=1, description="页码，1-based"),
    page_size: int = Query(20, ge=1, le=100, description="每页条数"),
    team_id: int = Depends(get_current_user_team),
    current_user = Depends(get_current_active_user),
    db: Session = Depends(get_db),
):
    # 参数校验
    if tab not in ("pending", "processed", "submitted"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"非法 tab: {tab}，仅支持 pending / processed / submitted",
        )
    if business_type is not None and not is_valid_business_type(business_type):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"无效的业务单据类型: {business_type}，仅支持 CONTRACT / PAYMENT / INVOICE",
        )

    # 当前用户在该 team 下的角色 code 集合（pending tab 过滤用）
    user_role_objs = role_crud.get_user_roles(db, current_user.id, team_id)
    user_roles = [r.code for r in user_role_objs]

    items, total, pending_count = approval_crud.list_approvals(
        db,
        team_id=team_id,
        user_id=current_user.id,
        user_roles=user_roles,
        tab=tab,
        business_type=business_type,
        page=page,
        page_size=page_size,
    )

    return ApprovalGenericListResponse(
        items=[ApprovalListItemResponse(**item) for item in items],
        total=total,
        pending_count=pending_count,
    )


# ============================================================================
# Task 4: 发票审批上传文件端点（POST /v1/approvals/INVOICE/{entity_id}/approve-with-file）
# ============================================================================
# 设计要点：
# - 仅支持 INVOICE 类型，其他类型返回 400
# - entity_id 是发票申请 ID（InvoiceApplication.id）
# - file: UploadFile（发票文件 PDF/JPG/PNG/OFD）
# - invoice_number: Optional[str]（发票号码，财务可从文件中查看）
# - comment: Optional[str]（审批意见）
# - 权限：invoice:approve（require_permission）
# - 安全校验：FileStorageService 防路径穿越 + 白名单扩展名
# - 状态检查：entity.status == PENDING_REVIEW 才可审批
# - 调用适配器：InvoiceApplicationAdapter.on_approved_with_file
# - 审批记录：创建 ApprovalRecord（action="approve_with_file")
# ============================================================================


@router.post(
    "/{entity_type}/{entity_id}/approve-with-file",
    summary="审批通过并上传发票文件（Task 4）",
    description="""
审批发票时上传发票文件，审批通过后自动变为已开票状态。

**功能说明：**
- 仅支持 INVOICE 类型（其他类型返回 400）
- 财务人员审批发票时上传发票文件（PDF/JPG/PNG/OFD）
- 审批通过后自动变为 ISSUED（已开票）状态
- 发票号码可选（财务可从上传的文件中查看）

**路径参数：**
- entity_type: INVOICE（仅支持发票类型）
- entity_id: 发票申请 ID

**请求体（multipart/form-data）：**
- file: 发票文件（必填）
- invoice_number: 发票号码（可选）
- comment: 审批意见（可选）

**权限要求：**
- invoice:approve 权限

**业务规则：**
- 发票状态必须为 PENDING_REVIEW（待审批）
- 文件大小限制：10MB
- 文件类型限制：PDF/JPG/PNG/OFD
""",
)
async def approve_with_file(
    entity_type: str,
    entity_id: int,
    file: UploadFile = File(..., description="发票文件（PDF/JPG/PNG/OFD）"),
    invoice_number: Optional[str] = Form(None, description="发票号码（可选，财务可从文件中查看）"),
    comment: Optional[str] = Form(None, description="审批意见"),
    team_id: int = Depends(get_current_user_team),
    current_user: User = Depends(require_permission("invoice:approve")),
    db: Session = Depends(get_db),
):
    """审批发票时上传文件——仅支持 INVOICE 类型"""

    # 只支持发票类型
    if entity_type != BusinessType.INVOICE:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="仅发票类型支持上传文件审批",
        )

    # 获取适配器和实体
    adapter = get_adapter(entity_type)
    entity = adapter.get_entity(db, entity_id, team_id)

    if not entity:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"{entity_type} 实体不存在",
        )

    # 检查状态
    if entity.status != InvoiceApplicationStatus.PENDING_REVIEW:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"发票状态为 {entity.status}，无法审批",
        )

    # 读取文件内容
    file_content = await file.read()

    # 保存文件
    try:
        file_path = file_storage_service.save_invoice_file(
            team_id=team_id,
            invoice_id=entity_id,
            filename=file.filename or "invoice.pdf",
            content=file_content,
        )
    except FileStorageError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )

    # 调用适配器的 on_approved_with_file
    adapter.on_approved_with_file(db, entity, file_path, invoice_number)

    # 获取审批实例
    approval = approval_crud.get_by_entity(db, entity_type, entity_id, team_id)

    # 更新审批状态为通过
    if approval:
        approval.status = ApprovalStatus.APPROVED
        approval.current_node_id = None

        # 创建审批操作记录
        record = ApprovalRecord(
            approval_id=approval.id,
            node_id=approval.current_node_id if approval else None,
            approver_id=str(current_user.id),
            approver_name=current_user.name,
            action="approve_with_file",
            comment=comment or f"审批通过，发票号码：{invoice_number or '未填写'}",
            created_time=func.now(),
        )
        db.add(record)

    # 记录日志
    log_approval_operation(
        operation="ApproveWithFile",
        approval_id=approval.id if approval else None,
        flow_name=approval.flow.flow_name if approval and approval.flow else None,
        node_name=approval.current_node.node_name if approval and approval.current_node else None,
        operator=current_user.name,
        flow_direction="completed",
        business_type=entity_type,
        business_id=entity_id,
        reason=f"file_path={file_path}, invoice_number={invoice_number}",
    )

    db.commit()

    return {
        "success": True,
        "message": "审批成功，发票已上传",
        "file_path": file_path,
        "invoice_number": invoice_number,
        "new_status": InvoiceApplicationStatus.ISSUED,
    }
