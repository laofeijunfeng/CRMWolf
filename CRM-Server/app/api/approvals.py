import os
from collections.abc import Callable, Iterable, Iterator
from datetime import date, datetime
from datetime import datetime as _datetime
from typing import TYPE_CHECKING, Any, cast
from urllib.parse import quote

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session

from app.constants.business_types import BusinessType, is_valid_business_type
from app.core.database import SessionLocal, get_db
from app.core.deps import (
    get_current_active_user,
    get_current_user_team,
    require_permission,
    user_can_view_customer,
)
from app.core.list_export import (
    APPROVALS_LIST_EXPORT_CATALOG,
    create_list_export_file,
    iter_batches,
    list_export_file_response,
    run_list_export_or_400,
)
from app.core.list_query import optional_request_list_query, run_or_400
from app.core.logging import get_logger, log_with_fields
from app.crud.approval import approval_crud, approval_flow_crud
from app.crud.contract import contract_crud
from app.crud.opportunity import opportunity_crud
from app.crud.role import role_crud
from app.models.approval import (
    Approval,
    ApprovalAction,
    ApprovalFlow,
    ApprovalParticipant,
    ApprovalParticipantKind,
    ApprovalRecord,
    ApprovalStatus,
)
from app.models.contract import ContractStatus
from app.models.payment import PaymentRecord
from app.models.user import User
from app.models.user_role import UserRole
from app.schemas.approval import (
    ApprovalActionEnum,
    ApprovalActionRequest,
    ApprovalDetailResponse,
    ApprovalFlowCreate,
    ApprovalFlowDetailResponse,
    ApprovalFlowResponse,
    ApprovalFlowUpdate,
    ApprovalRecordResponse,
    ApprovalSubmitRequest,
    MessageResponse,
    OverdueApprovalListResponse,
    OverdueApprovalResponse,
)
from app.schemas.approval_generic import (
    ApprovalCcDetailResponse,
    ApprovalGenericListResponse,
    ApprovalListItemResponse,
    GenericApprovalDetailResponse,
    GenericApprovalSubmitResponse,
)
from app.schemas.approval_generic import (
    ApprovalSubmitRequest as GenericApprovalSubmitRequest,
)
from app.schemas.list_export import ApprovalListExportRequest
from app.services.approval_adapter import get_adapter, get_approval_customer_id
from app.services.approval_routing import current_approver_ids, is_participant, snapshot_entry_for_node
from app.services.approval_transaction_manager import approval_transaction_manager
from app.services.customer_approval_intelligence_service import (
    CustomerApprovalChangeRefreshInput,
    customer_approval_intelligence_service,
)
from app.services.file_storage import FileStorageError, file_storage_service
from app.services.outbound_notification_job_service import outbound_notification_job_service
from app.utils.public_id import is_opportunity_public_id

if TYPE_CHECKING:
    from decimal import Decimal

    from app.services.customer_approval_intelligence_service import ApprovalSupportedEntity
    from app.services.outbound_notification_job_service import OutboundNotificationJobRequest


router = APIRouter(prefix="/v1/approvals", tags=["审批管理"])

# 审批操作日志记录器
logger = get_logger(__name__)

APPROVAL_STATUS_LABELS = {
    "PENDING": "审批中",
    "APPROVED": "已通过",
    "REJECTED": "已驳回",
    "CANCELLED": "已撤回",
}


def _approval_node_name(
    approval: Approval,
    node_id: int | None,
    legacy_node_name: str | None = None,
) -> str | None:
    entry = snapshot_entry_for_node(approval, node_id)
    if approval.nodes_snapshot is not None:
        return (entry or {}).get("node_name")
    return legacy_node_name


def _approval_current_node_name(approval: Approval) -> str | None:
    if approval.nodes_snapshot is not None:
        return _approval_node_name(
            approval,
            int(approval.current_node_id) if approval.current_node_id is not None else None,
        )
    return _approval_node_name(
        approval,
        approval.current_node_id,
        approval.current_node.node_name if approval.current_node else None,
    )


APPROVAL_TYPE_LABELS = {
    "PAYMENT": "回款",
    "INVOICE": "发票",
    "INVOICE_REISSUE": "发票重开",
    "CONTRACT": "合同",
    "CONTRACT_CHANGE": "合同变更",
    "LICENSE": "License",
    "OPPORTUNITY": "商机",
}
APPROVAL_TAB_STEMS = {
    "pending": "待我审批",
    "processed": "我已处理",
    "submitted": "我提交的",
    "cc": "抄送我",
}


def _approval_export_row(item: dict[str, Any]) -> dict[str, object]:
    created_time = item.get("created_time")
    if isinstance(created_time, str) and created_time:
        created_time = datetime.fromisoformat(created_time)
    elif not created_time:
        created_time = None
    status_value = item.get("status")
    if status_value is not None and hasattr(status_value, "value"):
        status_value = status_value.value
    business_type = item.get("business_type")
    application_number = item.get("application_number")
    business_id = item.get("business_id")
    if application_number and business_id is not None:
        fallbacks = {
            f"{business_type}-{business_id}",
            f"INVOICE-{business_id}",
            f"INVR-{business_id}",
            f"PAY-{business_id}",
            f"CONTRACT-{business_id}",
            f"LICENSE-{business_id}",
            f"OPP-{business_id}",
        }
        if application_number in fallbacks:
            application_number = None
    return {
        "application_number": application_number,
        "business_type": APPROVAL_TYPE_LABELS.get(cast("str", business_type), business_type),
        "entity_name": item.get("entity_name"),
        "entity_amount": item.get("entity_amount"),
        "submitter_name": item.get("submitter_name"),
        "created_time": created_time,
        "status": APPROVAL_STATUS_LABELS.get(cast("str", status_value), status_value),
        "overdue_hours": item.get("overdue_hours"),
    }


def _iter_approval_export_rows(
    stream: Iterable[Approval],
    team_id: int,
    projection_session_factory: Callable[[], Session] = SessionLocal,
) -> Iterator[dict[str, object]]:
    for batch in iter_batches(stream, 500):
        projection_db = projection_session_factory()
        try:
            for item in approval_crud.build_list_items(projection_db, batch, team_id):
                yield _approval_export_row(item)
        finally:
            projection_db.close()


_export_permission = Depends(require_permission("approval:export"))
_export_team_dependency = Depends(get_current_user_team)
_export_current_user_dependency = Depends(get_current_active_user)
_export_db_dependency = Depends(get_db)



@router.post(
    "/export",
    dependencies=[_export_permission],
    summary="导出审批列表",
    description="按当前筛选条件导出全部匹配审批为 Excel",
)
def export_approvals(
    request: ApprovalListExportRequest,
    team_id: int = _export_team_dependency,
    current_user: User = _export_current_user_dependency,
    db: Session = _export_db_dependency,
) -> FileResponse:
    query, _needs_summary_filter = run_or_400(lambda: approval_crud.build_list_query(
        db,
        team_id=team_id,
        user_id=current_user.id,
        tab=request.tab,
        search=request.search,
        filters=request.filters,
        sorts=request.sorts,
    ))
    stream = query.enable_eagerloads(False).execution_options(stream_results=True).yield_per(500)
    rows = _iter_approval_export_rows(stream, team_id, projection_session_factory=SessionLocal)
    generated = run_list_export_or_400(lambda: create_list_export_file(
        catalog=APPROVALS_LIST_EXPORT_CATALOG,
        selected_keys=request.fields,
        rows=rows,
        file_stem=f"审批列表-{APPROVAL_TAB_STEMS.get(request.tab, '待我审批')}",
    ))
    return list_export_file_response(generated)



class BulkApproveRequest(BaseModel):
    entity_type: str = Field(..., description="业务单据类型")
    ids: list[int] = Field(..., description="业务单据 ID 列表")
    action: ApprovalActionEnum = Field(..., description="审批动作")
    comment: str | None = Field(None, description="审批意见")
    updated_times: dict[str, _datetime] | None = Field(
        None,
        description="按业务单据 ID 传入的审批实例更新时间\uff0c用于乐观锁",
    )


def _resolve_generic_entity_id(
    db: Session,
    *,
    entity_type: str,
    entity_ref: str,
    team_id: int,
) -> int:
    """将对外路由标识解析为内部业务单据数据库 ID。"""
    if entity_type == BusinessType.OPPORTUNITY:
        if not is_opportunity_public_id(entity_ref):
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="商机不存在",
            )
        opportunity = opportunity_crud.get_by_public_id(db, entity_ref, team_id)
        if opportunity is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="商机不存在",
            )
        return opportunity.id

    try:
        return int(entity_ref)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="业务单据不存在",
        ) from exc


def _approval_file_content_type(file_path: str, fallback: str | None = None) -> str:
    if fallback:
        return fallback
    ext = os.path.splitext(file_path)[1].lower()
    return {
        ".pdf": "application/pdf",
        ".doc": "application/msword",
        ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".png": "image/png",
        ".gif": "image/gif",
        ".webp": "image/webp",
        ".ofd": "application/octet-stream",
    }.get(ext, "application/octet-stream")


def _approval_file_content_disposition(filename: str) -> str:
    encoded = quote(filename)
    ascii_name = filename.encode("ascii", "ignore").decode("ascii") or "attachment"
    return f'inline; filename="{ascii_name}"; filename*=UTF-8\'\'{encoded}'


def _enqueue_customer_approval_intelligence(
    db: Session,
    *,
    entity_type: str,
    entity: "ApprovalSupportedEntity",
    approval: Approval,
    actor_id: str,
    action: str,
) -> None:
    try:
        customer_approval_intelligence_service.enqueue_approval_change_refresh(
            db,
            CustomerApprovalChangeRefreshInput(
                entity_type=entity_type,
                entity=entity,
                approval=approval,
                actor_id=actor_id,
                action=action,
            ),
        )
    except Exception as refresh_error:
        db.rollback()
        logger.error(
            "[Approval] Customer intelligence refresh enqueue failed: "
            "entity_type=%s, business_id=%s, error=%s",
            entity_type,
            getattr(entity, "id", None),
            refresh_error,
        )


def log_approval_operation(
    operation: str,
    approval_id: int | None = None,
    contract_id: int | None = None,
    flow_name: str | None = None,
    node_name: str | None = None,
    operator: str | None = None,
    next_node: str | None = None,
    flow_direction: str | None = None,
    notification_status: str | None = None,
    reason: str | None = None,
    level: int = 20,  # INFO
    business_type: str | None = None,
    business_id: int | None = None,
) -> None:
    """
    记录审批操作日志

    Args:
        operation: 操作类型\uff08Submit/Approve/Reject/Cancel/BulkApprove\uff09
        approval_id: 审批实例ID
        contract_id: 合同ID\uff08CONTRACT 类型沿用\uff0c向下兼容\uff09
        flow_name: 审批流程名称
        node_name: 当前节点名称
        operator: 操作人姓名
        next_node: 下一节点名称
        flow_direction: 流转方向\uff08next_node/terminated/completed\uff09
        notification_status: 通知发送状态\uff08success/failed/skipped\uff09
        reason: 拒绝/撤回原因
        level: 日志级别\uff08默认 INFO\uff09
        business_type: 业务单据类型\uff08CONTRACT/PAYMENT/INVOICE/LICENSE/OPPORTUNITY\uff09
        business_id: 业务单据ID\uff08A6 通用端点\uff09
    """
    message = f"[Approval] {operation}"

    fields: dict[str, str | int] = {}
    # A6 通用端点用 business_type / business_id;CONTRACT 旧端点仍写 contract_id
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


_flow_list_skip_query = Query(0, ge=0, description="跳过记录数")
_flow_list_limit_query = Query(100, ge=1, le=100, description="每页记录数")
_flow_list_is_active_query = Query(None, description="是否启用")
_flow_list_team_dependency = Depends(get_current_user_team)
_flow_list_current_user_dependency = Depends(get_current_active_user)
_flow_list_db_dependency = Depends(get_db)


@router.get("/flows", response_model=list[ApprovalFlowResponse], summary="获取审批流程列表", description="""
获取所有审批流程模板列表\uff0c支持分页查询和按启用状态筛选。

**功能说明\uff1a**
- 支持分页查询\uff0c默认每页100条
- 可按启用/禁用状态筛选
- 返回流程基本信息\uff0c不包含节点详情

**业务场景\uff1a**
- 管理员查看所有审批流程配置
- 匹配合同对应的审批流程

**返回字段\uff1a**
- flow_id: 流程ID
- flow_name: 流程名称
- flow_code: 流程编码
- flow_type: 流程类型\uff08CONTRACT-合同审批\uff09
- is_active: 是否启用
- description: 流程描述
""")
def get_approval_flows(
    skip: int = _flow_list_skip_query,
    limit: int = _flow_list_limit_query,
    is_active: bool | None = _flow_list_is_active_query,
    team_id: int = _flow_list_team_dependency,
    current_user: User = _flow_list_current_user_dependency,
    db: Session = _flow_list_db_dependency,
) -> list[ApprovalFlow]:
    del current_user
    flows, _total = approval_flow_crud.get_multi(db, team_id, skip, limit, is_active)
    return flows


_overdue_min_hours_query = Query(48, ge=1, le=720, description="最小超时小时数\uff0c默认48小时\uff0c可选24/48/72")
_overdue_skip_query = Query(0, ge=0, description="跳过记录数")
_overdue_limit_query = Query(100, ge=1, le=100, description="每页记录数")
_overdue_team_dependency = Depends(get_current_user_team)
_overdue_current_user_dependency = Depends(get_current_active_user)
_overdue_db_dependency = Depends(get_db)


@router.get("/overdue", response_model=OverdueApprovalListResponse, summary="获取超时审批列表", description="""
获取所有超时的审批实例列表\uff0c供管理员进行应急处理。

**功能说明\uff1a**
- 查询所有状态为 PENDING 且超过指定小时数的审批
- 默认查询超过 48 小时的审批
- 支持按超时程度筛选\uff0824h/48h/72h\uff09
- 超时时间最长的排在最前面

**业务场景\uff1a**
- 管理员查看超时审批进行应急处理
- 批量发送催办通知
- 介入处理卡住的审批流程

**请求参数\uff1a**
- min_hours: 最小超时小时数\uff08默认48小时\uff09
- skip: 跳过记录数\uff08默认0\uff09
- limit: 每页记录数\uff08默认100\uff09

**返回字段\uff1a**
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

**权限要求\uff1a**
- 需要管理员权限或 approval:flow:view 权限
""")
def get_overdue_approvals(
    min_hours: int = _overdue_min_hours_query,
    skip: int = _overdue_skip_query,
    limit: int = _overdue_limit_query,
    team_id: int = _overdue_team_dependency,
    current_user: User = _overdue_current_user_dependency,
    db: Session = _overdue_db_dependency,
) -> OverdueApprovalListResponse:
    """
    获取超时审批列表

    管理员应急操作指南\uff1a
    1. 查看超时审批列表\uff0c了解哪些审批卡住了
    2. 批量发送催办通知给审批人
    3. 或联系审批人/提交人进行处理
    4. 必要时可撤回审批让提交人重新提交
    """

    del current_user
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


_flow_detail_team_dependency = Depends(get_current_user_team)
_flow_detail_current_user_dependency = Depends(get_current_active_user)
_flow_detail_db_dependency = Depends(get_db)


@router.get("/flows/{flow_id}", response_model=ApprovalFlowDetailResponse, summary="获取审批流程详情", description="""
获取指定审批流程的详细信息\uff0c包括流程配置和所有审批节点。

**功能说明\uff1a**
- 返回流程完整配置信息
- 包含所有审批节点列表
- 显示每个节点的审批角色、顺序等信息

**业务场景\uff1a**
- 管理员查看流程配置详情
- 了解审批链路和节点设置

**路径参数\uff1a**
- flow_id: 审批流程ID

**返回字段\uff1a**
- 基本信息\uff1a流程ID、名称、编码、类型、状态等
- nodes: 审批节点列表
  - node_id: 节点ID
  - node_name: 节点名称
  - node_type: 审批或抄送
  - approver_roles / approver_users: 整角色 / 指定成员
  - node_order: 节点顺序
  - is_active: 是否启用
""")
def get_approval_flow(
    flow_id: int,
    team_id: int = _flow_detail_team_dependency,
    current_user: User = _flow_detail_current_user_dependency,
    db: Session = _flow_detail_db_dependency,
) -> ApprovalFlow:
    del current_user
    flow = approval_flow_crud.get_by_id(db, flow_id, team_id)
    if not flow:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="审批流程不存在"
        )

    return flow


_flow_create_team_dependency = Depends(get_current_user_team)
_flow_create_permission = Depends(require_permission("approval:flow:create"))
_flow_create_db_dependency = Depends(get_db)


@router.post(
    "/flows",
    response_model=ApprovalFlowResponse,
    status_code=status.HTTP_201_CREATED,
    summary="创建审批流程",
    description="""
创建新的审批流程模板\uff0c支持配置多节点审批链路。

**功能说明\uff1a**
- 创建新的审批流程模板
- 可配置多个审批节点
- 节点按顺序依次审批

**业务场景\uff1a**
- 管理员配置新的审批流程
- 定义不同类型合同的审批规则

**权限要求\uff1a**
- 需要权限\uff1aapproval:flow:create

**请求体字段\uff1a**
- flow_name: 流程名称\uff08必填\uff09
- flow_code: 流程编码\uff0c唯一标识\uff08必填\uff09
- flow_type: 流程类型\uff0c如CONTRACT\uff08必填\uff09
- description: 流程描述
- is_active: 是否启用
- nodes: 审批节点列表
  - node_name: 节点名称
  - node_type: 审批或抄送
  - approver_roles / approver_users: 整角色 / 指定成员
  - node_order: 节点顺序

**注意事项\uff1a**
- flow_code必须唯一
- 节点顺序应连续且从1开始
""")
def create_approval_flow(
    flow_data: ApprovalFlowCreate,
    team_id: int = _flow_create_team_dependency,
    current_user: User = _flow_create_permission,
    db: Session = _flow_create_db_dependency,
) -> ApprovalFlow:
    del current_user
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
            detail=f"创建审批流程失败: {e!s}"
        ) from e


_flow_update_team_dependency = Depends(get_current_user_team)
_flow_update_current_user_dependency = Depends(get_current_active_user)
_flow_update_db_dependency = Depends(get_db)


@router.put("/flows/{flow_id}", response_model=ApprovalFlowResponse, summary="更新审批流程", description="""
更新现有审批流程模板的配置信息。

**功能说明\uff1a**
- 更新流程基本信息
- 调整审批节点配置
- 修改流程启用状态

**业务场景\uff1a**
- 调整审批规则
- 增加或减少审批节点
- 暂停/启用某个流程

**权限要求\uff1a**
- 需要 TEAM_ADMIN 角色 **或** approval:flow:edit 权限

**路径参数\uff1a**
- flow_id: 审批流程ID

**请求体字段\uff1a**
- 所有字段均为可选
- flow_name: 流程名称
- description: 流程描述
- is_active: 是否启用
- nodes: 审批节点列表\uff08完整替换\uff09

**注意事项\uff1a**
- 更新节点时会完全替换现有节点
- 正在使用的流程谨慎修改
""")
def update_approval_flow(
    flow_id: int,
    flow_data: ApprovalFlowUpdate,
    team_id: int = _flow_update_team_dependency,
    current_user: User = _flow_update_current_user_dependency,
    db: Session = _flow_update_db_dependency,
) -> ApprovalFlow:
    # 权限检查:TEAM_ADMIN 或 approval:flow:edit
    from app.crud.permission import permission_crud
    from app.crud.role import role_crud

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
                detail="您没有权限更新审批流程\uff08需要 TEAM_ADMIN 角色或 approval:flow:edit 权限\uff09"
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
                note="已有审批实例继续执行\uff0c新提交审批不会匹配该流程"
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
    except ValueError as exc:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc
    except Exception as e:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"更新审批流程失败: {e!s}"
        ) from e


_contract_submit_team_dependency = Depends(get_current_user_team)
_contract_submit_current_user_dependency = Depends(get_current_active_user)
_contract_submit_db_dependency = Depends(get_db)


@router.post(
    "/contracts/{contract_id}/submit",
    response_model=ApprovalDetailResponse,
    status_code=status.HTTP_201_CREATED,
    summary="提交合同审批",
    description="""
将草稿状态的合同提交到审批流程\uff0c系统会自动匹配对应的审批流程。

**功能说明\uff1a**
- 只有草稿状态的合同可以提交审批
- 系统自动匹配对应的审批流程
- 创建审批实例并流转到第一个节点
- 向首个节点的审批人发送通知

**业务场景\uff1a**
- 销售人员完成合同后提交审批
- 启动合同审批流程

**路径参数\uff1a**
- contract_id: 合同ID

**请求体字段\uff1a**
- flow_id: 指定审批流程ID\uff08可选\uff0c不指定则自动匹配\uff09
- comment: 提交说明\uff08可选\uff09

**业务规则\uff1a**
- 只能提交草稿\uff08DRAFT\uff09状态的合同
- 自动根据合同类型匹配审批流程
- 首个节点的审批人会收到飞书通知

**错误情况\uff1a**
- 合同不存在
- 合同状态不是草稿
- 未找到匹配的审批流程
- 该合同已有待审批流程
""")
async def submit_contract_approval(
    contract_id: int,
    submit_data: ApprovalSubmitRequest,
    team_id: int = _contract_submit_team_dependency,
    current_user: User = _contract_submit_current_user_dependency,
    db: Session = _contract_submit_db_dependency,
) -> Approval:
    del submit_data
    contract = contract_crud.get_by_id(db, contract_id, team_id)
    if not contract:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="合同不存在"
        )

    if contract.status != ContractStatus.DRAFT:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"只有草稿状态的合同可以提交审批\uff0c当前状态: {contract.status}"
        )

    existing_approval = approval_crud.get_by_contract_id(db, contract_id, team_id)
    if existing_approval and existing_approval.status == ApprovalStatus.PENDING:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="该合同已有审批流程\uff0c请等待审批完成"
        )
    
    flow, error_msg = approval_flow_crud.match_flow(db, contract, contract.team_id)
    if not flow:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=error_msg or "未找到匹配的审批流程\uff0c请联系管理员配置"
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
            approval_id=cast("int", approval.id),
            contract_id=contract_id,
            flow_name=cast("str", flow.flow_name),
            node_name=_approval_current_node_name(approval),
            operator=current_user.name,
            flow_direction="submitted"
        )

        notification_status = "skipped"

        if approval.current_node_id is not None:
            try:
                request = outbound_notification_job_service.enqueue_pending_for_approval(
                    db,
                    approval=approval,
                    team_id=team_id,
                    actor_id=str(current_user.id),
                )
                result = _queue_outbound_notification(db, request)
                notification_status = _feishu_notification_status(result)
            except Exception as notify_error:
                notification_status = "failed"
                logger.error(
                    f"[Approval] Submit notification failed: contract_id={contract_id}, error={notify_error!s}"
                )

            # 更新日志补充通知状态
            log_approval_operation(
                operation="Submit",
                approval_id=cast("int", approval.id),
                contract_id=contract_id,
                flow_name=cast("str", flow.flow_name),
                node_name=_approval_current_node_name(approval),
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
        ) from e
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
            detail=f"提交审批失败: {e!s}"
        ) from e


_contract_approve_team_dependency = Depends(get_current_user_team)
_contract_approve_current_user_dependency = Depends(get_current_active_user)
_contract_approve_db_dependency = Depends(get_db)


@router.post(
    "/contracts/{contract_id}/approve",
    response_model=ApprovalDetailResponse,
    summary="审批通过/拒绝",
    description="""
对当前待审批的合同进行审批操作\uff0c支持通过或拒绝。

**功能说明\uff1a**
- 审批人可以对当前节点的合同进行审批
- 支持通过\uff08APPROVE\uff09和拒绝\uff08REJECT\uff09两种操作
- 通过后自动流转到下一节点或结束审批
- 拒绝后流程终止\uff0c合同需要重新提交

**业务场景\uff1a**
- 审批人对合同进行审批
- 多级审批链路逐级流转

**路径参数\uff1a**
- contract_id: 合同ID

**请求体字段\uff1a**
- action: 审批动作\uff0cAPPROVE\uff08通过\uff09或REJECT\uff08拒绝\uff09
- comment: 审批意见\uff08必填\uff09

**权限要求\uff1a**
- 必须是提交时确定的当前节点审批人
- 如审批自己创建的合同\uff0c需要额外权限\uff1acontract:approve:own

**业务规则\uff1a**
- 只有当前节点审批人才能操作
- 通过后流转到下一审批节点
- 全部节点通过后合同状态变为已审批
- 拒绝后流程终止\uff0c合同回到草稿状态

**通知机制\uff1a**
- 通过且有下一节点\uff1a下一节点审批人收到通知
- 全部通过\uff1a合同创建人收到通过通知
- 拒绝\uff1a合同创建人收到拒绝通知及理由
""")
async def approve_contract(
    contract_id: int,
    action_request: ApprovalActionRequest,
    team_id: int = _contract_approve_team_dependency,
    current_user: User = _contract_approve_current_user_dependency,
    db: Session = _contract_approve_db_dependency,
) -> Approval:
    approval = approval_crud.get_by_contract_id(db, contract_id, team_id)
    if not approval:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="审批流程不存在"
        )

    if approval.current_node_id is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="当前审批节点不存在"
        )

    contract = contract_crud.get_by_id(db, contract_id, team_id)
    if not contract:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="合同不存在"
        )

    _check_approve_permissions(
        db, approval, current_user, team_id,
        entity_type=BusinessType.CONTRACT, entity_id=contract_id,
    )

    try:
        # 记录当前节点(审批前的状态)
        current_node_name = _approval_current_node_name(approval) or ""
        flow_name = approval.flow.flow_name if approval.flow else ""

        approval = approval_crud.approve(
            db,
            approval,
            action_request,
            str(current_user.id),
            current_user.name
        )

        notification_status = "skipped"

        if action_request.action.value == ApprovalAction.APPROVE:
            if approval.status == ApprovalStatus.APPROVED:
                # 全部节点通过
                flow_direction = "completed"
                next_node = None
                try:
                    request = outbound_notification_job_service.enqueue_approved(
                        db,
                        approval=approval,
                        team_id=team_id,
                        actor_id=str(current_user.id),
                    )
                    result = _queue_outbound_notification(db, request)
                    notification_status = _feishu_notification_status(result)
                except Exception as notify_error:
                    notification_status = "failed"
                    logger.error(
                        f"[Approval] Approve notification failed: contract_id={contract_id}, error={notify_error!s}"
                    )
            elif approval.current_node_id is not None:
                # 流转到下一节点;名称来自提交时冻结的快照。
                flow_direction = "next_node"
                next_node = _approval_current_node_name(approval)
                try:
                    request = outbound_notification_job_service.enqueue_pending_for_approval(
                        db,
                        approval=approval,
                        team_id=team_id,
                        actor_id=str(current_user.id),
                    )
                    result = _queue_outbound_notification(db, request)
                    notification_status = _feishu_notification_status(result)
                except Exception as notify_error:
                    notification_status = "failed"
                    logger.error(
                        f"[Approval] Approve notification failed: contract_id={contract_id}, error={notify_error!s}"
                    )
            else:
                flow_direction = "completed"
                next_node = None

            # 记录审批通过日志
            log_approval_operation(
                operation="Approve",
                approval_id=cast("int", approval.id),
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
            try:
                request = outbound_notification_job_service.enqueue_rejected(
                    db,
                    approval=approval,
                    team_id=team_id,
                    reject_reason=action_request.comment or "无",
                    actor_id=str(current_user.id),
                )
                result = _queue_outbound_notification(db, request)
                notification_status = _feishu_notification_status(result)
            except Exception as notify_error:
                notification_status = "failed"
                logger.error(
                    f"[Approval] Reject notification failed: contract_id={contract_id}, error={notify_error!s}"
                )

            # 记录审批拒绝日志
            log_approval_operation(
                operation="Reject",
                approval_id=cast("int", approval.id),
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
                approval_id=cast("int", approval.id) if approval else None,
                contract_id=contract_id,
                operator=current_user.name,
                reason="乐观锁冲突\uff1a审批已被其他用户处理",
                level=40  # ERROR
            )
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="该审批已被处理\uff0c请刷新页面查看最新状态"
            ) from e
        log_approval_operation(
            operation="Approve",
            approval_id=cast("int", approval.id) if approval else None,
            contract_id=contract_id,
            operator=current_user.name,
            reason=str(e),
            level=40  # ERROR
        )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        ) from e
    except Exception as e:
        log_approval_operation(
            operation="Approve",
            approval_id=cast("int", approval.id) if approval else None,
            contract_id=contract_id,
            operator=current_user.name,
            reason=str(e),
            level=40  # ERROR
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"审批操作失败: {e!s}"
        ) from e


_contract_cancel_team_dependency = Depends(get_current_user_team)
_contract_cancel_current_user_dependency = Depends(get_current_active_user)
_contract_cancel_db_dependency = Depends(get_db)


@router.post("/contracts/{contract_id}/cancel", response_model=MessageResponse, summary="撤回审批", description="""
撤回正在审批中的合同\uff0c终止审批流程。

**功能说明\uff1a**
- 只有审批提交人可以撤回
- 只能撤回待审批状态的流程
- 撤回后合同回到草稿状态
- 可以修改后重新提交

**业务场景\uff1a**
- 发现提交的合同有误\uff0c需要修改
- 暂时不需要审批\uff0c撤回后稍后再提交

**路径参数\uff1a**
- contract_id: 合同ID

**业务规则\uff1a**
- 只有审批创建者\uff08提交人\uff09可以撤回
- 只能撤回待审批\uff08PENDING\uff09状态的流程
- 已审批完成或已拒绝的流程无法撤回

**返回信息\uff1a**
- 成功\uff1a返回"审批已撤回"
- 失败\uff1a返回具体错误信息
""")
async def cancel_approval(
    contract_id: int,
    team_id: int = _contract_cancel_team_dependency,
    current_user: User = _contract_cancel_current_user_dependency,
    db: Session = _contract_cancel_db_dependency,
) -> MessageResponse:
    approval = approval_crud.get_by_contract_id(db, contract_id, team_id)
    if not approval:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="审批流程不存在"
        )

    # 记录撤回前的状态
    current_node_name = _approval_current_node_name(approval) or ""
    flow_name = approval.flow.flow_name if approval.flow else ""
    contract_crud.get_by_id(db, contract_id, team_id)
    approver_ids = current_approver_ids(db, approval)

    notify_request = None
    notification_status = "skipped"
    if approver_ids:
        try:
            notify_request = outbound_notification_job_service.enqueue_cancelled(
                db,
                approval=approval,
                team_id=team_id,
                actor_id=str(current_user.id),
                actor_name=current_user.name,
                recipient_user_ids=approver_ids,
            )
            notification_status = "queued" if notify_request is not None else "skipped"
        except Exception as notify_error:
            notification_status = "failed"
            logger.error(
                f"[Approval] Cancel notification failed: contract_id={contract_id}, error={notify_error!s}"
            )

    try:
        approval = approval_crud.cancel(db, approval, str(current_user.id))
        outbound_notification_job_service.kick(notify_request)

        # 记录撤回日志
        log_approval_operation(
            operation="Cancel",
            approval_id=cast("int", approval.id),
            contract_id=contract_id,
            flow_name=flow_name,
            node_name=current_node_name,
            operator=current_user.name,
            flow_direction="cancelled",
            notification_status=notification_status,
        )

        return MessageResponse(message="审批已撤回")
    except ValueError as e:
        log_approval_operation(
            operation="Cancel",
            approval_id=cast("int", approval.id) if approval else None,
            contract_id=contract_id,
            operator=current_user.name,
            reason=str(e),
            level=40  # ERROR
        )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        ) from e
    except Exception as e:
        log_approval_operation(
            operation="Cancel",
            approval_id=cast("int", approval.id) if approval else None,
            contract_id=contract_id,
            operator=current_user.name,
            reason=str(e),
            level=40  # ERROR
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"撤回审批失败: {e!s}"
        ) from e


_contract_detail_team_dependency = Depends(get_current_user_team)
_contract_detail_current_user_dependency = Depends(get_current_active_user)
_contract_detail_db_dependency = Depends(get_db)


@router.get(
    "/contracts/{contract_id}/detail",
    response_model=ApprovalDetailResponse,
    summary="获取审批详情",
    description="""
获取合同审批流程的完整详情\uff0c包括所有审批记录和当前状态。

**功能说明\uff1a**
- 查看合同的完整审批链路
- 显示所有节点的审批记录
- 显示当前审批进度和状态
- 包含每个审批人的意见和操作时间
- 显示审批流程是否被禁用的状态提示
- 显示审批人是否离职的状态标记

**业务场景\uff1a**
- 审批人查看合同审批历史
- 了解当前审批进度
- 查看其他审批人的意见
- 查看流程是否被禁用

**路径参数\uff1a**
- contract_id: 合同ID

**返回字段\uff1a**
- 基本信息\uff1a审批ID、状态、提交时间等
- flow: 审批流程信息
- flow_is_active: 审批流程是否启用\uff08True-启用\uff0cFalse-禁用\uff09
- flow_disabled_warning: 流程禁用提示信息\uff08仅当流程被禁用时显示\uff09
- current_node: 当前待审批节点
- records: 审批记录列表
  - node_name: 节点名称
  - approver_name: 审批人姓名\uff08离职人员显示「姓名\uff08已离职\uff09」\uff09
  - approver_status: 审批人状态\uff08active/inactive/suspended\uff09
  - approver_status_display: 审批人状态显示\uff08在职/已离职/已停用\uff09
  - action: 审批动作\uff08APPROVE/REJECT\uff09
  - comment: 审批意见
  - created_at: 审批时间

**状态说明\uff1a**
- PENDING: 待审批
- APPROVED: 已通过
- REJECTED: 已拒绝
- CANCELLED: 已撤回

**流程禁用处理\uff08场景六\uff09\uff1a**
- 已有审批实例继续执行现有流程\uff08不受影响\uff09
- 新提交审批不匹配已禁用流程
- 流程恢复启用后立即生效
""")
def get_approval_detail(
    contract_id: int,
    team_id: int = _contract_detail_team_dependency,
    current_user: User = _contract_detail_current_user_dependency,
    db: Session = _contract_detail_db_dependency,
) -> ApprovalDetailResponse:
    from app.models.user import UserStatus

    approval = approval_crud.get_by_contract_id(db, contract_id, team_id)
    if not approval:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="审批流程不存在"
        )

    _check_approval_detail_permissions(db, approval, current_user, team_id)
    # 获取审批记录并填充审批人状态信息
    records = approval_crud.get_records(db, int(approval.id), int(approval.team_id))

    # 收集所有审批人ID,批量查询用户状态;实例数据始终限定在审批团队内。
    approver_ids = [int(r.approver_id) for r in records if r.approver_id and str(r.approver_id).isdigit()]
    users = {}
    if approver_ids:
        user_list = db.query(User).join(UserRole, UserRole.user_id == User.id).filter(
            User.id.in_(approver_ids),
            UserRole.team_id == approval.team_id,
        ).distinct().all()
        users = {str(u.id): u for u in user_list}

    # 构建审批记录响应(含审批人状态)
    record_responses = []
    for record in records:
        approver_id = cast("str", record.approver_id)
        user = users.get(approver_id)
        approver_status = None
        approver_status_display = None
        approver_name = cast("str | None", record.approver_name)

        if user:
            approver_status = user.status.value if user.status else None
            # 状态显示:active=在职,inactive=已离职,suspended=已停用
            status_display_map: dict[UserStatus | None, str] = {
                UserStatus.ACTIVE: "在职",
                UserStatus.INACTIVE: "已离职",
                UserStatus.SUSPENDED: "已停用"
            }
            approver_status_display = status_display_map.get(user.status)
            # 如果审批人已离职,显示姓名时添加「已离职」标记
            if user.status == UserStatus.INACTIVE and approver_name:
                approver_name = f"{approver_name}\uff08已离职\uff09"

        record_responses.append(
            ApprovalRecordResponse(
                id=cast("int", record.id),
                approval_id=cast("int", record.approval_id),
                node_id=cast("int | None", record.node_id),
                node_name=_approval_node_name(
                    approval,
                    int(record.node_id) if record.node_id is not None else None,
                    record.node.node_name if record.node else None,
                ),
                approver_id=approver_id,
                approver_name=approver_name,
                approver_status=approver_status,
                approver_status_display=approver_status_display,
                action=cast("str", record.action),
                comment=cast("str | None", record.comment),
                created_time=cast("datetime", record.created_time)
            )
        )

    # 检查流程是否被禁用,添加提示信息
    flow_is_active = None
    flow_disabled_warning = None

    if approval.flow:
        flow_is_active = approval.flow.is_active == 1
        if not flow_is_active:
            flow_disabled_warning = "审批流程已被管理员禁用\uff0c当前审批将继续执行\uff0c但新提交审批不会使用该流程"

    # 构建审批详情响应
    return ApprovalDetailResponse(
        id=cast("int", approval.id),
        contract_id=cast("int", approval.contract_id),
        flow_id=cast("int | None", approval.flow_id),
        flow_name=approval.flow.flow_name if approval.flow else None,
        current_node_id=approval.current_node_id,
        current_node_name=_approval_current_node_name(approval),
        status=cast("str", approval.status),
        submitter_id=cast("str", approval.submitter_id),
        submitter_name=cast("str | None", approval.submitter_name),
        created_time=cast("datetime", approval.created_time),
        updated_time=cast("datetime", approval.updated_time),
        flow=_approval_flow_detail_payload(approval),
        flow_is_active=flow_is_active,
        flow_disabled_warning=flow_disabled_warning,
        records=record_responses
    )


def _approval_flow_detail_payload(approval: Approval) -> ApprovalFlowDetailResponse | None:
    flow = approval.flow
    if not flow:
        return None
    if approval.nodes_snapshot is None:
        return ApprovalFlowDetailResponse.model_validate(flow)
    return ApprovalFlowDetailResponse.model_validate({
        "id": flow.id,
        "flow_name": flow.flow_name,
        "flow_code": flow.flow_code,
        "description": flow.description,
        "min_amount": flow.min_amount,
        "max_amount": flow.max_amount,
        "license_type": flow.license_type,
        "is_active": flow.is_active,
        "business_type": flow.business_type,
        "created_time": flow.created_time,
        "last_modified_time": flow.last_modified_time,
        "nodes": [
            {
                "id": node.get("node_id"),
                "flow_id": flow.id,
                "node_name": node.get("node_name") or "",
                "node_code": node.get("node_code") or "",
                "node_order": index,
                "description": None,
                "node_type": node.get("node_type") or "APPROVAL",
                "approver_roles": [],
                "approver_users": [],
                "created_time": approval.created_time,
            }
            for index, node in enumerate(approval.nodes_snapshot, start=1)
        ],
    })


def _feishu_notification_status(result: dict[str, int]) -> str:
    if result.get("queued", 0) > 0:
        return "queued"
    if result.get("success", 0) > 0:
        return "success"
    if result.get("failed", 0) > 0:
        return "failed"
    return "skipped"


def _queue_outbound_notification(
    db: Session, request: "OutboundNotificationJobRequest | None", *, commit: bool = True
) -> dict[str, int]:
    if request is None:
        return {"success": 0, "failed": 0, "skipped": 1, "queued": 0}
    if commit:
        db.commit()
    outbound_notification_job_service.kick(request)
    return {"success": 0, "failed": 0, "skipped": 0, "queued": 1}


# 自审追加权限校验失败文案(按 entity_type 分发)。
# 按 entity_type 统一分发自审权限提示。
_SELF_APPROVE_DENY_MSG = {
    BusinessType.CONTRACT: "您没有权限审批自己创建的合同",
    BusinessType.CONTRACT_CHANGE: "您没有权限审批自己创建的合同",
    BusinessType.PAYMENT: "您没有权限审批自己创建的回款",
    BusinessType.INVOICE: "您没有权限审批自己创建的发票",
    BusinessType.INVOICE_REISSUE: "您没有权限审批自己创建的发票重开申请",
    BusinessType.LICENSE: "您没有权限审批自己创建的License申请",
    BusinessType.OPPORTUNITY: "您没有权限审批自己创建的商机",
}


def _check_self_approval_permission(
    db: Session,
    current_user: User,
    team_id: int,
    entity_type: str,
    entity_id: int,
) -> None:
    """自审追加权限校验\uff1a审批人 == 单据提交人时需 `<resource>:approve:own` 权限码。

    泛化自原 CONTRACT 自审校验\uff08contract.creator_id + contract:approve:own\uff09\uff0c
    按 entity_type 分发到 A4 适配器取实体 / 提交人\uff0c避免在 API 层硬编码各模型
    字段名\uff08CONTRACT/PAYMENT→creator_id\uff0cINVOICE→applicant_id\uff09。

    - entity 为 None\uff08单据已删 / 跨 team\uff09时跳过\uff08对齐原 `if contract and ...` 语义\uff09
    - 提交人 id == str(current_user.id) 视为自审\uff0c查用户权限码\uff0c
      缺 `<resource>:approve:own`\uff08contract/payment/invoice/invoice_reissue/...\uff09→ 403
    - 重复查 DB\uff08approve 端点已取过 entity\uff09可接受——审批非高频\uff0c留 M-1 一并优化
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
    permission_resource = (
        BusinessType.CONTRACT if entity_type == BusinessType.CONTRACT_CHANGE else entity_type
    )
    required_code = f"{permission_resource.lower()}:approve:own"
    if required_code not in permission_codes:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=_SELF_APPROVE_DENY_MSG[entity_type],
        )


def _check_approve_permissions(
    db: Session,
    approval: Approval,
    current_user: User,
    team_id: int,
    *,
    entity_type: str | None = None,
    entity_id: int | None = None,
) -> None:
    """审批权限校验\uff08旧 `/contracts/{id}/approve` 与新 generic approve 共用\uff09。

    - 当前节点冻结审批人校验 → 403
    - 自审追加\uff1acurrent_user 是单据提交人时需 `<resource>:approve:own` 权限 → 403
      \uff08CONTRACT/PAYMENT/INVOICE/LICENSE/OPPORTUNITY 均校验\uff0c泛化自原 CONTRACT-only 逻辑\uff0cM-3\uff09

    旧合同端点传 entity_type=BusinessType.CONTRACT / entity_id=contract_id\uff1b
    新通用端点传路由参数 entity_type / entity_id。
    """
    if approval.team_id != team_id or not is_participant(
        db, approval, current_user.id, ApprovalParticipantKind.APPROVER
    ):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="您不是当前节点的审批人",
        )

    # 自审追加权限校验(CONTRACT/PAYMENT/INVOICE/INVOICE_REISSUE/LICENSE/OPPORTUNITY 通用)
    if entity_type is not None and entity_id is not None:
        _check_self_approval_permission(
            db, current_user, team_id, entity_type, entity_id
        )


def _check_approval_detail_permissions(
    db: Session,
    approval: Approval,
    current_user: User,
    team_id: int,
) -> None:
    """审批详情允许提交人、当前审批人、已处理人、团队管理员\uff0c以及可查看该客户的人只读。"""
    if approval.team_id != team_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="审批流程不存在")
    user_id_str = str(current_user.id)
    user_roles = role_crud.get_user_roles(db, current_user.id, team_id)
    role_codes = {r.code for r in user_roles}

    if "TEAM_ADMIN" in role_codes:
        return

    if approval.submitter_id == user_id_str:
        return

    if is_participant(db, approval, current_user.id, ApprovalParticipantKind.APPROVER) or is_participant(
        db, approval, int(current_user.id), ApprovalParticipantKind.CC,
    ):
        return

    has_processed_record = db.query(ApprovalRecord.id).filter(
        ApprovalRecord.team_id == team_id,
        ApprovalRecord.approval_id == approval.id,
        ApprovalRecord.approver_id == user_id_str,
        ApprovalRecord.action != ApprovalAction.SUBMIT,
    ).first()
    if has_processed_record:
        return

    try:
        adapter = get_adapter(cast("str", approval.business_type))
    except ValueError:
        adapter = None
    entity = adapter.get_entity(db, cast("int", approval.business_id), team_id) if adapter is not None else None
    customer_id = get_approval_customer_id(db, cast("str", approval.business_type), entity)
    if customer_id and user_can_view_customer(db, team_id, customer_id, current_user.id):
        return

    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="您没有权限查看该审批详情",
    )


# ============================================================================
# 通用审批 API 端点(CONTRACT / PAYMENT / INVOICE / LICENSE / OPPORTUNITY 统一入口)
# ============================================================================
# 设计要点:
# - 新端点 prefix 沿用既有 router 的 `/v1/approvals`
# - entity_type 用 is_valid_business_type(A1)校验,非法 → 400
# - submit:创建审批实例,由事务管理器入队当前节点审批通知。
# - approve:校验冻结的当前 APPROVER 参与人;发票额外回写 reviewer_id / review_comment。
# - cancel:approval_crud.cancel 内部校验 submitter_id==user_id
# - detail:get_by_entity → 序列化返回
# - 旧 `/contracts/{contract_id}/submit|approve|cancel|detail` 保留为 wrapper,
#   合同回归契约(E1)由此保证。
# ============================================================================


def _serialize_generic_approval(approval: Approval, db: Session) -> dict[str, object]:
    """通用审批实例序列化 —— 不依赖 contract_id\uff08INVOICE/PAYMENT 该字段为 None\uff09。

    复刻 `/contracts/{contract_id}/detail`\uff08:950-1039\uff09关键字段\uff0c但 contract_id 可空、
    并补 business_type / business_id。审批人状态展示\uff08在职/离职\uff09由 A8 通知泛化时
    统一加\uff0c此处先返回基础字段\uff0c保证前端通用审批页可用。
    """
    from app.models.user import UserStatus

    records = approval_crud.get_records(db, int(approval.id), int(approval.team_id))

    approver_ids = []
    for r in records:
        if r.approver_id and str(r.approver_id).isdigit():
            approver_ids.append(int(r.approver_id))
    users: dict[str, User] = {}
    if approver_ids:
        user_list = db.query(User).join(UserRole, UserRole.user_id == User.id).filter(
            User.id.in_(approver_ids),
            UserRole.team_id == approval.team_id,
        ).distinct().all()
        users = {str(u.id): u for u in user_list}

    status_display_map: dict[UserStatus | None, str] = {
        UserStatus.ACTIVE: "在职",
        UserStatus.INACTIVE: "已离职",
        UserStatus.SUSPENDED: "已停用",
    }

    record_list = []
    for record in records:
        user = users.get(str(record.approver_id)) if record.approver_id else None
        approver_name = cast("str | None", record.approver_name)
        approver_status = None
        approver_status_display = None
        if user:
            approver_status = user.status.value if user.status else None
            approver_status_display = status_display_map.get(user.status)
            if user.status == UserStatus.INACTIVE and approver_name:
                approver_name = f"{approver_name}\uff08已离职\uff09"
        record_list.append({
            "id": record.id,
            "approval_id": record.approval_id,
            "node_id": record.node_id,
            "node_name": _approval_node_name(
                approval,
                int(record.node_id) if record.node_id is not None else None,
                record.node.node_name if record.node else None,
            ),
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
                "审批流程已被管理员禁用\uff0c当前审批将继续执行\uff0c但新提交审批不会使用该流程"
            )

    summary = None
    if approval.business_id:
        summaries = approval_crud._batch_entity_summaries(db, [approval], cast("int", approval.team_id))
        summary = summaries.get((cast("str", approval.business_type), cast("int", approval.business_id)))
    entity_detail = _build_approval_entity_detail(approval, db)

    return {
        "id": approval.id,
        "business_type": approval.business_type,
        "business_id": approval.business_id,
        "business_public_id": summary.get("business_public_id") if summary else None,
        "original_invoice_application_id": summary.get("original_invoice_application_id") if summary else None,
        "contract_id": approval.contract_id,
        "flow_id": approval.flow_id,
        "flow_name": approval.flow.flow_name if approval.flow else None,
        "current_node_id": approval.current_node_id,
        "current_node_name": _approval_current_node_name(approval),
        "status": approval.status,
        "submitter_id": approval.submitter_id,
        "submitter_name": approval.submitter_name,
        "created_time": approval.created_time,
        "updated_time": approval.updated_time,
        "overdue_hours": (
            int((datetime.now() - approval.created_time).total_seconds() // 3600)
            if approval.status == ApprovalStatus.PENDING and approval.created_time
            else None
        ),
        "flow_is_active": flow_is_active,
        "flow_disabled_warning": flow_disabled_warning,
        "application_number": (
            summary.get("application_number") if summary else f"{approval.business_type}-{approval.business_id}"
        ),
        "entity_name": summary.get("entity_name") if summary else None,
        "entity_amount": summary.get("entity_amount") if summary else None,
        "actual_payer_name": summary.get("actual_payer_name") if summary else None,
        "customer_info": summary.get("customer_info") if summary else None,
        "contract_file_path": summary.get("contract_file_path") if summary else None,
        "contract_file_name": summary.get("contract_file_name") if summary else None,
        "contract_file_size": summary.get("contract_file_size") if summary else None,
        "contract_file_mime_type": summary.get("contract_file_mime_type") if summary else None,
        "invoice_file_path": summary.get("invoice_file_path") if summary else None,
        "invoice_number": summary.get("invoice_number") if summary else None,
        "change_items": summary.get("change_items") if summary else None,
        "reason": summary.get("reason") if summary else None,
        "attachment_name": summary.get("attachment_name") if summary else None,
        "attachment_size": summary.get("attachment_size") if summary else None,
        "attachment_mime_type": summary.get("attachment_mime_type") if summary else None,
        "issued_time": summary.get("issued_time") if summary else None,
        "license_status": summary.get("license_status") if summary else None,
        "entity_detail": entity_detail,
        "records": record_list,
    }



def _payment_composition_detail(record: PaymentRecord) -> dict[str, int | float]:
    renewal_headcount = record.renewal_headcount
    renewal_amount = record.renewal_amount
    expansion_headcount = record.expansion_headcount
    expansion_amount = record.expansion_amount
    if (
        renewal_headcount is None
        or renewal_amount is None
        or expansion_headcount is None
        or expansion_amount is None
    ):
        return {}
    return {
        "renewal_headcount": int(renewal_headcount),
        "renewal_amount": float(renewal_amount),
        "expansion_headcount": int(expansion_headcount),
        "expansion_amount": float(expansion_amount),
    }


def _build_approval_entity_detail(approval: Approval, db: Session) -> dict[str, object]:
    try:
        return _build_approval_entity_detail_unsafe(approval, db)
    except OperationalError as exc:
        db.rollback()
        log_with_fields(
            logger,
            30,
            "[Approval] Entity detail unavailable; returning approval metadata only",
            business_type=approval.business_type,
            business_id=approval.business_id,
            error=str(exc),
        )
        return {}


def _build_approval_entity_detail_unsafe(approval: Approval, db: Session) -> dict[str, object]:
    """Build business-facing detail for approval readers.

    The approval center should present the actual business object under review,
    not only approval-instance metadata. Keep this payload generic so the
    frontend can render type-specific fields without extra round trips.
    """
    from app.crud.invoice import invoice_application_crud
    from app.models.contract import Contract
    from app.models.contract_change import ContractChangeRequest
    from app.models.customer import Contact
    from app.models.deployment import DeploymentInfo
    from app.models.invoice import InvoiceApplication, InvoiceReissueApplication
    from app.models.license_application import LicenseApplication
    from app.models.opportunity import Opportunity
    from app.models.payment import PaymentPlan, PaymentRecord

    def money(value: "int | float | Decimal | None") -> float | None:
        return float(value) if value is not None else None

    team_id = approval.team_id
    business_id = approval.business_id
    if approval.business_type == BusinessType.CONTRACT_CHANGE:
        change = db.query(ContractChangeRequest).filter(
            ContractChangeRequest.id == business_id,
            ContractChangeRequest.team_id == team_id,
            ContractChangeRequest.deleted_at.is_(None),
        ).first()
        if not change:
            return {}
        contract = db.query(Contract).filter(
            Contract.id == change.contract_id,
            Contract.team_id == team_id,
            Contract.deleted_at.is_(None),
        ).first()
        if not contract:
            return {}
        from app.services.contract_change import amount_change_values, contract_change_service
        old_amount, new_amount = amount_change_values(change)
        snapshot = contract_change_service.get_financial_snapshot(db, cast("int", team_id), contract.id)
        return {
            "contract_id": contract.id,
            "contract_number": contract.contract_number,
            "contract_name": contract.contract_name,
            "original_amount": money(old_amount),
            "new_amount": money(new_amount),
            "change_items": change.change_items_json or [],
            "reason": change.reason,
            "attachment_name": change.attachment_name,
            "attachment_size": change.attachment_size,
            "attachment_mime_type": change.attachment_mime_type,
            "financial_snapshot": {
                "paid_amount": str(snapshot.paid_amount),
                "invoiced_amount": str(snapshot.invoiced_amount),
                "planned_amount": str(snapshot.planned_amount),
                "floor_amount": str(snapshot.floor_amount),
            },
        }

    if approval.business_type == BusinessType.CONTRACT:
        contract = db.query(Contract).filter(
            Contract.id == business_id,
            Contract.team_id == team_id,
        ).first()
        if not contract:
            return {}
        contact = None
        if contract.signing_contact_id:
            contact = db.query(Contact).filter(
                Contact.id == contract.signing_contact_id,
                Contact.team_id == team_id,
            ).first()
        return {
            "contract_number": contract.contract_number,
            "contract_name": contract.contract_name,
            "user_count": contract.user_count,
            "total_amount": money(contract.total_amount),
            "license_type": contract.license_type,
            "subscription_years": contract.subscription_years,
            "standard_unit_price": money(contract.standard_unit_price),
            "signing_date": contract.signing_date,
            "effective_date": contract.effective_date,
            "expiry_date": contract.expiry_date,
            "status": contract.status,
            "payment_status": contract.payment_status,
            "opportunity_name": contract.opportunity.opportunity_name if contract.opportunity else None,
            "opportunity_public_id": contract.opportunity.public_id if contract.opportunity else None,
            "signing_contact_name": contact.name if contact else None,
            "signing_contact_mobile": contact.mobile if contact else None,
            "contract_file_name": contract.contract_file_name,
            "contract_file_path": contract.contract_file_path,
        }

    if approval.business_type == BusinessType.PAYMENT:
        record = db.query(PaymentRecord).filter(
            PaymentRecord.id == business_id,
            PaymentRecord.team_id == team_id,
        ).first()
        if not record:
            return {}
        plan = db.query(PaymentPlan).filter(
            PaymentPlan.id == record.payment_plan_id,
            PaymentPlan.team_id == team_id,
        ).first()
        contract = plan.contract if plan else None
        opportunity = contract.opportunity if contract else None
        return {
            "record_number": record.record_number,
            "actual_amount": money(record.actual_amount),
            "actual_payer_name": record.actual_payer_name,
            "payment_date": record.payment_date,
            "confirmation_status": record.confirmation_status,
            "confirmed_by_name": record.confirmed_by_name,
            "confirmed_time": record.confirmed_time,
            "confirmation_notes": record.confirmation_notes,
            "proof_attachment": record.proof_attachment,
            "notes": record.notes,
            **_payment_composition_detail(record),
            "plan_number": plan.plan_number if plan else None,
            "stage_name": plan.stage_name if plan else None,
            "planned_amount": money(plan.planned_amount) if plan else None,
            "due_date": plan.due_date if plan else None,
            "contract_name": contract.contract_name if contract else None,
            "contract_number": contract.contract_number if contract else None,
            "opportunity_name": opportunity.opportunity_name if opportunity else None,
            "contract_id": contract.id if contract else None,
            "opportunity_public_id": opportunity.public_id if opportunity else None,
        }

    if approval.business_type == BusinessType.INVOICE:
        invoice = db.query(InvoiceApplication).filter(
            InvoiceApplication.id == business_id,
            InvoiceApplication.team_id == team_id,
        ).first()
        if not invoice:
            return {}
        contract = invoice.contract
        opportunity = invoice.opportunity
        plan = invoice.payment_plan
        return {
            "application_number": invoice.application_number,
            "invoice_title_type": invoice.invoice_title_type,
            "invoice_title_text": invoice.invoice_title_text,
            "invoice_type": invoice.invoice_type,
            "invoice_amount": money(invoice.invoice_amount),
            "remark": invoice.remark,
            "invoice_taxpayer_id": invoice.invoice_taxpayer_id,
            "invoice_bank_name": invoice.invoice_bank_name,
            "invoice_bank_account": invoice.invoice_bank_account,
            "invoice_address": invoice.invoice_address,
            "invoice_phone": invoice.invoice_phone,
            "status": invoice.status,
            "invoice_number": invoice.invoice_number,
            "issued_time": invoice.issued_time,
            "contract_name": contract.contract_name if contract else None,
            "opportunity_name": opportunity.opportunity_name if opportunity else None,
            "payment_plan_stage_name": plan.stage_name if plan else None,
            "contract_id": contract.id if contract else None,
            "opportunity_public_id": opportunity.public_id if opportunity else None,
        }

    if approval.business_type == BusinessType.INVOICE_REISSUE:
        reissue = db.query(InvoiceReissueApplication).filter(
            InvoiceReissueApplication.id == business_id,
            InvoiceReissueApplication.team_id == team_id,
        ).first()
        if not reissue:
            return {}
        original = invoice_application_crud.get_by_id(
            db, reissue.original_invoice_application_id, cast("int", team_id)
        )
        return {
            "application_number": reissue.application_number,
            "original_invoice_application_id": reissue.original_invoice_application_id,
            "original_invoice_application_number": original.application_number if original else None,
            "original_invoice": {
                "invoice_type": original.invoice_type,
                "invoice_title_type": original.invoice_title_type,
                "invoice_title_text": original.invoice_title_text,
                "invoice_taxpayer_id": original.invoice_taxpayer_id,
                "invoice_address": original.invoice_address,
                "invoice_phone": original.invoice_phone,
                "invoice_bank_name": original.invoice_bank_name,
                "invoice_bank_account": original.invoice_bank_account,
                "invoice_amount": money(original.invoice_amount),
            } if original else None,
            "reason": reissue.reason,
            "invoice_title_type": reissue.invoice_title_type,
            "invoice_title_text": reissue.invoice_title_text,
            "invoice_type": reissue.invoice_type,
            "invoice_amount": money(reissue.invoice_amount),
            "invoice_taxpayer_id": reissue.invoice_taxpayer_id,
            "invoice_bank_name": reissue.invoice_bank_name,
            "invoice_bank_account": reissue.invoice_bank_account,
            "invoice_address": reissue.invoice_address,
            "invoice_phone": reissue.invoice_phone,
            "status": reissue.status,
            "red_invoice_file_path": reissue.red_invoice_file_path,
            "red_invoice_number": reissue.red_invoice_number,
            "red_issued_time": reissue.red_issued_time,
            "new_invoice_file_path": reissue.new_invoice_file_path,
            "new_invoice_number": reissue.new_invoice_number,
            "new_issued_time": reissue.new_issued_time,
            "completed_time": reissue.completed_time,
        }

    if approval.business_type == BusinessType.LICENSE:
        license_application = db.query(LicenseApplication).filter(
            LicenseApplication.id == business_id,
            LicenseApplication.team_id == team_id,
        ).first()
        if not license_application:
            return {}
        deployment = db.query(DeploymentInfo).filter(
            DeploymentInfo.id == license_application.deployment_info_id,
            DeploymentInfo.team_id == team_id,
        ).first() if license_application.deployment_info_id else None
        return {
            "application_number": license_application.application_number,
            "license_type": license_application.license_type,
            "product_name": license_application.product_name,
            "expiry_date": license_application.expiry_date,
            "is_permanent": license_application.is_permanent,
            "status": license_application.status,
            "deployment_name": deployment.deployment_name if deployment else None,
            "server_address": deployment.server_address if deployment else None,
            "authorized_users": license_application.authorized_users,
            "contract_name": license_application.contract.contract_name if license_application.contract else None,
            "contract_id": license_application.contract_id,
            "remark": license_application.remark,
            "enterprise_id": license_application.enterprise_id,
            "supported_modules": license_application.supported_modules,
            "server_license_code": license_application.server_license_code,
            "client_license_code": license_application.client_license_code,
        }

    if approval.business_type == BusinessType.OPPORTUNITY:
        opportunity = db.query(Opportunity).filter(
            Opportunity.id == business_id,
            Opportunity.team_id == team_id,
        ).first()
        if not opportunity:
            return {}
        return {
            "opportunity_name": opportunity.opportunity_name,
            "opportunity_public_id": opportunity.public_id,
            "opportunity_number": opportunity.opportunity_number,
            "product_name": opportunity.product.name if opportunity.product else None,
            "total_amount": money(opportunity.total_amount),
            "user_count": opportunity.user_count,
            "unit_price": money(opportunity.unit_price),
            "license_type": opportunity.license_type,
            "subscription_years": opportunity.subscription_years,
            "purchase_type": opportunity.purchase_type,
            "decision_maker_count": opportunity.decision_maker_count,
            "expected_closing_date": opportunity.expected_closing_date,
            "current_stage_name": opportunity.current_stage_name,
            "win_probability": opportunity.win_probability,
            "status": opportunity.status,
            "owner_id": opportunity.owner_id,
        }

    return {}


def _validate_entity_type(entity_type: str) -> None:
    """entity_type 校验\uff1a配置类型或内部合同变更类型。"""
    if not is_valid_business_type(entity_type) and entity_type != BusinessType.CONTRACT_CHANGE:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                f"无效的业务单据类型: {entity_type}\uff0c仅支持 "
                "CONTRACT / CONTRACT_CHANGE / PAYMENT / INVOICE / LICENSE / OPPORTUNITY"
            ),
        )


_bulk_approve_db_dependency = Depends(get_db)
_bulk_approve_team_dependency = Depends(get_current_user_team)
_bulk_approve_current_user_dependency = Depends(get_current_active_user)


@router.post("/bulk-approve", response_model=None, summary="批量审批")
async def bulk_approve(
    request: BulkApproveRequest,
    db: Session = _bulk_approve_db_dependency,
    team_id: int = _bulk_approve_team_dependency,
    current_user: User = _bulk_approve_current_user_dependency,
) -> dict[str, object]:
    _validate_entity_type(request.entity_type)

    success_count = 0
    failed = []
    for entity_id in request.ids:
        try:
            approval = approval_crud.get_by_entity(db, request.entity_type, entity_id, team_id)
            if not approval:
                failed.append({"id": entity_id, "reason": "审批流程不存在"})
                continue
            updated_time = (request.updated_times or {}).get(str(entity_id))
            if approval.status != ApprovalStatus.PENDING:
                _check_approval_detail_permissions(db, approval, current_user, team_id)
                if updated_time is not None and approval.updated_time != updated_time:
                    failed.append({"id": entity_id, "reason": "已被他人处理"})
                else:
                    failed.append({"id": entity_id, "reason": "当前审批已结束\uff0c无法进行审批操作"})
                continue
            if approval.current_node_id is None:
                failed.append({"id": entity_id, "reason": "当前审批节点不存在"})
                continue

            _check_approve_permissions(
                db,
                approval,
                current_user,
                team_id,
                entity_type=request.entity_type,
                entity_id=entity_id,
            )
            action_request = ApprovalActionRequest(
                action=request.action,
                comment=request.comment,
                updated_time=updated_time,
            )
            approval = approval_crud.approve(
                db,
                approval,
                action_request,
                str(current_user.id),
                current_user.name,
            )
            success_count += 1
            try:
                if request.action.value == ApprovalAction.REJECT:
                    notification = outbound_notification_job_service.enqueue_rejected(
                        db, approval=approval, team_id=team_id, actor_id=str(current_user.id),
                        reject_reason=request.comment or "无",
                    )
                elif approval.status == ApprovalStatus.APPROVED:
                    notification = outbound_notification_job_service.enqueue_approved(
                        db, approval=approval, team_id=team_id, actor_id=str(current_user.id),
                    )
                else:
                    notification = outbound_notification_job_service.enqueue_pending_for_approval(
                        db, approval=approval, team_id=team_id, actor_id=str(current_user.id),
                    )
                _queue_outbound_notification(db, notification)
            except Exception:
                db.rollback()
                logger.exception("批量审批通知入队失败 approval_id=%s", approval.id)
        except HTTPException as exc:
            db.rollback()
            failed.append({"id": entity_id, "reason": exc.detail})
        except ValueError as exc:
            db.rollback()
            reason = "已被他人处理" if "审批已被其他用户处理" in str(exc) else str(exc)
            failed.append({"id": entity_id, "reason": reason})
        except Exception as exc:
            db.rollback()
            logger.error("批量审批失败 entity_type=%s id=%s: %s", request.entity_type, entity_id, exc)
            failed.append({"id": entity_id, "reason": "审批失败"})

    return {
        "success_count": success_count,
        "failed_count": len(failed),
        "failed": failed,
    }


_generic_submit_db_dependency = Depends(get_db)
_generic_submit_team_dependency = Depends(get_current_user_team)
_generic_submit_current_user_dependency = Depends(get_current_active_user)


@router.post(
    "/{entity_type}/{entity_id}/submit",
    response_model=GenericApprovalSubmitResponse,
    summary="提交审批\uff08通用\uff09",
    description="""
将草稿状态的业务单据\uff08合同/回款/发票/License/商机\uff09提交到审批流程\uff0c统一入口。

**功能说明\uff1a**
- 按 entity_type 走对应适配器取实体\uff1b不存在 → 404
- 统一通过 ApprovalTransactionManager 提交审批\uff0c覆盖驳回重提、状态流转、审批实例创建
- 通知意图写入提交事务\uff0c由出站通知 worker 发送\uff0c失败不阻断业务流程

**路径参数\uff1a**
- entity_type: CONTRACT / PAYMENT / INVOICE / LICENSE / OPPORTUNITY
- entity_id: 业务单据标识\uff1bOPPORTUNITY 必须传商机对外 ID\uff08opp_...\uff09
""",
)
async def submit_generic_approval(
    entity_type: str,
    entity_id: str,
    submit_data: GenericApprovalSubmitRequest,
    db: Session = _generic_submit_db_dependency,
    team_id: int = _generic_submit_team_dependency,
    current_user: User = _generic_submit_current_user_dependency,
) -> GenericApprovalSubmitResponse:
    del submit_data
    _validate_entity_type(entity_type)
    resolved_entity_id = _resolve_generic_entity_id(
        db, entity_type=entity_type, entity_ref=entity_id, team_id=team_id
    )

    adapter = get_adapter(entity_type)
    entity = adapter.get_entity(db, resolved_entity_id, team_id)
    if entity is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="业务单据不存在",
        )

    ap, error_msg = approval_transaction_manager.submit_for_approval(
        db=db,
        business_type=entity_type,
        entity_id=resolved_entity_id,
        team_id=team_id,
        submitter_id=str(current_user.id),
        submitter_name=current_user.name,
    )
    if ap is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=error_msg or "提交审批失败",
        )

    # 幂等重试只返回现有审批实例,不重复写提交日志或发送通知。
    if error_msg is None:
        log_approval_operation(
            operation="Submit",
            approval_id=cast("int", ap.id),
            flow_name=ap.flow.flow_name if ap.flow else None,
            node_name=_approval_current_node_name(ap),
            operator=current_user.name,
            flow_direction="submitted",
            business_type=entity_type,
            business_id=resolved_entity_id,
        )
        if ap.current_node_id is not None:
            log_approval_operation(
                operation="Submit",
                approval_id=cast("int", ap.id),
                flow_name=ap.flow.flow_name if ap.flow else None,
                node_name=_approval_current_node_name(ap),
                operator=current_user.name,
                flow_direction="submitted",
                notification_status="queued",
                business_type=entity_type,
                business_id=resolved_entity_id,
            )

    return GenericApprovalSubmitResponse(approval_id=cast("int", ap.id), status=cast("str", ap.status))


_generic_approve_db_dependency = Depends(get_db)
_generic_approve_team_dependency = Depends(get_current_user_team)
_generic_approve_current_user_dependency = Depends(get_current_active_user)


@router.post(
    "/{entity_type}/{entity_id}/approve",
    response_model=None,
    summary="审批通过/拒绝\uff08通用\uff09",
    description="""
对当前待审批的业务单据\uff08合同/回款/发票/License\uff09进行审批操作。

**功能说明\uff1a**
- get_by_entity 取审批实例\uff1b不存在 → 404
- OPPORTUNITY 路由参数必须传商机对外 ID\uff08opp_...\uff09\uff0c接口内部解析为数据库 ID
- 只有提交时确定的当前节点审批人可操作\uff0c否则返回 403
- approval_crud.approve(...) 内部已调适配器 on_approved/on_rejected 切单据状态
  \uff08INVOICE 写 status / reviewed_time\uff1bPAYMENT 写 confirmation_status\uff1bCONTRACT/LICENSE 写 status\uff09
- **D3 端点回写**\uff1abusiness_type==INVOICE 时\uff0c由本端点补写 reviewer_id / review_comment
  两字段\uff08不扩适配器签名\uff0cPre-Flight 定案\uff09
- 按审批结果入队下一节点的待审批通知或审批结果通知\uff1b抄送由审批流程推进时入队。
""",
)
async def approve_generic_approval(
    entity_type: str,
    entity_id: str,
    action_request: ApprovalActionRequest,
    db: Session = _generic_approve_db_dependency,
    team_id: int = _generic_approve_team_dependency,
    current_user: User = _generic_approve_current_user_dependency,
) -> dict[str, object]:
    _validate_entity_type(entity_type)
    resolved_entity_id = _resolve_generic_entity_id(
        db, entity_type=entity_type, entity_ref=entity_id, team_id=team_id
    )

    approval = approval_crud.get_by_entity(db, entity_type, resolved_entity_id, team_id)
    if not approval:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="审批流程不存在",
        )
    if approval.current_node_id is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="当前审批节点不存在",
        )

    # 校验冻结的当前节点审批人及自审权限(与合同端点共用)。
    _check_approve_permissions(
        db, approval, current_user, team_id,
        entity_type=entity_type, entity_id=resolved_entity_id,
    )

    current_node_name = _approval_current_node_name(approval) or ""
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
                approval_id=cast("int", approval.id),
                business_type=entity_type,
                business_id=resolved_entity_id,
                operator=current_user.name,
                reason="乐观锁冲突\uff1a审批已被其他用户处理",
                level=40,
            )
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="该审批已被处理\uff0c请刷新页面查看最新状态",
            ) from e
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        ) from e

    # ---- D3 端点回写:INVOICE 补 reviewer_id / review_comment(不扩适配器)----
    # approval_crud.approve 已调 InvoiceApplicationAdapter.on_approved/on_rejected
    # 写 invoice.status / reviewed_time;此处仅补 reviewer_id / review_comment 两字段。
    # 对 APPROVE 与 REJECT 都写:审批人即 reviewer,意见即 review_comment。
    # D3 时序:approval_crud.approve 内部已 commit 落审批状态;此处是第二次 commit,
    # 失败时仅记 ERROR 日志——审批已完成不可回滚,reviewer 是审计信息可后补。
    if entity_type == BusinessType.INVOICE:
        inv_adapter = get_adapter(BusinessType.INVOICE)
        invoice = inv_adapter.get_entity(db, cast("int", approval.business_id), cast("int", approval.team_id))
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
                     "next_node" if approval.current_node_id is not None else "terminated")

    # 通知泛化:按审批结果入队 pending/approved/rejected
    notification_status = "skipped"
    adapter = get_adapter(entity_type)
    entity = adapter.get_entity(db, cast("int", approval.business_id), cast("int", approval.team_id))
    if entity is not None:
        _enqueue_customer_approval_intelligence(
            db,
            entity_type=entity_type,
            entity=entity,
            approval=approval,
            actor_id=str(current_user.id),
            action=action_request.action.value,
        )

    try:
        request = None
        if action_request.action.value == ApprovalAction.APPROVE:
            if approval.status == ApprovalStatus.APPROVED:
                request = outbound_notification_job_service.enqueue_approved(
                    db,
                    approval=approval,
                    team_id=team_id,
                    actor_id=str(current_user.id),
                )
            elif approval.current_node_id is not None:
                request = outbound_notification_job_service.enqueue_pending_for_approval(
                    db,
                    approval=approval,
                    team_id=team_id,
                    actor_id=str(current_user.id),
                )
        elif action_request.action.value == ApprovalAction.REJECT:
            request = outbound_notification_job_service.enqueue_rejected(
                db,
                approval=approval,
                team_id=team_id,
                reject_reason=action_request.comment or "无",
                actor_id=str(current_user.id),
            )
        result = _queue_outbound_notification(db, request)
        notification_status = _feishu_notification_status(result)
    except Exception as notify_error:
        notification_status = "failed"
        logger.error(
            f"[Approval] Generic notification failed: entity_type={entity_type}, "
            f"business_id={resolved_entity_id}, error={notify_error!s}"
        )

    log_approval_operation(
        operation="Approve" if action_request.action.value == ApprovalAction.APPROVE else "Reject",
        approval_id=cast("int", approval.id),
        flow_name=flow_name,
        node_name=current_node_name,
        operator=current_user.name,
        flow_direction=flow_direction_str,
        notification_status=notification_status,
        business_type=entity_type,
        business_id=resolved_entity_id,
    )

    db.refresh(approval)
    return _serialize_generic_approval(approval, db)


_generic_cancel_db_dependency = Depends(get_db)
_generic_cancel_team_dependency = Depends(get_current_user_team)
_generic_cancel_current_user_dependency = Depends(get_current_active_user)


@router.post(
    "/{entity_type}/{entity_id}/cancel",
    response_model=MessageResponse,
    summary="撤回审批\uff08通用\uff09",
    description="""
撤回审批中的业务单据审批流程。只有提交人本人可撤回\uff0c且仅限 PENDING 状态。
OPPORTUNITY 路由参数必须传商机对外 ID\uff08opp_...\uff09\uff0c接口内部解析为数据库 ID。
""",
)
async def cancel_generic_approval(
    entity_type: str,
    entity_id: str,
    db: Session = _generic_cancel_db_dependency,
    team_id: int = _generic_cancel_team_dependency,
    current_user: User = _generic_cancel_current_user_dependency,
) -> MessageResponse:
    _validate_entity_type(entity_type)
    resolved_entity_id = _resolve_generic_entity_id(
        db, entity_type=entity_type, entity_ref=entity_id, team_id=team_id
    )

    approval = approval_crud.get_by_entity(db, entity_type, resolved_entity_id, team_id)
    if not approval:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="审批流程不存在",
        )
    if entity_type == BusinessType.CONTRACT_CHANGE:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="合同变更审批不支持撤回",
        )

    current_node_name = _approval_current_node_name(approval) or ""
    flow_name = approval.flow.flow_name if approval.flow else ""
    approver_ids = current_approver_ids(db, approval)

    notify_request = None
    notification_status = "skipped"
    if approver_ids:
        try:
            notify_request = outbound_notification_job_service.enqueue_cancelled(
                db,
                approval=approval,
                team_id=team_id,
                actor_id=str(current_user.id),
                actor_name=current_user.name,
                recipient_user_ids=approver_ids,
            )
            notification_status = "queued" if notify_request is not None else "skipped"
        except Exception as notify_error:
            notification_status = "failed"
            logger.error(
                f"[Approval] Cancel notification failed: approval_id={approval.id}, error={notify_error!s}"
            )

    try:
        approval = approval_crud.cancel(db, approval, str(current_user.id))
    except ValueError as e:
        log_approval_operation(
            operation="Cancel",
            approval_id=cast("int", approval.id),
            business_type=entity_type,
            business_id=resolved_entity_id,
            operator=current_user.name,
            reason=str(e),
            level=40,
        )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        ) from e
    outbound_notification_job_service.kick(notify_request)
    entity = get_adapter(entity_type).get_entity(db, resolved_entity_id, team_id)
    if entity is not None:
        _enqueue_customer_approval_intelligence(
            db,
            entity_type=entity_type,
            entity=entity,
            approval=approval,
            actor_id=str(current_user.id),
            action="CANCEL",
        )

    log_approval_operation(
        operation="Cancel",
        approval_id=cast("int", approval.id),
        flow_name=flow_name,
        node_name=current_node_name,
        operator=current_user.name,
        flow_direction="cancelled",
        notification_status=notification_status,
        business_type=entity_type,
        business_id=resolved_entity_id,
    )
    return MessageResponse(message="审批已撤回")


_generic_remind_db_dependency = Depends(get_db)
_generic_remind_team_dependency = Depends(get_current_user_team)
_generic_remind_current_user_dependency = Depends(get_current_active_user)


@router.post(
    "/{entity_type}/{entity_id}/remind",
    response_model=MessageResponse,
    summary="手动催办审批\uff08通用\uff09",
    description=(
        "提交人可对自己提交且仍在审批中的单据手动发送催办通知给当前节点审批人。"
        "OPPORTUNITY 路由参数必须传商机对外 ID\uff08opp_...\uff09。"
    ),
)
async def remind_generic_approval(
    entity_type: str,
    entity_id: str,
    db: Session = _generic_remind_db_dependency,
    team_id: int = _generic_remind_team_dependency,
    current_user: User = _generic_remind_current_user_dependency,
) -> MessageResponse:
    _validate_entity_type(entity_type)
    resolved_entity_id = _resolve_generic_entity_id(
        db, entity_type=entity_type, entity_ref=entity_id, team_id=team_id
    )

    approval = approval_crud.get_by_entity(db, entity_type, resolved_entity_id, team_id)
    if not approval:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="审批流程不存在",
        )
    if approval.status != ApprovalStatus.PENDING:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="只有审批中的单据可以催办",
        )
    if approval.submitter_id != str(current_user.id):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="只能催办自己提交的审批",
        )
    if approval.current_node_id is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="当前审批节点不存在",
        )

    adapter = get_adapter(entity_type)
    entity = adapter.get_entity(db, resolved_entity_id, team_id)
    if entity is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="业务单据不存在",
        )

    approver_ids = current_approver_ids(db, approval)
    if not approver_ids:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="当前审批节点没有可通知的审批人",
        )

    notification_status = "skipped"
    try:
        request = outbound_notification_job_service.enqueue_reminder(
            db,
            approval=approval,
            team_id=team_id,
            actor_id=str(current_user.id),
            recipient_user_ids=approver_ids,
        )
        result = _queue_outbound_notification(db, request)
        notification_status = _feishu_notification_status(result)
    except Exception as notify_error:
        notification_status = "failed"
        logger.error(
            f"[Approval] Manual reminder failed: entity_type={entity_type}, "
            f"business_id={resolved_entity_id}, error={notify_error!s}"
        )

    log_approval_operation(
        operation="Remind",
        approval_id=cast("int", approval.id),
        flow_name=approval.flow.flow_name if approval.flow else "",
        node_name=_approval_current_node_name(approval) or "",
        operator=current_user.name,
        flow_direction="manual_reminder",
        notification_status=notification_status,
        business_type=entity_type,
        business_id=resolved_entity_id,
    )

    if notification_status == "failed":
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="催办通知发送失败",
        )
    if notification_status == "skipped":
        return MessageResponse(message="催办已提交\uff0c但暂无可发送的飞书通知对象")
    return MessageResponse(message="已发送催办通知")


_generic_detail_db_dependency = Depends(get_db)
_generic_detail_team_dependency = Depends(get_current_user_team)
_generic_detail_current_user_dependency = Depends(get_current_active_user)


@router.get(
    "/{entity_type}/{entity_id}/detail",
    response_model=GenericApprovalDetailResponse,
    summary="获取审批详情\uff08通用\uff09",
    description="""
按业务单据类型+ID 查询最新一条审批实例的完整详情\uff0c包括所有审批记录和当前状态。
OPPORTUNITY 路由参数必须传商机对外 ID\uff08opp_...\uff09\uff0c接口内部解析为数据库 ID。
""",
)
def detail_generic_approval(
    entity_type: str,
    entity_id: str,
    db: Session = _generic_detail_db_dependency,
    team_id: int = _generic_detail_team_dependency,
    current_user: User = _generic_detail_current_user_dependency,
) -> dict[str, object]:
    _validate_entity_type(entity_type)
    resolved_entity_id = _resolve_generic_entity_id(
        db, entity_type=entity_type, entity_ref=entity_id, team_id=team_id
    )

    approval = approval_crud.get_by_entity(db, entity_type, resolved_entity_id, team_id)
    if not approval:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="审批流程不存在",
        )
    _check_approval_detail_permissions(db, approval, current_user, team_id)
    return _serialize_generic_approval(approval, db)


_cc_detail_db_dependency = Depends(get_db)
_cc_detail_team_dependency = Depends(get_current_user_team)
_cc_detail_current_user_dependency = Depends(get_current_active_user)


@router.get("/cc/{approval_id}", response_model=ApprovalCcDetailResponse, summary="查看抄送审批详情")
def detail_cc_approval(
    approval_id: int,
    db: Session = _cc_detail_db_dependency,
    team_id: int = _cc_detail_team_dependency,
    current_user: User = _cc_detail_current_user_dependency,
) -> dict[str, object]:
    approval = approval_crud.get_by_id(db, approval_id, team_id)
    if approval is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="抄送审批不存在")
    deliveries = db.query(ApprovalParticipant).filter_by(
        team_id=team_id, approval_id=approval.id, user_id=current_user.id, kind=ApprovalParticipantKind.CC,
    ).order_by(ApprovalParticipant.id).all()
    if not deliveries:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="抄送审批不存在")
    return {
        **_serialize_generic_approval(approval, db),
        "cc_deliveries": [
            {"id": row.id, "node_id": row.node_id, "node_name": row.node_name, "created_time": row.created_time}
            for row in deliveries
        ],
    }


def _approval_attachment_response(
    db: Session,
    *,
    entity_type: str,
    resolved_entity_id: int,
    team_id: int,
) -> Response:
    """Load an approval-backed business attachment after authorization."""
    file_path: str | None = None
    file_name: str | None = None
    mime_type: str | None = None

    if entity_type == BusinessType.CONTRACT:
        from app.models.contract import Contract

        contract = db.query(Contract).filter(
            Contract.id == resolved_entity_id,
            Contract.team_id == team_id,
        ).first()
        if contract:
            file_path = contract.contract_file_path
            file_name = contract.contract_file_name
            mime_type = contract.contract_file_mime_type
    elif entity_type == BusinessType.INVOICE:
        from app.models.invoice import InvoiceApplication

        invoice = db.query(InvoiceApplication).filter(
            InvoiceApplication.id == resolved_entity_id,
            InvoiceApplication.team_id == team_id,
        ).first()
        if invoice:
            file_path = invoice.invoice_file_path
            extension = os.path.splitext(invoice.invoice_file_path or "")[1].lower()
            file_name = (
                f"{invoice.invoice_number or invoice.application_number or f'invoice_{resolved_entity_id}'}"
                f"{extension}"
            )
    elif entity_type == BusinessType.CONTRACT_CHANGE:
        from app.models.contract_change import ContractChangeRequest

        change = db.query(ContractChangeRequest).filter(
            ContractChangeRequest.id == resolved_entity_id,
            ContractChangeRequest.team_id == team_id,
            ContractChangeRequest.deleted_at.is_(None),
        ).first()
        if change:
            file_path = cast("str | None", change.attachment_path)
            file_name = cast("str | None", change.attachment_name)
            mime_type = cast("str | None", change.attachment_mime_type)
    else:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="该审批单据暂无可预览附件",
        )

    if not file_path:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="该审批单据暂无可预览附件",
        )

    try:
        full_path = file_storage_service.get_full_path(file_path)
    except FileStorageError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="文件路径非法",
        ) from exc

    if not os.path.exists(full_path):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="文件不存在",
        )

    with open(full_path, "rb") as f:
        content = f.read()

    filename = file_name or f"{entity_type.lower()}_{resolved_entity_id}{os.path.splitext(file_path)[1].lower()}"
    return Response(
        content=content,
        media_type=_approval_file_content_type(file_path, mime_type),
        headers={
            "Content-Disposition": _approval_file_content_disposition(filename),
        },
    )


_cc_file_db_dependency = Depends(get_db)
_cc_file_team_dependency = Depends(get_current_user_team)
_cc_file_current_user_dependency = Depends(get_current_active_user)


@router.get("/cc/{approval_id}/file", summary="预览或下载抄送审批附件")
def download_cc_approval_file(
    approval_id: int,
    db: Session = _cc_file_db_dependency,
    team_id: int = _cc_file_team_dependency,
    current_user: User = _cc_file_current_user_dependency,
) -> Response:
    approval = approval_crud.get_by_id(db, approval_id, team_id)
    if approval is None or not is_participant(
        db, approval, int(current_user.id), ApprovalParticipantKind.CC
    ):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="抄送审批不存在",
        )
    if approval.business_type not in {
        BusinessType.CONTRACT,
        BusinessType.INVOICE,
        BusinessType.CONTRACT_CHANGE,
    }:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="该审批单据暂无可预览附件",
        )
    return _approval_attachment_response(
        db,
        entity_type=str(approval.business_type),
        resolved_entity_id=int(approval.business_id),
        team_id=team_id,
    )


_generic_file_db_dependency = Depends(get_db)
_generic_file_team_dependency = Depends(get_current_user_team)
_generic_file_current_user_dependency = Depends(get_current_active_user)


@router.get(
    "/{entity_type}/{entity_id}/file",
    summary="预览或下载审批附件\uff08通用\uff09",
    description="在审批上下文中读取合同附件或发票文件\uff0c权限与审批详情保持一致。",
)
def download_generic_approval_file(
    entity_type: str,
    entity_id: str,
    db: Session = _generic_file_db_dependency,
    team_id: int = _generic_file_team_dependency,
    current_user: User = _generic_file_current_user_dependency,
) -> Response:
    _validate_entity_type(entity_type)
    resolved_entity_id = _resolve_generic_entity_id(
        db, entity_type=entity_type, entity_ref=entity_id, team_id=team_id
    )

    approval = approval_crud.get_by_entity(db, entity_type, resolved_entity_id, team_id)
    if not approval:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="审批流程不存在",
        )
    _check_approval_detail_permissions(db, approval, current_user, team_id)
    return _approval_attachment_response(
        db,
        entity_type=entity_type,
        resolved_entity_id=resolved_entity_id,
        team_id=team_id,
    )


# ============================================================================
# Task C3:通用审批列表端点 GET /v1/approvals
# ============================================================================
# 设计要点:
# - 各 tab 按当前审批人、处理记录、提交人或抄送参与人过滤,并限制在当前团队。
# - E9 N+1:approval_crud.list_approvals 内部分组批量预取实体摘要。
# - 响应:{items, total, pending_count}(pending_count=pending tab total,任意 tab 附)。
# ============================================================================


_list_tab_query = Query("pending", description="过滤维度\uff1apending/processed/submitted/cc")
_list_business_type_query = Query(None, description="业务类型过滤 CONTRACT/PAYMENT/INVOICE/LICENSE/OPPORTUNITY")
_list_business_type_exclude_query = Query(None, description="排除业务类型\uff0c多个值用英文逗号分隔")
_list_approval_status_query = Query(
    None,
    alias="status",
    description="审批状态过滤 PENDING/APPROVED/REJECTED/CANCELLED\uff0c多个值用英文逗号分隔",
)
_list_status_exclude_query = Query(None, description="排除审批状态\uff0c多个值用英文逗号分隔")
_list_application_number_query = Query(None, description="单号模糊搜索")
_list_entity_name_query = Query(None, description="实体名称模糊搜索")
_list_submitter_name_query = Query(None, description="提交人模糊搜索")
_list_search_query = Query(None, description="统一搜索\uff0c可搜索单号、实体或提交人")
_list_entity_amount_query = Query(None, description="金额精确筛选")
_list_created_time_start_query = Query(None, description="提交时间起始")
_list_created_time_end_query = Query(None, description="提交时间结束")
_list_filters_query = Query(None, description="通用筛选条件 JSON")
_list_sorts_query = Query(None, description="通用排序条件 JSON")
_list_page_query = Query(1, ge=1, description="页码\uff0c1-based")
_list_page_size_query = Query(20, ge=1, le=100, description="每页条数")
_list_team_dependency = Depends(get_current_user_team)
_list_current_user_dependency = Depends(get_current_active_user)
_list_db_dependency = Depends(get_db)


@router.get(
    "",
    response_model=ApprovalGenericListResponse,
    summary="获取审批列表\uff08通用\uff0cTask C3\uff09",
    description="""
按 tab 维度查询当前用户相关审批列表\uff0c团队隔离 + 提交时冻结的参与人过滤。

**功能说明\uff1a**
- tab=pending\uff1a当前节点冻结 APPROVER 参与人 + 状态 PENDING
- tab=processed\uff1a我作为审批人留下过 APPROVE/REJECT 记录的审批
- tab=submitted\uff1a我提交的所有审批\uff08含已通过/驳回/撤回\uff09
- tab=cc\uff1a当前用户收到 CC 参与人记录的审批\uff08只读\uff09
- 任意 tab 响应都附 `pending_count`\uff08当前用户待我审批总数\uff0c供侧边栏徽章\uff09

**查询参数\uff1a**
- tab: pending / processed / submitted / cc
- business_type: 可选 CONTRACT / PAYMENT / INVOICE / LICENSE / OPPORTUNITY 维度过滤
- business_type_exclude: 可选排除业务类型\uff0c多个值用英文逗号分隔
- page / page_size: 分页

**返回字段\uff1a**
- items: 审批列表项\uff0c含按 business_type 内存 join 出的 application_number /
  entity_name / entity_amount 三摘要\uff08避免 N+1\uff09
- total: 当前 tab+business_type 过滤后的总数
- pending_count: 当前用户待我审批总数\uff08任意 tab 都附\uff09
""",
)
def list_approvals(
    tab: str = _list_tab_query,
    business_type: str | None = _list_business_type_query,
    business_type_exclude: str | None = _list_business_type_exclude_query,
    approval_status: str | None = _list_approval_status_query,
    status_exclude: str | None = _list_status_exclude_query,
    application_number: str | None = _list_application_number_query,
    entity_name: str | None = _list_entity_name_query,
    submitter_name: str | None = _list_submitter_name_query,
    search: str | None = _list_search_query,
    entity_amount: float | None = _list_entity_amount_query,
    created_time_start: date | None = _list_created_time_start_query,
    created_time_end: date | None = _list_created_time_end_query,
    filters: str | None = _list_filters_query,
    sorts: str | None = _list_sorts_query,
    page: int = _list_page_query,
    page_size: int = _list_page_size_query,
    team_id: int = _list_team_dependency,
    current_user: User = _list_current_user_dependency,
    db: Session = _list_db_dependency,
) -> ApprovalGenericListResponse:
    # 参数校验
    if tab not in ("pending", "processed", "submitted", "cc"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"非法 tab: {tab}\uff0c仅支持 pending / processed / submitted / cc",
        )
    parsed_filters, parsed_sorts = optional_request_list_query(
        filters_raw=filters,
        sorts_raw=sorts,
    )
    unified_protocol = parsed_filters is not None or parsed_sorts is not None

    business_types: list[str] = []
    business_types_exclude: list[str] = []
    statuses: list[str] = []
    statuses_exclude: list[str] = []
    if not unified_protocol:
        business_types = [item.strip() for item in business_type.split(",") if item.strip()] if business_type else []
        business_types_exclude = (
            [item.strip() for item in business_type_exclude.split(",") if item.strip()] if business_type_exclude else []
        )
        invalid_business_types = [
            item for item in [*business_types, *business_types_exclude]
            if item != BusinessType.CONTRACT_CHANGE and not is_valid_business_type(item)
        ]
        if invalid_business_types:
            invalid_value = invalid_business_types[0]
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=(
                    f"无效的业务单据类型: {invalid_value}\uff0c仅支持 "
                    "CONTRACT / PAYMENT / INVOICE / LICENSE / OPPORTUNITY"
                ),
            )
        statuses = [item.strip() for item in approval_status.split(",") if item.strip()] if approval_status else []
        statuses_exclude = (
            [item.strip() for item in status_exclude.split(",") if item.strip()] if status_exclude else []
        )
        valid_statuses = {
            ApprovalStatus.PENDING,
            ApprovalStatus.APPROVED,
            ApprovalStatus.REJECTED,
            ApprovalStatus.CANCELLED,
        }
        invalid_statuses = [item for item in [*statuses, *statuses_exclude] if item not in valid_statuses]
        if invalid_statuses:
            invalid_value = invalid_statuses[0]
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"无效的审批状态: {invalid_value}\uff0c仅支持 PENDING / APPROVED / REJECTED / CANCELLED",
            )

    items, total, pending_count = run_or_400(lambda: approval_crud.list_approvals(
        db,
        team_id=team_id,
        user_id=current_user.id,
        tab=tab,
        business_types=business_types,
        business_types_exclude=business_types_exclude,
        statuses=statuses,
        statuses_exclude=statuses_exclude,
        application_number=application_number,
        entity_name=entity_name,
        submitter_name=submitter_name,
        search=search,
        entity_amount=entity_amount,
        created_time_start=created_time_start,
        created_time_end=created_time_end,
        page=page,
        page_size=page_size,
        filters=parsed_filters,
        sorts=parsed_sorts,
    ))

    return ApprovalGenericListResponse(
        items=[ApprovalListItemResponse(**item) for item in items],
        total=total,
        pending_count=pending_count,
    )
