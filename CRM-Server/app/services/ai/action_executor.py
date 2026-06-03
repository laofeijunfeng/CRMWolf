"""AI Actions CRUD 调用层（降级版）

职责：
- 仅负责 CRUD 调用
- 不记录审计日志（由 action_entry 负责）
- 仅被 action_entry 调用

整改要点（Phase 4）：
- 移除 _log_ai_action（审计职责上移到 action_entry）
- 保持纯 CRUD 调用职责
- 不持有 Preview/Gate 逻辑

R-D 合规（Phase 9）：
- 使用 UserExecCtx 替代裸 User 参数
- Entry 内部管理 db，Executor 接收 UserExecCtx

参见: CRM-Docs/plans/AI-GLUE-DEEP-REMEDIATION-PLAN.md Phase 4
参见: CRM-Docs/requirements/AI-GLUE-REQUIREMENTS.md 17.3 R-D
"""

from typing import Optional, Dict, Any, List
from sqlalchemy.orm import Session
from datetime import datetime, date

from app.models.opportunity import OpportunityStatus
from app.models.customer_follow_up import CustomerFollowUp
from app.crud.customer_follow_up import customer_follow_up_crud
from app.crud.opportunity import opportunity_crud
from app.crud.customer import customer_crud
from app.crud.procurement import procurement_stage_template_crud
from app.schemas.customer_follow_up import CustomerFollowUpCreate
from app.schemas.opportunity import OpportunityCreate, OpportunityUpdate, OpportunityWin, OpportunityLose


class ActionExecutor:
    """CRUD 调用层

    仅负责调用 CRUD，不记录审计日志。
    所有审计日志由 ActionEntry 层统一处理。

    R-D 合规：使用 UserExecCtx 替代裸 User 参数
    """

    def __init__(self, db: Session, user_ctx):
        """CRUD 调用层构造器

        Args:
            db: 数据库 Session
            user_ctx: UserExecCtx 实例（从 action_entry 传入）
        """
        self.db = db
        self.user_ctx = user_ctx
        self.operator_id = str(user_ctx.user_id)
        self.operator_name = user_ctx.user_name or f"user_{user_ctx.user_id}"
        self.team_id = user_ctx.tenant_id

    # ==================== 创建跟进 ====================

    def create_follow_up(
        self,
        customer_id: int,
        content: str,
        follow_up_time: Optional[datetime] = None,
        method: Optional[str] = "电话",
        next_action: Optional[str] = None,
        opportunity_id: Optional[int] = None,
    ) -> CustomerFollowUp:
        """创建跟进记录（纯 CRUD 调用）

        Args:
            customer_id: 客户ID
            content: 跟进内容
            follow_up_time: 跟进时间（可选）
            method: 跟进方式（默认电话）
            next_action: 下一步动作（可选）
            opportunity_id: 关联商机ID（可选）

        Returns:
            CustomerFollowUp: 创建的跟进记录
        """
        customer = customer_crud.get_by_id(self.db, customer_id)
        if not customer:
            raise ValueError(f"客户 {customer_id} 不存在")

        follow_up_data = CustomerFollowUpCreate(
            content=content,
            method=method,
            next_follow_time=follow_up_time.date() if follow_up_time else None,
            next_action=next_action,
        )

        follow_up = customer_follow_up_crud.create(
            self.db,
            obj_in=follow_up_data,
            customer_id=customer_id,
            creator_id=self.operator_id,
            team_id=self.team_id or customer.team_id,
            operator_name=self.operator_name,
        )

        return follow_up

    # ==================== 设置提醒 ====================

    def set_reminder(
        self,
        customer_id: int,
        reminder_time: datetime,
        content: str,
        opportunity_id: Optional[int] = None,
    ) -> CustomerFollowUp:
        """设置跟进提醒（纯 CRUD 调用）

        通过创建跟进记录并设置 next_follow_time 实现。
        """
        return self.create_follow_up(
            customer_id=customer_id,
            content=f"[提醒] {content}",
            follow_up_time=reminder_time,
            method="系统提醒",
            next_action=content,
            opportunity_id=opportunity_id,
        )

    # ==================== 初始化商机 ====================

    def init_opportunity(
        self,
        customer_id: int,
        opportunity_name: str,
        procurement_method_id: Optional[int] = None,
    ) -> Any:  # Returns Opportunity
        """初始化商机（纯 CRUD 调用）

        AI 场景下的商机创建，只要求最核心字段。
        """
        customer = customer_crud.get_by_id(self.db, customer_id)
        if not customer:
            raise ValueError(f"客户 {customer_id} 不存在")

        if procurement_method_id is None:
            procurement_method_id = customer.default_procurement_method_id
        if procurement_method_id is None:
            raise ValueError("未指定采购方式，且客户无默认采购方式")

        default_stage = procurement_stage_template_crud.get_default_stage(
            self.db, procurement_method_id
        )
        if not default_stage:
            raise ValueError(f"采购方式 {procurement_method_id} 无默认起始阶段")

        opportunity_data = OpportunityCreate(
            opportunity_name=opportunity_name,
            customer_id=customer_id,
            procurement_method_id=procurement_method_id,
            total_amount=0,
            user_count=1,
            license_type="SUBSCRIPTION",
            purchase_type="NEW",
            expected_closing_date=date.today(),
            owner_id=self.operator_id,
            stage_id=default_stage.id,
        )

        opportunity = opportunity_crud.create(
            self.db,
            obj_in=opportunity_data,
            creator_id=self.operator_id,
            team_id=self.team_id or customer.team_id,
        )

        return opportunity

    # ==================== 更新金额 ====================

    def update_amount(
        self,
        opportunity_id: int,
        amount: float,
        user_count: Optional[int] = None,
    ) -> Any:  # Returns Opportunity
        """更新商机金额（纯 CRUD 调用）"""
        opportunity = opportunity_crud.get_by_id(self.db, opportunity_id)
        if not opportunity:
            raise ValueError(f"商机 {opportunity_id} 不存在")

        if opportunity.status != OpportunityStatus.FOLLOWING.value:
            raise ValueError("只能更新跟进中的商机")

        update_data = OpportunityUpdate(total_amount=amount)
        if user_count is not None:
            update_data.user_count = user_count

        opportunity = opportunity_crud.update(self.db, opportunity, update_data)

        return opportunity

    # ==================== 更新阶段 ====================

    def update_stage(
        self,
        opportunity_id: int,
        target_stage_template_id: int,
    ) -> Any:  # Returns Opportunity
        """更新商机阶段（纯 CRUD 调用）"""
        opportunity = opportunity_crud.get_by_id(self.db, opportunity_id)
        if not opportunity:
            raise ValueError(f"商机 {opportunity_id} 不存在")

        if opportunity.status != OpportunityStatus.FOLLOWING.value:
            raise ValueError("只能更新跟进中的商机阶段")

        opportunity = opportunity_crud.move_to_stage(
            self.db,
            opportunity_id,
            target_stage_template_id,
            self.operator_id,
        )

        return opportunity

    # ==================== 赢单 ====================

    def win_opportunity(
        self,
        opportunity_id: int,
        actual_amount: Optional[float] = None,
        actual_closing_date: Optional[date] = None,
    ) -> Any:  # Returns Opportunity
        """标记商机赢单（纯 CRUD 调用）"""
        opportunity = opportunity_crud.get_by_id(self.db, opportunity_id)
        if not opportunity:
            raise ValueError(f"商机 {opportunity_id} 不存在")

        if opportunity.status == OpportunityStatus.WON.value:
            raise ValueError("商机已是赢单状态")

        if opportunity.status == OpportunityStatus.LOST.value:
            raise ValueError("商机已输单，无法标记为赢单")

        win_amount = actual_amount or float(opportunity.total_amount)
        closing_date = actual_closing_date or date.today()

        win_data = OpportunityWin(
            actual_amount=win_amount,
            actual_closing_date=closing_date,
        )

        opportunity = opportunity_crud.mark_as_won(
            self.db, opportunity, win_data, self.operator_id
        )

        return opportunity

    # ==================== 输单 ====================

    def lose_opportunity(
        self,
        opportunity_id: int,
        loss_reason: Optional[str] = None,
    ) -> Any:  # Returns Opportunity
        """标记商机输单（纯 CRUD 调用）"""
        opportunity = opportunity_crud.get_by_id(self.db, opportunity_id)
        if not opportunity:
            raise ValueError(f"商机 {opportunity_id} 不存在")

        if opportunity.status == OpportunityStatus.LOST.value:
            raise ValueError("商机已是输单状态")

        if opportunity.status == OpportunityStatus.WON.value:
            raise ValueError("商机已赢单，无法标记为输单")

        lose_data = OpportunityLose(loss_reason=loss_reason or "未填写")

        opportunity = opportunity_crud.mark_as_lost(
            self.db, opportunity, lose_data, self.operator_id
        )

        return opportunity


__all__ = ["ActionExecutor"]