"""AI Actions 入口函数层

职责：
1. 权限校验（当前用户能否对该实体做该操作）
2. 业务校验（阶段流合法性、字段约束、必填语义）
3. Preview 构造（单一 truth）
4. Execute 执行（调用 CRUD）
5. 审计留痕（source="ai"、action_id）

Contract: (user_ctx: UserExecCtx, params, preview: bool) → ActionEntryResult

参见: CRM-Docs/plans/AI-GLUE-DEEP-REMEDIATION-PLAN.md
参见: CRM-Docs/requirements/AI-GLUE-REQUIREMENTS.md 17.3 R-D
"""

from typing import Dict, Any, Optional, List
from dataclasses import dataclass, field
from datetime import datetime, date
from sqlalchemy.orm import Session

from app.models.user import User
from app.models.customer import Customer
from app.models.opportunity import Opportunity
from app.schemas.ai.common import ActionPlan, FieldChange, generate_action_id
from app.services.ai.action_executor import ActionExecutor
from app.services.operation_log_service import operation_log_service
from app.crud.customer import customer_crud
from app.crud.opportunity import opportunity_crud
from app.constants.ai_rules import RiskLevel, get_action_risk


@dataclass
class UserExecCtx:
    """用户执行上下文（R-D 合规）

    替代裸 db: Session 参数，提供干净的用户上下文。
    调用方（HTTP adapter、glue executor）通过此上下文传递用户信息，
    不暴露底层数据库 Session。

    Attributes:
        user_id: 用户 ID
        tenant_id: 租户/团队 ID
        roles: 用户角色列表
        is_ai: 是否为 AI 调用
        source: 调用来源 ("web" | "ai" | "glue")
        user_name: 用户名称（可选，用于审计）
    """

    user_id: int
    tenant_id: int
    roles: List[str] = field(default_factory=list)
    is_ai: bool = False
    source: str = "web"  # "web" | "ai" | "glue"
    user_name: Optional[str] = None

    @classmethod
    def from_user(cls, user: User, is_ai: bool = False, source: str = "web") -> "UserExecCtx":
        """从 User 模型创建 UserExecCtx

        Args:
            user: User 模型实例
            is_ai: 是否为 AI 调用
            source: 调用来源

        Returns:
            UserExecCtx 实例
        """
        return cls(
            user_id=user.id,
            tenant_id=user.team_id or 0,
            roles=[user.role] if user.role else [],
            is_ai=is_ai,
            source=source,
            user_name=user.name,
        )


@dataclass
class ActionEntryResult:
    """入口函数统一返回类型"""
    action_id: str
    status: str  # "preview" | "completed" | "failed"
    plan: Optional[ActionPlan] = None  # preview 态
    data: Optional[Dict[str, Any]] = None  # execute 态
    error: Optional[str] = None
    requires_confirmation: bool = False
    confidence: float = 0.9


class ActionEntry:
    """入口函数层

    设计原则：
    1. 入口函数是所有写操作的唯一入口
    2. Preview 逻辑统一在此层（单一 truth）
    3. 权限校验 + 业务校验在此层
    4. 审计留痕在此层
    5. ActionExecutor 仅负责 CRUD 调用

    R-D 合规：
    - 使用 UserExecCtx 替代裸 User 参数
    - 调用方不直接暴露 db: Session（由 Entry 内部管理）
    """

    def __init__(self, db: Session, user_ctx: UserExecCtx):
        """入口函数构造器

        Args:
            db: Session - **transitional** 内部持有，终态目标 ActionEntry.from_ctx(ctx: UserExecCtx)
            user_ctx: UserExecCtx - 用户执行上下文（来源：web/ai/glue）
        """
        self.db = db
        self.user_ctx = user_ctx
        # ActionExecutor 内部使用 db + user_ctx
        self.executor = ActionExecutor(db, user_ctx)
        self.operator_id = str(user_ctx.user_id)
        self.team_id = user_ctx.tenant_id

    # ==================== 创建跟进 ====================

    def create_follow_up(
        self,
        customer_id: int,
        content: str,
        follow_up_time: Optional[datetime] = None,
        method: Optional[str] = "电话",
        follow_up_method: Optional[str] = None,  # Alias (AI may use this)
        next_action: Optional[str] = None,
        opportunity_id: Optional[int] = None,
        preview: bool = True,
        action_id: Optional[str] = None,
        **kwargs,  # Accept additional params from AI (customer_name, etc.)
    ) -> ActionEntryResult:
        """创建跟进入口函数

        流程：
        1. 权限校验：用户是否有该客户的操作权限
        2. 业务校验：客户是否存在
        3. preview=True → 返回 ActionPlan
        4. preview=False → 调用 CRUD → 记录审计
        """
        # Normalize method parameter
        final_method = method or follow_up_method or "电话"

        # Step 1: 权限校验 + 业务校验
        customer = self._check_customer_permission(customer_id)
        if customer is None:
            return ActionEntryResult(
                action_id=action_id or generate_action_id(),
                status="failed",
                error=f"无权限或客户 {customer_id} 不存在",
            )

        # Step 2: 生成 action_id（唯一标识）
        action_id = action_id or generate_action_id()

        # Step 3: Preview 态
        if preview:
            plan = ActionPlan(
                description=f"为客户 #{customer_id} ({customer.account_name}) 创建跟进记录",
                changes=[
                    FieldChange(field="content", to_value=content),
                    FieldChange(field="method", to_value=final_method),
                    FieldChange(
                        field="follow_up_time",
                        to_value=follow_up_time.isoformat() if follow_up_time else None
                    ),
                    FieldChange(field="next_action", to_value=next_action),
                    FieldChange(field="opportunity_id", to_value=opportunity_id),
                ],
                entity_type="FollowUp",
            )
            risk_level = get_action_risk("create_follow_up")
            return ActionEntryResult(
                action_id=action_id,
                status="preview",
                plan=plan,
                requires_confirmation=risk_level == RiskLevel.HIGH,
            )

        # Step 4: Execute 态
        try:
            follow_up = self.executor.create_follow_up(
                customer_id=customer_id,
                content=content,
                follow_up_time=follow_up_time,
                method=final_method,  # Use normalized method
                next_action=next_action,
                opportunity_id=opportunity_id,
            )

            # R-E: 记录 AI 审计日志（source/is_ai/action_id）
            self._log_ai_action(
                action_id=action_id,
                action_type="create_follow_up",
                resource_type="CUSTOMER",
                resource_id=customer_id,
                outcome="success",
                params={
                    "content": content,
                    "method": final_method,  # Use normalized method
                    "opportunity_id": opportunity_id,
                }
            )

            return ActionEntryResult(
                action_id=action_id,
                status="completed",
                data={
                    "follow_up_id": follow_up.id,
                    "customer_id": customer_id,
                    "content": content,
                },
            )
        except ValueError as e:
            # R-E: 记录失败审计
            self._log_ai_action(
                action_id=action_id,
                action_type="create_follow_up",
                resource_type="CUSTOMER",
                resource_id=customer_id,
                outcome="failed",
                error=str(e),
            )
            return ActionEntryResult(
                action_id=action_id,
                status="failed",
                error=str(e),
            )

    # ==================== 设置提醒 ====================

    def set_reminder(
        self,
        customer_id: int,
        reminder_time: datetime,
        content: str,
        opportunity_id: Optional[int] = None,
        preview: bool = True,
        action_id: Optional[str] = None,
    ) -> ActionEntryResult:
        """设置提醒入口函数"""
        # 权限校验
        customer = self._check_customer_permission(customer_id)
        if customer is None:
            return ActionEntryResult(
                action_id=action_id or generate_action_id(),
                status="failed",
                error=f"无权限或客户 {customer_id} 不存在",
            )

        action_id = action_id or generate_action_id()

        # Preview 态
        if preview:
            plan = ActionPlan(
                description=f"为客户 #{customer_id} ({customer.account_name}) 设置提醒",
                changes=[
                    FieldChange(
                        field="reminder_time",
                        to_value=reminder_time.isoformat()
                    ),
                    FieldChange(field="content", to_value=content),
                ],
                entity_type="Reminder",
            )
            return ActionEntryResult(
                action_id=action_id,
                status="preview",
                plan=plan,
                requires_confirmation=False,
            )

        # Execute 态
        try:
            follow_up = self.executor.set_reminder(
                customer_id=customer_id,
                reminder_time=reminder_time,
                content=content,
                opportunity_id=opportunity_id,
            )

            return ActionEntryResult(
                action_id=action_id,
                status="completed",
                data={
                    "follow_up_id": follow_up.id,
                    "reminder_time": reminder_time.isoformat(),
                },
            )
        except ValueError as e:
            return ActionEntryResult(
                action_id=action_id,
                status="failed",
                error=str(e),
            )

    # ==================== 初始化商机 ====================

    def init_opportunity(
        self,
        customer_id: int,
        opportunity_name: str,
        procurement_method_id: Optional[int] = None,
        preview: bool = True,
        action_id: Optional[str] = None,
    ) -> ActionEntryResult:
        """初始化商机会入口函数"""
        # 权限校验
        customer = self._check_customer_permission(customer_id)
        if customer is None:
            return ActionEntryResult(
                action_id=action_id or generate_action_id(),
                status="failed",
                error=f"无权限或客户 {customer_id} 不存在",
            )

        action_id = action_id or generate_action_id()

        # Preview 态
        if preview:
            plan = ActionPlan(
                description=f"为客户 #{customer_id} ({customer.account_name}) 创建商机: {opportunity_name}",
                changes=[
                    FieldChange(field="opportunity_name", to_value=opportunity_name),
                    FieldChange(field="customer_id", to_value=customer_id),
                    FieldChange(field="procurement_method_id", to_value=procurement_method_id),
                ],
                entity_type="Opportunity",
            )
            risk_level = get_action_risk("init_opportunity")
            return ActionEntryResult(
                action_id=action_id,
                status="preview",
                plan=plan,
                requires_confirmation=risk_level == RiskLevel.HIGH,
            )

        # Execute 态
        try:
            opportunity = self.executor.init_opportunity(
                customer_id=customer_id,
                opportunity_name=opportunity_name,
                procurement_method_id=procurement_method_id,
            )

            return ActionEntryResult(
                action_id=action_id,
                status="completed",
                data={
                    "opportunity_id": opportunity.id,
                    "opportunity_name": opportunity.opportunity_name,
                    "customer_id": customer_id,
                    "current_stage": opportunity.current_stage_name,
                },
            )
        except ValueError as e:
            return ActionEntryResult(
                action_id=action_id,
                status="failed",
                error=str(e),
            )

    # ==================== 更新金额 ====================

    def update_amount(
        self,
        opportunity_id: int,
        amount: float,
        user_count: Optional[int] = None,
        preview: bool = True,
        action_id: Optional[str] = None,
    ) -> ActionEntryResult:
        """更新金额入口函数"""
        # 权限校验
        opportunity = self._check_opportunity_permission(opportunity_id)
        if opportunity is None:
            return ActionEntryResult(
                action_id=action_id or generate_action_id(),
                status="failed",
                error=f"无权限或商机 {opportunity_id} 不存在",
            )

        action_id = action_id or generate_action_id()

        # Preview 态
        if preview:
            plan = ActionPlan(
                description=f"更新商机 #{opportunity_id} ({opportunity.opportunity_name}) 金额",
                changes=[
                    FieldChange(
                        field="amount",
                        from_value=float(opportunity.total_amount),
                        to_value=amount
                    ),
                    FieldChange(field="user_count", to_value=user_count),
                ],
                entity_type="Opportunity",
                entity_id=opportunity_id,
            )
            risk_level = get_action_risk("update_amount")
            return ActionEntryResult(
                action_id=action_id,
                status="preview",
                plan=plan,
                requires_confirmation=risk_level == RiskLevel.HIGH,
            )

        # Execute 态
        try:
            updated = self.executor.update_amount(
                opportunity_id=opportunity_id,
                amount=amount,
                user_count=user_count,
            )

            return ActionEntryResult(
                action_id=action_id,
                status="completed",
                data={
                    "opportunity_id": updated.id,
                    "total_amount": float(updated.total_amount),
                },
            )
        except ValueError as e:
            return ActionEntryResult(
                action_id=action_id,
                status="failed",
                error=str(e),
            )

    # ==================== 更新阶段 ====================

    def update_stage(
        self,
        opportunity_id: int,
        target_stage_template_id: int,
        preview: bool = True,
        action_id: Optional[str] = None,
    ) -> ActionEntryResult:
        """更新阶段入口函数"""
        # 权限校验
        opportunity = self._check_opportunity_permission(opportunity_id)
        if opportunity is None:
            return ActionEntryResult(
                action_id=action_id or generate_action_id(),
                status="failed",
                error=f"无权限或商机 {opportunity_id} 不存在",
            )

        action_id = action_id or generate_action_id()

        # 获取目标阶段信息
        from app.crud.procurement import procurement_stage_template_crud
        target_stage = procurement_stage_template_crud.get(self.db, target_stage_template_id)
        if not target_stage:
            return ActionEntryResult(
                action_id=action_id,
                status="failed",
                error=f"阶段模板 {target_stage_template_id} 不存在",
            )

        # Preview 态
        if preview:
            plan = ActionPlan(
                description=f"更新商机 #{opportunity_id} ({opportunity.opportunity_name}) 阶段",
                changes=[
                    FieldChange(
                        field="stage",
                        from_value=opportunity.current_stage_name,
                        to_value=target_stage.stage_name
                    ),
                    FieldChange(
                        field="win_rate",
                        from_value=opportunity.current_win_probability,
                        to_value=target_stage.win_probability / 100.0
                    ),
                ],
                entity_type="Opportunity",
                entity_id=opportunity_id,
            )
            risk_level = get_action_risk("update_stage")
            return ActionEntryResult(
                action_id=action_id,
                status="preview",
                plan=plan,
                requires_confirmation=risk_level == RiskLevel.HIGH,
            )

        # Execute 态
        try:
            updated = self.executor.update_stage(
                opportunity_id=opportunity_id,
                target_stage_template_id=target_stage_template_id,
            )

            return ActionEntryResult(
                action_id=action_id,
                status="completed",
                data={
                    "opportunity_id": updated.id,
                    "current_stage": updated.current_stage_name,
                    "win_probability": updated.current_win_probability,
                },
            )
        except ValueError as e:
            return ActionEntryResult(
                action_id=action_id,
                status="failed",
                error=str(e),
            )

    # ==================== 赢单（高风险） ====================

    def win_opportunity(
        self,
        opportunity_id: int,
        actual_amount: Optional[float] = None,
        actual_closing_date: Optional[date] = None,
        preview: bool = True,
        action_id: Optional[str] = None,
    ) -> ActionEntryResult:
        """赢单入口函数（高风险，强制确认）"""
        # 权限校验
        opportunity = self._check_opportunity_permission(opportunity_id)
        if opportunity is None:
            return ActionEntryResult(
                action_id=action_id or generate_action_id(),
                status="failed",
                error=f"无权限或商机 {opportunity_id} 不存在",
            )

        action_id = action_id or generate_action_id()

        # Preview 态
        if preview:
            win_amount = actual_amount or float(opportunity.total_amount)
            plan = ActionPlan(
                description=f"标记商机 #{opportunity_id} ({opportunity.opportunity_name}) 为赢单",
                changes=[
                    FieldChange(field="status", from_value=opportunity.status, to_value="WON"),
                    FieldChange(field="win_rate", to_value=1.0),
                    FieldChange(field="actual_amount", to_value=win_amount),
                    FieldChange(
                        field="actual_closing_date",
                        to_value=actual_closing_date.isoformat() if actual_closing_date else None
                    ),
                ],
                entity_type="Opportunity",
                entity_id=opportunity_id,
            )
            # HIGH 风险强制确认
            return ActionEntryResult(
                action_id=action_id,
                status="preview",
                plan=plan,
                requires_confirmation=True,  # 强制确认
            )

        # Execute 态
        try:
            updated = self.executor.win_opportunity(
                opportunity_id=opportunity_id,
                actual_amount=actual_amount,
                actual_closing_date=actual_closing_date,
            )

            return ActionEntryResult(
                action_id=action_id,
                status="completed",
                data={
                    "opportunity_id": updated.id,
                    "actual_amount": float(updated.actual_amount),
                    "actual_closing_date": updated.actual_closing_date.isoformat() if updated.actual_closing_date else None,
                },
            )
        except ValueError as e:
            return ActionEntryResult(
                action_id=action_id,
                status="failed",
                error=str(e),
            )

    # ==================== 输单（高风险） ====================

    def lose_opportunity(
        self,
        opportunity_id: int,
        loss_reason: Optional[str] = None,
        preview: bool = True,
        action_id: Optional[str] = None,
    ) -> ActionEntryResult:
        """输单入口函数（高风险，强制确认）"""
        # 权限校验
        opportunity = self._check_opportunity_permission(opportunity_id)
        if opportunity is None:
            return ActionEntryResult(
                action_id=action_id or generate_action_id(),
                status="failed",
                error=f"无权限或商机 {opportunity_id} 不存在",
            )

        action_id = action_id or generate_action_id()

        # Preview 态
        if preview:
            plan = ActionPlan(
                description=f"标记商机 #{opportunity_id} ({opportunity.opportunity_name}) 为输单",
                changes=[
                    FieldChange(field="status", from_value=opportunity.status, to_value="LOST"),
                    FieldChange(field="win_rate", to_value=0.0),
                    FieldChange(field="loss_reason", to_value=loss_reason),
                ],
                entity_type="Opportunity",
                entity_id=opportunity_id,
            )
            # HIGH 风险强制确认
            return ActionEntryResult(
                action_id=action_id,
                status="preview",
                plan=plan,
                requires_confirmation=True,  # 强制确认
            )

        # Execute 态
        try:
            updated = self.executor.lose_opportunity(
                opportunity_id=opportunity_id,
                loss_reason=loss_reason,
            )

            return ActionEntryResult(
                action_id=action_id,
                status="completed",
                data={
                    "opportunity_id": updated.id,
                    "loss_reason": updated.loss_reason,
                },
            )
        except ValueError as e:
            return ActionEntryResult(
                action_id=action_id,
                status="failed",
                error=str(e),
            )

    # ==================== 创建客户 ====================

    def create_customer(
        self,
        account_name: str,
        contact_phone: Optional[str] = None,
        contact_name: Optional[str] = None,
        customer_source: Optional[str] = None,
        source: Optional[str] = None,  # Alias for customer_source (AI may use either)
        address: Optional[str] = None,
        remark: Optional[str] = None,
        city: Optional[str] = None,  # 必填字段
        preview: bool = True,
        action_id: Optional[str] = None,
        **kwargs,  # Accept additional params from AI
    ) -> ActionEntryResult:
        """创建客户入口函数

        流程：
        1. 业务校验：客户名称是否重复
        2. Preview → 返回 ActionPlan
        3. Execute → 调用 CRUD → 记录审计
        """
        from app.crud.customer import customer_crud

        action_id = action_id or generate_action_id()

        # Normalize parameter names
        final_source = customer_source or source or "其他"

        # 业务校验：检查同名客户（可选）
        # Note: 根据业务规则，可能允许同名客户

        # Preview 态
        if preview:
            plan = ActionPlan(
                description=f"创建客户: {account_name}",
                changes=[
                    FieldChange(field="account_name", to_value=account_name),
                    FieldChange(field="city", to_value=city or "未知"),
                    FieldChange(field="contact_phone", to_value=contact_phone),
                    FieldChange(field="contact_name", to_value=contact_name),
                    FieldChange(field="customer_source", to_value=final_source),
                    FieldChange(field="address", to_value=address),
                    FieldChange(field="remark", to_value=remark),
                ],
                entity_type="Customer",
            )
            risk_level = get_action_risk("create_customer")
            return ActionEntryResult(
                action_id=action_id,
                status="preview",
                plan=plan,
                requires_confirmation=risk_level == RiskLevel.HIGH,
            )

        # Execute 态
        try:
            customer = self.executor.create_customer(
                account_name=account_name,
                city=city,  # 传递 city 参数
                contact_phone=contact_phone,
                contact_name=contact_name,
                customer_source=final_source,  # 使用 normalized source
                address=address,
                remark=remark,
            )

            # 记录 AI 审计日志
            self._log_ai_action(
                action_id=action_id,
                action_type="create_customer",
                resource_type="CUSTOMER",
                resource_id=customer.id,
                outcome="success",
                params={
                    "account_name": account_name,
                    "contact_phone": contact_phone,
                }
            )

            return ActionEntryResult(
                action_id=action_id,
                status="completed",
                data={
                    "customer_id": customer.id,
                    "account_name": customer.account_name,
                },
            )
        except ValueError as e:
            return ActionEntryResult(
                action_id=action_id,
                status="failed",
                error=str(e),
            )

    # ==================== 查询客户 ====================

    def query_customer(
        self,
        keyword: Optional[str] = None,
        account_name: Optional[str] = None,  # AI may use account_name for search
        status: Optional[str] = None,
        page: int = 1,
        page_size: int = 20,
        preview: bool = True,
        action_id: Optional[str] = None,
        **kwargs,  # Accept additional params from AI
    ) -> ActionEntryResult:
        """查询客户入口函数

        流程：
        1. Preview → 返回查询参数预览
        2. Execute → 调用 CRUD → 返回结果
        """
        action_id = action_id or generate_action_id()

        # Normalize search keyword
        final_keyword = keyword or account_name or None

        # Preview 态
        if preview:
            plan = ActionPlan(
                description=f"查询客户列表（关键词: {final_keyword or '全部'}）",
                changes=[
                    FieldChange(field="keyword", to_value=final_keyword),
                    FieldChange(field="status", to_value=status),
                    FieldChange(field="page", to_value=page),
                    FieldChange(field="page_size", to_value=page_size),
                ],
                entity_type="CustomerQuery",
            )
            # 查询操作无风险，无需确认
            return ActionEntryResult(
                action_id=action_id,
                status="preview",
                plan=plan,
                requires_confirmation=False,
            )

        # Execute 态
        try:
            result = self.executor.query_customer_list(
                keyword=final_keyword,
                status=status,
                page=page,
                page_size=page_size,
            )

            # 查询操作不记录审计日志（只读操作）

            return ActionEntryResult(
                action_id=action_id,
                status="completed",
                data=result,
            )
        except Exception as e:
            return ActionEntryResult(
                action_id=action_id,
                status="failed",
                error=str(e),
            )

    # ==================== 辅助方法 ====================

    def _log_ai_action(
        self,
        action_id: str,
        action_type: str,
        resource_type: str,
        resource_id: int,
        outcome: str,  # "success" | "failed"
        params: Optional[Dict[str, Any]] = None,
        error: Optional[str] = None,
    ) -> None:
        """记录 AI 审计日志（R-E 合规）

        将 source、is_ai、action_id 等字段存入 OperationLog.content JSON。

        Args:
            action_id: 动作唯一标识
            action_type: 动作类型
            resource_type: 资源类型
            resource_id: 资源 ID
            outcome: 结果状态
            params: 操作参数（脱敏）
            error: 错误信息（失败时）
        """
        try:
            content = {
                "action_id": action_id,
                "action_type": action_type,
                "source": self.user_ctx.source,  # R-D.2: 记录来源
                "is_ai": self.user_ctx.is_ai,    # R-D.2: 记录 AI 标记
                "outcome": outcome,
                "params_digest": params or {},   # R-E.1: 参数摘要
            }
            if error:
                content["error"] = error

            operation_log_service.log(
                db=self.db,
                event_type=f"AI_{action_type.upper()}",
                event_action="EXECUTE" if outcome == "success" else "FAILED",
                resource_type=resource_type,
                resource_id=resource_id,
                operator_id=self.operator_id,
                operator_name=self.user_ctx.user_name,
                content=content,
                team_id=self.team_id,
            )
        except Exception as e:
            # 审计日志失败不应影响业务流程
            import logging
            logging.warning(f"AI 审计日志记录失败: {e}")

    def _check_customer_permission(self, customer_id: int) -> Optional[Customer]:
        """权限校验：用户是否有该客户的操作权限

        租户隔离：只能操作本团队的客户
        """
        customer = customer_crud.get_by_id(self.db, customer_id)
        if not customer:
            return None
        # 租户隔离检查
        if customer.team_id != self.team_id:
            return None
        return customer

    def _check_opportunity_permission(self, opportunity_id: int) -> Optional[Opportunity]:
        """权限校验：用户是否有该商机的操作权限

        租户隔离：只能操作本团队的商机
        """
        opportunity = opportunity_crud.get_by_id(self.db, opportunity_id)
        if not opportunity:
            return None
        # 租户隔离检查
        if opportunity.team_id != self.team_id:
            return None
        return opportunity


__all__ = ["ActionEntry", "ActionEntryResult", "UserExecCtx"]