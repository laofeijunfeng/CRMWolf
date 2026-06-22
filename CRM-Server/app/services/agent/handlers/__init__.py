"""
Agent Handlers
工具处理器（支持 Preview）

核心设计：
- 遵循规范：CRUD 统一入口、team_id 必传
- 复用现有的 CRUD 层
- Pydantic 强制校验
- 新增：Preview 方法（生成变更计划）

安全机制：
- 所有 Handler 支持 preview 方法（生成变更预览）
- 危险工具（删除、赢单等）强制 Preview
"""

from typing import Dict, Any, Optional
from dataclasses import dataclass
import logging

logger = logging.getLogger(__name__)


@dataclass
class ToolResult:
    """工具执行结果（支持 Preview）"""
    success: bool
    error: Optional[str]
    data: Optional[Any]
    message: Optional[str]
    # ===== 新增：Preview 支持 =====
    waiting_for_user: bool = False  # 是否等待用户确认
    preview_data: Optional[Dict[str, Any]] = None  # Preview 变更计划


class SearchCustomerHandler:
    """搜索客户 Handler"""

    async def execute(
        self,
        db,
        team_id: int,
        user_id: int,
        params: Dict[str, Any],
    ) -> ToolResult:
        """执行搜索客户"""
        from app.crud.customer import customer_crud

        keyword = params.get("keyword")
        limit = params.get("limit", 5)

        if not keyword:
            return ToolResult(
                success=False,
                error="缺少 keyword 参数",
                message="请提供客户名称关键词",
            )

        try:
            # CRUD 统一入口
            customers, total = customer_crud.get_multi(
                db=db,
                team_id=team_id,
                keyword=keyword,
                limit=limit,
            )

            if not customers:
                return ToolResult(
                    success=True,
                    data=[],
                    message=f"未找到包含'{keyword}'的客户",
                )

            # 转换为统一格式
            result = [
                {
                    "id": c.id,
                    "name": c.account_name,
                    "hint": f"客户ID: {c.id}",
                }
                for c in customers
            ]

            return ToolResult(
                success=True,
                data=result,
                message=f"找到 {len(result)} 个客户",
            )

        except Exception as e:
            logger.error(f"Search customer failed: {str(e)}")
            return ToolResult(success=False, error=str(e))

    async def preview(
        self,
        db,
        team_id: int,
        user_id: int,
        params: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Preview：搜索客户（只读操作，无需 Preview）"""
        return {
            "description": f"搜索客户：{params.get('keyword', '未知')}",
            "changes": [],  # 只读操作
            "risk_level": "low"
        }


class SearchOpportunityHandler:
    """搜索商机 Handler"""

    async def execute(
        self,
        db,
        team_id: int,
        user_id: int,
        params: Dict[str, Any],
    ) -> ToolResult:
        """执行搜索商机"""
        from app.crud.opportunity import opportunity_crud

        keyword = params.get("keyword")
        customer_id = params.get("customer_id")

        if not keyword and not customer_id:
            return ToolResult(
                success=False,
                error="缺少 keyword 或 customer_id 参数",
            )

        try:
            # CRUD 统一入口
            if customer_id:
                opportunities, total = opportunity_crud.get_by_customer_id(
                    db=db,
                    customer_id=customer_id,
                    team_id=team_id,
                )
            else:
                opportunities = opportunity_crud.search_by_name(
                    db=db,
                    keyword=keyword,
                    team_id=team_id,
                )

            if not opportunities:
                return ToolResult(success=True, data=[], message="未找到商机")

            # 转换为统一格式
            result = [
                {
                    "id": o.id,
                    "name": o.opportunity_name,
                    "stage": o.current_stage_name,
                    "amount": o.amount,
                }
                for o in opportunities
            ]

            return ToolResult(
                success=True,
                data=result,
                message=f"找到 {len(result)} 个商机",
            )

        except Exception as e:
            logger.error(f"Search opportunity failed: {str(e)}")
            return ToolResult(success=False, error=str(e))

    async def preview(
        self,
        db,
        team_id: int,
        user_id: int,
        params: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Preview：搜索商机（只读操作，无需 Preview）"""
        return {
            "description": f"搜索商机：{params.get('keyword', '未知')}",
            "changes": [],  # 只读操作
            "risk_level": "low"
        }


class SetReminderHandler:
    """设置提醒 Handler"""

    async def execute(
        self,
        db,
        team_id: int,
        user_id: int,
        params: Dict[str, Any],
    ) -> ToolResult:
        """执行设置提醒"""
        from app.crud.customer_follow_up import customer_follow_up_crud
        from app.schemas.customer_follow_up import CustomerFollowUpCreate
        from datetime import datetime

        reminder_time = params.get("reminder_time")
        content = params.get("content")
        customer_id = params.get("customer_id")

        if not reminder_time or not content:
            return ToolResult(
                success=False,
                error="缺少 reminder_time 或 content 参数",
            )

        try:
            # Pydantic 强制校验
            try:
                next_follow_time = datetime.strptime(reminder_time, "%Y-%m-%d")
            except ValueError:
                return ToolResult(
                    success=False,
                    error=f"日期格式错误：{reminder_time}，应为 YYYY-MM-DD",
                )

            # 构建 FollowUp 数据
            follow_up_data = CustomerFollowUpCreate(
                content=f"提醒：{content}",
                follow_up_method="其他",
                next_follow_time=next_follow_time,
                customer_id=customer_id,
            )

            # CRUD 统一入口
            follow_up = customer_follow_up_crud.create(
                db=db,
                obj_in=follow_up_data,
                team_id=team_id,
                operator_id=str(user_id),
            )

            return ToolResult(
                success=True,
                data={
                    "reminder_id": follow_up.id,
                    "reminder_time": reminder_time,
                },
                message=f"提醒已设置：{reminder_time}",
            )

        except Exception as e:
            logger.error(f"Set reminder failed: {str(e)}")
            return ToolResult(success=False, error=str(e))

    async def preview(
        self,
        db,
        team_id: int,
        user_id: int,
        params: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Preview：设置提醒"""
        reminder_time = params.get("reminder_time", "未知时间")
        content = params.get("content", "未知内容")
        customer_id = params.get("customer_id")

        return {
            "description": f"设置提醒：{reminder_time}，内容：{content}",
            "changes": [
                {"field": "content", "from": None, "to": f"提醒：{content}"},
                {"field": "next_follow_time", "from": None, "to": reminder_time},
            ],
            "risk_level": "low"
        }


__all__ = [
    "ToolResult",
    "SearchCustomerHandler",
    "SearchOpportunityHandler",
    "SetReminderHandler",
]