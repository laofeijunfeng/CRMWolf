from sqlalchemy.orm import Session
from sqlalchemy import and_, or_
from typing import Optional, List, Tuple
from decimal import Decimal

from app.models.approval import Approval, ApprovalRecord, ApprovalFlow, ApprovalNode, ApprovalStatus, ApprovalAction
from app.models.contract import Contract, ContractStatus
from app.schemas.approval import (
    ApprovalFlowCreate, ApprovalFlowUpdate,
    ApprovalSubmitRequest, ApprovalActionRequest
)


class ApprovalFlowCRUD:
    def get_by_id(self, db: Session, flow_id: int) -> Optional[ApprovalFlow]:
        return db.query(ApprovalFlow).filter(ApprovalFlow.id == flow_id).first()

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
    
    def match_flow(self, db: Session, contract: Contract, team_id: Optional[int] = None) -> Optional[ApprovalFlow]:
        query = db.query(ApprovalFlow).filter(ApprovalFlow.is_active == 1)

        if team_id is not None:
            query = query.filter(ApprovalFlow.team_id == team_id)

        total_amount = float(contract.total_amount) if contract.total_amount else 0

        flows = query.all()
        for flow in flows:
            if flow.min_amount and total_amount < float(flow.min_amount):
                continue
            if flow.max_amount and total_amount > float(flow.max_amount):
                continue
            if flow.license_type and contract.license_type != flow.license_type:
                continue
            
            return flow
        
        return None


class ApprovalCRUD:
    def get_by_id(self, db: Session, approval_id: int) -> Optional[Approval]:
        return db.query(Approval).filter(Approval.id == approval_id).first()
    
    def get_by_contract_id(self, db: Session, contract_id: int) -> Optional[Approval]:
        return db.query(Approval).filter(
            Approval.contract_id == contract_id
        ).order_by(Approval.created_time.desc()).first()
    
    def get_multi(self, db: Session, skip: int = 0, limit: int = 100, status: Optional[str] = None) -> Tuple[List[Approval], int]:
        query = db.query(Approval)
        
        if status:
            query = query.filter(Approval.status == status)
        
        total = query.count()
        approvals = query.order_by(Approval.created_time.desc()).offset(skip).limit(limit).all()
        
        return approvals, total
    
    def create_approval(self, db: Session, contract: Contract, flow: ApprovalFlow, submitter_id: str, submitter_name: str) -> Approval:
        from app.models.approval import ApprovalNode

        first_node = db.query(ApprovalNode).filter(
            ApprovalNode.flow_id == flow.id,
            ApprovalNode.node_order == 1
        ).first()

        db_approval = Approval(
            contract_id=contract.id,
            flow_id=flow.id,
            team_id=contract.team_id,
            current_node_id=first_node.id if first_node else None,
            status=ApprovalStatus.PENDING,
            submitter_id=submitter_id,
            submitter_name=submitter_name
        )
        
        db.add(db_approval)
        db.flush()
        
        from app.models.approval import ApprovalRecord
        record = ApprovalRecord(
            approval_id=db_approval.id,
            node_id=first_node.id if first_node else None,
            approver_id=submitter_id,
            approver_name=submitter_name,
            action=ApprovalAction.SUBMIT,
            comment=None
        )
        db.add(record)
        
        contract.status = ContractStatus.PENDING_REVIEW
        
        db.commit()
        db.refresh(db_approval)
        return db_approval
    
    def approve(self, db: Session, approval: Approval, action_request: ApprovalActionRequest, approver_id: str, approver_name: str) -> Approval:
        from app.models.approval import ApprovalNode
        
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
            comment=action_request.comment
        )
        db.add(record)
        
        if action_request.action.value == ApprovalAction.APPROVE:
            next_node = db.query(ApprovalNode).filter(
                ApprovalNode.flow_id == approval.flow_id,
                ApprovalNode.node_order == current_node.node_order + 1
            ).first()
            
            if next_node:
                approval.current_node_id = next_node.id
            else:
                approval.status = ApprovalStatus.APPROVED
                from app.models.contract import Contract
                contract = db.query(Contract).filter(Contract.id == approval.contract_id).first()
                if contract:
                    contract.status = ContractStatus.SIGNED
        
        elif action_request.action.value == ApprovalAction.REJECT:
            approval.status = ApprovalStatus.REJECTED
            from app.models.contract import Contract
            contract = db.query(Contract).filter(Contract.id == approval.contract_id).first()
            if contract:
                contract.status = ContractStatus.DRAFT
        
        db.commit()
        db.refresh(approval)
        return approval
    
    def cancel(self, db: Session, approval: Approval, user_id: str) -> Approval:
        if approval.status != ApprovalStatus.PENDING:
            raise ValueError("只能撤回审批中的审批流程")
        
        if approval.submitter_id != user_id:
            raise ValueError("只有提交人可以撤回审批")
        
        approval.status = ApprovalStatus.CANCELLED
        
        from app.models.contract import Contract
        contract = db.query(Contract).filter(Contract.id == approval.contract_id).first()
        if contract:
            contract.status = ContractStatus.DRAFT
        
        db.commit()
        db.refresh(approval)
        return approval
    
    def get_records(self, db: Session, approval_id: int) -> List[ApprovalRecord]:
        return db.query(ApprovalRecord).filter(
            ApprovalRecord.approval_id == approval_id
        ).order_by(ApprovalRecord.created_time.asc()).all()


approval_flow_crud = ApprovalFlowCRUD()
approval_crud = ApprovalCRUD()
