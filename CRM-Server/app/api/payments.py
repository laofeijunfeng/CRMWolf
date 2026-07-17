from fastapi import APIRouter, Depends, HTTPException, status, Query
from app.core.deps import require_permission
from sqlalchemy.orm import Session, joinedload
from typing import List, Optional
from datetime import date
import logging

from app.core.database import get_db
from app.core.deps import get_current_active_user, get_current_user_team, require_permission
from app.crud.approval import approval_crud, approval_flow_crud
from app.crud.payment import payment_plan_crud, payment_record_crud, query_pending_approval_me
from app.crud.contract import contract_crud
from app.crud.role import role_crud
from app.constants.business_types import BusinessType
from app.models.payment import PaymentPlan, PaymentPlanStatus, PaymentRecord, PaymentConfirmationStatus
from app.models.approval import Approval, ApprovalStatus, ApprovalRecord, ApprovalNode
from app.schemas.payment import (
    PaymentPlanCreate, PaymentPlanUpdate, PaymentPlanBatchCreate, PaymentPlanResponse,
    PaymentRecordCreate, PaymentRecordUpdate, PaymentRecordResponse,
    PaymentRecordConfirm, PaymentRecordWithConfirmation,
    ContractPaymentSummary, PaymentReminder, PaginatedResponse,
    PaymentRecordListItem, PaymentRecordListResponse
)
from app.services.approval_adapter import get_adapter


router = APIRouter(prefix="/v1/payments", tags=["回款管理"])
logger = logging.getLogger(__name__)


def _get_current_approver_names(db: Session, approval: Approval, team_id: int) -> Optional[str]:
    """
    获取当前审批人姓名（从 approve_role 查询）

    Args:
        db: 数据库会话
        approval: 审批实例
        team_id: 团队ID

    Returns:
        审批人姓名（多个审批人用逗号分隔），如无审批人则返回 None

    Note:
        审批人姓名是从 approval.current_node.approve_role 查询角色成员得到的，
        不是节点名称（node_name）。节点名称是审批节点名称（如"财务审批"）。
    """
    if not approval:
        return None

    # 检查审批状态是否为 PENDING
    if approval.status != ApprovalStatus.PENDING:
        return None

    # 获取当前审批节点
    if not approval.current_node:
        return None

    # 从 approve_role 查询审批人姓名
    approve_role = approval.current_node.approve_role
    if not approve_role:
        return None

    role = role_crud.get_by_code(db, approve_role)
    if not role:
        return None

    users = role_crud.get_role_users(db, role.id, team_id)
    if not users:
        return None

    # 返回审批人姓名（多个审批人用逗号分隔）
    return ", ".join([user.name for user in users if user.name])


@router.post("/contracts/{contract_id}/payment-plans", response_model=List[PaymentPlanResponse], status_code=status.HTTP_201_CREATED, summary="创建回款计划", description="为指定合同创建回款计划，支持批量创建多个阶段。只有已签署或已生效的合同可以创建回款计划，所有阶段的计划金额之和不能超过合同总金额。返回创建成功的回款计划列表。")
def create_payment_plans(
    contract_id: int,
    plans_data: PaymentPlanBatchCreate,
    team_id: int = Depends(get_current_user_team),
    current_user = Depends(require_permission("payment:plan:create")),
    db: Session = Depends(get_db)
):
    contract = contract_crud.get_by_id(db, contract_id, team_id)
    if not contract:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="合同不存在"
        )

    from app.models.contract import ContractStatus
    if contract.status not in [ContractStatus.SIGNED, ContractStatus.EFFECTIVE]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"只有已签署或已生效的合同可以创建回款计划，当前状态: {contract.status}"
        )

    try:
        plans = payment_plan_crud.batch_create(db, contract_id, plans_data.plans, str(current_user.id), team_id)
        return plans
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"创建回款计划失败: {str(e)}"
        )


@router.get("/contracts/{contract_id}/payment-plans", response_model=List[PaymentPlanResponse], summary="查询合同回款计划", description="获取指定合同下的所有回款计划，包括计划金额、已回款金额、待回款金额等信息。支持按回款状态筛选（PENDING待回款、OVERDUE已逾期、PARTIAL部分回款、COMPLETED已完成）。")
def get_payment_plans(
    contract_id: int,
    status: Optional[str] = Query(None, description="回款状态筛选"),
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

    plans = payment_plan_crud.get_by_contract_id(db, contract_id, status)

    # Task 1.2: Add computed fields to each plan
    # Note: paid_amount, remaining_amount, invoiced_amount, invoice_count, is_invoiced
    # are computed properties on the model, no need to set them

    return plans


@router.get("/payment-plans", response_model=PaginatedResponse[PaymentPlanResponse], summary="查询回款计划列表", description="支持按状态、负责人、日期范围等条件筛选并分页查询回款计划。返回计划详情及关联的客户、商机、合同信息。可用于前端表格渲染和数据筛选。")
def list_payment_plans(
    plan_status: Optional[str] = Query(None, alias="status", description="回款状态筛选：PENDING, OVERDUE, PARTIAL, COMPLETED"),
    owner_id: Optional[str] = Query(None, description="负责人飞书ID（合同创建人）"),
    me: bool = Query(False, description="是否只查询当前用户的计划"),
    due_date_start: Optional[date] = Query(None, description="计划回款日期起始（YYYY-MM-DD）"),
    due_date_end: Optional[date] = Query(None, description="计划回款日期结束（YYYY-MM-DD）"),
    page: int = Query(1, ge=1, description="页码"),
    page_size: int = Query(20, ge=1, le=100, description="每页大小"),
    team_id: int = Depends(get_current_user_team),
    current_user = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """
    查询回款计划列表（添加权限隔离）

    权限逻辑：
    - payment:view:all → 可查看所有回款计划
    - payment:view:own → 只能查看自己创建的回款计划（通过合同创建人）
    - 都没有 → 403 Forbidden
    """
    from app.crud.permission import permission_crud

    # 权限检查
    user_permissions = permission_crud.get_user_permissions(db, current_user.id, team_id)
    permission_codes = {p.code for p in user_permissions}

    has_view_all = "payment:view:all" in permission_codes
    has_view_own = "payment:view:own" in permission_codes

    if not has_view_all and not has_view_own:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="没有查看回款计划的权限"
        )

    skip = (page - 1) * page_size

    # 数据所有权隔离
    current_user_id = None
    if me or (has_view_own and not has_view_all):
        # 如果只有 view:own 权限，或者用户明确选择只看自己的数据
        current_user_id = str(current_user.id)

    try:
        plans, total = payment_plan_crud.list_plans(
            db,
            team_id=team_id,
            skip=skip,
            limit=page_size,
            status=plan_status,
            owner_id=owner_id,
            due_date_start=due_date_start,
            due_date_end=due_date_end,
            current_user_id=current_user_id
        )

        # Task 1.2: Computed fields are properties on the model, no need to set them
        # Just enrich with contract/customer info
        for plan in plans:
            if hasattr(plan, 'contract') and plan.contract:
                plan.contract_name = plan.contract.contract_name
                plan.creator_id = plan.contract.creator_id
                # 负责人：通过合同关联商机获取
                if hasattr(plan.contract, 'opportunity') and plan.contract.opportunity:
                    plan.owner_id = plan.contract.opportunity.owner_id
                    # 查询负责人姓名
                    from app.crud.user import user_crud
                    owner = user_crud.get_by_id(db, int(plan.contract.opportunity.owner_id)) if plan.contract.opportunity.owner_id else None
                    plan.owner_name = owner.name if owner else None
                if hasattr(plan.contract, 'customer') and plan.contract.customer:
                    plan.customer_id = plan.contract.customer.id
                    plan.customer_name = plan.contract.customer.account_name
        
        total_pages = (total + page_size - 1) // page_size if total > 0 else 0
        
        return PaginatedResponse[PaymentPlanResponse](
            items=plans,
            total=total,
            page=page,
            page_size=page_size,
            total_pages=total_pages
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"查询回款计划失败: {str(e)}"
        )


@router.get("/payment-plans/badge-counts", summary="获取回款计划 Badge 数量", description="返回各类待处理数量：pending(未登记)、partial(部分回款)、overdue(逾期)、pending_submit(待提交审批)、pending_approval(审批中-团队)、pending_approval_me(审批中-待我审批)")
def get_payment_plan_badge_counts(
    team_id: int = Depends(get_current_user_team),
    current_user = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """
    获取回款计划 Badge 数量（Task 8.3: 增加 pending_approval_me）

    返回：
    - pending: 未登记的计划数（status=PENDING 且 payment_records.length=0）
    - partial: 部分回款的计划数（status=PARTIAL）
    - overdue: 逾期计划数（status=OVERDUE）
    - pending_submit: 待提交审批的记录数（confirmation_status=PENDING 且无关联审批）
    - pending_approval: 审批中的记录数（confirmation_status=PENDING 且审批状态=PENDING）- 团队总数
    - pending_approval_me: 待我审批的数量（与审批中心一致）
    """
    # 1. 未登记的计划数（PENDING 且没有任何回款记录）
    pending_count = db.query(PaymentPlan).filter(
        PaymentPlan.team_id == team_id,
        PaymentPlan.status == PaymentPlanStatus.PENDING,
        ~PaymentPlan.payment_records.any()
    ).count()

    # 2. 部分回款的计划数
    partial_count = db.query(PaymentPlan).filter(
        PaymentPlan.team_id == team_id,
        PaymentPlan.status == PaymentPlanStatus.PARTIAL
    ).count()

    # 3. 逾期计划数
    overdue_count = db.query(PaymentPlan).filter(
        PaymentPlan.team_id == team_id,
        PaymentPlan.status == PaymentPlanStatus.OVERDUE
    ).count()

    # 4. 待提交审批的记录数（confirmation_status=PENDING 且没有关联审批）
    # 查找没有审批记录的回款记录
    pending_submit_count = db.query(PaymentRecord).filter(
        PaymentRecord.team_id == team_id,
        PaymentRecord.confirmation_status == PaymentConfirmationStatus.PENDING,
        ~PaymentRecord.id.in_(
            db.query(Approval.business_id).filter(
                Approval.business_type == BusinessType.PAYMENT,
                Approval.team_id == team_id
            )
        )
    ).count()

    # 5. 审批中的记录数（confirmation_status=PENDING 且审批状态=PENDING）- 团队总数
    pending_approval_count = db.query(PaymentRecord).join(
        Approval,
        PaymentRecord.id == Approval.business_id
    ).filter(
        PaymentRecord.team_id == team_id,
        Approval.business_type == BusinessType.PAYMENT,
        Approval.team_id == team_id,
        PaymentRecord.confirmation_status == PaymentConfirmationStatus.PENDING,
        Approval.status == ApprovalStatus.PENDING
    ).count()

    # Task 8.3: 6. 待我审批的数量（与审批中心一致）
    # 查询当前审批节点角色属于当前用户角色集的审批记录

    # 获取当前用户的角色集合
    user_role_objs = role_crud.get_user_roles(db, current_user.id, team_id)
    user_roles = [r.code for r in user_role_objs]

    # 查询待我审批的数量（JOIN ApprovalNode，过滤 approve_role IN user_roles）
    if not user_roles:
        # 无任何角色 → 0
        pending_approval_me_count = 0
    else:
        pending_approval_me_query = (
            db.query(Approval)
            .join(ApprovalNode, Approval.current_node_id == ApprovalNode.id)
            .join(PaymentRecord, Approval.business_id == PaymentRecord.id)
            .join(PaymentPlan, PaymentRecord.payment_plan_id == PaymentPlan.id)
            .filter(
                Approval.business_type == BusinessType.PAYMENT,
                Approval.team_id == team_id,
                Approval.status == ApprovalStatus.PENDING,
                PaymentPlan.team_id == team_id,
                ApprovalNode.approve_role.in_(user_roles)
            )
        )
        pending_approval_me_count = pending_approval_me_query.count()

    return {
        "pending": pending_count,
        "partial": partial_count,
        "overdue": overdue_count,
        "pending_submit": pending_submit_count,
        "pending_approval": pending_approval_count,
        "pending_approval_me": pending_approval_me_count  # Task 8.3: 新增
    }


@router.get("/contracts/{contract_id}/payment-summary", response_model=ContractPaymentSummary, summary="查询合同回款汇总", description="获取指定合同的回款汇总信息，包括合同金额、已回款金额、回款状态、计划完成情况等")
def get_payment_summary(
    contract_id: int,
    team_id: int = Depends(get_current_user_team),
    current_user = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    from app.models.contract import Contract
    from app.models.customer import Customer
    from app.models.opportunity import Opportunity

    contract = db.query(Contract).filter(Contract.id == contract_id, Contract.team_id == team_id).first()
    
    if not contract:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="合同不存在"
        )
    
    plans = payment_plan_crud.get_by_contract_id(db, contract_id)
    
    completed_count = sum(1 for p in plans if p.status == PaymentPlanStatus.COMPLETED)
    overdue_count = sum(1 for p in plans if p.status == PaymentPlanStatus.OVERDUE)
    total_planned = sum(float(p.planned_amount) for p in plans)
    
    customer_id = None
    customer_name = None
    opportunity_id = None
    opportunity_name = None
    
    if contract.customer_id:
        customer = db.query(Customer).filter(Customer.id == contract.customer_id).first()
        if customer:
            customer_id = customer.id
            customer_name = customer.account_name
    
    if contract.opportunity_id:
        opportunity = db.query(Opportunity).filter(Opportunity.id == contract.opportunity_id).first()
        if opportunity:
            opportunity_id = opportunity.id
            opportunity_name = opportunity.opportunity_name
    
    return ContractPaymentSummary(
        contract_id=contract.id,
        contract_name=contract.contract_name,
        total_amount=float(contract.total_amount),
        total_paid_amount=float(contract.total_paid_amount),
        payment_status=contract.payment_status,
        payment_plans_count=len(plans),
        completed_plans_count=completed_count,
        overdue_plans_count=overdue_count,
        remaining_amount=total_planned - float(contract.total_paid_amount),
        customer_id=customer_id,
        customer_name=customer_name,
        opportunity_id=opportunity_id,
        opportunity_name=opportunity_name
    )


@router.get("/payment-plans/{plan_id}", summary="查询回款计划详情", description="获取指定回款计划的详细信息，包括计划金额、已回款金额、待回款金额、回款记录列表、关联的合同和客户信息、最新审批信息。")
def get_payment_plan_detail(
    plan_id: int,
    team_id: int = Depends(get_current_user_team),
    current_user = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """
    获取回款计划详情（含回款记录 + 审批信息）

    返回（Task 8.2）：
    - PaymentPlan 基本信息
    - PaymentRecord 列表
    - latest_approval：最新回款记录的审批信息
    """
    plan = payment_plan_crud.get_by_id(db, plan_id, team_id)
    if not plan:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="回款计划不存在"
        )

    # 从关联对象获取信息（不修改 plan 对象）
    contract_name = None
    creator_id = None
    customer_id = None
    customer_name = None
    opportunity_id = None
    opportunity_name = None

    # 确保 contract 已加载
    if plan.contract:
        contract_name = plan.contract.contract_name
        creator_id = plan.contract.creator_id
        customer_id = plan.contract.customer_id
        opportunity_id = plan.contract.opportunity_id

        # 手动查询 customer（Contract 没有 customer relationship）
        if customer_id:
            from app.crud.customer import customer_crud
            customer = customer_crud.get_by_id(db, customer_id)
            if customer:
                customer_name = customer.account_name

        # 手动查询 opportunity（Contract 没有 opportunity relationship）
        if opportunity_id:
            from app.crud.opportunity import opportunity_crud
            opportunity = opportunity_crud.get_by_id(db, opportunity_id, team_id)
            if opportunity:
                opportunity_name = opportunity.opportunity_name

    # Task 8.2: 获取最新回款记录的审批信息
    latest_record = None
    latest_approval = None

    if plan.payment_records:
        latest_record = plan.payment_records[-1]  # 最后一条记录

        # 查询该回款记录关联的审批
        approval = db.query(Approval).filter(
            Approval.business_type == BusinessType.PAYMENT,
            Approval.business_id == latest_record.id,
            Approval.team_id == team_id
        ).order_by(Approval.created_time.desc()).first()

        if approval:
            # 获取审批节点信息
            approval_records = db.query(ApprovalRecord).filter(
                ApprovalRecord.approval_id == approval.id
            ).order_by(ApprovalRecord.created_time).all()

            # 构建审批节点信息（按节点顺序）
            if approval.flow_id:
                flow_nodes = db.query(ApprovalNode).filter(
                    ApprovalNode.flow_id == approval.flow_id
                ).order_by(ApprovalNode.node_order).all()

                # 构建节点列表，包含审批状态
                nodes_info = []
                for node in flow_nodes:
                    # 查找该节点的所有审批记录（可能有 SUBMIT + APPROVE）
                    node_records = [r for r in approval_records if r.node_id == node.id]

                    # 节点状态逻辑：
                    # - 如果有多条记录（SUBMIT + APPROVE/REJECT），取最后一条（审批结果）
                    # - 如果只有一条 SUBMIT，显示 SUBMIT
                    # - 如果没有记录，显示 PENDING
                    node_status = "PENDING"
                    final_record = None

                    if node_records:
                        # 按时间排序，取最后一条（审批结果）
                        node_records_sorted = sorted(node_records, key=lambda r: r.created_time)
                        final_record = node_records_sorted[-1]

                        # 如果最后一条是 SUBMIT，说明还在审批中
                        # 如果最后一条是 APPROVE/REJECT，说明审批已完成
                        if final_record.action == "SUBMIT":
                            # 只有 SUBMIT 记录，审批中
                            node_status = "SUBMIT"
                        elif final_record.action == "APPROVE":
                            node_status = "APPROVE"
                        elif final_record.action == "REJECT":
                            node_status = "REJECT"

                    # approver_id/approver_name：取最后一条记录的审批人（如果有 APPROVE/REJECT）
                    # 如果只有 SUBMIT，approver_id 是提交人
                    approver_id = final_record.approver_id if final_record else None
                    approver_name = final_record.approver_name if final_record else None

                    # 但对于审批通过的情况，应该显示审批人（APPROVE 记录），而不是提交人
                    if node_status == "APPROVE":
                        # 找 APPROVE 记录
                        approve_record = next(
                            (r for r in node_records if r.action == "APPROVE"),
                            None
                        )
                        if approve_record:
                            approver_id = approve_record.approver_id
                            approver_name = approve_record.approver_name

                    nodes_info.append({
                        "id": node.id,
                        "node_name": node.node_name,
                        "node_order": node.node_order,
                        "approve_role": node.approve_role,
                        "status": node_status,
                        "approver_id": approver_id,
                        "approver_name": approver_name,
                        "approved_time": final_record.created_time.isoformat() if final_record else None,
                        "comment": final_record.comment if final_record else None
                    })

                latest_approval = {
                    "id": approval.id,
                    "status": approval.status,
                    "submitter_id": approval.submitter_id,
                    "submitter_name": approval.submitter_name,
                    "created_time": approval.created_time.isoformat(),
                    "nodes": nodes_info
                }

    # 构建响应（添加 approval 信息）
    # Task 1.2: Compute invoice fields using model properties
    invoiced_amount = float(plan.invoiced_amount)
    invoice_count = plan.invoice_count
    is_invoiced = invoice_count > 0

    response = {
        "id": plan.id,
        "contract_id": plan.contract_id,
        "stage_name": plan.stage_name,
        "planned_amount": float(plan.planned_amount),
        "due_date": plan.due_date.isoformat(),
        "notes": plan.notes,
        "status": plan.status.value if hasattr(plan.status, 'value') else plan.status,
        "paid_amount": float(plan.paid_amount),
        "remaining_amount": float(plan.remaining_amount),
        "payment_records": [
            {
                "id": r.id,
                "actual_amount": float(r.actual_amount),
                "payment_date": r.payment_date.isoformat(),
                "proof_attachment": r.proof_attachment,
                "creator_name": r.creator_name,
                "notes": r.notes,
                "confirmation_status": r.confirmation_status.value if hasattr(r.confirmation_status, 'value') else r.confirmation_status,
                "created_time": r.created_time.isoformat()
            }
            for r in plan.payment_records
        ],
        "contract_name": contract_name,
        "creator_id": creator_id,
        "customer_id": customer_id,
        "customer_name": customer_name,
        "opportunity_id": opportunity_id,
        "opportunity_name": opportunity_name,
        "created_time": plan.created_time.isoformat(),
        "last_modified_time": plan.last_modified_time.isoformat(),
        # Task 1.2: Invoice computed fields
        "invoiced_amount": invoiced_amount,
        "invoice_count": invoice_count,
        "is_invoiced": is_invoiced,
        # Task 8.2: 新增审批信息字段
        "latest_record_id": latest_record.id if latest_record else None,
        "latest_approval": latest_approval
    }

    return response


@router.put("/payment-plans/{plan_id}", response_model=PaymentPlanResponse, summary="修改回款计划", description="修改指定的回款计划。已完成的计划或已有回款记录的计划不能修改金额和日期，只能修改阶段名称和备注。")
def update_payment_plan(
    plan_id: int,
    plan_data: PaymentPlanUpdate,
    team_id: int = Depends(get_current_user_team),
    current_user = Depends(require_permission("payment:plan:edit")),
    db: Session = Depends(get_db)
):
    plan = payment_plan_crud.get_by_id(db, plan_id, team_id)
    if not plan:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="回款计划不存在"
        )

    if plan.status in [PaymentPlanStatus.COMPLETED]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="已完成的回款计划不能修改"
        )

    if plan.payment_records:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="存在关联的回款记录，不能修改金额和日期"
        )

    try:
        updated_plan = payment_plan_crud.update(db, plan, plan_data)
        # Task 1.2: Computed fields are properties on the model, no need to set them
        return updated_plan
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )


@router.delete("/payment-plans/{plan_id}", status_code=status.HTTP_204_NO_CONTENT, summary="删除回款计划", description="删除指定的回款计划。存在关联回款记录的计划不能删除，删除后无法恢复。")
def delete_payment_plan(
    plan_id: int,
    team_id: int = Depends(get_current_user_team),
    current_user = Depends(require_permission("payment:plan:delete")),
    db: Session = Depends(get_db)
):
    try:
        success = payment_plan_crud.delete(db, plan_id, team_id)
        if not success:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="回款计划不存在"
            )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )


@router.post("/payment-plans/{plan_id}/records", response_model=PaymentRecordResponse, status_code=status.HTTP_201_CREATED, summary="登记回款", description="为指定的回款计划登记回款记录。系统会自动校验回款金额，确保累计回款不超过计划金额。登记后自动更新计划状态和合同回款状态。返回创建成功的回款记录。")
async def create_payment_record(
    plan_id: int,
    record_data: PaymentRecordCreate,
    team_id: int = Depends(get_current_user_team),
    current_user = Depends(require_permission("payment:register")),
    db: Session = Depends(get_db)
):
    """
    登记回款（异步版本 - 正确处理通知）

    流程：
    1. 验证回款计划存在
    2. 创建回款记录（CRUD 层）
    3. 发送审批通知（API 层 - 异步）
    """
    plan = payment_plan_crud.get_by_id(db, plan_id, team_id)
    if not plan:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="回款计划不存在"
        )

    if plan.status == PaymentPlanStatus.COMPLETED:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="该回款计划已完成，无法继续登记回款"
        )

    try:
        # 创建回款记录（CRUD 层 - 同步，不包含通知逻辑）
        record = payment_record_crud.create(
            db,
            plan_id,
            record_data,
            str(current_user.id),
            current_user.name,
            team_id
        )

        # 发送审批通知（API 层 - 异步）
        # 注意：通知失败不阻断业务流程，只记录日志
        if record.approval_id:
            from app.services.notification import notification_service_factory
            from app.api.approvals import get_approvers_by_role
            from app.constants.business_types import BusinessType

            notification_service = notification_service_factory(db, team_id)

            # 获取审批实例
            from app.crud.approval import approval_crud
            approval = approval_crud.get_by_id(db, record.approval_id, team_id)

            if approval and approval.current_node:
                approvers = get_approvers_by_role(db, approval.current_node.approve_role)

                # 构造通知内容
                from app.models.contract import Contract
                contract = db.query(Contract).filter(Contract.id == plan.contract_id).first()
                entity_name = contract.contract_name if contract else f"回款登记#{record.id}"

                try:
                    for approver in approvers:
                        await notification_service.notify_approval_pending(
                            entity_type=BusinessType.PAYMENT,
                            entity_name=entity_name,
                            flow_name=approval.flow.flow_name if approval.flow else "",
                            node_name=approval.current_node.node_name,
                            approver_open_id=approver.feishu_open_id or "",
                            approver_name=approver.name or "",
                            business_id=record.id,
                        )
                except Exception as notify_error:
                    # 通知失败不阻断业务，记录日志
                    logger.error(
                        f"[Payment] 通知发送失败: record_id={record.id}, "
                        f"approval_id={record.approval_id}, error={str(notify_error)}"
                    )

        return record

    except ValueError as e:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except Exception as e:
        db.rollback()
        logger.error(f"[Payment] 登记回款失败: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"登记回款失败: {str(e)}"
        )


@router.get("/payment-plans/{plan_id}/records", response_model=List[PaymentRecordResponse], summary="查询回款记录", description="获取指定回款计划下的所有回款记录，按回款日期倒序排列。包含每笔回款的详细信息，如回款金额、回款日期、登记人等。")
def get_payment_records(
    plan_id: int,
    team_id: int = Depends(get_current_user_team),
    current_user = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    plan = payment_plan_crud.get_by_id(db, plan_id, team_id)
    if not plan:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="回款计划不存在"
        )
    
    return payment_record_crud.get_by_plan_id(db, plan_id)


@router.put("/payment-records/{record_id}", response_model=PaymentRecordResponse, summary="更新回款记录", description="更新指定的回款记录。更新后会自动重新计算相关金额、计划状态和合同回款状态。支持修改回款金额、回款日期、凭证附件和备注信息。")
def update_payment_record(
    record_id: int,
    record_data: PaymentRecordUpdate,
    team_id: int = Depends(get_current_user_team),
    current_user = Depends(require_permission("payment:record:edit")),
    db: Session = Depends(get_db)
):
    """
    更新回款记录（用于驳回后修正）

    仅允许更新：
    - actual_amount（回款金额）
    - payment_date（回款日期）
    - proof_attachment（凭证附件）
    - notes（备注）

    注意：只有审批被驳回的记录才能更新（Task 8.1）
    """
    record = payment_record_crud.get_by_id(db, record_id, team_id)
    if not record:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="回款记录不存在"
        )

    # Task 8.1: 检查审批状态 - 只有驳回的记录才能更新
    # 查询该回款记录关联的审批
    approval = db.query(Approval).filter(
        Approval.business_type == BusinessType.PAYMENT,
        Approval.business_id == record_id,
        Approval.team_id == team_id
    ).order_by(Approval.created_time.desc()).first()

    if approval and approval.status != ApprovalStatus.REJECTED:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="只有审批被驳回的记录才能修改"
        )

    try:
        updated_record = payment_record_crud.update(db, record, record_data)
        return updated_record
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )


@router.delete("/payment-records/{record_id}", status_code=status.HTTP_204_NO_CONTENT, summary="删除回款记录", description="删除指定的回款记录。删除后会自动重新计算相关金额、计划状态和合同回款状态。删除后无法恢复，请谨慎操作。")
def delete_payment_record(
    record_id: int,
    team_id: int = Depends(get_current_user_team),
    current_user = Depends(require_permission("payment:record:delete")),
    db: Session = Depends(get_db)
):
    try:
        success = payment_record_crud.delete(db, record_id, team_id)
        if not success:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="回款记录不存在"
            )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )


@router.get("/payment-records", response_model=PaymentRecordListResponse[PaymentRecordListItem], summary="查询回款记录列表", description="支持按合同、计划、日期范围、金额、审批状态等条件筛选并分页查询回款记录。返回记录详情及关联的客户、商机、合同、回款阶段信息、审批信息、待我审批数量。可用于前端表格渲染和回款历史查询。")
def list_payment_records(
    contract_id: Optional[int] = Query(None, description="合同ID筛选"),
    payment_plan_id: Optional[int] = Query(None, description="回款计划ID筛选"),
    payment_date_start: Optional[date] = Query(None, description="回款日期起始（YYYY-MM-DD）"),
    payment_date_end: Optional[date] = Query(None, description="回款日期结束（YYYY-MM-DD）"),
    min_amount: Optional[float] = Query(None, ge=0, description="最小回款金额"),
    creator_id: Optional[str] = Query(None, description="登记人飞书ID"),
    me: bool = Query(False, description="是否只查询当前用户登记的记录"),
    approval_status: Optional[str] = Query(None, description="审批状态筛选: pending_submit(待提交), pending_approval(审批中), approved(已通过), rejected(已驳回)"),
    page: int = Query(1, ge=1, description="页码"),
    page_size: int = Query(20, ge=1, le=100, description="每页大小"),
    team_id: int = Depends(get_current_user_team),
    current_user = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """
    查询回款记录列表（添加权限隔离）

    权限逻辑：
    - payment:view:all → 可查看所有回款记录
    - payment:view:own → 只能查看自己登记的回款记录
    - 都没有 → 403 Forbidden
    """
    from app.crud.permission import permission_crud

    # 权限检查
    user_permissions = permission_crud.get_user_permissions(db, current_user.id, team_id)
    permission_codes = {p.code for p in user_permissions}

    has_view_all = "payment:view:all" in permission_codes
    has_view_own = "payment:view:own" in permission_codes

    if not has_view_all and not has_view_own:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="没有查看回款记录的权限"
        )

    skip = (page - 1) * page_size

    # 数据所有权隔离
    current_user_id = None
    if me or (has_view_own and not has_view_all):
        # 如果只有 view:own 权限，或者用户明确选择只看自己的数据
        current_user_id = str(current_user.id)

    try:
        records, total = payment_record_crud.list_records(
            db,
            team_id=team_id,
            skip=skip,
            limit=page_size,
            contract_id=contract_id,
            payment_plan_id=payment_plan_id,
            payment_date_start=payment_date_start,
            payment_date_end=payment_date_end,
            min_amount=min_amount,
            creator_id=creator_id,
            current_user_id=current_user_id,
            approval_status=approval_status
        )

        # Task 1.4: Calculate pending_approval_me_count
        user_role_objs = role_crud.get_user_roles(db, current_user.id, team_id)
        user_roles = [r.code for r in user_role_objs]
        pending_approval_me_count = query_pending_approval_me(db, team_id, user_roles)

        # Build response with approval info
        items = []
        for record in records:
            # Enrich with contract/customer info
            record.contract_id = None
            record.contract_name = None
            record.customer_id = None
            record.customer_name = None
            record.opportunity_id = None
            record.opportunity_name = None
            record.stage_name = None

            if hasattr(record, 'payment_plan') and record.payment_plan:
                record.contract_id = record.payment_plan.contract_id
                if hasattr(record.payment_plan, 'contract') and record.payment_plan.contract:
                    record.contract_name = record.payment_plan.contract.contract_name
                    if hasattr(record.payment_plan.contract, 'customer') and record.payment_plan.contract.customer:
                        record.customer_id = record.payment_plan.contract.customer.id
                        record.customer_name = record.payment_plan.contract.customer.account_name
                    if hasattr(record.payment_plan.contract, 'opportunity') and record.payment_plan.contract.opportunity:
                        record.opportunity_id = record.payment_plan.contract.opportunity.id
                        record.opportunity_name = record.payment_plan.contract.opportunity.opportunity_name
                record.stage_name = record.payment_plan.stage_name

            # Build item dict with approval info
            item_dict = {
                "id": record.id,
                "payment_plan_id": record.payment_plan_id,
                "record_number": record.record_number,
                "actual_amount": float(record.actual_amount),
                "payment_date": record.payment_date.isoformat(),
                "proof_attachment": record.proof_attachment,
                "notes": record.notes,
                "creator_id": record.creator_id,
                "creator_name": record.creator_name,
                "confirmation_status": record.confirmation_status,
                "created_time": record.created_time.isoformat(),
                "contract_id": record.contract_id,
                "contract_name": record.contract_name,
                "stage_name": record.stage_name,
                "customer_id": record.customer_id,
                "customer_name": record.customer_name,
                "opportunity_id": record.opportunity_id,
                "opportunity_name": record.opportunity_name,
                "approval_id": record.approval_id,
            }

            # Task 1.4: Add approval info if exists
            if record.approval_id and record.approval:
                approval_records = db.query(ApprovalRecord).filter(
                    ApprovalRecord.approval_id == record.approval.id
                ).order_by(ApprovalRecord.created_time).all()

                # Get flow nodes
                nodes_info = []
                if record.approval.flow_id:
                    flow_nodes = db.query(ApprovalNode).filter(
                        ApprovalNode.flow_id == record.approval.flow_id
                    ).order_by(ApprovalNode.node_order).all()

                    for node in flow_nodes:
                        # 查找该节点的所有审批记录（可能有 SUBMIT + APPROVE）
                        node_records = [r for r in approval_records if r.node_id == node.id]

                        # 节点状态逻辑：
                        # - 如果有多条记录（SUBMIT + APPROVE/REJECT），取最后一条（审批结果）
                        # - 如果只有一条 SUBMIT，显示 SUBMIT
                        # - 如果没有记录，显示 PENDING
                        node_status = "PENDING"
                        final_record = None

                        if node_records:
                            # 按时间排序，取最后一条（审批结果）
                            node_records_sorted = sorted(node_records, key=lambda r: r.created_time)
                            final_record = node_records_sorted[-1]

                            if final_record.action == "SUBMIT":
                                node_status = "SUBMIT"
                            elif final_record.action == "APPROVE":
                                node_status = "APPROVE"
                            elif final_record.action == "REJECT":
                                node_status = "REJECT"

                        # approver_id/approver_name：取最后一条记录
                        approver_id = final_record.approver_id if final_record else None
                        approver_name = final_record.approver_name if final_record else None

                        # 对于审批通过，显示审批人（APPROVE 记录）
                        if node_status == "APPROVE":
                            approve_record = next(
                                (r for r in node_records if r.action == "APPROVE"),
                                None
                            )
                            if approve_record:
                                approver_id = approve_record.approver_id
                                approver_name = approve_record.approver_name

                        nodes_info.append({
                            "id": node.id,
                            "node_order": node.node_order,
                            "node_name": node.node_name,
                            "approve_role": node.approve_role,
                            "status": node_status,
                            "approver_id": approver_id,
                            "approver_name": approver_name,
                            "comment": final_record.comment if final_record else None,
                        })

                item_dict["approval"] = {
                    "id": record.approval.id,
                    "status": record.approval.status,
                    "current_approver_name": _get_current_approver_names(db, record.approval, team_id),
                    "nodes": nodes_info,
                }

            items.append(item_dict)

        total_pages = (total + page_size - 1) // page_size if total > 0 else 0

        # Task 1.4: Return response with pending_approval_me_count
        return {
            "items": items,
            "total": total,
            "page": page,
            "page_size": page_size,
            "total_pages": total_pages,
            "pending_approval_me_count": pending_approval_me_count,
        }
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"查询回款记录失败: {str(e)}"
        )


@router.get("/reminders/upcoming", response_model=List[PaymentReminder], summary="查询即将到期的回款", description="获取指定天数内即将到期的回款计划，用于提醒。支持查询未来1-30天内的回款计划")
def get_upcoming_payments(
    days: int = Query(7, ge=1, le=30, description="查询天数范围，默认7天，可设置1-30天"),
    team_id: int = Depends(get_current_user_team),
    current_user = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    plans = payment_plan_crud.get_upcoming_payments(db, team_id, days)
    
    reminders = []
    for plan in plans:
        days_until = (plan.due_date - date.today()).days
        
        customer_name = None
        opportunity_name = None
        
        if hasattr(plan, 'contract') and plan.contract:
            if hasattr(plan.contract, 'customer') and plan.contract.customer:
                customer_name = plan.contract.customer.account_name
            if hasattr(plan.contract, 'opportunity') and plan.contract.opportunity:
                opportunity_name = plan.contract.opportunity.opportunity_name
        
        reminders.append(PaymentReminder(
            plan_id=plan.id,
            contract_name=plan.contract.contract_name,
            stage_name=plan.stage_name,
            planned_amount=float(plan.planned_amount),
            due_date=plan.due_date,
            days_until_due=days_until,
            contract_owner_id=plan.contract.creator_id,
            customer_name=customer_name,
            opportunity_name=opportunity_name
        ))
    
    return reminders


@router.get("/reminders/overdue", response_model=List[PaymentReminder], summary="查询逾期回款", description="获取所有逾期的回款计划，用于催收提醒")
def get_overdue_payments(
    team_id: int = Depends(get_current_user_team),
    current_user = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    plans = payment_plan_crud.get_overdue_payments(db, team_id)
    
    reminders = []
    for plan in plans:
        days_overdue = (date.today() - plan.due_date).days
        
        customer_name = None
        opportunity_name = None
        
        if hasattr(plan, 'contract') and plan.contract:
            if hasattr(plan.contract, 'customer') and plan.contract.customer:
                customer_name = plan.contract.customer.account_name
            if hasattr(plan.contract, 'opportunity') and plan.contract.opportunity:
                opportunity_name = plan.contract.opportunity.opportunity_name
        
        reminders.append(PaymentReminder(
            plan_id=plan.id,
            contract_name=plan.contract.contract_name,
            stage_name=plan.stage_name,
            planned_amount=float(plan.planned_amount),
            due_date=plan.due_date,
            days_until_due=-days_overdue,
            contract_owner_id=plan.contract.creator_id,
            customer_name=customer_name,
            opportunity_name=opportunity_name
        ))

    return reminders


# ---------- B1: 回款审批提交 & 财务直确认 -----------------------------------
#
# 业务语义 sugar 端点（通用引擎 /v1/approvals/PAYMENT/{id}/submit 已可覆盖）。
# 本端点叠加 payment:submit 权限码；未匹配审批流程时统一报错并提示管理员配置。


@router.post(
    "/records/{record_id}/submit-approval",
    summary="提交回款审批",
    description=(
        "为指定回款记录提交审批。系统按回款金额匹配审批流程，审批通过后自动确认入账。"
        "权限码：payment:submit。"
    ),
)
def submit_payment_approval(
    record_id: int,
    team_id: int = Depends(get_current_user_team),
    current_user=Depends(require_permission("payment:submit")),
    db: Session = Depends(get_db),
):
    """
    提交回款审批（统一走审批流程）

    所有回款必须走审批流程，审批通过后自动确认入账（confirmation_status=CONFIRMED）。
    """
    record = payment_record_crud.get_by_id(db, record_id, team_id)
    if not record:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="回款记录不存在"
        )

    # 匹配 PAYMENT 审批流程
    flow, error_msg = approval_flow_crud.match_flow_generic(
        db, BusinessType.PAYMENT, team_id, record.actual_amount, None
    )

    # 未匹配审批流时统一报错
    if flow is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=error_msg or "未找到匹配的回款审批流程，请联系管理员配置完整的审批流程覆盖范围"
        )

    # 经适配器取提交人（PaymentRecordAdapter.get_submitter → creator_id, creator_name）
    adapter = get_adapter(BusinessType.PAYMENT)
    submitter_id, submitter_name = adapter.get_submitter(record)

    approval = approval_crud.create_approval_generic(
        db,
        BusinessType.PAYMENT,
        record.id,
        record.team_id,
        flow,
        submitter_id,
        submitter_name,
    )

    return {
        "approval_id": approval.id,
        "status": approval.status,
        "message": "回款审批已提交"
    }


# ========== 已废弃：财务直接确认 API（统一走审批流程）==========
# 所有回款必须走审批流程，审批通过后自动确认入账。
# 此 API 已废弃，保留仅用于向后兼容，请勿使用。
#
# @router.post(
#     "/records/{record_id}/confirm",
#     response_model=PaymentRecordWithConfirmation,
#     summary="[已废弃] 财务确认回款入账",
#     description="已废弃：所有回款统一走审批流程，审批通过后自动确认入账。请使用审批中心进行审批操作。",
#     deprecated=True,
# )
# def confirm_payment_record(...):
#     pass
