"""
撤销处理器

提供各类操作的撤销能力，每种操作类型对应一个 Handler。

核心设计：
1. UndoHandler 基类 - 定义撤销接口
2. UndoResult - 撤销结果结构
3. UndoImpact - 撤销影响范围
4. 具体 Handler 实现各类操作的撤销逻辑
"""
from typing import Dict, Any, Optional, List
from abc import ABC, abstractmethod
from datetime import datetime
from sqlalchemy.orm import Session

from app.models.operation_log import OperationLog


class UndoImpact:
    """撤销影响"""

    def __init__(
        self,
        type: str,
        resource_type: str,
        resource_id: int,
        description: str = None
    ):
        self.type = type                # 影响类型：soft_delete, status_revert, stage_revert, etc.
        self.resource_type = resource_type
        self.resource_id = resource_id
        self.description = description


class UndoResult:
    """撤销结果"""

    def __init__(
        self,
        success: bool,
        message: str = None,
        reason: str = None,
        undone_count: int = 0,
        impact: List[UndoImpact] = None,
        failed_operations: List[Dict] = None
    ):
        self.success = success
        self.message = message
        self.reason = reason
        self.undone_count = undone_count
        self.impact = impact or []
        self.failed_operations = failed_operations or []


class UndoHandler(ABC):
    """撤销处理器基类"""

    @abstractmethod
    def undo(self, db: Session, log: OperationLog) -> UndoResult:
        """
        执行撤销

        Args:
            db: 数据库会话
            log: 操作日志

        Returns:
            撤销结果
        """
        pass

    @abstractmethod
    def get_undo_impact(self, log: OperationLog) -> List[UndoImpact]:
        """
        获取撤销影响范围

        Args:
            log: 操作日志

        Returns:
            撤销影响列表
        """
        pass


class FollowUpUndoHandler(UndoHandler):
    """跟进记录撤销"""

    def undo(self, db: Session, log: OperationLog) -> UndoResult:
        """软删除跟进记录"""
        from app.crud.lead_follow_up import lead_follow_up_crud
        from app.crud.customer_follow_up import customer_follow_up_crud

        resource_type = log.primary_resource_type

        # 根据 resource_type 选择 CRUD
        if resource_type == "LEAD_FOLLOW_UP":
            crud = lead_follow_up_crud
        elif resource_type == "CUSTOMER_FOLLOW_UP":
            crud = customer_follow_up_crud
        else:
            # 尝试从 secondary_resource_type
            if log.secondary_resource_type == "LEAD_FOLLOW_UP":
                crud = lead_follow_up_crud
            elif log.secondary_resource_type == "CUSTOMER_FOLLOW_UP":
                crud = customer_follow_up_crud
            else:
                return UndoResult(
                    success=False,
                    reason=f"无法识别跟进记录类型: {resource_type}"
                )

        # 软删除（设置 deleted 字段）
        try:
            # 检查是否有 deleted 字段
            follow_up = crud.get_by_id(db, log.primary_resource_id)
            if not follow_up:
                return UndoResult(
                    success=False,
                    reason="跟进记录不存在"
                )

            # 设置删除标记
            if hasattr(follow_up, 'deleted'):
                setattr(follow_up, 'deleted', True)
            elif hasattr(follow_up, 'is_deleted'):
                setattr(follow_up, 'is_deleted', True)
            else:
                # 如果没有软删除字段，使用硬删除
                crud.remove(db, log.primary_resource_id)

            db.commit()

            return UndoResult(
                success=True,
                message="跟进记录已撤销",
                impact=[
                    UndoImpact(
                        type="soft_delete",
                        resource_type=resource_type,
                        resource_id=log.primary_resource_id,
                        description="跟进记录已标记为删除"
                    )
                ]
            )

        except Exception as e:
            db.rollback()
            return UndoResult(
                success=False,
                reason=f"撤销失败: {str(e)}"
            )

    def get_undo_impact(self, log: OperationLog) -> List[UndoImpact]:
        """获取撤销影响"""
        return [
            UndoImpact(
                type="soft_delete",
                resource_type=log.primary_resource_type,
                resource_id=log.primary_resource_id,
                description="跟进记录将被标记为删除"
            )
        ]


class OpportunityWinUndoHandler(UndoHandler):
    """赢单撤销"""

    def undo(self, db: Session, log: OperationLog) -> UndoResult:
        """恢复商机状态"""
        from app.crud.opportunity import opportunity_crud
        from app.models.opportunity import OpportunityStatus
        from app.models.opportunity import OpportunityStageSnapshot

        opportunity_id = log.primary_resource_id

        # 1. 获取商机
        opportunity = opportunity_crud.get_by_id(db, opportunity_id)
        if not opportunity:
            return UndoResult(
                success=False,
                reason="商机不存在"
            )

        # 2. 恢复状态
        before_snapshot = log.before_snapshot or {}
        original_status = before_snapshot.get("status", OpportunityStatus.FOLLOWING.value)
        original_win_probability = before_snapshot.get("win_probability", 0)
        original_stage_name = before_snapshot.get("current_stage_name")
        original_stage_snapshot_id = before_snapshot.get("current_stage_snapshot_id")

        impacts = []

        try:
            # 2.1 恢复商机状态
            opportunity.status = original_status
            opportunity.win_probability = original_win_probability
            opportunity.actual_amount = None
            opportunity.actual_closing_date = None

            if original_stage_name:
                opportunity.current_stage_name = original_stage_name

            if original_stage_snapshot_id:
                opportunity.current_stage_snapshot_id = original_stage_snapshot_id

            impacts.append(UndoImpact(
                type="status_revert",
                resource_type="OPPORTUNITY",
                resource_id=opportunity_id,
                description=f"商机状态恢复为 {original_status}, 赢率恢复为 {original_win_probability}%"
            ))

            # 2.2 恢复阶段快照（如果快照记录中有信息）
            after_snapshot = log.after_snapshot or {}
            new_snapshot_id = after_snapshot.get("new_snapshot_id")

            if new_snapshot_id:
                # 删除新创建的快照（如果存在）
                new_snapshot = db.query(OpportunityStageSnapshot).filter(
                    OpportunityStageSnapshot.id == new_snapshot_id
                ).first()

                if new_snapshot:
                    # 设置删除标记或直接删除
                    db.delete(new_snapshot)
                    impacts.append(UndoImpact(
                        type="snapshot_delete",
                        resource_type="OPPORTUNITY_STAGE_SNAPSHOT",
                        resource_id=new_snapshot_id,
                        description="删除赢单创建的阶段快照"
                    ))

            db.commit()

            return UndoResult(
                success=True,
                message="赢单已撤销，商机恢复跟进状态",
                impact=impacts
            )

        except Exception as e:
            db.rollback()
            return UndoResult(
                success=False,
                reason=f"撤销失败: {str(e)}"
            )

    def get_undo_impact(self, log: OperationLog) -> List[UndoImpact]:
        """获取撤销影响"""
        before_snapshot = log.before_snapshot or {}

        impacts = [
            UndoImpact(
                type="status_revert",
                resource_type="OPPORTUNITY",
                resource_id=log.primary_resource_id,
                description=f"商机状态恢复为跟进中，赢率恢复为 {before_snapshot.get('win_probability', 0)}%"
            )
        ]

        # 如果有阶段变更
        if before_snapshot.get("current_stage_name"):
            impacts.append(UndoImpact(
                type="stage_revert",
                resource_type="OPPORTUNITY",
                resource_id=log.primary_resource_id,
                description=f"阶段恢复为 {before_snapshot.get('current_stage_name')}"
            ))

        return impacts


class OpportunityStageUndoHandler(UndoHandler):
    """商机阶段变更撤销"""

    def undo(self, db: Session, log: OperationLog) -> UndoResult:
        """恢复商机阶段"""
        from app.crud.opportunity import opportunity_crud
        from app.models.opportunity import OpportunityStageSnapshot

        opportunity_id = log.primary_resource_id
        before_snapshot = log.before_snapshot or {}
        after_snapshot = log.after_snapshot or {}

        try:
            opportunity = opportunity_crud.get_by_id(db, opportunity_id)
            if not opportunity:
                return UndoResult(success=False, reason="商机不存在")

            # 恢复阶段信息
            original_stage_name = before_snapshot.get("current_stage_name")
            original_win_probability = before_snapshot.get("win_probability")
            original_stage_snapshot_id = before_snapshot.get("current_stage_snapshot_id")

            if original_stage_name:
                opportunity.current_stage_name = original_stage_name

            if original_win_probability:
                opportunity.win_probability = original_win_probability
                opportunity.current_win_probability = original_win_probability

            if original_stage_snapshot_id:
                opportunity.current_stage_snapshot_id = original_stage_snapshot_id

            # 删除新创建的快照
            new_snapshot_id = after_snapshot.get("new_snapshot_id")
            if new_snapshot_id:
                new_snapshot = db.query(OpportunityStageSnapshot).filter(
                    OpportunityStageSnapshot.id == new_snapshot_id
                ).first()
                if new_snapshot:
                    db.delete(new_snapshot)

            db.commit()

            return UndoResult(
                success=True,
                message="阶段已恢复",
                impact=[
                    UndoImpact(
                        type="stage_revert",
                        resource_type="OPPORTUNITY",
                        resource_id=opportunity_id,
                        description=f"阶段恢复为 {original_stage_name}"
                    )
                ]
            )

        except Exception as e:
            db.rollback()
            return UndoResult(success=False, reason=f"撤销失败: {str(e)}")

    def get_undo_impact(self, log: OperationLog) -> List[UndoImpact]:
        before_snapshot = log.before_snapshot or {}
        return [
            UndoImpact(
                type="stage_revert",
                resource_type="OPPORTUNITY",
                resource_id=log.primary_resource_id,
                description=f"阶段将恢复为 {before_snapshot.get('current_stage_name', '未知')}"
            )
        ]


class LeadConvertUndoHandler(UndoHandler):
    """线索转化撤销"""

    def undo(self, db: Session, log: OperationLog) -> UndoResult:
        """恢复线索状态，删除创建的客户和商机"""
        from app.crud.lead import lead_crud
        from app.crud.customer import customer_crud
        from app.crud.opportunity import opportunity_crud
        from app.models.lead import LeadStatus

        lead_id = log.primary_resource_id
        before_snapshot = log.before_snapshot or {}
        after_snapshot = log.after_snapshot or {}

        impacts = []

        try:
            # 1. 恢复线索状态
            lead = lead_crud.get_by_id(db, lead_id)
            if not lead:
                return UndoResult(success=False, reason="线索不存在")

            original_status = before_snapshot.get("status", LeadStatus.FOLLOWING.value)
            lead.status = original_status

            impacts.append(UndoImpact(
                type="status_revert",
                resource_type="LEAD",
                resource_id=lead_id,
                description=f"线索状态恢复为 {original_status}"
            ))

            # 2. 删除创建的客户（如果无其他关联）
            created_customer_id = after_snapshot.get("created_customer_id")
            if created_customer_id:
                customer = customer_crud.get_by_id(db, created_customer_id)
                if customer:
                    # 检查是否有其他商机或合同
                    # 如果只有这一个商机，可以删除
                    has_other_opportunities = db.query(
                        opportunity_crud.model
                    ).filter(
                        opportunity_crud.model.customer_id == created_customer_id,
                        opportunity_crud.model.id != after_snapshot.get("created_opportunity_id")
                    ).count()

                    if has_other_opportunities == 0:
                        customer_crud.remove(db, created_customer_id)
                        impacts.append(UndoImpact(
                            type="delete",
                            resource_type="CUSTOMER",
                            resource_id=created_customer_id,
                            description="删除转化创建的客户"
                        ))

            # 3. 删除创建的商机
            created_opportunity_id = after_snapshot.get("created_opportunity_id")
            if created_opportunity_id:
                opportunity_crud.remove(db, created_opportunity_id)
                impacts.append(UndoImpact(
                    type="delete",
                    resource_type="OPPORTUNITY",
                    resource_id=created_opportunity_id,
                    description="删除转化创建的商机"
                ))

            db.commit()

            return UndoResult(
                success=True,
                message="线索转化已撤销",
                impact=impacts
            )

        except Exception as e:
            db.rollback()
            return UndoResult(success=False, reason=f"撤销失败: {str(e)}")

    def get_undo_impact(self, log: OperationLog) -> List[UndoImpact]:
        after_snapshot = log.after_snapshot or {}
        impacts = [
            UndoImpact(
                type="status_revert",
                resource_type="LEAD",
                resource_id=log.primary_resource_id,
                description="线索状态将恢复为跟进中"
            )
        ]

        if after_snapshot.get("created_customer_id"):
            impacts.append(UndoImpact(
                type="delete",
                resource_type="CUSTOMER",
                resource_id=after_snapshot["created_customer_id"],
                description="转化创建的客户将被删除"
            ))

        if after_snapshot.get("created_opportunity_id"):
            impacts.append(UndoImpact(
                type="delete",
                resource_type="OPPORTUNITY",
                resource_id=after_snapshot["created_opportunity_id"],
                description="转化创建的商机将被删除"
            ))

        return impacts


class ContractUndoHandler(UndoHandler):
    """合同创建撤销"""

    def undo(self, db: Session, log: OperationLog) -> UndoResult:
        """软删除合同"""
        from app.crud.contract import contract_crud

        contract_id = log.primary_resource_id

        try:
            contract = contract_crud.get_by_id(db, contract_id)
            if not contract:
                return UndoResult(success=False, reason="合同不存在")

            # 检查状态，只有草稿状态才能撤销
            if contract.status not in [0, "DRAFT"]:  # DRAFT 状态
                return UndoResult(
                    success=False,
                    reason="合同已进入审批流程，无法撤销"
                )

            # 软删除
            if hasattr(contract, 'deleted'):
                contract.deleted = True
            else:
                contract_crud.remove(db, contract_id)

            db.commit()

            return UndoResult(
                success=True,
                message="合同已撤销",
                impact=[
                    UndoImpact(
                        type="soft_delete",
                        resource_type="CONTRACT",
                        resource_id=contract_id,
                        description="合同已标记为删除"
                    )
                ]
            )

        except Exception as e:
            db.rollback()
            return UndoResult(success=False, reason=f"撤销失败: {str(e)}")

    def get_undo_impact(self, log: OperationLog) -> List[UndoImpact]:
        return [
            UndoImpact(
                type="soft_delete",
                resource_type="CONTRACT",
                resource_id=log.primary_resource_id,
                description="合同将被标记为删除"
            )
        ]


class CustomerCreateUndoHandler(UndoHandler):
    """客户创建撤销"""

    def undo(self, db: Session, log: OperationLog) -> UndoResult:
        """软删除客户"""
        from app.crud.customer import customer_crud

        customer_id = log.primary_resource_id

        try:
            customer = customer_crud.get_by_id(db, customer_id)
            if not customer:
                return UndoResult(success=False, reason="客户不存在")

            # 检查是否有商机或合同关联
            from app.crud.opportunity import opportunity_crud
            has_opportunities = db.query(opportunity_crud.model).filter(
                opportunity_crud.model.customer_id == customer_id
            ).count()

            if has_opportunities > 0:
                return UndoResult(
                    success=False,
                    reason="客户有商机关联，无法删除"
                )

            # 软删除
            if hasattr(customer, 'deleted'):
                customer.deleted = True
            else:
                customer_crud.remove(db, customer_id)

            db.commit()

            return UndoResult(
                success=True,
                message="客户已撤销",
                impact=[
                    UndoImpact(
                        type="soft_delete",
                        resource_type="CUSTOMER",
                        resource_id=customer_id,
                        description="客户已标记为删除"
                    )
                ]
            )

        except Exception as e:
            db.rollback()
            return UndoResult(success=False, reason=f"撤销失败: {str(e)}")

    def get_undo_impact(self, log: OperationLog) -> List[UndoImpact]:
        return [
            UndoImpact(
                type="soft_delete",
                resource_type="CUSTOMER",
                resource_id=log.primary_resource_id,
                description="客户将被标记为删除"
            )
        ]


class DefaultUndoHandler(UndoHandler):
    """默认撤销处理器（不支持撤销）"""

    def undo(self, db: Session, log: OperationLog) -> UndoResult:
        return UndoResult(
            success=False,
            reason="此操作不支持撤销"
        )

    def get_undo_impact(self, log: OperationLog) -> List[UndoImpact]:
        return []