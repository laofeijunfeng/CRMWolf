from __future__ import annotations

import logging
from datetime import date, datetime, time
from decimal import Decimal
from typing import TYPE_CHECKING, Any, Protocol, TypeVar, cast

from sqlalchemy import and_, or_
from sqlalchemy import exists as db_exists
from sqlalchemy.exc import OperationalError

from app.constants.business_types import BusinessType
from app.core.list_query import (
    FilterCondition,
    ListQueryContext,
    SortCondition,
    apply_search,
    build_optional_list_query,
    uses_unified_list_query,
    without_filter_field,
)
from app.core.list_query.catalogs import APPROVALS_LIST_QUERY_CATALOG
from app.models.approval import (
    Approval,
    ApprovalAction,
    ApprovalFlow,
    ApprovalNode,
    ApprovalParticipant,
    ApprovalParticipantKind,
    ApprovalRecord,
    ApprovalStatus,
)
from app.models.contract import Contract
from app.models.contract_change import ContractChangeRequest
from app.schemas.approval import (
    ApprovalActionRequest,
    ApprovalFlowCreate,
    ApprovalFlowUpdate,
    ApprovalNodeCreate,
)
from app.utils.time import business_now

if TYPE_CHECKING:
    from collections.abc import Callable

    from sqlalchemy.orm import Query, Session
    from sqlalchemy.sql.expression import Exists

    from app.models.user import User

logger = logging.getLogger(__name__)

_RowT = TypeVar("_RowT")


class _ApprovalInstance(Protocol):
    """Instance values for the legacy SQLAlchemy Column declarations used below."""

    team_id: int
    business_type: str
    business_id: int | None
    status: str


def _approval_instance(approval: Approval) -> _ApprovalInstance:
    return cast("_ApprovalInstance", approval)


def _serialize_optional_datetime(value: object) -> str | None:
    if value is None:
        return None
    if hasattr(value, "isoformat"):
        return cast("Callable[[], str]", value.isoformat)()
    return str(value)


def calculate_flow_precision_score(flow: ApprovalFlow, amount: Decimal | float | None, license_type: str | None) -> int:
    """
    计算审批流程的精确度评分

    评分规则\uff08总分100分\uff09\uff1a
    1. 金额精确度评分\uff080-50分\uff09\uff1a
       - 有上下限\uff08min_amount 和 max_amount 都有\uff09\uff1a50分
       - 只有上限\uff08只有 max_amount\uff09\uff1a30分
       - 只有下限\uff08只有 min_amount\uff09\uff1a20分
       - 无金额限制\uff1a0分
       - 范围越窄额外加分\uff08范围宽度越小\uff0c评分越高\uff09

    2. 条件数量评分\uff080-30分\uff09\uff1a
       - 有金额条件\uff1a10分
       - 有授权类型条件\uff1a20分
       - 总计最多30分

    3. 创建时间评分\uff080-20分\uff09\uff1a
       - 作为兜底策略\uff0c最早创建的流程得分高
       - 需要在多流程比较时使用

    A5 重构\uff1a入参由 (flow, contract) 泛化为 (flow, amount, license_type)\uff0c
    原合同语义保留——amount 即原 contract.total_amount\uff0clicense_type 即原
    contract.license_type。评分逻辑逐字不变\uff08E1 合同回归契约\uff09。

    Args:
        flow: 审批流程
        amount: 业务单据金额\uff08合同为 total_amount\uff0c回款为 actual_amount\uff0c发票为 invoice_amount\uff09
        license_type: 授权类型\uff08仅合同有值\uff1b回款/发票传 None\uff09

    Returns:
        int: 精确度评分\uff080-100分\uff09
    """
    score = 0

    # 1. 金额精确度评分(0-50分)
    min_amount = float(flow.min_amount) if flow.min_amount else None
    max_amount = float(flow.max_amount) if flow.max_amount else None

    if min_amount is not None and max_amount is not None:
        # 有上下限:范围最精确,基础分50分
        score += 50
        # 范围越窄额外加分(范围宽度越小,评分越高)
        # 计算范围宽度占合同金额的比例
        contract_amount = float(amount) if amount else 0
        if contract_amount > 0:
            range_width = max_amount - min_amount
            # 范围宽度越小,加分越多(最多10分)
            # 如果范围宽度小于合同金额的10%,加10分
            # 如果范围宽度小于合同金额的50%,加5分
            if range_width < contract_amount * 0.1:
                score += 10
            elif range_width < contract_amount * 0.5:
                score += 5
    elif max_amount is not None:
        # 只有上限:中等精确,30分
        score += 30
    elif min_amount is not None:
        # 只有下限:较低精确,20分
        score += 20
    # 无金额限制:0分(不加分)

    # 2. 条件数量评分(0-30分)
    if min_amount is not None or max_amount is not None:
        # 有金额条件:10分
        score += 10

    if flow.license_type is not None and license_type == flow.license_type:
        # 有授权类型条件且匹配:20分
        score += 20

    return score


def _participant_exists(user_id: int, kind: str) -> Exists:
    return db_exists().where(
        ApprovalParticipant.approval_id == Approval.id,
        ApprovalParticipant.team_id == Approval.team_id,
        ApprovalParticipant.user_id == int(user_id),
        ApprovalParticipant.kind == kind,
    )


class ApprovalFlowCRUD:
    def get_by_id(self, db: Session, flow_id: int, team_id: int | None = None) -> ApprovalFlow | None:
        query = db.query(ApprovalFlow).filter(ApprovalFlow.id == flow_id)
        if team_id is not None:
            query = query.filter(ApprovalFlow.team_id == team_id)
        return query.first()

    def get_by_code(self, db: Session, flow_code: str, team_id: int | None = None) -> ApprovalFlow | None:
        query = db.query(ApprovalFlow).filter(ApprovalFlow.flow_code == flow_code)
        if team_id is not None:
            query = query.filter(ApprovalFlow.team_id == team_id)
        return query.first()

    def get_multi(
        self,
        db: Session,
        team_id: int | None = None,
        skip: int = 0,
        limit: int = 100,
        is_active: bool | None = None,
    ) -> tuple[list[ApprovalFlow], int]:
        query = db.query(ApprovalFlow)

        if team_id is not None:
            query = query.filter(ApprovalFlow.team_id == team_id)
        if is_active is not None:
            query = query.filter(ApprovalFlow.is_active == (1 if is_active else 0))

        total = query.count()
        flows = query.order_by(ApprovalFlow.created_time.desc()).offset(skip).limit(limit).all()

        return flows, total

    def create(self, db: Session, obj_in: ApprovalFlowCreate, team_id: int) -> ApprovalFlow:
        flow_data = obj_in.model_dump(exclude={'nodes'})
        flow_data['team_id'] = team_id

        db_flow = ApprovalFlow(**flow_data)
        db.add(db_flow)
        db.flush()

        for node_data in obj_in.nodes:
            node_dict = node_data.model_dump()
            node_dict['flow_id'] = db_flow.id
            node_dict['team_id'] = team_id
            db_node = ApprovalNode(**node_dict)
            db.add(db_node)

        db.commit()
        db.refresh(db_flow)
        return db_flow
    
    def update(self, db: Session, db_obj: ApprovalFlow, obj_in: ApprovalFlowUpdate) -> ApprovalFlow:
        payload = obj_in.model_dump(exclude_unset=True)
        nodes_data = payload.pop('nodes', None)

        if nodes_data is not None:
            if not nodes_data:
                raise ValueError('审批节点不能为空')

            existing_nodes = db.query(ApprovalNode).filter(
                ApprovalNode.flow_id == db_obj.id,
                ApprovalNode.team_id == db_obj.team_id,
                ApprovalNode.is_archived == 0,
            ).all()
            existing_by_id = {int(node.id): node for node in existing_nodes}
            requested_ids = [node.get('id') for node in nodes_data if node.get('id') is not None]
            if len(requested_ids) != len(set(requested_ids)):
                raise ValueError('审批流程节点不能重复')
            unknown_ids = set(requested_ids) - set(existing_by_id)
            if unknown_ids:
                raise ValueError('审批流程节点不存在或不属于当前流程')

            final_nodes: list[tuple[int | None, dict[str, Any]]] = []
            for node_data in nodes_data:
                node_id = node_data.get('id')
                if node_id is None:
                    final_nodes.append((None, dict(node_data)))
                    continue
                current = existing_by_id[node_id]
                merged = {
                    'node_name': current.node_name,
                    'node_code': current.node_code,
                    'node_order': current.node_order,
                    'description': current.description,
                    'node_type': current.node_type or 'APPROVAL',
                    'approver_roles': current.approver_roles,
                    'approver_users': current.approver_users,
                }
                merged.update({key: value for key, value in node_data.items() if key != 'id'})
                final_nodes.append((node_id, merged))

            ordered_nodes = sorted(final_nodes, key=lambda item: item[1].get('node_order') or 0)
            validated_nodes: list[tuple[int | None, ApprovalNodeCreate]] = []
            for index, (node_id, node_data) in enumerate(ordered_nodes, start=1):
                try:
                    validated = ApprovalNodeCreate.model_validate(node_data)
                except Exception as exc:
                    raise ValueError(f'第 {index} 个节点配置无效: {exc}') from exc
                if not (validated.approver_roles or validated.approver_users):
                    raise ValueError(f'第 {index} 个节点未选择审批人员')
                validated_nodes.append((node_id, validated))

            if validated_nodes[0][1].node_type.value != 'APPROVAL':
                raise ValueError('抄送节点需位于审批节点之后')
            orders = [node.node_order for _, node in validated_nodes]
            if orders != list(range(1, len(orders) + 1)):
                raise ValueError('审批节点顺序必须从1开始连续编号')
            codes = [node.node_code for _, node in validated_nodes]
            if len(codes) != len(set(codes)):
                raise ValueError('节点编码不能重复')

            requested_id_set = set(requested_ids)
            for node in existing_nodes:
                if node.id not in requested_id_set:
                    node.is_archived = 1
            for node_id, node_model in validated_nodes:
                values = node_model.model_dump(mode='json')
                if node_id is None:
                    db.add(ApprovalNode(flow_id=db_obj.id, team_id=db_obj.team_id, **values))
                else:
                    node = existing_by_id[node_id]
                    for field, value in values.items():
                        setattr(node, field, value)

        for field, value in payload.items():
            setattr(db_obj, field, value)

        db.commit()
        db.refresh(db_obj)
        return db_obj

    def delete(self, db: Session, flow_id: int, team_id: int | None = None) -> bool:
        flow = self.get_by_id(db, flow_id, team_id)
        if not flow:
            return False
        approval_query = db.query(Approval.id).filter(Approval.flow_id == flow.id)
        if flow.team_id is not None:
            approval_query = approval_query.filter(Approval.team_id == flow.team_id)
        if approval_query.first() is not None:
            raise ValueError('存在关联的审批实例\uff0c不能删除审批流程')
        db.delete(flow)
        db.commit()
        return True
    

    def match_flow(
        self, db: Session, contract: Contract, team_id: int | None = None,
    ) -> tuple[ApprovalFlow | None, str | None]:
        """
        匹配审批流程\uff08合同专用 thin wrapper\uff0cA5 解耦后保留以兼容现有调用方\uff09

        语义与改造前逐字一致\uff1a直接委托 match_flow_generic('CONTRACT', team_id,
        contract.total_amount, contract.license_type)。E1 合同回归契约由此保证。

        Args:
            db: 数据库会话
            contract: 合同对象
            team_id: 团队ID\uff08可选\uff09

        Returns:
            Tuple[Optional[ApprovalFlow], Optional[str]]: (匹配的审批流程, 错误信息)
        """
        return self.match_flow_generic(
            db,
            BusinessType.CONTRACT,
            team_id,
            contract.total_amount,
            contract.license_type,
        )

    def match_flow_generic(
        self,
        db: Session,
        business_type: str,
        team_id: int | None,
        amount: Decimal | float | None,
        license_type: str | None,
    ) -> tuple[ApprovalFlow | None, str | None]:
        """
        通用审批流程匹配\uff08支持 CONTRACT/PAYMENT/INVOICE/INVOICE_REISSUE/LICENSE/OPPORTUNITY\uff09

        E1 合同回归契约\uff08P0\uff09\uff1abusiness_type='CONTRACT' 的匹配结果必须与改造前
        match_flow(contract) 逐字一致——仅多 `ApprovalFlow.business_type == 'CONTRACT'`
        一个过滤条件。team_id 隔离、金额范围比较、license_type 匹配、
        calculate_flow_precision_score 评分、(-score, created_time) 排序逻辑全部沿用原代码。

        未匹配分支统一为配置错误\uff1a所有业务类型都必须配置审批流程。
        调用方收到 (None, error) 后应提示管理员创建或完善审批流程。

        Args:
            db: 数据库会话
            business_type: 业务单据类型\uff08CONTRACT/PAYMENT/INVOICE/INVOICE_REISSUE/LICENSE/OPPORTUNITY\uff09
            team_id: 团队ID\uff08可选\uff0c用于团队隔离\uff09
            amount: 单据金额\uff08合同 total_amount / 回款 actual_amount / 发票 invoice_amount\uff09
            license_type: 授权类型\uff08仅合同有值\uff0c回款/发票传 None\uff09

        Returns:
            Tuple[Optional[ApprovalFlow], Optional[str]]: (匹配的审批流程, 错误信息)
        """
        # 合同变更复用团队已配置的合同审批流程,不新增可配置流程类型。
        flow_business_type = BusinessType.CONTRACT if business_type == BusinessType.CONTRACT_CHANGE else business_type
        query = db.query(ApprovalFlow).filter(
            ApprovalFlow.is_active == 1,
            ApprovalFlow.business_type == flow_business_type,
        )

        if team_id is not None:
            query = query.filter(ApprovalFlow.team_id == team_id)

        # 检查金额是否为 0 或 null
        total_amount = float(amount) if amount else 0
        is_amount_empty = total_amount == 0

        # 查询所有启用的流程
        flows = query.all()

        # 未匹配时统一报错。合同金额为空保留更具体的历史提示。
        def _no_match() -> tuple[ApprovalFlow | None, str | None]:
            if business_type == BusinessType.CONTRACT and is_amount_empty:
                return None, "合同金额为空\uff0c无法匹配审批流程\uff0c请补充金额或让管理员创建默认流程"
            display_names = {
                BusinessType.CONTRACT: "合同",
                BusinessType.CONTRACT_CHANGE: "合同",
                BusinessType.PAYMENT: "回款",
                BusinessType.INVOICE: "发票",
                BusinessType.INVOICE_REISSUE: "发票重开申请",
                BusinessType.LICENSE: "License",
                BusinessType.OPPORTUNITY: "商机",
            }
            display_name = display_names.get(business_type, "业务单据")
            return None, f"未找到匹配的{display_name}审批流程\uff0c请联系管理员创建或完善审批流程"

        # 金额为空时,优先匹配无金额限制的流程
        if is_amount_empty:
            no_amount_flows = [f for f in flows if f.min_amount is None and f.max_amount is None]
            # 收集匹配的无金额限制流程
            matched_no_amount: list[tuple[ApprovalFlow, int]] = []
            for flow in no_amount_flows:
                # 检查授权类型
                if flow.license_type and license_type != flow.license_type:
                    continue
                # 计算精确度评分(主要用于多流程匹配时的选择)
                score = calculate_flow_precision_score(flow, total_amount, license_type)
                matched_no_amount.append((flow, score))

            if matched_no_amount:
                # 如果只有一个匹配的流程,直接返回
                if len(matched_no_amount) == 1:
                    flow, score = matched_no_amount[0]
                    logger.info(f"金额为空\uff0c匹配无金额限制流程: {flow.flow_name} (精确度评分: {score}分)")
                    return flow, None

                # 多个流程匹配时,按精确度评分排序
                matched_no_amount.sort(key=lambda x: (-x[1], x[0].created_time))
                selected_flow, selected_score = matched_no_amount[0]
                flow_names = [f"{f.flow_name}({s}分)" for f, s in matched_no_amount]
                logger.info(
                    f"金额为空\uff0c多流程匹配\uff0c已选择流程 {selected_flow.flow_name} "
                    f"(精确度评分: {selected_score}分)\uff0c候选流程: {', '.join(flow_names)}"
                )
                return selected_flow, None

            # 无匹配流程,按 business_type 分支返回
            return _no_match()

        # 正常金额匹配逻辑
        # 收集所有匹配的流程
        matched_flows: list[tuple[ApprovalFlow, int]] = []

        for flow in flows:
            # 检查金额范围匹配
            if flow.min_amount and total_amount < float(flow.min_amount):
                continue
            if flow.max_amount and total_amount > float(flow.max_amount):
                continue

            # 检查授权类型匹配
            if flow.license_type and license_type != flow.license_type:
                continue

            # 流程匹配成功,计算精确度评分
            score = calculate_flow_precision_score(flow, total_amount, license_type)
            matched_flows.append((flow, score))

        # 如果没有匹配的流程,按 business_type 分支返回
        if not matched_flows:
            return _no_match()

        # 如果只有一个匹配的流程,直接返回
        if len(matched_flows) == 1:
            flow, score = matched_flows[0]
            logger.info(f"审批流程匹配成功: {flow.flow_name} (精确度评分: {score}分)")
            return flow, None

        # 多个流程匹配时,按精确度评分排序
        # 评分高的优先,评分相同时按创建时间排序(最早创建的优先)
        matched_flows.sort(key=lambda x: (-x[1], x[0].created_time))

        # 选择评分最高的流程
        selected_flow, selected_score = matched_flows[0]

        # 记录多流程匹配日志
        flow_names = [f"{f.flow_name}({s}分)" for f, s in matched_flows]
        logger.info(
            f"多流程匹配\uff0c已选择流程 {selected_flow.flow_name} "
            f"(精确度评分: {selected_score}分)\uff0c候选流程: {', '.join(flow_names)}"
        )

        return selected_flow, None

    def check_flow_has_all_approvers(self, db: Session, flow_id: int, team_id: int) -> dict[str, Any]:
        """检查流程各审批节点是否有人可批\uff08整角色成员 \u222a 仍在角色内的指定成员\uff09。

        node_index 为节点在全部节点\uff08含抄送\uff09中的 1-based 位置\uff0c与「第 N 个节点」提示一致。
        """
        from app.services.approval_routing import NODE_TYPE_APPROVAL, resolve_node_user_ids

        flow = self.get_by_id(db, flow_id, team_id)
        nodes = list(flow.nodes) if flow else []
        result: dict[str, Any] = {"all_have_approvers": bool(nodes), "nodes": [], "missing_nodes": []}
        for index, node in enumerate(nodes, start=1):
            user_ids = resolve_node_user_ids(db, node, team_id)
            is_approval = (node.node_type or NODE_TYPE_APPROVAL) == NODE_TYPE_APPROVAL
            has_approvers = bool(user_ids) or not is_approval
            status = {
                "node_id": node.id,
                "node_index": index,
                "node_name": node.node_name,
                "node_type": node.node_type,
                "has_approvers": has_approvers,
                "approver_count": len(user_ids),
            }
            result["nodes"].append(status)
            if not has_approvers:
                result["all_have_approvers"] = False
                result["missing_nodes"].append(status)
        return result


class ApprovalCRUD:
    def get_by_id(self, db: Session, approval_id: int, team_id: int | None = None) -> Approval | None:
        query = db.query(Approval).filter(Approval.id == approval_id)
        if team_id is not None:
            query = query.filter(Approval.team_id == team_id)
        return query.first()

    def get_by_entity(
        self, db: Session, business_type: str, business_id: int, team_id: int | None = None,
    ) -> Approval | None:
        """
        通用\uff1a按业务单据类型+ID+团队查询最新一条审批实例\uff08A5\uff09

        Args:
            db: 数据库会话
            business_type: 业务单据类型\uff08CONTRACT/PAYMENT/INVOICE/INVOICE_REISSUE/LICENSE/OPPORTUNITY\uff09
            business_id: 业务单据ID
            team_id: 团队ID\uff08可选\uff0c团队隔离\uff09

        Returns:
            Optional[Approval]: 最新一条审批实例\uff0c无则 None
        """
        query = db.query(Approval).filter(
            Approval.business_type == business_type,
            Approval.business_id == business_id,
        )
        if team_id is not None:
            query = query.filter(Approval.team_id == team_id)
        return query.order_by(Approval.id.desc()).first()

    def get_pending_by_entity(
        self,
        db: Session,
        business_type: str,
        business_id: int,
        team_id: int | None = None,
    ) -> Approval | None:
        """Return the active pending approval for a business entity, if any.

        A retry of the same submit action must reuse the existing workflow
        instance rather than creating a second approval.  Historical rejected
        or cancelled instances are intentionally excluded.
        """
        query = db.query(Approval).filter(
            Approval.business_type == business_type,
            Approval.business_id == business_id,
            Approval.status == ApprovalStatus.PENDING,
        )
        if team_id is not None:
            query = query.filter(Approval.team_id == team_id)
        return query.order_by(Approval.id.desc()).first()

    def get_by_contract_id(self, db: Session, contract_id: int, team_id: int | None = None) -> Approval | None:
        """
        根据合同ID查询审批实例\uff08合同专用 thin wrapper\uff0cA5 解耦后保留以兼容现有调用方\uff09

        注意\uff1a即使合同已删除\uff08deleted_at != null\uff09\uff0c审批记录仍然可以查询
        外键 contract_id 在合同删除后会置为 NULL\uff0c但审批记录保留。
        本 wrapper 委托 get_by_entity(CONTRACT, contract_id, team_id)——
        A3 迁移 012 已把旧审批行的 business_id 回填为 contract_id\uff0c
        故 business_id == contract_id 的查询等价于原 contract_id 过滤。

        Args:
            db: 数据库会话
            contract_id: 合同ID
            team_id: 团队ID\uff08可选\uff09

        Returns:
            Optional[Approval]: 审批实例
        """
        return self.get_by_entity(db, BusinessType.CONTRACT, contract_id, team_id)

    def get_by_approval_id_include_deleted_contract(
        self,
        db: Session,
        approval_id: int,
        team_id: int | None = None
    ) -> Approval | None:
        """
        根据审批ID查询审批实例\uff08包含已删除合同的审批\uff09

        用途\uff1a管理员查询已删除合同的审批历史

        Args:
            db: 数据库会话
            approval_id: 审批实例ID
            team_id: 团队ID\uff08可选\uff09

        Returns:
            Optional[Approval]: 审批实例\uff08合同可能已删除\uff09
        """
        query = db.query(Approval).filter(Approval.id == approval_id)
        if team_id is not None:
            query = query.filter(Approval.team_id == team_id)
        return query.first()

    def get_approvals_for_deleted_contracts(
        self,
        db: Session,
        team_id: int,
        skip: int = 0,
        limit: int = 100,
        status: str | None = None
    ) -> tuple[list[Approval], int]:
        """
        查询已删除合同的审批记录列表\uff08管理员查询\uff09

        用途\uff1a管理员查询已删除合同的审批历史

        Args:
            db: 数据库会话
            team_id: 团队ID\uff08团队隔离\uff09
            skip: 跳过记录数
            limit: 返回记录数上限
            status: 审批状态筛选\uff08可选\uff09

        Returns:
            Tuple[List[Approval], int]: 已删除合同的审批列表和总数
        """
        query = db.query(Approval).filter(
            Approval.team_id == team_id,
            Approval.contract_id.is_(None)  # 合同删除后 contract_id 置为 NULL
        )

        if status:
            query = query.filter(Approval.status == status)

        total = query.count()
        approvals = query.order_by(Approval.updated_time.desc()).offset(skip).limit(limit).all()
        return approvals, total
    
    def get_multi(
        self, db: Session, skip: int = 0, limit: int = 100, status: str | None = None,
    ) -> tuple[list[Approval], int]:
        query = db.query(Approval)
        
        if status:
            query = query.filter(Approval.status == status)
        
        total = query.count()
        approvals = query.order_by(Approval.created_time.desc()).offset(skip).limit(limit).all()
        
        return approvals, total
    
    def create_approval(
        self, db: Session, contract: Contract, flow: ApprovalFlow,
        submitter_id: str, submitter_name: str | None,
    ) -> Approval:
        """
        创建合同审批实例\uff08合同专用 thin wrapper\uff0cA5 解耦后保留以兼容现有调用方\uff09

        委托 create_approval_generic(CONTRACT, contract.id, contract.team_id, ...)\uff0c
        合同回归语义\uff1aCONTRACT 分支额外写 contract_id=business_id\uff0c兼容旧外键字段。
        """
        return self.create_approval_generic(
            db, BusinessType.CONTRACT, contract.id, contract.team_id,
            flow, submitter_id, submitter_name,
        )

    def create_approval_generic(
        self,
        db: Session,
        business_type: str,
        business_id: int,
        team_id: int,
        flow: ApprovalFlow,
        submitter_id: str,
        submitter_name: str | None,
    ) -> Approval:
        """
        通用审批实例创建\uff08支持 CONTRACT/PAYMENT/INVOICE/INVOICE_REISSUE/LICENSE/OPPORTUNITY\uff09

        - 通过适配器 get_entity 取业务单据\uff1b不存在则 raise ValueError\uff08防幻觉单据ID\uff09
        - 写 Approval.business_type/business_id\uff1bCONTRACT 额外写 contract_id=business_id 兼容旧字段
        - adapter.on_submit 切单据状态\uff08适配器自带 E4 None 守卫\uff0c此处 entity 已校验非 None\uff09
        - 创建首个 ApprovalRecord(SUBMIT)

        Args:
            db: 数据库会话
            business_type: 业务单据类型
            business_id: 业务单据ID
            team_id: 团队ID
            flow: 匹配到的审批流程
            submitter_id: 提交人系统用户ID
            submitter_name: 提交人姓名

        Returns:
            Approval: 创建后的审批实例
        """
        approval = self._create_approval_impl(
            db, business_type, business_id, team_id, flow,
            submitter_id, submitter_name, auto_commit=True
        )
        db.commit()
        db.refresh(approval)
        return approval

    def create_approval_only(
        self,
        db: Session,
        business_type: str,
        business_id: int,
        team_id: int,
        flow: ApprovalFlow,
        submitter_id: str,
        submitter_name: str | None,
    ) -> Approval:
        """
        创建审批实例\uff08不自动 commit\uff09

        用途\uff1aApprovalTransactionManager.create_with_approval 中使用\uff0c
        在同一事务中创建业务单据 + approval_phase 切换 + Approval 创建。

        Args:
            db: 数据库会话
            business_type: 业务单据类型
            business_id: 业务单据ID
            team_id: 团队ID
            flow: 匹配到的审批流程
            submitter_id: 提交人系统用户ID
            submitter_name: 提交人姓名

        Returns:
            Approval: 创建后的审批实例\uff08已 flush\uff0c未 commit\uff09
        """
        return self._create_approval_impl(
            db, business_type, business_id, team_id, flow,
            submitter_id, submitter_name, auto_commit=False
        )

    def _create_approval_impl(
        self,
        db: Session,
        business_type: str,
        business_id: int,
        team_id: int,
        flow: ApprovalFlow,
        submitter_id: str,
        submitter_name: str | None,
        auto_commit: bool = False,
    ) -> Approval:
        """
        审批实例创建核心实现\uff08避免代码重复\uff09

        Args:
            db: 数据库会话
            business_type: 业务单据类型
            business_id: 业务单据ID
            team_id: 团队ID
            flow: 匹配到的审批流程
            submitter_id: 提交人系统用户ID
            submitter_name: 提交人姓名
            auto_commit: True 由 create_approval_generic 统一提交并回写单据状态\uff1bFalse 由事务管理器提交

        Returns:
            Approval: 创建后的审批实例
        """
        from app.services.approval_adapter import get_adapter

        adapter = get_adapter(business_type)
        with db.no_autoflush:
            entity = adapter.get_entity(db, business_id, team_id)
        if entity is None:
            raise ValueError("业务单据不存在")
        from app.services.approval_routing import build_snapshot, enter_next

        # 提交时冻结审批人;任一审批节点无人可批则拒绝,单据不进入审批。
        nodes_snapshot = build_snapshot(db, list(flow.nodes), team_id)

        if auto_commit:
            from app.services.approval_adapter import advance_approval_source, get_approval_customer_id

            with db.no_autoflush:
                customer_id = get_approval_customer_id(db, business_type, entity)
            if customer_id is not None and business_type in {
                BusinessType.CONTRACT, BusinessType.PAYMENT, BusinessType.INVOICE,
                BusinessType.OPPORTUNITY, BusinessType.LICENSE,
            }:
                with db.no_autoflush:
                    entity = db.query(type(entity)).filter(
                        type(entity).id == business_id, type(entity).team_id == team_id,
                    ).populate_existing().with_for_update().one()
                if get_approval_customer_id(db, business_type, entity) != customer_id:
                    raise ValueError("业务单据所属客户已变更\uff0c请重新提交")
        # contract_id 是旧合同审批兼容字段;非合同审批统一依赖 business_type/business_id 定位。
        contract_id = business_id if business_type == BusinessType.CONTRACT else None

        # 补充 submitter_name(INVOICE/PAYMENT 可能无姓名字段)
        if submitter_name is None and submitter_id:
            from app.crud.user import user_crud
            user = user_crud.get_by_id(db, int(submitter_id))
            submitter_name = user.name if user else None

        first_node_id = nodes_snapshot[0]["node_id"]

        db_approval = Approval(
            business_type=business_type,
            business_id=business_id,
            contract_id=contract_id,
            flow_id=flow.id,
            team_id=team_id,
            current_node_id=first_node_id,
            nodes_snapshot=nodes_snapshot,
            status=ApprovalStatus.PENDING,
            submitter_id=submitter_id,
            submitter_name=submitter_name,
        )
        if auto_commit:
            source_state = (
                getattr(entity, "approval_phase", None),
                getattr(entity, "status", None),
                getattr(entity, "confirmation_status", None),
            )

        if auto_commit:
            from app.constants.approval_phase import ApprovalPhase
            if hasattr(entity, "approval_phase"):
                entity.approval_phase = ApprovalPhase.PENDING_REVIEW.value
            adapter.on_submit(db, entity)
            if source_state != (
                getattr(entity, "approval_phase", None),
                getattr(entity, "status", None),
                getattr(entity, "confirmation_status", None),
            ):
                advance_approval_source(db, business_type, entity)
        db.add(db_approval)
        db.flush()
        enter_next(db, db_approval, start_index=0)

        db.add(ApprovalRecord(
            approval_id=db_approval.id,
            node_id=first_node_id,
            approver_id=submitter_id,
            approver_name=submitter_name,  # 同样使用补充后的 submitter_name
            action=ApprovalAction.SUBMIT,
            comment=None,
            team_id=team_id,
        ))

        # 更新业务单据的 approval_id(关键修复)
        # 将创建的 Approval.id 关联到业务单据,使前端能正确显示审批状态
        if hasattr(entity, 'approval_id'):
            entity.approval_id = db_approval.id

        # False: ApprovalTransactionManager 切换单据状态并统一提交;True: wrapper 提交。
        return db_approval



    def approve(
        self, db: Session, approval: Approval, action_request: ApprovalActionRequest,
        approver_id: str, approver_name: str,
    ) -> Approval:
        from app.constants.approval_phase import ApprovalPhase
        from app.services.approval_adapter import advance_approval_source, get_adapter, get_approval_customer_id
        from app.services.approval_routing import clear_approvers, current_snapshot_entry, enter_next, is_participant
        from app.services.outbound_notification_job_service import (
            OutboundNotificationJobRequest,
            outbound_notification_job_service,
        )

        expected_node_id = approval.current_node_id

        instance = _approval_instance(approval)
        adapter = get_adapter(instance.business_type)
        with db.no_autoflush:
            # Keep passing legacy nullable IDs through to the adapter unchanged.
            entity = adapter.get_entity(db, cast("int", instance.business_id), instance.team_id)
        with db.no_autoflush:
            customer_id = get_approval_customer_id(db, instance.business_type, entity)
        approval = db.query(Approval).filter(
            Approval.id == approval.id, Approval.team_id == approval.team_id,
        ).populate_existing().with_for_update().one()
        instance = _approval_instance(approval)
        if approval.current_node_id != expected_node_id:
            raise ValueError('审批已被其他用户处理')
        if action_request.updated_time is not None and approval.updated_time != action_request.updated_time:
            raise ValueError('审批已被其他用户处理')
        if approval.status != ApprovalStatus.PENDING:
            raise ValueError(f'当前审批状态为 {approval.status}\uff0c无法进行审批操作')
        if not is_participant(db, approval, int(approver_id), ApprovalParticipantKind.APPROVER):
            raise ValueError('您不是当前节点的审批人')
        current_entry = current_snapshot_entry(approval)
        if current_entry is None:
            raise ValueError('当前审批节点不存在')

        record = ApprovalRecord(
            approval_id=approval.id,
            node_id=approval.current_node_id,
            approver_id=approver_id,
            approver_name=approver_name,
            action=action_request.action.value,
            comment=action_request.comment,
            team_id=approval.team_id,
        )
        db.add(record)

        # The customer fence precedes this entity lock and all adapter side effects.
        if entity is not None:
            with db.no_autoflush:
                entity = db.query(type(entity)).filter(
                    type(entity).id == entity.id, type(entity).team_id == approval.team_id,
                ).populate_existing().with_for_update().one()
            if customer_id is not None and get_approval_customer_id(db, instance.business_type, entity) != customer_id:
                raise ValueError("业务单据所属客户已变更\uff0c请刷新后重试")

        cc_requests: list[OutboundNotificationJobRequest] = []
        if action_request.action.value == ApprovalAction.APPROVE:
            # 跳过抄送节点(写入抄送人)直达下一审批节点;无后续审批节点即通过。
            routed = enter_next(db, approval)
            cc_requests = outbound_notification_job_service.enqueue_cc_entries(
                db, approval=approval, team_id=int(approval.team_id),
                cc_entries=routed.cc_entries, actor_id=approver_id,
            )
            if routed.finished:
                # 最后节点通过:Approval.status = APPROVED
                if entity is not None:
                    advance_approval_source(db, instance.business_type, entity)
                instance.status = ApprovalStatus.APPROVED
                if entity is not None:
                    # 切换 entity.approval_phase = APPROVED
                    if hasattr(entity, 'approval_phase'):
                        entity.approval_phase = ApprovalPhase.APPROVED.value
                    adapter.on_approved(db, entity)

        elif action_request.action.value == ApprovalAction.REJECT:
            clear_approvers(db, approval)
            # Approval.status = REJECTED
            if entity is not None:
                advance_approval_source(db, instance.business_type, entity)
            instance.status = ApprovalStatus.REJECTED
            if entity is not None:
                # 切换 entity.approval_phase = REJECTED
                if hasattr(entity, 'approval_phase'):
                    entity.approval_phase = ApprovalPhase.REJECTED.value
                adapter.on_rejected(db, entity)

        db.commit()
        db.refresh(approval)
        for request in cc_requests:
            outbound_notification_job_service.kick(request)
        return approval

    def cancel(self, db: Session, approval: Approval, user_id: str) -> Approval:
        from app.constants.approval_phase import ApprovalPhase
        from app.services.approval_adapter import advance_approval_source, get_adapter, get_approval_customer_id

        if approval.business_type == BusinessType.CONTRACT_CHANGE:
            raise ValueError("合同变更审批不支持撤回")

        instance = _approval_instance(approval)
        adapter = get_adapter(instance.business_type)
        with db.no_autoflush:
            # Keep passing legacy nullable IDs through to the adapter unchanged.
            entity = adapter.get_entity(db, cast("int", instance.business_id), instance.team_id)
        with db.no_autoflush:
            customer_id = get_approval_customer_id(db, instance.business_type, entity)
        approval = db.query(Approval).filter(
            Approval.id == approval.id, Approval.team_id == approval.team_id,
        ).populate_existing().with_for_update().one()
        instance = _approval_instance(approval)
        if approval.status != ApprovalStatus.PENDING:
            raise ValueError("只能撤回审批中的审批流程")

        if approval.submitter_id != user_id:
            raise ValueError("只有提交人可以撤回审批")

        instance.status = ApprovalStatus.CANCELLED
        from app.services.approval_routing import clear_approvers
        clear_approvers(db, approval)

        if entity is not None:
            with db.no_autoflush:
                entity = db.query(type(entity)).filter(
                    type(entity).id == entity.id, type(entity).team_id == approval.team_id,
                ).populate_existing().with_for_update().one()
            if customer_id is not None and get_approval_customer_id(db, instance.business_type, entity) != customer_id:
                raise ValueError("业务单据所属客户已变更\uff0c请刷新后重试")
        if entity is not None:
            advance_approval_source(db, instance.business_type, entity)
            # 切换 entity.approval_phase = DRAFT(允许重新提交)
            if hasattr(entity, 'approval_phase'):
                entity.approval_phase = ApprovalPhase.DRAFT.value
            adapter.on_cancelled(db, entity)

        db.commit()
        db.refresh(approval)
        return approval
    
    def get_records(self, db: Session, approval_id: int, team_id: int) -> list[ApprovalRecord]:
        return db.query(ApprovalRecord).filter(
            ApprovalRecord.approval_id == approval_id,
            ApprovalRecord.team_id == team_id,
        ).order_by(ApprovalRecord.created_time.asc()).all()

    def get_overdue_approvals(
        self,
        db: Session,
        team_id: int,
        min_hours: int = 48,
        skip: int = 0,
        limit: int = 100
    ) -> tuple[list[dict[str, Any]], int]:
        """
        查询超时的审批实例列表\uff08泛化覆盖 CONTRACT/PAYMENT/INVOICE/INVOICE_REISSUE/LICENSE/OPPORTUNITY\uff09。

        I-1 修复\uff1a原实现 `JOIN Contract ON Approval.contract_id == Contract.id`
        为 INNER JOIN\uff0c非合同审批 contract_id 可能为 NULL\uff0c导致超时审批在
        /overdue 不可见。现去掉 Contract JOIN\uff0c按 Approval 基本
        信息\uff08business_type/business_id\uff09返回\uff1bcontract_id 仍透传\uff08CONTRACT 类
        非空、非合同为 None\uff09\uff0c实体名由调用方按需经适配器 get_entity
        取\uff08前端铃铛已走 list_approvals 不消费 /overdue\uff0c本端点仅作管理端应急\uff0c
        泛化后覆盖三类即可\uff09。保留 team_id 过滤与 overdue_hours 计算。

        Args:
            db: 数据库会话
            team_id: 团队ID\uff08团队隔离\uff09
            min_hours: 最小超时小时数\uff0c默认48小时
            skip: 跳过记录数
            limit: 返回记录数上限

        Returns:
            Tuple[List[Dict], int]: 超时审批列表和总数
        """
        from datetime import timedelta


        # 计算超时阈值时间点
        now = business_now()
        threshold_time = now - timedelta(hours=min_hours)

        # 查询超时的审批实例(不再 INNER JOIN Contract——非合同审批
        # contract_id=NULL,INNER JOIN 会把它们排除在外)
        query = db.query(
            Approval.id.label('approval_id'),
            Approval.business_type,
            Approval.business_id,
            Approval.contract_id,
            Approval.status,
            Approval.created_time.label('submit_time'),
            Approval.submitter_name,
            Approval.current_node_id,
            Approval.nodes_snapshot,
            ApprovalNode.node_name.label('legacy_node_name'),
        ).outerjoin(
            ApprovalNode,
            and_(
                Approval.nodes_snapshot.is_(None),
                Approval.current_node_id == ApprovalNode.id,
                or_(ApprovalNode.team_id == Approval.team_id, ApprovalNode.team_id.is_(None)),
            ),
        ).filter(
            Approval.team_id == team_id,
            Approval.status == ApprovalStatus.PENDING,
            Approval.created_time <= threshold_time
        ).order_by(
            Approval.created_time.asc()
        )

        total = query.count()
        results = query.offset(skip).limit(limit).all()

        # 转换为字典列表并计算超时小时数
        overdue_list = []
        for row in results:
            overdue_hours = int((now - row.submit_time).total_seconds() / 3600)

            current_entry = next(
                (item for item in (row.nodes_snapshot or []) if item.get('node_id') == row.current_node_id),
                None,
            )
            current_node_name = (
                (current_entry or {}).get('node_name')
                if row.nodes_snapshot is not None
                else row.legacy_node_name
            )
            approvers = self._current_approvers(db, row.approval_id, team_id)
            current_approver_name = ', '.join(a.name for a in approvers if a.name) or None
            overdue_list.append({
                'approval_id': row.approval_id,
                'business_type': row.business_type,
                'business_id': row.business_id,
                'contract_id': row.contract_id,
                'contract_name': None,
                'contract_number': None,
                'current_node_name': current_node_name,
                'current_approver_name': current_approver_name,
                'overdue_hours': overdue_hours,
                'submitter_name': row.submitter_name,
                'submit_time': row.submit_time,
                'status': row.status
            })

        return overdue_list, total

    def _current_approvers(self, db: Session, approval_id: int, team_id: int) -> list[User]:
        """当前审批节点的冻结审批人。"""
        from app.models.user import User

        return db.query(User).join(ApprovalParticipant, ApprovalParticipant.user_id == User.id).filter(
            ApprovalParticipant.approval_id == approval_id,
            ApprovalParticipant.team_id == team_id,
            ApprovalParticipant.kind == ApprovalParticipantKind.APPROVER,
        ).all()

    # ========================================================================
    # Task C3:通用审批列表(GET /v1/approvals)
    # ========================================================================
    # E2 越权过滤(P0)——按 tab 切换查询主体:
    #   pending  : status=PENDING AND team_id AND 我是当前节点冻结审批人(participants APPROVER)
    #   cc       : 我是已流转到的抄送节点的抄送人(participants CC)
    #   processed: EXISTS(records WHERE approver_id=user_id AND action!=SUBMIT) AND team_id
    #   submitted: submitter_id=user_id AND team_id
    # E9 N+1 规避:审批行先取主体,再按 business_type 分组批量预取
    #   Contract/PaymentRecord/InvoiceApplication/LicenseApplication 四表,内存 join 出
    #   application_number / entity_name / entity_amount 三摘要字段。
    # overdue_hours:Python 计算(now - created_time)/3600,DB 无关,与
    #   get_overdue_approvals 同套路;非 PENDING 行也回传(前端按需展示)。
    # pending_count:当前用户「待我审批」总数,任意 tab 都附给前端徽章。
    # ========================================================================

    def build_list_query(
        self,
        db: Session,
        *,
        team_id: int,
        user_id: int,
        tab: str,
        search: str | None,
        filters: list[FilterCondition],
        sorts: list[SortCondition],
    ) -> tuple[Query[Approval], bool]:
        """Return ordered approvals and whether legacy summary filtering is required."""
        user_id_str = str(user_id)
        query = db.query(Approval).filter(Approval.team_id == team_id)
        if tab == "pending":
            query = query.filter(
                Approval.status == ApprovalStatus.PENDING,
                _participant_exists(user_id, ApprovalParticipantKind.APPROVER),
            )
        elif tab == "cc":
            query = query.filter(_participant_exists(user_id, ApprovalParticipantKind.CC))
        elif tab == "submitted":
            query = query.filter(Approval.submitter_id == user_id_str)
        elif tab == "processed":
            processed_sub = (
                db.query(ApprovalRecord.approval_id)
                .filter(
                    ApprovalRecord.team_id == team_id,
                    ApprovalRecord.approver_id == user_id_str,
                    ApprovalRecord.action != ApprovalAction.SUBMIT,
                )
                .distinct()
            )
            query = query.filter(Approval.id.in_(processed_sub))
        else:
            raise ValueError(f"非法 tab: {tab}\uff0c仅支持 pending / processed / submitted / cc")

        context = ListQueryContext(
            db=db,
            team_id=team_id,
            current_user_id=user_id_str,
            now=business_now(),
        )
        effective_filters = without_filter_field(filters, "status") if tab == "pending" else filters
        effective_sorts = sorts
        if tab == "pending" and not effective_sorts:
            effective_sorts = [SortCondition(field="overdue_hours", direction="desc")]
        _, ordered = build_optional_list_query(
            query,
            APPROVALS_LIST_QUERY_CATALOG,
            filters=effective_filters,
            sorts=effective_sorts,
            context=context,
            search=search,
        )
        return ordered.order_by(Approval.id.asc()), False

    def build_list_items(
        self, projection_db: Session, rows: list[Approval], team_id: int, *, cc_user_id: int | None = None,
    ) -> list[dict[str, Any]]:
        summaries = self._batch_entity_summaries(projection_db, rows, team_id)
        latest_cc: dict[int, ApprovalParticipant] = {}
        if rows and cc_user_id is not None:
            deliveries = projection_db.query(ApprovalParticipant).filter(
                ApprovalParticipant.team_id == team_id,
                ApprovalParticipant.user_id == cc_user_id,
                ApprovalParticipant.kind == ApprovalParticipantKind.CC,
                ApprovalParticipant.approval_id.in_([ap.id for ap in rows]),
            ).order_by(ApprovalParticipant.created_time.desc(), ApprovalParticipant.id.desc())
            for delivery in deliveries:
                latest_cc.setdefault(int(delivery.approval_id), delivery)
        now = business_now()
        items: list[dict[str, Any]] = []
        for ap in rows:
            cc_delivery = latest_cc.get(int(ap.id))
            instance = _approval_instance(ap)
            sum_key = (instance.business_type, instance.business_id) if instance.business_id else None
            summary = summaries.get(sum_key) if sum_key else None
            overdue_hours: int | None = None
            if ap.status == ApprovalStatus.PENDING and ap.created_time is not None:
                overdue_hours = int((now - ap.created_time).total_seconds() // 3600)
            contract_file_path = summary.get("contract_file_path") if summary else None
            invoice_file_path = summary.get("invoice_file_path") if summary else None
            change_file_path = summary.get("attachment_path") if summary else None
            items.append({
                "id": ap.id,
                "business_type": ap.business_type,
                "business_id": ap.business_id if ap.business_id is not None else 0,
                "business_public_id": summary.get("business_public_id") if summary else None,
                "original_invoice_application_id": summary.get("original_invoice_application_id") if summary else None,
                "application_number": (
                    summary["application_number"] if summary else f"{ap.business_type}-{ap.business_id}"
                ),
                "entity_name": summary["entity_name"] if summary else None,
                "entity_amount": summary["entity_amount"] if summary else None,
                "actual_payer_name": summary.get("actual_payer_name") if summary else None,
                "license_status": summary.get("license_status") if summary else None,
                "customer_info": summary["customer_info"] if summary else None,
                "has_attachment": bool(contract_file_path or invoice_file_path or change_file_path),
                "contract_file_path": contract_file_path,
                "contract_file_name": summary.get("contract_file_name") if summary else None,
                "contract_file_size": summary.get("contract_file_size") if summary else None,
                "contract_file_mime_type": summary.get("contract_file_mime_type") if summary else None,
                "invoice_file_path": invoice_file_path,
                "invoice_number": summary.get("invoice_number") if summary else None,
                "issued_time": _serialize_optional_datetime(summary.get("issued_time")) if summary else None,
                "change_items": summary.get("change_items") if summary else None,
                "reason": summary.get("reason") if summary else None,
                "attachment_name": summary.get("attachment_name") if summary else None,
                "attachment_size": summary.get("attachment_size") if summary else None,
                "attachment_mime_type": summary.get("attachment_mime_type") if summary else None,
                "submitter_id": ap.submitter_id,
                "submitter_name": ap.submitter_name,
                "status": ap.status,
                "created_time": ap.created_time.isoformat() if ap.created_time else "",
                "updated_time": ap.updated_time.isoformat() if ap.updated_time else "",
                "overdue_hours": overdue_hours,
                "cc_node_name": cc_delivery.node_name if cc_delivery else None,
                "cc_time": cc_delivery.created_time.isoformat() if cc_delivery else None,
            })
        return items

    def list_approvals(
        self,
        db: Session,
        team_id: int,
        user_id: int,
        tab: str = "pending",
        business_type: str | None = None,
        business_types: list[str] | None = None,
        business_types_exclude: list[str] | None = None,
        statuses: list[str] | None = None,
        statuses_exclude: list[str] | None = None,
        application_number: str | None = None,
        entity_name: str | None = None,
        submitter_name: str | None = None,
        entity_amount: float | None = None,
        created_time_start: date | None = None,
        created_time_end: date | None = None,
        page: int = 1,
        page_size: int = 20,
        search: str | None = None,
        filters: list[FilterCondition] | None = None,
        sorts: list[SortCondition] | None = None,
    ) -> tuple[list[dict[str, Any]], int, int]:
        """通用审批列表查询\uff08E2 越权过滤 + E9 摘要内存 join\uff09。

        Args:
            db: 数据库会话
            team_id: 团队ID\uff08团队隔离\uff09
            user_id: 当前用户ID\uff08int\uff0c用于 submitted/processed 过滤\uff09
            tab: pending / processed / submitted / cc
            business_type: 可选业务类型过滤\uff08兼容旧调用\uff09
            business_types: 可选业务类型包含过滤\uff08CONTRACT / PAYMENT / INVOICE / LICENSE / OPPORTUNITY\uff09
            business_types_exclude: 可选业务类型排除过滤
            statuses: 可选审批状态包含过滤
            statuses_exclude: 可选审批状态排除过滤
            application_number: 可选单号模糊搜索\uff08摘要字段\uff0c组装后过滤\uff09
            entity_name: 可选实体名称模糊搜索\uff08摘要字段\uff0c组装后过滤\uff09
            submitter_name: 可选提交人模糊搜索
            entity_amount: 可选金额精确筛选\uff08摘要字段\uff0c组装后过滤\uff09
            created_time_start: 可选提交时间起始
            created_time_end: 可选提交时间结束
            page: 页码\uff081-based\uff09
            page_size: 每页条数

        Returns:
            Tuple[List[Dict], int, int]: (items, total, pending_count)
                items 每行对齐前端 ApprovalListItemSchema\uff1b
                total 为当前 tab+business_type 过滤后的总数\uff1b
                pending_count 为当前用户待我审批总数\uff08任意 tab 都附\uff09。
        """

        user_id_str = str(user_id)
        skip = max(0, (page - 1) * page_size)

        # ---- 主体查询:按 tab 构造过滤 ----
        query = db.query(Approval).filter(Approval.team_id == team_id)

        unified_protocol = uses_unified_list_query(filters=filters, sorts=sorts)
        if not unified_protocol:
            include_types = business_types or ([business_type] if business_type else [])
            exclude_types = business_types_exclude or []

            if include_types:
                query = query.filter(Approval.business_type.in_(include_types))
            if exclude_types:
                query = query.filter(~Approval.business_type.in_(exclude_types))
            if statuses:
                query = query.filter(Approval.status.in_(statuses))
            if statuses_exclude:
                query = query.filter(~Approval.status.in_(statuses_exclude))
            if submitter_name:
                query = query.filter(Approval.submitter_name.ilike(f"%{submitter_name.strip()}%"))
            if created_time_start:
                query = query.filter(Approval.created_time >= datetime.combine(created_time_start, time.min))
            if created_time_end:
                query = query.filter(Approval.created_time <= datetime.combine(created_time_end, time.max))

        if tab == "pending":
            query = query.filter(
                Approval.status == ApprovalStatus.PENDING,
                _participant_exists(user_id, ApprovalParticipantKind.APPROVER),
            )
        elif tab == "cc":
            query = query.filter(_participant_exists(user_id, ApprovalParticipantKind.CC))
        elif tab == "submitted":
            query = query.filter(Approval.submitter_id == user_id_str)
        elif tab == "processed":
            # 我已处理:作为审批人留下过 APPROVE/REJECT 记录(排除 SUBMIT,否则
            # 提交人会在 processed 里看到自己的提交)。用 EXISTS 子查询去重,
            # 避免一条审批多条记录导致行重复。
            processed_sub = (
                db.query(ApprovalRecord.approval_id)
                .filter(
                    ApprovalRecord.team_id == team_id,
                    ApprovalRecord.approver_id == user_id_str,
                    ApprovalRecord.action != ApprovalAction.SUBMIT,
                )
                .distinct()
            )
            query = query.filter(Approval.id.in_(processed_sub))
        else:
            raise ValueError(f"非法 tab: {tab}\uff0c仅支持 pending / processed / submitted / cc")

        query = apply_search(
            query,
            APPROVALS_LIST_QUERY_CATALOG,
            search,
            context=ListQueryContext(
                db=db,
                team_id=team_id,
                current_user_id=user_id_str,
                now=business_now(),
            ),
        )

        if unified_protocol:
            query, _needs_summary_filter = self.build_list_query(
                db,
                team_id=team_id,
                user_id=user_id,
                tab=tab,
                search=search,
                filters=filters or [],
                sorts=sorts or [],
            )
            total = query.order_by(None).count()
            rows = query.offset(skip).limit(page_size).all()
            items = self.build_list_items(db, rows, team_id, cc_user_id=user_id if tab == "cc" else None)
            pending_count = self._count_pending_for_user(db, team_id, user_id)
            return items, total, pending_count

        needs_summary_filter = any([
            application_number,
            entity_name,
            entity_amount is not None,
        ])
        ordered_query = query.order_by(Approval.created_time.desc())
        if needs_summary_filter:
            rows = ordered_query.all()
        else:
            total = query.count()
            rows = ordered_query.offset(skip).limit(page_size).all()

        items = self.build_list_items(db, rows, team_id, cc_user_id=user_id if tab == "cc" else None)

        def matches_summary_filters(item: dict[str, Any]) -> bool:
            if application_number:
                needle = application_number.strip().lower()
                value = (item.get("application_number") or "").lower()
                if needle not in value:
                    return False
            if entity_name:
                needle = entity_name.strip().lower()
                value = (item.get("entity_name") or "").lower()
                if needle not in value:
                    return False
            if entity_amount is not None:
                value = item.get("entity_amount")
                if value is None:
                    return False
                if Decimal(str(value)) != Decimal(str(entity_amount)):
                    return False
            return True


        if needs_summary_filter:
            items = [item for item in items if matches_summary_filters(item)]
            total = len(items)
            items = items[skip:skip + page_size]

        # ---- pending_count:当前用户待我审批总数,任意 tab 都附 ----
        pending_count = self._count_pending_for_user(db, team_id, user_id)

        return items, total, pending_count

    def _batch_entity_summaries(
        self,
        db: Session,
        approvals: list[Approval],
        team_id: int,
    ) -> dict[tuple[str, int], dict[str, Any]]:
        """按 business_type 分组批量预取实体摘要\uff08application_number/entity_name/entity_amount\uff09。

        - CONTRACT: contract_number / contract_name / total_amount
        - INVOICE: application_number / invoice_title_text / invoice_amount
        - PAYMENT: record_number 或 PAY-{id} / 合同名 / actual_amount
        - LICENSE: application_number / license_type / None
        - OPPORTUNITY: opportunity_number / opportunity_name / total_amount
        - customer_info: 四类业务统一返回关联客户/公司基础信息

        Returns:
            Dict[(business_type, business_id), {application_number, entity_name, entity_amount, customer_info}]
        """
        from app.models.customer import Customer
        from app.models.invoice import InvoiceApplication, InvoiceReissueApplication
        from app.models.license_application import LicenseApplication
        from app.models.opportunity import Opportunity
        from app.models.payment import PaymentPlan, PaymentRecord

        ids_by_type: dict[str, list[int]] = {
            BusinessType.CONTRACT: [],
            BusinessType.CONTRACT_CHANGE: [],
            BusinessType.INVOICE: [],
            BusinessType.INVOICE_REISSUE: [],
            BusinessType.PAYMENT: [],
            BusinessType.LICENSE: [],
            BusinessType.OPPORTUNITY: [],
        }
        for ap in approvals:
            instance = _approval_instance(ap)
            if instance.business_id and instance.business_type in ids_by_type:
                ids_by_type[instance.business_type].append(instance.business_id)

        summaries: dict[tuple[str, int], dict[str, Any]] = {}

        def safe_all(query: Query[_RowT]) -> list[_RowT]:
            try:
                return query.all()
            except OperationalError as exc:
                db.rollback()
                logger.warning("审批列表实体摘要查询失败\uff0c已降级返回基础审批信息: %s", exc)
                return []

        def serialize_customer(customer: Customer | None) -> dict[str, Any] | None:
            if not customer:
                return None
            return {
                "id": customer.public_id,
                "public_id": customer.public_id,
                "account_name": customer.account_name,
                "industry": customer.industry,
                "city": customer.city,
                "company_scale": customer.company_scale,
                "source": customer.source,
                "status": customer.status,
                "owner_id": customer.owner_id,
            }

        def fetch_customers(customer_ids: list[int]) -> dict[int, dict[str, Any] | None]:
            unique_ids = list({cid for cid in customer_ids if cid})
            if not unique_ids:
                return {}
            customers = safe_all(db.query(Customer).filter(
                Customer.id.in_(unique_ids),
                Customer.team_id == team_id,
            ))
            return {c.id: serialize_customer(c) for c in customers}

        # CONTRACT_CHANGE: both change and original contract remain team scoped.
        if ids_by_type[BusinessType.CONTRACT_CHANGE]:
            from app.services.contract_change import amount_change_values

            changes = safe_all(db.query(ContractChangeRequest).filter(
                ContractChangeRequest.id.in_(ids_by_type[BusinessType.CONTRACT_CHANGE]),
                ContractChangeRequest.team_id == team_id,
                ContractChangeRequest.deleted_at.is_(None),
            ))
            changed_contract_ids = list({cast("int", item.contract_id) for item in changes if item.contract_id})
            contracts = safe_all(db.query(Contract).filter(
                Contract.id.in_(changed_contract_ids),
                Contract.team_id == team_id,
                Contract.deleted_at.is_(None),
            )) if changed_contract_ids else []
            contracts_by_id = {item.id: item for item in contracts}
            customers_by_id = fetch_customers([item.customer_id for item in contracts])
            for change in changes:
                contract = contracts_by_id.get(cast("int", change.contract_id))
                if not contract:
                    continue
                _old_amount, new_amount = amount_change_values(change)
                change_id = cast("int", change.id)
                summaries[(BusinessType.CONTRACT_CHANGE, change_id)] = {
                    "application_number": contract.contract_number or f"CONTRACT-{contract.id}",
                    "entity_name": contract.contract_name,
                    "entity_amount": float(new_amount),
                    "customer_info": customers_by_id.get(contract.customer_id),
                    "change_items": change.change_items_json,
                    "reason": change.reason,
                    "attachment_path": change.attachment_path,
                    "attachment_name": change.attachment_name,
                    "attachment_size": change.attachment_size,
                    "attachment_mime_type": change.attachment_mime_type,
                }

        # CONTRACT
        if ids_by_type["CONTRACT"]:
            contracts = safe_all(db.query(Contract).filter(
                Contract.id.in_(ids_by_type["CONTRACT"]), Contract.team_id == team_id
            ))
            customers_by_id = fetch_customers([c.customer_id for c in contracts])
            for c in contracts:
                summaries[(BusinessType.CONTRACT, c.id)] = {
                    "application_number": c.contract_number or f"CONTRACT-{c.id}",
                    "entity_name": c.contract_name,
                    "entity_amount": float(c.total_amount) if c.total_amount is not None else None,
                    "customer_info": customers_by_id.get(c.customer_id),
                    "contract_file_path": c.contract_file_path,
                    "contract_file_name": c.contract_file_name,
                    "contract_file_size": c.contract_file_size,
                    "contract_file_mime_type": c.contract_file_mime_type,
                }

        # INVOICE
        if ids_by_type["INVOICE"]:
            invoices = safe_all(db.query(InvoiceApplication).filter(
                InvoiceApplication.id.in_(ids_by_type["INVOICE"]),
                InvoiceApplication.team_id == team_id,
            ))
            customers_by_id = fetch_customers([inv.customer_id for inv in invoices])
            for inv in invoices:
                summaries[(BusinessType.INVOICE, inv.id)] = {
                    "application_number": inv.application_number or f"INVOICE-{inv.id}",
                    "entity_name": inv.invoice_title_text,
                    "entity_amount": float(inv.invoice_amount) if inv.invoice_amount is not None else None,
                    "customer_info": customers_by_id.get(inv.customer_id),
                    "invoice_file_path": inv.invoice_file_path,
                    "invoice_number": inv.invoice_number,
                    "issued_time": inv.issued_time,
                }

        # INVOICE_REISSUE(通过原发票申请关联获取客户信息)
        if ids_by_type["INVOICE_REISSUE"]:
            reissues = safe_all(db.query(InvoiceReissueApplication).filter(
                InvoiceReissueApplication.id.in_(ids_by_type["INVOICE_REISSUE"]),
                InvoiceReissueApplication.team_id == team_id,
            ))
            original_ids = [
                item.original_invoice_application_id for item in reissues if item.original_invoice_application_id
            ]
            originals = safe_all(db.query(InvoiceApplication).filter(
                InvoiceApplication.id.in_(list(set(original_ids))),
                InvoiceApplication.team_id == team_id,
            )) if original_ids else []
            originals_by_id = {item.id: item for item in originals}
            customers_by_id = fetch_customers([item.customer_id for item in originals])
            for item in reissues:
                original = originals_by_id.get(item.original_invoice_application_id)
                summaries[(BusinessType.INVOICE_REISSUE, item.id)] = {
                    "application_number": item.application_number or f"INVR-{item.id}",
                    "original_invoice_application_id": item.original_invoice_application_id,
                    "entity_name": item.invoice_title_text,
                    "entity_amount": float(item.invoice_amount) if item.invoice_amount is not None else None,
                    "customer_info": customers_by_id.get(original.customer_id) if original else None,
                }

        # PAYMENT(通过 payment_plan_id 批量关联获取合同名称和客户信息)
        if ids_by_type["PAYMENT"]:
            records = safe_all(db.query(PaymentRecord).filter(
                PaymentRecord.id.in_(ids_by_type["PAYMENT"]),
                PaymentRecord.team_id == team_id,
            ))
            plan_ids = [pr.payment_plan_id for pr in records if pr.payment_plan_id]
            plans = safe_all(db.query(PaymentPlan).filter(
                PaymentPlan.id.in_(list(set(plan_ids))),
                PaymentPlan.team_id == team_id,
            )) if plan_ids else []
            plans_by_id = {p.id: p for p in plans}
            contract_ids = [p.contract_id for p in plans if p.contract_id]
            contracts = safe_all(db.query(Contract).filter(
                Contract.id.in_(list(set(contract_ids))),
                Contract.team_id == team_id,
            )) if contract_ids else []
            contracts_by_id = {c.id: c for c in contracts}
            customers_by_id = fetch_customers([c.customer_id for c in contracts])
            for pr in records:
                plan = plans_by_id.get(pr.payment_plan_id)
                contract = contracts_by_id.get(plan.contract_id) if plan else None
                summaries[(BusinessType.PAYMENT, pr.id)] = {
                    "application_number": pr.record_number or f"PAY-{pr.id}",
                    "entity_name": contract.contract_name if contract else None,
                    "entity_amount": float(pr.actual_amount) if pr.actual_amount is not None else None,
                    "actual_payer_name": pr.actual_payer_name,
                    "customer_info": customers_by_id.get(contract.customer_id) if contract else None,
                }

        # LICENSE
        if ids_by_type["LICENSE"]:
            licenses = safe_all(db.query(LicenseApplication).filter(
                LicenseApplication.id.in_(ids_by_type["LICENSE"]),
                LicenseApplication.team_id == team_id,
            ))
            customers_by_id = fetch_customers([cast("int", lic.customer_id) for lic in licenses])
            for lic in licenses:
                license_id = cast("int", lic.id)
                summaries[(BusinessType.LICENSE, license_id)] = {
                    "application_number": lic.application_number or f"LICENSE-{lic.id}",
                    "entity_name": lic.license_type,
                    "entity_amount": None,
                    "license_status": lic.status,
                    "customer_info": customers_by_id.get(cast("int", lic.customer_id)),
                }

        # OPPORTUNITY
        if ids_by_type["OPPORTUNITY"]:
            opportunities = safe_all(db.query(Opportunity).filter(
                Opportunity.id.in_(ids_by_type["OPPORTUNITY"]),
                Opportunity.team_id == team_id,
            ))
            customers_by_id = fetch_customers([opp.customer_id for opp in opportunities])
            for opp in opportunities:
                summaries[(BusinessType.OPPORTUNITY, opp.id)] = {
                    "application_number": opp.opportunity_number or f"OPP-{opp.id}",
                    "business_public_id": opp.public_id,
                    "entity_name": opp.opportunity_name,
                    "entity_amount": float(opp.total_amount) if opp.total_amount is not None else None,
                    "customer_info": customers_by_id.get(opp.customer_id),
                }

        return summaries

    def _count_pending_for_user(
        self,
        db: Session,
        team_id: int,
        user_id: int,
    ) -> int:
        """当前用户「待我审批」总数\uff08pending tab 的 total\uff0c任意 tab 响应都附给前端徽章\uff09。"""
        return db.query(Approval).filter(
            Approval.team_id == team_id,
            Approval.status == ApprovalStatus.PENDING,
            _participant_exists(user_id, ApprovalParticipantKind.APPROVER),
        ).count()


approval_flow_crud = ApprovalFlowCRUD()
approval_crud = ApprovalCRUD()
