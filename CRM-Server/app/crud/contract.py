from sqlalchemy.orm import Session
from sqlalchemy import and_
from typing import Optional, List, Tuple
from decimal import Decimal
from datetime import datetime
import logging

from app.models.contract import Contract, ContractStatus
from app.schemas.contract import ContractCreate, ContractUpdate, ContractStatusUpdate
from app.services.contract import ContractNumberGenerator, ContractPricingService

logger = logging.getLogger(__name__)


class ApprovalService:
    """审批服务"""
    
    @staticmethod
    def submit_for_approval(db: Session, contract_id: int):
        """
        创建合同后自动提交审批

        业务规则：
        - 创建合同后自动提交到审批流程
        - 只有草稿状态的合同可以提交
        - 系统自动匹配对应的审批流程
        - 创建审批实例并流转到第一个节点
        - 向首个节点的审批人发送通知（通过 notification_service）

        注意：
        - 保留撤回功能，用户可以手动撤回审批
        - 撤回后合同回到草稿状态，可以修改后重新提交
        """
        from app.models.contract import Contract
        from app.models.approval import ApprovalFlow, Approval, ApprovalStatus, ApprovalAction, BusinessType
        from app.crud.approval import approval_flow_crud, approval_crud
        from app.services.notification import NotificationService

        contract = db.query(Contract).filter(Contract.id == contract_id).first()
        if not contract:
            return

        if contract.status != ContractStatus.DRAFT:
            return

        existing_approval = approval_crud.get_by_contract_id(db, contract_id)
        if existing_approval and existing_approval.status == ApprovalStatus.PENDING:
            return

        # A5 修复：match_flow(contract) 返回 tuple (flow, error_msg)，需要正确解构
        flow, error_msg = approval_flow_crud.match_flow(db, contract)
        if not flow:
            logger.warning(f"合同自动提交审批失败：{error_msg or '未匹配审批流程'}")
            return

        try:
            from app.crud.user import user_crud

            submitter_id = contract.creator_id
            submitter = user_crud.get_by_id(db, int(submitter_id))
            submitter_name = submitter.name if submitter else "系统"

            approval = approval_crud.create_approval(
                db,
                contract,
                flow,
                submitter_id,
                submitter_name
            )

            # 注意：通知发送移至 API 层（异步上下文）
            # CRUD 层不再包含异步通知逻辑，避免 "no running event loop" 错误

            db.refresh(approval)
        except Exception:
            pass


class ContractCRUD:
    def get_by_id(self, db: Session, contract_id: int, team_id: Optional[int] = None) -> Optional[Contract]:
        query = db.query(Contract).filter(Contract.id == contract_id)
        if team_id is not None:
            query = query.filter(Contract.team_id == team_id)
        return query.first()

    def get_by_number(self, db: Session, contract_number: str, team_id: Optional[int] = None) -> Optional[Contract]:
        query = db.query(Contract).filter(Contract.contract_number == contract_number)
        if team_id is not None:
            query = query.filter(Contract.team_id == team_id)
        return query.first()

    def get_by_customer_id(
        self,
        db: Session,
        customer_id: int,
        team_id: Optional[int] = None,
        skip: int = 0,
        limit: int = 100,
        status: Optional[str] = None
    ) -> Tuple[List[Contract], int]:
        query = db.query(Contract).filter(Contract.customer_id == customer_id)
        if team_id is not None:
            query = query.filter(Contract.team_id == team_id)

        if status:
            query = query.filter(Contract.status == status)

        total = query.count()
        contracts = query.order_by(Contract.created_time.desc()).offset(skip).limit(limit).all()
        return contracts, total

    def get_by_opportunity_id(
        self,
        db: Session,
        opportunity_id: int,
        team_id: Optional[int] = None
    ) -> Optional[Contract]:
        query = db.query(Contract).filter(Contract.opportunity_id == opportunity_id)
        if team_id is not None:
            query = query.filter(Contract.team_id == team_id)
        return query.first()

    def get_multi(
        self,
        db: Session,
        team_id: int,
        skip: int = 0,
        limit: int = 100,
        customer_id: Optional[int] = None,
        status: Optional[str] = None,
        contract_number: Optional[str] = None,
        license_type: Optional[str] = None,
        keyword: Optional[str] = None,
        owner_id: Optional[str] = None,
        order_by: Optional[str] = None,
        order_dir: Optional[str] = None,
        include_deleted: bool = False
    ) -> Tuple[List[Contract], int]:
        """
        查询合同列表

        Args:
            db: 数据库会话
            team_id: 团队ID
            skip: 跳过记录数
            limit: 返回记录数上限
            customer_id: 客户ID筛选
            status: 合同状态筛选
            contract_number: 合同编号筛选
            license_type: 授权类型筛选
            keyword: 关键词筛选
            owner_id: 负责人ID筛选
            order_by: 排序字段
            order_dir: 排序方向
            include_deleted: 是否包含已删除的合同（默认不包含）

        Returns:
            Tuple[List[Contract], int]: 合同列表和总数
        """
        query = db.query(Contract).filter(Contract.team_id == team_id)

        # 默认不包含已删除的合同
        if not include_deleted:
            query = query.filter(Contract.deleted_at.is_(None))

        if customer_id:
            query = query.filter(Contract.customer_id == customer_id)

        if status:
            query = query.filter(Contract.status == status)

        if contract_number:
            query = query.filter(Contract.contract_number.like(f"%{contract_number}%"))

        if license_type:
            query = query.filter(Contract.license_type == license_type)

        if keyword:
            query = query.filter(Contract.contract_name.like(f"%{keyword}%"))

        if owner_id:
            # Contract 使用 creator_id 作为负责人字段
            query = query.filter(Contract.creator_id == owner_id)

        total = query.count()

        allowed_sort_fields = ['created_time', 'contract_name', 'total_amount', 'status', 'effective_date', 'expiry_date']
        if order_by and order_dir and order_by in allowed_sort_fields:
            order_column = getattr(Contract, order_by)
            if order_dir.lower() == 'desc':
                query = query.order_by(order_column.desc())
            else:
                query = query.order_by(order_column.asc())
        else:
            query = query.order_by(Contract.created_time.desc())

        contracts = query.offset(skip).limit(limit).all()

        return contracts, total

    def create(
        self,
        db: Session,
        obj_in: ContractCreate,
        creator_id: str,
        team_id: int
    ) -> Contract:
        from app.crud.user import user_crud
        from app.crud.customer import customer_crud
        from app.services.operation_log_service import operation_log_service
        
        contract_data = obj_in.model_dump()
        
        contract_number = ContractNumberGenerator.generate_contract_number(db)
        
        standard_unit_price = ContractPricingService.calculate_standard_unit_price(
            total_amount=contract_data['total_amount'],
            user_count=contract_data['user_count'],
            license_type=contract_data['license_type'],
            subscription_years=contract_data.get('subscription_years')
        )
        
        expiry_date = ContractPricingService.calculate_expiry_date(
            effective_date=contract_data.get('effective_date'),
            license_type=contract_data['license_type'],
            subscription_years=contract_data.get('subscription_years')
        )
        
        db_obj = Contract(
            contract_number=contract_number,
            standard_unit_price=standard_unit_price,
            expiry_date=expiry_date,
            status=ContractStatus.DRAFT,
            creator_id=creator_id,
            team_id=team_id,
            **contract_data
        )
        
        db.add(db_obj)
        db.commit()
        db.refresh(db_obj)

        operator = user_crud.get_by_id(db, int(creator_id))
        operator_name = operator.name if operator else None
        
        customer = customer_crud.get_by_id(db, db_obj.customer_id)
        
        operation_log_service.log(
            db=db,
            event_type="CONTRACT_CREATED",
            event_action="CREATE",
            resource_type="CUSTOMER",
            resource_id=db_obj.customer_id,
            secondary_resource_type="CONTRACT",
            secondary_resource_id=db_obj.id,
            operator_id=creator_id,
            operator_name=operator_name,
            content={
                "contractNumber": db_obj.contract_number,
                "contractName": db_obj.contract_name,
                "totalAmount": float(db_obj.total_amount),
                "customerId": db_obj.customer_id,
                "customerName": customer.account_name if customer else None
            }
        )
        
        ApprovalService.submit_for_approval(db, db_obj.id)
        
        return db_obj
    
    def create_from_opportunity(
        self,
        db: Session,
        opportunity_id: int,
        customer_id: int,
        signing_contact_id: int,
        contract_name: str,
        creator_id: str,
        team_id: int
    ) -> Contract:
        from app.models.opportunity import Opportunity

        opportunity = db.query(Opportunity).filter(Opportunity.id == opportunity_id).first()
        if not opportunity:
            raise ValueError("商机不存在")

        contract_number = ContractNumberGenerator.generate_contract_number(db)

        actual_amount = opportunity.actual_amount if opportunity.actual_amount else Decimal('0')
        standard_unit_price = ContractPricingService.calculate_standard_unit_price(
            total_amount=actual_amount,
            user_count=opportunity.user_count,
            license_type=opportunity.license_type,
            subscription_years=opportunity.subscription_years
        )

        db_obj = Contract(
            team_id=team_id,
            contract_number=contract_number,
            contract_name=contract_name,
            customer_id=customer_id,
            opportunity_id=opportunity_id,
            signing_contact_id=signing_contact_id,
            user_count=opportunity.user_count,
            total_amount=opportunity.actual_amount,
            license_type=opportunity.license_type,
            subscription_years=opportunity.subscription_years,
            standard_unit_price=standard_unit_price,
            status=ContractStatus.DRAFT,
            creator_id=creator_id
        )
        
        db.add(db_obj)
        db.commit()
        db.refresh(db_obj)
        
        ApprovalService.submit_for_approval(db, db_obj.id)
        
        return db_obj
    
    def update(
        self,
        db: Session,
        db_obj: Contract,
        obj_in: ContractUpdate
    ) -> Contract:
        update_data = obj_in.model_dump(exclude_unset=True)
        
        if 'total_amount' in update_data or 'user_count' in update_data or \
           'license_type' in update_data or 'subscription_years' in update_data:
            
            total_amount = update_data.get('total_amount', db_obj.total_amount)
            user_count = update_data.get('user_count', db_obj.user_count)
            license_type = update_data.get('license_type', db_obj.license_type)
            subscription_years = update_data.get('subscription_years', db_obj.subscription_years)
            
            standard_unit_price = ContractPricingService.calculate_standard_unit_price(
                total_amount=total_amount,
                user_count=user_count,
                license_type=license_type,
                subscription_years=subscription_years
            )
            update_data['standard_unit_price'] = standard_unit_price
            
            if 'effective_date' in update_data or 'license_type' in update_data or 'subscription_years' in update_data:
                effective_date = update_data.get('effective_date', db_obj.effective_date)
                expiry_date = ContractPricingService.calculate_expiry_date(
                    effective_date=effective_date,
                    license_type=license_type,
                    subscription_years=subscription_years
                )
                update_data['expiry_date'] = expiry_date
        
        for field, value in update_data.items():
            setattr(db_obj, field, value)
        
        db.commit()
        db.refresh(db_obj)
        return db_obj
    
    def update_status(
        self,
        db: Session,
        db_obj: Contract,
        obj_in: ContractStatusUpdate
    ) -> Contract:
        db_obj.status = obj_in.status
        db.commit()
        db.refresh(db_obj)
        return db_obj
    
    def delete(self, db: Session, contract_id: int) -> bool:
        """
        删除合同（软删除）

        业务规则：
        1. 只能删除草稿状态的合同
        2. 使用软删除（设置 deleted_at 时间戳）
        3. 正在审批的合同删除后自动终止审批流程
        4. 审批记录保留，不随合同删除

        Args:
            db: 数据库会话
            contract_id: 合同ID

        Returns:
            bool: 是否成功删除

        Raises:
            ValueError: 合同状态不允许删除
        """
        from app.models.approval import Approval, ApprovalStatus, ApprovalAction
        from app.crud.approval import approval_crud

        contract = self.get_by_id(db, contract_id)
        if not contract:
            return False

        if contract.deleted_at is not None:
            raise ValueError("合同已被删除")

        # 检查合同状态
        if contract.status not in [ContractStatus.DRAFT, ContractStatus.PENDING_REVIEW]:
            raise ValueError("只能删除草稿或审批中的合同")

        # 如果合同正在审批中，终止审批流程
        if contract.status == ContractStatus.PENDING_REVIEW:
            approval = approval_crud.get_by_contract_id(db, contract_id)
            if approval and approval.status == ApprovalStatus.PENDING:
                # 终止审批流程：状态更新为 CANCELLED
                approval.status = ApprovalStatus.CANCELLED
                # 置空 contract_id（软删除不会触发外键 SET NULL，需手动处理）
                approval.contract_id = None
                # 记录删除原因（使用原生 SQL 避免 SQLite RETURNING 问题）
                from sqlalchemy import text
                # 查询最大 id 并 +1（兼容 SQLite）
                max_id_result = db.execute(text("SELECT COALESCE(MAX(id), 0) + 1 FROM crm_contract_approval_records")).scalar()
                db.execute(
                    text(
                        "INSERT INTO crm_contract_approval_records "
                        "(id, team_id, approval_id, node_id, approver_id, approver_name, action, comment, created_time) "
                        "VALUES (:id, :team_id, :approval_id, :node_id, :approver_id, :approver_name, :action, :comment, :created_time)"
                    ),
                    {
                        "id": max_id_result,
                        "team_id": approval.team_id,
                        "approval_id": approval.id,
                        "node_id": approval.current_node_id,
                        "approver_id": contract.creator_id,
                        "approver_name": "系统",
                        "action": "SUBMIT",
                        "comment": "合同已删除，审批流程终止",
                        "created_time": datetime.now()
                    }
                )

        # 软删除：设置 deleted_at 时间戳
        contract.deleted_at = datetime.now()
        contract.status = ContractStatus.DRAFT  # 合同状态回到草稿

        db.commit()
        return True

    def get_deleted(
        self,
        db: Session,
        team_id: int,
        skip: int = 0,
        limit: int = 100
    ) -> Tuple[List[Contract], int]:
        """
        查询已删除的合同列表（管理员查询）

        Args:
            db: 数据库会话
            team_id: 团队ID
            skip: 跳过记录数
            limit: 返回记录数上限

        Returns:
            Tuple[List[Contract], int]: 已删除合同列表和总数
        """
        query = db.query(Contract).filter(
            Contract.team_id == team_id,
            Contract.deleted_at.isnot(None)
        )

        total = query.count()
        contracts = query.order_by(Contract.deleted_at.desc()).offset(skip).limit(limit).all()
        return contracts, total

    def restore(self, db: Session, contract_id: int) -> bool:
        """
        恢复已删除的合同（管理员操作）

        Args:
            db: 数据库会话
            contract_id: 合同ID

        Returns:
            bool: 是否成功恢复
        """
        contract = self.get_by_id(db, contract_id)
        if not contract or not contract.deleted_at:
            return False

        contract.deleted_at = None
        db.commit()
        return True


contract_crud = ContractCRUD()
