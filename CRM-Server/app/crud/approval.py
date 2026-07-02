from sqlalchemy.orm import Session
from sqlalchemy import and_, or_
from typing import Optional, List, Tuple, Dict, Any
from decimal import Decimal
import logging

from app.models.approval import Approval, ApprovalRecord, ApprovalFlow, ApprovalNode, ApprovalStatus, ApprovalAction
from app.models.contract import Contract
from app.constants.business_types import BusinessType
from app.schemas.approval import (
    ApprovalFlowCreate, ApprovalFlowUpdate,
    ApprovalSubmitRequest, ApprovalActionRequest
)

logger = logging.getLogger(__name__)


def calculate_flow_precision_score(flow: ApprovalFlow, amount, license_type: Optional[str]) -> int:
    """
    计算审批流程的精确度评分

    评分规则（总分100分）：
    1. 金额精确度评分（0-50分）：
       - 有上下限（min_amount 和 max_amount 都有）：50分
       - 只有上限（只有 max_amount）：30分
       - 只有下限（只有 min_amount）：20分
       - 无金额限制：0分
       - 范围越窄额外加分（范围宽度越小，评分越高）

    2. 条件数量评分（0-30分）：
       - 有金额条件：10分
       - 有授权类型条件：20分
       - 总计最多30分

    3. 创建时间评分（0-20分）：
       - 作为兜底策略，最早创建的流程得分高
       - 需要在多流程比较时使用

    A5 重构：入参由 (flow, contract) 泛化为 (flow, amount, license_type)，
    原合同语义保留——amount 即原 contract.total_amount，license_type 即原
    contract.license_type。评分逻辑逐字不变（E1 合同回归契约）。

    Args:
        flow: 审批流程
        amount: 业务单据金额（合同为 total_amount，回款为 actual_amount，发票为 invoice_amount）
        license_type: 授权类型（仅合同有值；回款/发票传 None）

    Returns:
        int: 精确度评分（0-100分）
    """
    score = 0

    # 1. 金额精确度评分（0-50分）
    min_amount = float(flow.min_amount) if flow.min_amount else None
    max_amount = float(flow.max_amount) if flow.max_amount else None

    if min_amount is not None and max_amount is not None:
        # 有上下限：范围最精确，基础分50分
        score += 50
        # 范围越窄额外加分（范围宽度越小，评分越高）
        # 计算范围宽度占合同金额的比例
        contract_amount = float(amount) if amount else 0
        if contract_amount > 0:
            range_width = max_amount - min_amount
            # 范围宽度越小，加分越多（最多10分）
            # 如果范围宽度小于合同金额的10%，加10分
            # 如果范围宽度小于合同金额的50%，加5分
            if range_width < contract_amount * 0.1:
                score += 10
            elif range_width < contract_amount * 0.5:
                score += 5
    elif max_amount is not None:
        # 只有上限：中等精确，30分
        score += 30
    elif min_amount is not None:
        # 只有下限：较低精确，20分
        score += 20
    # 无金额限制：0分（不加分）

    # 2. 条件数量评分（0-30分）
    if min_amount is not None or max_amount is not None:
        # 有金额条件：10分
        score += 10

    if flow.license_type is not None and license_type == flow.license_type:
        # 有授权类型条件且匹配：20分
        score += 20

    return score


class ApprovalFlowCRUD:
    def get_by_id(self, db: Session, flow_id: int, team_id: Optional[int] = None) -> Optional[ApprovalFlow]:
        query = db.query(ApprovalFlow).filter(ApprovalFlow.id == flow_id)
        if team_id is not None:
            query = query.filter(ApprovalFlow.team_id == team_id)
        return query.first()

    def get_by_code(self, db: Session, flow_code: str, team_id: Optional[int] = None) -> Optional[ApprovalFlow]:
        query = db.query(ApprovalFlow).filter(ApprovalFlow.flow_code == flow_code)
        if team_id is not None:
            query = query.filter(ApprovalFlow.team_id == team_id)
        return query.first()

    def get_multi(self, db: Session, team_id: Optional[int] = None, skip: int = 0, limit: int = 100, is_active: Optional[bool] = None) -> Tuple[List[ApprovalFlow], int]:
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
        from app.models.approval import ApprovalNode
        
        update_data = obj_in.model_dump(exclude_unset=True, exclude={'nodes'})
        
        for field, value in update_data.items():
            setattr(db_obj, field, value)
        
        nodes_data = obj_in.model_dump(exclude_unset=True).get('nodes')
        if nodes_data is not None:
            existing_nodes = {node.id: node for node in db_obj.nodes}
            
            for node_data in nodes_data:
                node_id = node_data.get('id')
                node_fields = {k: v for k, v in node_data.items() if k != 'id' and v is not None}
                
                if node_id and node_id in existing_nodes:
                    for field, value in node_fields.items():
                        setattr(existing_nodes[node_id], field, value)
                else:
                    new_node = ApprovalNode(flow_id=db_obj.id, **node_fields)
                    db.add(new_node)
            
            node_ids_to_keep = {n.get('id') for n in nodes_data if n.get('id')}
            for existing_node in db_obj.nodes:
                if existing_node.id not in node_ids_to_keep:
                    db.delete(existing_node)
        
        db.commit()
        db.refresh(db_obj)
        return db_obj
    
    def delete(self, db: Session, flow_id: int) -> bool:
        flow = self.get_by_id(db, flow_id)
        if not flow:
            return False
        
        db.delete(flow)
        db.commit()
        return True
    
    def match_flow(self, db: Session, contract: Contract, team_id: Optional[int] = None) -> Tuple[Optional[ApprovalFlow], Optional[str]]:
        """
        匹配审批流程（合同专用 thin wrapper，A5 解耦后保留以兼容现有调用方）

        语义与改造前逐字一致：直接委托 match_flow_generic('CONTRACT', team_id,
        contract.total_amount, contract.license_type)。E1 合同回归契约由此保证。

        Args:
            db: 数据库会话
            contract: 合同对象
            team_id: 团队ID（可选）

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
        team_id: Optional[int],
        amount,
        license_type: Optional[str],
    ) -> Tuple[Optional[ApprovalFlow], Optional[str]]:
        """
        通用审批流程匹配（A5：支持 CONTRACT/PAYMENT/INVOICE）

        E1 合同回归契约（P0）：business_type='CONTRACT' 的匹配结果必须与改造前
        match_flow(contract) 逐字一致——仅多 `ApprovalFlow.business_type == 'CONTRACT'`
        一个过滤条件。team_id 隔离、金额范围比较、license_type 匹配、
        calculate_flow_precision_score 评分、(-score, created_time) 排序逻辑全部沿用原代码。

        决策1 语义（未匹配分支）：
        - CONTRACT：沿用合同"未匹配=报错阻断"语义——金额为空时返回
          "合同金额为空，无法匹配审批流程，请补充金额或让管理员创建默认流程"，
          正常未匹配返回 "未找到匹配的审批流程，请联系管理员配置"（调用方报 400）。
        - PAYMENT/INVOICE：未匹配返回 (None, None)（非报错，调用方判定 None=免审批直通）。

        Args:
            db: 数据库会话
            business_type: 业务单据类型（CONTRACT/PAYMENT/INVOICE）
            team_id: 团队ID（可选，用于团队隔离）
            amount: 单据金额（合同 total_amount / 回款 actual_amount / 发票 invoice_amount）
            license_type: 授权类型（仅合同有值，回款/发票传 None）

        Returns:
            Tuple[Optional[ApprovalFlow], Optional[str]]: (匹配的审批流程, 错误信息)
        """
        query = db.query(ApprovalFlow).filter(
            ApprovalFlow.is_active == 1,
            ApprovalFlow.business_type == business_type,
        )

        if team_id is not None:
            query = query.filter(ApprovalFlow.team_id == team_id)

        # 检查金额是否为 0 或 null
        total_amount = float(amount) if amount else 0
        is_amount_empty = total_amount == 0

        # 查询所有启用的流程
        flows = query.all()

        # 未匹配时按 business_type 分支决定"报错"还是"直通"
        def _no_match() -> Tuple[Optional[ApprovalFlow], Optional[str]]:
            if business_type == BusinessType.CONTRACT:
                # 沿用合同原 match_flow 的两条错误信息（E1 逐字一致）
                if is_amount_empty:
                    return None, "合同金额为空，无法匹配审批流程，请补充金额或让管理员创建默认流程"
                return None, "未找到匹配的审批流程，请联系管理员配置"
            # PAYMENT/INVOICE：未配置流=免审批直通（决策1）
            return None, None

        # 金额为空时，优先匹配无金额限制的流程
        if is_amount_empty:
            no_amount_flows = [f for f in flows if f.min_amount is None and f.max_amount is None]
            # 收集匹配的无金额限制流程
            matched_no_amount: List[Tuple[ApprovalFlow, int]] = []
            for flow in no_amount_flows:
                # 检查授权类型
                if flow.license_type and license_type != flow.license_type:
                    continue
                # 计算精确度评分（主要用于多流程匹配时的选择）
                score = calculate_flow_precision_score(flow, total_amount, license_type)
                matched_no_amount.append((flow, score))

            if matched_no_amount:
                # 如果只有一个匹配的流程，直接返回
                if len(matched_no_amount) == 1:
                    flow, score = matched_no_amount[0]
                    logger.info(f"金额为空，匹配无金额限制流程: {flow.flow_name} (精确度评分: {score}分)")
                    return flow, None

                # 多个流程匹配时，按精确度评分排序
                matched_no_amount.sort(key=lambda x: (-x[1], x[0].created_time))
                selected_flow, selected_score = matched_no_amount[0]
                flow_names = [f"{f.flow_name}({s}分)" for f, s in matched_no_amount]
                logger.info(
                    f"金额为空，多流程匹配，已选择流程 {selected_flow.flow_name} "
                    f"(精确度评分: {selected_score}分)，候选流程: {', '.join(flow_names)}"
                )
                return selected_flow, None

            # 无匹配流程，按 business_type 分支返回
            return _no_match()

        # 正常金额匹配逻辑
        # 收集所有匹配的流程
        matched_flows: List[Tuple[ApprovalFlow, int]] = []

        for flow in flows:
            # 检查金额范围匹配
            if flow.min_amount and total_amount < float(flow.min_amount):
                continue
            if flow.max_amount and total_amount > float(flow.max_amount):
                continue

            # 检查授权类型匹配
            if flow.license_type and license_type != flow.license_type:
                continue

            # 流程匹配成功，计算精确度评分
            score = calculate_flow_precision_score(flow, total_amount, license_type)
            matched_flows.append((flow, score))

        # 如果没有匹配的流程，按 business_type 分支返回
        if not matched_flows:
            return _no_match()

        # 如果只有一个匹配的流程，直接返回
        if len(matched_flows) == 1:
            flow, score = matched_flows[0]
            logger.info(f"审批流程匹配成功: {flow.flow_name} (精确度评分: {score}分)")
            return flow, None

        # 多个流程匹配时，按精确度评分排序
        # 评分高的优先，评分相同时按创建时间排序（最早创建的优先）
        matched_flows.sort(key=lambda x: (-x[1], x[0].created_time))

        # 选择评分最高的流程
        selected_flow, selected_score = matched_flows[0]

        # 记录多流程匹配日志
        flow_names = [f"{f.flow_name}({s}分)" for f, s in matched_flows]
        logger.info(
            f"多流程匹配，已选择流程 {selected_flow.flow_name} "
            f"(精确度评分: {selected_score}分)，候选流程: {', '.join(flow_names)}"
        )

        return selected_flow, None

    def check_node_has_approvers(self, db: Session, node_id: int, team_id: int) -> bool:
        """
        检查审批节点是否有审批人

        Args:
            db: 数据库会话
            node_id: 审批节点ID
            team_id: 团队ID

        Returns:
            bool: 是否有审批人
        """
        from app.crud.role import role_crud

        # 获取审批节点
        node = db.query(ApprovalNode).filter(
            ApprovalNode.id == node_id,
            ApprovalNode.team_id == team_id
        ).first()

        if not node:
            return False

        # 获取审批角色
        if not node.approve_role:
            return False

        # 获取角色的成员列表
        role = role_crud.get_by_code(db, node.approve_role)
        if not role:
            return False

        users = role_crud.get_role_users(db, role.id, team_id)
        return len(users) > 0

    def check_flow_has_all_approvers(self, db: Session, flow_id: int, team_id: int) -> Dict[str, Any]:
        """
        检查审批流程所有节点是否有审批人

        Args:
            db: 数据库会话
            flow_id: 审批流程ID
            team_id: 团队ID

        Returns:
            Dict: 包含各节点的审批人状态
                {
                    "all_have_approvers": bool,  # 是否所有节点都有审批人
                    "nodes": [  # 各节点状态列表
                        {
                            "node_id": int,
                            "node_name": str,
                            "approve_role": str,
                            "has_approvers": bool,
                            "approver_count": int
                        }
                    ],
                    "missing_nodes": [  # 无审批人的节点列表
                        {
                            "node_id": int,
                            "node_name": str,
                            "approve_role": str
                        }
                    ]
                }
        """
        from app.crud.role import role_crud

        # 获取审批流程的所有节点
        nodes = db.query(ApprovalNode).filter(
            ApprovalNode.flow_id == flow_id,
            ApprovalNode.team_id == team_id
        ).order_by(ApprovalNode.node_order).all()

        if not nodes:
            return {
                "all_have_approvers": False,
                "nodes": [],
                "missing_nodes": []
            }

        result = {
            "all_have_approvers": True,
            "nodes": [],
            "missing_nodes": []
        }

        for node in nodes:
            approver_count = 0
            has_approvers = False

            if node.approve_role:
                role = role_crud.get_by_code(db, node.approve_role)
                if role:
                    users = role_crud.get_role_users(db, role.id, team_id)
                    approver_count = len(users)
                    has_approvers = approver_count > 0

            node_status = {
                "node_id": node.id,
                "node_name": node.node_name,
                "approve_role": node.approve_role or "",
                "has_approvers": has_approvers,
                "approver_count": approver_count
            }
            result["nodes"].append(node_status)

            if not has_approvers:
                result["all_have_approvers"] = False
                result["missing_nodes"].append({
                    "node_id": node.id,
                    "node_name": node.node_name,
                    "approve_role": node.approve_role or ""
                })

        return result


class ApprovalCRUD:
    def get_by_id(self, db: Session, approval_id: int, team_id: Optional[int] = None) -> Optional[Approval]:
        query = db.query(Approval).filter(Approval.id == approval_id)
        if team_id is not None:
            query = query.filter(Approval.team_id == team_id)
        return query.first()

    def get_by_entity(self, db: Session, business_type: str, business_id: int, team_id: Optional[int] = None) -> Optional[Approval]:
        """
        通用：按业务单据类型+ID+团队查询最新一条审批实例（A5）

        Args:
            db: 数据库会话
            business_type: 业务单据类型（CONTRACT/PAYMENT/INVOICE）
            business_id: 业务单据ID
            team_id: 团队ID（可选，团队隔离）

        Returns:
            Optional[Approval]: 最新一条审批实例，无则 None
        """
        query = db.query(Approval).filter(
            Approval.business_type == business_type,
            Approval.business_id == business_id,
        )
        if team_id is not None:
            query = query.filter(Approval.team_id == team_id)
        return query.order_by(Approval.created_time.desc()).first()

    def get_by_contract_id(self, db: Session, contract_id: int, team_id: Optional[int] = None) -> Optional[Approval]:
        """
        根据合同ID查询审批实例（合同专用 thin wrapper，A5 解耦后保留以兼容现有调用方）

        注意：即使合同已删除（deleted_at != null），审批记录仍然可以查询
        外键 contract_id 在合同删除后会置为 NULL，但审批记录保留。
        本 wrapper 委托 get_by_entity(CONTRACT, contract_id, team_id)——
        A3 迁移 012 已把旧审批行的 business_id 回填为 contract_id，
        故 business_id == contract_id 的查询等价于原 contract_id 过滤。

        Args:
            db: 数据库会话
            contract_id: 合同ID
            team_id: 团队ID（可选）

        Returns:
            Optional[Approval]: 审批实例
        """
        return self.get_by_entity(db, BusinessType.CONTRACT, contract_id, team_id)

    def get_by_approval_id_include_deleted_contract(
        self,
        db: Session,
        approval_id: int,
        team_id: Optional[int] = None
    ) -> Optional[Approval]:
        """
        根据审批ID查询审批实例（包含已删除合同的审批）

        用途：管理员查询已删除合同的审批历史

        Args:
            db: 数据库会话
            approval_id: 审批实例ID
            team_id: 团队ID（可选）

        Returns:
            Optional[Approval]: 审批实例（合同可能已删除）
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
        status: Optional[str] = None
    ) -> Tuple[List[Approval], int]:
        """
        查询已删除合同的审批记录列表（管理员查询）

        用途：管理员查询已删除合同的审批历史

        Args:
            db: 数据库会话
            team_id: 团队ID（团队隔离）
            skip: 跳过记录数
            limit: 返回记录数上限
            status: 审批状态筛选（可选）

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
    
    def get_multi(self, db: Session, skip: int = 0, limit: int = 100, status: Optional[str] = None) -> Tuple[List[Approval], int]:
        query = db.query(Approval)
        
        if status:
            query = query.filter(Approval.status == status)
        
        total = query.count()
        approvals = query.order_by(Approval.created_time.desc()).offset(skip).limit(limit).all()
        
        return approvals, total
    
    def create_approval(self, db: Session, contract: Contract, flow: ApprovalFlow, submitter_id: str, submitter_name: str) -> Approval:
        """
        创建合同审批实例（合同专用 thin wrapper，A5 解耦后保留以兼容现有调用方）

        委托 create_approval_generic(CONTRACT, contract.id, contract.team_id, ...)，
        合同回归语义：CONTRACT 分支额外写 contract_id=business_id，兼容旧外键字段。
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
        submitter_name: str,
    ) -> Approval:
        """
        通用审批实例创建（A5：支持 CONTRACT/PAYMENT/INVOICE）

        - 通过适配器 get_entity 取业务单据；不存在则 raise ValueError（防幻觉单据ID）
        - 写 Approval.business_type/business_id；CONTRACT 额外写 contract_id=business_id 兼容旧字段
        - adapter.on_submit 切单据状态（适配器自带 E4 None 守卫，此处 entity 已校验非 None）
        - 创建首个 ApprovalRecord(SUBMIT)

        Args:
            db: 数据库会话
            business_type: 业务单据类型
            business_id: 业务单据ID
            team_id: 团队ID
            flow: 匹配到的审批流程
            submitter_id: 提交人飞书用户ID
            submitter_name: 提交人姓名

        Returns:
            Approval: 创建后的审批实例
        """
        from app.models.approval import ApprovalNode, ApprovalRecord
        from app.services.approval_adapter import get_adapter

        adapter = get_adapter(business_type)
        entity = adapter.get_entity(db, business_id, team_id)
        if entity is None:
            raise ValueError("业务单据不存在")

        first_node = db.query(ApprovalNode).filter(
            ApprovalNode.flow_id == flow.id,
            ApprovalNode.node_order == 1
        ).first()

        db_approval = Approval(
            business_type=business_type,
            business_id=business_id,
            contract_id=business_id if business_type == BusinessType.CONTRACT else None,
            flow_id=flow.id,
            team_id=team_id,
            current_node_id=first_node.id if first_node else None,
            status=ApprovalStatus.PENDING,
            submitter_id=submitter_id,
            submitter_name=submitter_name,
        )

        db.add(db_approval)
        db.flush()

        db.add(ApprovalRecord(
            approval_id=db_approval.id,
            node_id=first_node.id if first_node else None,
            approver_id=submitter_id,
            approver_name=submitter_name,
            action=ApprovalAction.SUBMIT,
            comment=None,
            team_id=team_id,
        ))
        adapter.on_submit(db, entity)

        db.commit()
        db.refresh(db_approval)
        return db_approval
    
    def approve(self, db: Session, approval: Approval, action_request: ApprovalActionRequest, approver_id: str, approver_name: str) -> Approval:
        from app.models.approval import ApprovalNode
        from app.services.approval_adapter import get_adapter

        # 乐观锁检查：防止并发审批冲突
        if action_request.updated_time is not None:
            if approval.updated_time != action_request.updated_time:
                raise ValueError("审批已被其他用户处理")

        if approval.status != ApprovalStatus.PENDING:
            raise ValueError(f"当前审批状态为 {approval.status}，无法进行审批操作")

        current_node = approval.current_node
        if not current_node:
            raise ValueError("当前审批节点不存在")

        record = ApprovalRecord(
            approval_id=approval.id,
            node_id=current_node.id,
            approver_id=approver_id,
            approver_name=approver_name,
            action=action_request.action.value,
            comment=action_request.comment,
            team_id=approval.team_id
        )
        db.add(record)

        # A5：经适配器回写单据状态；E4 守卫——单据已删则仅终结审批，不回写
        adapter = get_adapter(approval.business_type)
        entity = adapter.get_entity(db, approval.business_id, approval.team_id)

        if action_request.action.value == ApprovalAction.APPROVE:
            next_node = db.query(ApprovalNode).filter(
                ApprovalNode.flow_id == approval.flow_id,
                ApprovalNode.node_order == current_node.node_order + 1
            ).first()

            if next_node:
                approval.current_node_id = next_node.id
            else:
                approval.status = ApprovalStatus.APPROVED
                if entity is not None:
                    adapter.on_approved(db, entity)

        elif action_request.action.value == ApprovalAction.REJECT:
            approval.status = ApprovalStatus.REJECTED
            if entity is not None:
                adapter.on_rejected(db, entity)

        db.commit()
        db.refresh(approval)
        return approval

    def cancel(self, db: Session, approval: Approval, user_id: str) -> Approval:
        from app.services.approval_adapter import get_adapter

        if approval.status != ApprovalStatus.PENDING:
            raise ValueError("只能撤回审批中的审批流程")

        if approval.submitter_id != user_id:
            raise ValueError("只有提交人可以撤回审批")

        approval.status = ApprovalStatus.CANCELLED

        # A5：经适配器回写单据状态；E4 守卫——单据已删则仅终结审批，不回写
        adapter = get_adapter(approval.business_type)
        entity = adapter.get_entity(db, approval.business_id, approval.team_id)
        if entity is not None:
            adapter.on_cancelled(db, entity)

        db.commit()
        db.refresh(approval)
        return approval
    
    def get_records(self, db: Session, approval_id: int) -> List[ApprovalRecord]:
        return db.query(ApprovalRecord).filter(
            ApprovalRecord.approval_id == approval_id
        ).order_by(ApprovalRecord.created_time.asc()).all()

    def get_overdue_approvals(
        self,
        db: Session,
        team_id: int,
        min_hours: int = 48,
        skip: int = 0,
        limit: int = 100
    ) -> Tuple[List[Dict[str, Any]], int]:
        """
        查询超时的审批实例列表

        Args:
            db: 数据库会话
            team_id: 团队ID（团队隔离）
            min_hours: 最小超时小时数，默认48小时
            skip: 跳过记录数
            limit: 返回记录数上限

        Returns:
            Tuple[List[Dict], int]: 超时审批列表和总数
        """
        from datetime import datetime, timedelta

        # 计算超时阈值时间点
        threshold_time = datetime.now() - timedelta(hours=min_hours)

        # 查询超时的审批实例
        query = db.query(
            Approval.id.label('approval_id'),
            Approval.contract_id,
            Approval.status,
            Approval.created_time.label('submit_time'),
            Approval.submitter_name,
            Approval.current_node_id,
            ApprovalNode.node_name.label('current_node_name'),
            ApprovalNode.approve_role,
            Contract.contract_name,
            Contract.contract_number
        ).join(
            Contract, Approval.contract_id == Contract.id
        ).outerjoin(
            ApprovalNode, Approval.current_node_id == ApprovalNode.id
        ).filter(
            Approval.team_id == team_id,
            Approval.status == ApprovalStatus.PENDING,
            Approval.created_time <= threshold_time
        ).order_by(
            Approval.created_time.asc()  # 超时时间最长的排在前面
        )

        total = query.count()
        results = query.offset(skip).limit(limit).all()

        # 转换为字典列表并计算超时小时数
        overdue_list = []
        for row in results:
            overdue_hours = int((datetime.now() - row.submit_time).total_seconds() / 3600)

            # 获取当前审批人姓名
            current_approver_name = None
            if row.approve_role:
                approvers = self._get_approvers_by_role(db, row.approve_role, team_id)
                if approvers:
                    current_approver_name = ", ".join([a.name for a in approvers if a.name])

            overdue_list.append({
                'approval_id': row.approval_id,
                'contract_id': row.contract_id,
                'contract_name': row.contract_name,
                'contract_number': row.contract_number,
                'current_node_name': row.current_node_name,
                'current_approver_name': current_approver_name,
                'overdue_hours': overdue_hours,
                'submitter_name': row.submitter_name,
                'submit_time': row.submit_time,
                'status': row.status
            })

        return overdue_list, total

    def _get_approvers_by_role(self, db: Session, role_code: str, team_id: int) -> List[Any]:
        """获取指定角色的审批人列表"""
        from app.models.role import Role, UserRole
        from app.models.user import User

        role = db.query(Role).filter(Role.code == role_code).first()
        if not role:
            return []

        # 查询拥有该角色的用户
        users = db.query(User).join(
            UserRole, User.id == UserRole.user_id
        ).filter(
            UserRole.role_id == role.id
        ).all()

        return users

    # ========================================================================
    # Task C3：通用审批列表（GET /v1/approvals）
    # ========================================================================
    # E2 越权过滤（P0）——按 tab 切换查询主体：
    #   pending  : status=PENDING AND team_id AND current_node.approve_role IN user_roles
    #   processed: EXISTS(records WHERE approver_id=user_id AND action!=SUBMIT) AND team_id
    #   submitted: submitter_id=user_id AND team_id
    # E9 N+1 规避：审批行先取主体，再按 business_type 分组批量预取
    #   Contract/PaymentRecord/InvoiceApplication 三表，内存 join 出
    #   application_number / entity_name / entity_amount 三摘要字段。
    # overdue_hours：Python 计算（now - created_time）/3600，DB 无关，与
    #   get_overdue_approvals 同套路；非 PENDING 行也回传（前端按需展示）。
    # pending_count：当前用户「待我审批」总数，任意 tab 都附给前端徽章。
    # ========================================================================

    def list_approvals(
        self,
        db: Session,
        team_id: int,
        user_id: int,
        user_roles: List[str],
        tab: str = "pending",
        business_type: Optional[str] = None,
        page: int = 1,
        page_size: int = 20,
    ) -> Tuple[List[Dict[str, Any]], int, int]:
        """通用审批列表查询（E2 越权过滤 + E9 摘要内存 join）。

        Args:
            db: 数据库会话
            team_id: 团队ID（团队隔离）
            user_id: 当前用户ID（int，用于 submitted/processed 过滤）
            user_roles: 当前用户在 team_id 下的角色 code 列表（用于 pending 过滤）
            tab: pending / processed / submitted
            business_type: 可选业务类型过滤（CONTRACT / PAYMENT / INVOICE）
            page: 页码（1-based）
            page_size: 每页条数

        Returns:
            Tuple[List[Dict], int, int]: (items, total, pending_count)
                items 每行对齐前端 ApprovalListItemSchema；
                total 为当前 tab+business_type 过滤后的总数；
                pending_count 为当前用户待我审批总数（任意 tab 都附）。
        """
        from datetime import datetime
        from app.models.approval import ApprovalNode, ApprovalRecord, ApprovalAction

        user_id_str = str(user_id)
        skip = max(0, (page - 1) * page_size)

        # ---- 主体查询：按 tab 构造过滤 ----
        query = db.query(Approval).filter(Approval.team_id == team_id)

        if business_type:
            query = query.filter(Approval.business_type == business_type)

        if tab == "pending":
            # JOIN current_node 取 approve_role 过滤
            query = (
                query.join(ApprovalNode, Approval.current_node_id == ApprovalNode.id)
                .filter(Approval.status == ApprovalStatus.PENDING)
            )
            if user_roles:
                query = query.filter(ApprovalNode.approve_role.in_(user_roles))
            else:
                # 无任何角色 → 不返任何 pending 行（避免 IN () SQL 报错）
                query = query.filter(ApprovalNode.approve_role.is_(None))
        elif tab == "submitted":
            query = query.filter(Approval.submitter_id == user_id_str)
        elif tab == "processed":
            # 我已处理：作为审批人留下过 APPROVE/REJECT 记录（排除 SUBMIT，否则
            # 提交人会在 processed 里看到自己的提交）。用 EXISTS 子查询去重，
            # 避免一条审批多条记录导致行重复。
            processed_sub = (
                db.query(ApprovalRecord.approval_id)
                .filter(
                    ApprovalRecord.approver_id == user_id_str,
                    ApprovalRecord.action != ApprovalAction.SUBMIT,
                )
                .distinct()
            )
            query = query.filter(Approval.id.in_(processed_sub))
        else:
            raise ValueError(f"非法 tab: {tab}，仅支持 pending / processed / submitted")

        total = query.count()
        rows = (
            query.order_by(Approval.created_time.desc())
            .offset(skip)
            .limit(page_size)
            .all()
        )

        # ---- E9：按 business_type 批量预取实体摘要，内存 join 避免 N+1 ----
        summaries = self._batch_entity_summaries(db, rows, team_id)

        # ---- 组装列表项 + overdue_hours Python 计算 ----
        now = datetime.now()
        items: List[Dict[str, Any]] = []
        for ap in rows:
            sum_key = (ap.business_type, ap.business_id) if ap.business_id else None
            summary = summaries.get(sum_key) if sum_key else None
            overdue_hours: Optional[int] = None
            if ap.status == ApprovalStatus.PENDING and ap.created_time is not None:
                overdue_hours = int((now - ap.created_time).total_seconds() // 3600)
            items.append({
                "id": ap.id,
                "business_type": ap.business_type,
                "business_id": ap.business_id if ap.business_id is not None else 0,
                "application_number": summary["application_number"] if summary else f"{ap.business_type}-{ap.business_id}",
                "entity_name": summary["entity_name"] if summary else None,
                "entity_amount": summary["entity_amount"] if summary else None,
                "submitter_id": ap.submitter_id,
                "submitter_name": ap.submitter_name,
                "status": ap.status,
                "created_time": ap.created_time.isoformat() if ap.created_time else "",
                "updated_time": ap.updated_time.isoformat() if ap.updated_time else "",
                "overdue_hours": overdue_hours,
            })

        # ---- pending_count：当前用户待我审批总数，任意 tab 都附 ----
        pending_count = self._count_pending_for_user(db, team_id, user_roles)

        return items, total, pending_count

    def _batch_entity_summaries(
        self,
        db: Session,
        approvals: List[Approval],
        team_id: int,
    ) -> Dict[Tuple[str, int], Dict[str, Any]]:
        """按 business_type 分组批量预取实体摘要（application_number/entity_name/entity_amount）。

        - CONTRACT: contract_number / contract_name / total_amount
        - INVOICE: application_number / invoice_title_text / invoice_amount
        - PAYMENT: 合成 PAY-{id} / None / actual_amount（无单号字段，entity_name 暂空）

        Returns:
            Dict[(business_type, business_id), {application_number, entity_name, entity_amount}]
        """
        from app.models.contract import Contract
        from app.models.invoice import InvoiceApplication
        from app.models.payment import PaymentRecord

        ids_by_type: Dict[str, List[int]] = {"CONTRACT": [], "INVOICE": [], "PAYMENT": []}
        for ap in approvals:
            if ap.business_id and ap.business_type in ids_by_type:
                ids_by_type[ap.business_type].append(ap.business_id)

        summaries: Dict[Tuple[str, int], Dict[str, Any]] = {}

        # CONTRACT
        if ids_by_type["CONTRACT"]:
            for c in db.query(Contract).filter(
                Contract.id.in_(ids_by_type["CONTRACT"]), Contract.team_id == team_id
            ).all():
                summaries[(BusinessType.CONTRACT, c.id)] = {
                    "application_number": c.contract_number or f"CONTRACT-{c.id}",
                    "entity_name": c.contract_name,
                    "entity_amount": float(c.total_amount) if c.total_amount is not None else None,
                }

        # INVOICE
        if ids_by_type["INVOICE"]:
            for inv in db.query(InvoiceApplication).filter(
                InvoiceApplication.id.in_(ids_by_type["INVOICE"]),
                InvoiceApplication.team_id == team_id,
            ).all():
                summaries[(BusinessType.INVOICE, inv.id)] = {
                    "application_number": inv.application_number or f"INVOICE-{inv.id}",
                    "entity_name": inv.invoice_title_text,
                    "entity_amount": float(inv.invoice_amount) if inv.invoice_amount is not None else None,
                }

        # PAYMENT（无单号字段，合成 PAY-{id}；entity_name 暂 None 避免多层 join plan→contract）
        if ids_by_type["PAYMENT"]:
            for pr in db.query(PaymentRecord).filter(
                PaymentRecord.id.in_(ids_by_type["PAYMENT"]),
                PaymentRecord.team_id == team_id,
            ).all():
                summaries[(BusinessType.PAYMENT, pr.id)] = {
                    "application_number": f"PAY-{pr.id}",
                    "entity_name": None,
                    "entity_amount": float(pr.actual_amount) if pr.actual_amount is not None else None,
                }

        return summaries

    def _count_pending_for_user(
        self,
        db: Session,
        team_id: int,
        user_roles: List[str],
    ) -> int:
        """当前用户「待我审批」总数（pending tab 的 total，任意 tab 响应都附给前端徽章）。"""
        from app.models.approval import ApprovalNode

        query = (
            db.query(Approval)
            .join(ApprovalNode, Approval.current_node_id == ApprovalNode.id)
            .filter(
                Approval.team_id == team_id,
                Approval.status == ApprovalStatus.PENDING,
            )
        )
        if user_roles:
            query = query.filter(ApprovalNode.approve_role.in_(user_roles))
        else:
            query = query.filter(ApprovalNode.approve_role.is_(None))
        return query.count()


approval_flow_crud = ApprovalFlowCRUD()
approval_crud = ApprovalCRUD()
