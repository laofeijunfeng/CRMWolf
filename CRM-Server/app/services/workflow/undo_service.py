"""
撤销服务

提供单步撤销和流程级撤销能力，支持在 TTL 内回滚操作。

核心功能：
1. can_undo() - 检查是否可撤销
2. undo_single() - 单步撤销
3. undo_workflow() - 流程级撤销
4. get_undo_handler() - 获取撤销处理器
"""
from typing import Dict, Any, Optional, List
from datetime import datetime, timedelta
from sqlalchemy.orm import Session

from app.crud.operation_log import operation_log_crud
from app.services.workflow.undo_handlers import (
    UndoHandler,
    UndoResult,
    UndoImpact,
    FollowUpUndoHandler,
    OpportunityWinUndoHandler,
    OpportunityStageUndoHandler,
    LeadConvertUndoHandler,
    ContractUndoHandler,
    CustomerCreateUndoHandler,
    DefaultUndoHandler
)


class UndoService:
    """撤销服务"""

    # 撤销处理器注册表
    UNDO_HANDLERS: Dict[str, UndoHandler] = {
        "FOLLOW_UP_CREATED": FollowUpUndoHandler(),
        "CUSTOMER_FOLLOW_UP_CREATED": FollowUpUndoHandler(),
        "OPPORTUNITY_WON": OpportunityWinUndoHandler(),
        "OPPORTUNITY_STAGE_CHANGED": OpportunityStageUndoHandler(),
        "LEAD_CONVERTED": LeadConvertUndoHandler(),
        "CONTRACT_CREATED": ContractUndoHandler(),
        "CUSTOMER_CREATED": CustomerCreateUndoHandler(),
    }

    def can_undo(self, db: Session, operation_id: int) -> bool:
        """
        检查是否可撤销

        Args:
            db: 数据库会话
            operation_id: 操作ID

        Returns:
            是否可撤销
        """
        log = operation_log_crud.get_by_id(db, operation_id)
        if not log:
            return False

        return (
            log.undoable and
            not log.undone and
            log.undo_deadline and
            datetime.now() < log.undo_deadline
        )

    def get_undo_status(self, db: Session, operation_id: int) -> Dict[str, Any]:
        """
        获取撤销状态

        Args:
            db: 数据库会话
            operation_id: 操作ID

        Returns:
            撤销状态信息
        """
        log = operation_log_crud.get_by_id(db, operation_id)
        if not log:
            return {"can_undo": False, "reason": "操作不存在"}

        if not log.undoable:
            return {"can_undo": False, "reason": "此操作不支持撤销"}

        if log.undone:
            return {"can_undo": False, "reason": "操作已撤销"}

        if not log.undo_deadline or datetime.now() >= log.undo_deadline:
            return {"can_undo": False, "reason": "撤销窗口已过期"}

        # 计算剩余时间
        ttl = (log.undo_deadline - datetime.now()).seconds

        return {
            "can_undo": True,
            "ttl": ttl,
            "undo_endpoint": f"/workflow/undo/{operation_id}",
            "undo_impact": self._get_undo_impact_preview(log)
        }

    def undo_single(
        self,
        db: Session,
        operation_id: int,
        user_id: int
    ) -> UndoResult:
        """
        单步撤销

        Args:
            db: 数据库会话
            operation_id: 操作ID
            user_id: 撤销操作人ID

        Returns:
            撤销结果
        """
        # 1. 验证可撤销
        if not self.can_undo(db, operation_id):
            return UndoResult(
                success=False,
                reason="撤销窗口已过期或操作不支持撤销"
            )

        # 2. 获取操作日志
        log = operation_log_crud.get_by_id(db, operation_id)

        # 3. 获取撤销处理器
        undo_handler = self._get_undo_handler(log.event_type)

        # 4. 执行撤销
        try:
            result = undo_handler.undo(db, log)

            if result.success:
                # 5. 更新操作日志状态
                operation_log_crud.update(db, log.id, {
                    "undone": True,
                    "undo_by": str(user_id),
                    "undo_at": datetime.now()
                })

                db.commit()

            return result

        except Exception as e:
            db.rollback()
            return UndoResult(
                success=False,
                reason=f"撤销失败: {str(e)}"
            )

    def undo_workflow(
        self,
        db: Session,
        session_id: str,
        user_id: int
    ) -> UndoResult:
        """
        流程级撤销

        按时间倒序撤销流程中的所有操作

        Args:
            db: 数据库会话
            session_id: Workflow Session ID
            user_id: 撤销操作人ID

        Returns:
            撤销结果（包含撤销的操作数量）
        """
        # 1. 获取流程所有操作
        operations = operation_log_crud.get_by_workflow_session(db, session_id)

        if not operations:
            return UndoResult(
                success=False,
                reason="未找到流程操作记录"
            )

        # 2. 按时间倒序撤销
        undone_count = 0
        failed_operations = []

        for op in reversed(operations):  # 倒序，先撤销最近的操作
            if self.can_undo(db, op.id):
                result = self.undo_single(db, op.id, user_id)
                if result.success:
                    undone_count += 1
                else:
                    failed_operations.append({
                        "operation_id": op.id,
                        "event_type": op.event_type,
                        "reason": result.reason
                    })

        # 3. 返回结果
        if undone_count == len(operations):
            return UndoResult(
                success=True,
                undone_count=undone_count,
                message=f"已撤销 {undone_count} 个操作"
            )
        elif undone_count > 0:
            return UndoResult(
                success=True,
                undone_count=undone_count,
                message=f"已撤销 {undone_count} 个操作，{len(failed_operations)} 个操作无法撤销",
                failed_operations=failed_operations
            )
        else:
            return UndoResult(
                success=False,
                reason="所有操作都已过期或无法撤销",
                failed_operations=failed_operations
            )

    def _get_undo_handler(self, event_type: str) -> UndoHandler:
        """
        获取撤销处理器

        Args:
            event_type: 事件类型

        Returns:
            撤销处理器实例
        """
        # 优先匹配具体事件类型
        if event_type in self.UNDO_HANDLERS:
            return self.UNDO_HANDLERS[event_type]

        # 尝试模糊匹配（如 OPPORTUNITY_* 都用 OpportunityUndoHandler）
        for pattern, handler in self.UNDO_HANDLERS.items():
            if event_type.startswith(pattern.split("_")[0]):
                return handler

        # 默认处理器（不支持撤销）
        return DefaultUndoHandler()

    def _get_undo_impact_preview(self, log: Any) -> List[Dict[str, Any]]:
        """
        获取撤销影响预览

        Args:
            log: 操作日志

        Returns:
            撤销影响列表
        """
        undo_handler = self._get_undo_handler(log.event_type)
        impacts = undo_handler.get_undo_impact(log)

        return [
            {
                "type": impact.type,
                "resource_type": impact.resource_type,
                "resource_id": impact.resource_id,
                "description": impact.description
            }
            for impact in impacts
        ]


# 单例实例
undo_service = UndoService()