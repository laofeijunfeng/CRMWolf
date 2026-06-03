"""ActionExecutor（合规版 - 入口函数模式）

执行 AI 动作，通过入口函数层调用 CRUD。

整改要点（R-1~R-5 合规）：
- R-1: 末级调用是入口函数，不是 CRUD
- R-2: 移除 _build_preview_from_slots（删除第二套 Preview）
- R-3: 调用入口函数签名 (preview: bool) → ActionEntryResult
- R-4: action_id 从入口函数获取（统一归因）
- R-5: EntityResolver 使用只读路径（不在此文件处理）
- R-D: 使用 UserExecCtx 替代裸 User 参数

参见: CRM-Docs/plans/AI-GLUE-DEEP-REMEDIATION-PLAN.md Phase 2
参见: CRM-Docs/requirements/AI-GLUE-REQUIREMENTS.md 17.3 R-D
"""

from typing import Dict, Any, Optional, List
from dataclasses import dataclass
import logging
from datetime import datetime, date

from sqlalchemy.orm import Session

from app.glue.core.session import PendingAction
from app.models.user import User
from app.services.ai.action_entry import ActionEntry, ActionEntryResult, UserExecCtx


logger = logging.getLogger(__name__)


@dataclass
class ExecutionResult:
    """执行结果"""

    success: bool
    message: str
    action_id: Optional[str] = None
    data: Optional[Dict[str, Any]] = None
    error: Optional[str] = None


@dataclass
class PreviewResult:
    """预览结果"""

    success: bool
    message: str
    action_id: Optional[str] = None
    preview_data: Optional[Dict[str, Any]] = None  # ActionPlan.model_dump()
    requires_confirmation: bool = True
    error: Optional[str] = None


class ActionExecutor:
    """动作执行器（合规版）

    调用入口函数层，不自建 Preview，不直接调用 CRUD。
    满足 Single Writer 原则：末级调用是 action_entry → CRUD。

    R-D 合规：使用 UserExecCtx 替代裸 User 参数
    """

    def __init__(self, db: Session, tenant_id: int, user_id: int):
        """初始化动作执行器

        Args:
            db: 数据库会话（传递给入口函数）
            tenant_id: 租户 ID（用于验证）
            user_id: 用户 ID（用于权限校验）
        """
        self.db = db
        self.tenant_id = tenant_id
        self.user_id = user_id

    def _get_user(self) -> Optional[User]:
        """获取用户对象（用于创建 UserExecCtx）"""
        return self.db.query(User).filter(User.id == self.user_id).first()

    def _build_user_ctx(self, user: User) -> UserExecCtx:
        """构建用户执行上下文（R-D 合规）

        Args:
            user: User 模型实例

        Returns:
            UserExecCtx 实例
        """
        return UserExecCtx.from_user(user, is_ai=True, source="glue")

    def _get_intent_type(self, pending: PendingAction) -> Optional[str]:
        """获取意图类型（兼容旧 skill_name）"""
        if pending.intent_type:
            return pending.intent_type

        # 从旧 skill_name 提取
        legacy_map = {
            "create_follow_up": "create_follow_up",
            "set_reminder": "set_reminder",
            "init_opportunity": "init_opportunity",
            "update_amount": "update_amount",
            "advance_stage": "update_stage",
            "win_opportunity": "win_opportunity",
            "lose_opportunity": "lose_opportunity",
        }
        return legacy_map.get(pending.skill_name)

    async def preview(self, pending: PendingAction) -> PreviewResult:
        """生成预览

        调用 action_entry(preview=True)，返回单一 truth 的 ActionPlan。

        Args:
            pending: 待执行的 pending action

        Returns:
            PreviewResult: 预览结果
        """
        if not pending:
            return PreviewResult(
                success=False,
                message="无待执行操作。",
                error="invalid_pending",
            )

        # 获取用户
        user = self._get_user()
        if not user:
            return PreviewResult(
                success=False,
                message="用户不存在。",
                error="user_not_found",
            )

        # R-D: 构建用户执行上下文
        user_ctx = self._build_user_ctx(user)

        # 获取意图类型
        intent_type = self._get_intent_type(pending)
        if not intent_type:
            return PreviewResult(
                success=False,
                message="缺少意图类型信息。",
                error="missing_intent_type",
            )

        # 创建入口函数实例（使用 UserExecCtx）
        entry = ActionEntry(self.db, user_ctx)

        # 调用入口函数的 preview 态
        result = self._call_entry_preview(entry, intent_type, pending.slots)

        # 处理结果
        if result.status == "failed":
            return PreviewResult(
                success=False,
                message=result.error or "预览生成失败",
                error="preview_failed",
            )

        # 返回预览结果（单一 truth）
        return PreviewResult(
            success=True,
            message=f"预览：即将执行 {intent_type}",
            action_id=result.action_id,
            preview_data=result.plan.model_dump() if result.plan else None,
            requires_confirmation=result.requires_confirmation,
        )

    async def execute(
        self,
        pending: PendingAction,
        action_id: str,  # 从 preview 继承的 action_id
    ) -> ExecutionResult:
        """执行动作

        调用 action_entry(preview=False)，使用同一 action_id。

        Args:
            pending: 待执行的 pending action
            action_id: 从 preview 继承的 action_id（R-4 归因）

        Returns:
            ExecutionResult: 执行结果
        """
        if not pending:
            return ExecutionResult(
                success=False,
                message="无待执行操作。",
                error="invalid_pending",
            )

        # 获取用户
        user = self._get_user()
        if not user:
            return ExecutionResult(
                success=False,
                message="用户不存在。",
                error="user_not_found",
            )

        # R-D: 构建用户执行上下文
        user_ctx = self._build_user_ctx(user)

        # 获取意图类型
        intent_type = self._get_intent_type(pending)
        if not intent_type:
            return ExecutionResult(
                success=False,
                message="缺少意图类型信息。",
                error="missing_intent_type",
            )

        # 创建入口函数实例（使用 UserExecCtx）
        entry = ActionEntry(self.db, user_ctx)

        # 调用入口函数的 execute 态（绑定同一 action_id）
        result = self._call_entry_execute(entry, intent_type, pending.slots, action_id)

        # 处理结果
        if result.status == "failed":
            return ExecutionResult(
                success=False,
                message=result.error or "执行失败",
                error="execution_failed",
            )

        # 返回执行结果
        return ExecutionResult(
            success=True,
            message=self._build_success_message(intent_type, result.data),
            action_id=result.action_id,
            data=result.data,
        )

    def _call_entry_preview(
        self,
        entry: ActionEntry,
        intent_type: str,
        slots: Dict[str, Any],
    ) -> ActionEntryResult:
        """调用入口函数的 preview 态

        Args:
            entry: 入口函数实例
            intent_type: 意图类型
            slots: 槽位数据

        Returns:
            ActionEntryResult: 入口函数返回结果
        """
        # 根据意图类型分发
        if intent_type == "create_follow_up":
            return entry.create_follow_up(
                customer_id=slots.get("customer_id"),
                content=slots.get("content"),
                follow_up_time=self._parse_datetime(slots.get("follow_up_time")),
                method=slots.get("method", "电话"),
                next_action=slots.get("next_action"),
                opportunity_id=slots.get("opportunity_id"),
                preview=True,
            )

        elif intent_type == "set_reminder":
            return entry.set_reminder(
                customer_id=slots.get("customer_id"),
                reminder_time=self._parse_datetime(slots.get("reminder_time")),
                content=slots.get("content"),
                opportunity_id=slots.get("opportunity_id"),
                preview=True,
            )

        elif intent_type == "init_opportunity":
            return entry.init_opportunity(
                customer_id=slots.get("customer_id"),
                opportunity_name=slots.get("opportunity_name"),
                procurement_method_id=slots.get("procurement_method_id"),
                preview=True,
            )

        elif intent_type == "update_amount":
            return entry.update_amount(
                opportunity_id=slots.get("opportunity_id"),
                amount=float(slots.get("amount", 0)),
                user_count=slots.get("user_count"),
                preview=True,
            )

        elif intent_type == "update_stage":
            return entry.update_stage(
                opportunity_id=slots.get("opportunity_id"),
                target_stage_template_id=slots.get("target_stage_template_id"),
                preview=True,
            )

        elif intent_type == "win_opportunity":
            return entry.win_opportunity(
                opportunity_id=slots.get("opportunity_id"),
                actual_amount=slots.get("actual_amount"),
                actual_closing_date=self._parse_date(slots.get("actual_closing_date")),
                preview=True,
            )

        elif intent_type == "lose_opportunity":
            return entry.lose_opportunity(
                opportunity_id=slots.get("opportunity_id"),
                loss_reason=slots.get("loss_reason"),
                preview=True,
            )

        else:
            return ActionEntryResult(
                action_id="",
                status="failed",
                error=f"不支持的意图类型：{intent_type}",
            )

    def _call_entry_execute(
        self,
        entry: ActionEntry,
        intent_type: str,
        slots: Dict[str, Any],
        action_id: str,
    ) -> ActionEntryResult:
        """调用入口函数的 execute 态

        Args:
            entry: 入口函数实例
            intent_type: 意图类型
            slots: 槽位数据
            action_id: 绑定的 action_id（R-4 归因）

        Returns:
            ActionEntryResult: 入口函数返回结果
        """
        # 根据意图类型分发
        if intent_type == "create_follow_up":
            return entry.create_follow_up(
                customer_id=slots.get("customer_id"),
                content=slots.get("content"),
                follow_up_time=self._parse_datetime(slots.get("follow_up_time")),
                method=slots.get("method", "电话"),
                next_action=slots.get("next_action"),
                opportunity_id=slots.get("opportunity_id"),
                preview=False,
                action_id=action_id,
            )

        elif intent_type == "set_reminder":
            return entry.set_reminder(
                customer_id=slots.get("customer_id"),
                reminder_time=self._parse_datetime(slots.get("reminder_time")),
                content=slots.get("content"),
                opportunity_id=slots.get("opportunity_id"),
                preview=False,
                action_id=action_id,
            )

        elif intent_type == "init_opportunity":
            return entry.init_opportunity(
                customer_id=slots.get("customer_id"),
                opportunity_name=slots.get("opportunity_name"),
                procurement_method_id=slots.get("procurement_method_id"),
                preview=False,
                action_id=action_id,
            )

        elif intent_type == "update_amount":
            return entry.update_amount(
                opportunity_id=slots.get("opportunity_id"),
                amount=float(slots.get("amount", 0)),
                user_count=slots.get("user_count"),
                preview=False,
                action_id=action_id,
            )

        elif intent_type == "update_stage":
            return entry.update_stage(
                opportunity_id=slots.get("opportunity_id"),
                target_stage_template_id=slots.get("target_stage_template_id"),
                preview=False,
                action_id=action_id,
            )

        elif intent_type == "win_opportunity":
            return entry.win_opportunity(
                opportunity_id=slots.get("opportunity_id"),
                actual_amount=slots.get("actual_amount"),
                actual_closing_date=self._parse_date(slots.get("actual_closing_date")),
                preview=False,
                action_id=action_id,
            )

        elif intent_type == "lose_opportunity":
            return entry.lose_opportunity(
                opportunity_id=slots.get("opportunity_id"),
                loss_reason=slots.get("loss_reason"),
                preview=False,
                action_id=action_id,
            )

        else:
            return ActionEntryResult(
                action_id=action_id,
                status="failed",
                error=f"不支持的意图类型：{intent_type}",
            )

    def _parse_datetime(self, value: Optional[str]) -> Optional[datetime]:
        """解析 datetime 字符串"""
        if not value:
            return None
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None

    def _parse_date(self, value: Optional[str]) -> Optional[date]:
        """解析 date 字符串"""
        if not value:
            return None
        try:
            return date.fromisoformat(value)
        except ValueError:
            return None

    def _build_success_message(self, intent_type: str, data: Optional[Dict[str, Any]]) -> str:
        """构建成功消息"""
        templates = {
            "create_follow_up": "跟进记录已创建",
            "set_reminder": "提醒已设置",
            "init_opportunity": "商机已创建",
            "update_amount": f"金额已更新为 {data.get('total_amount', 0) if data else 0}",
            "update_stage": f"阶段已更新为 {data.get('current_stage', '') if data else ''}",
            "win_opportunity": "商机已标记为赢单",
            "lose_opportunity": "商机已标记为输单",
        }
        return templates.get(intent_type, "操作已完成")


__all__ = [
    "ExecutionResult",
    "PreviewResult",
    "ActionExecutor",
    "UserExecCtx",  # R-D: 暴露给调用方
]