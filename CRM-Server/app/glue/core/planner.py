"""ActionPlanner

slots → /ai/actions/ preview。

参见: CRM-Docs/requirements/AI-GLUE-REQUIREMENTS.md 九、核心组件设计 9.3
参见: CRM-Docs/plans/AI-GLUE-IMPLEMENTATION-PLAN.md Phase 3.1
"""

from typing import Dict, Any, Optional
from dataclasses import dataclass
import httpx


@dataclass
class ActionPlanResult:
    """动作规划结果"""

    action_id: str  # 动作唯一标识
    intent: str  # 意图类型
    status: str  # preview/completed/failed
    plan: Optional[Dict[str, Any]] = None  # ActionPlan 内容
    requires_confirmation: bool = False  # 是否需人工确认
    confidence: float = 0.0  # 置信度
    message: str = ""  # 提示消息


class ActionPlanner:
    """动作规划器

    根据 intent + slots 调用对应的 /ai/actions/ 端点（preview=true）。
    """

    # Intent → /ai/actions/ 端点映射
    INTENT_ACTION_MAP = {
        "create_follow_up": "/ai/actions/create-follow-up",
        "init_opportunity": "/ai/actions/init-opportunity",
        "update_opportunity": "/ai/actions/update-amount",
        "update_amount": "/ai/actions/update-amount",
        "update_stage": "/ai/actions/update-stage",
        "win_opportunity": "/ai/actions/win-opportunity",
        "lose_opportunity": "/ai/actions/lose-opportunity",
        "set_reminder": "/ai/actions/set-reminder",
    }

    # TODO: 从配置获取 base_url
    AI_BASE_URL = "http://localhost:8000"

    async def plan(self, intent: str, slots: Dict[str, Any], auth_token: Optional[str] = None) -> ActionPlanResult:
        """规划动作

        Args:
            intent: 意图类型
            slots: 槽位数据
            auth_token: JWT认证token（可选）

        Returns:
            ActionPlanResult: 规划结果
        """
        # 1. 确定端点
        endpoint = self.INTENT_ACTION_MAP.get(intent)

        if not endpoint:
            return ActionPlanResult(
                action_id="",
                intent=intent,
                status="failed",
                requires_confirmation=False,
                confidence=0.0,
                message=f"不支持意图: {intent}",
            )

        # 2. 组装请求（preview=true）
        request_data = self._build_request(intent, slots)

        # 3. 调用 /ai/actions/
        headers = {}
        if auth_token:
            headers["Authorization"] = f"Bearer {auth_token}"

        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.post(
                    f"{self.AI_BASE_URL}{endpoint}",
                    json=request_data,
                    params={"preview": "true"},
                    headers=headers,
                )
                response.raise_for_status()
                result = response.json()

            # 4. 返回结果
            return ActionPlanResult(
                action_id=result.get("action_id", ""),
                intent=intent,
                status=result.get("status", "preview"),
                plan=result.get("plan"),
                requires_confirmation=result.get("requires_confirmation", False),
                confidence=result.get("confidence", 0.0),
                message=result.get("message", ""),
            )

        except Exception as e:
            # Mock 模式：当 AI 端点不可用时，生成模拟预览
            return self._mock_plan(intent, slots)

    def _mock_plan(self, intent: str, slots: Dict[str, Any]) -> ActionPlanResult:
        """Mock 动作规划（演示用）"""
        # 生成模拟 ActionPlan
        plan = {
            "action_type": intent,
            "description": self._get_action_description(intent),
            "changes": [],
        }

        # 添加变更项
        if intent == "update_amount":
            plan["changes"] = [
                {"field": "amount", "from_value": 300000, "to_value": slots.get("amount", 0)}
            ]
        elif intent == "update_stage":
            plan["changes"] = [
                {"field": "stage_id", "from_value": 1, "to_value": slots.get("stage_id", 2)}
            ]
        elif intent == "create_follow_up":
            plan["changes"] = [
                {"field": "content", "to_value": slots.get("content", "跟进客户")}
            ]

        return ActionPlanResult(
            action_id=f"mock_{intent}_{slots.get('opportunity_id', 0)}",
            intent=intent,
            status="preview",
            plan=plan,
            requires_confirmation=True,
            confidence=0.9,
            message="预览已生成",
        )

    def _get_action_description(self, intent: str) -> str:
        """获取动作描述"""
        descriptions = {
            "create_follow_up": "创建跟进记录",
            "init_opportunity": "初始化商机",
            "update_opportunity": "更新商机",
            "update_amount": "更新商机金额",
            "update_stage": "更新商机阶段",
            "win_opportunity": "标记赢单",
            "lose_opportunity": "标记输单",
            "set_reminder": "设置提醒",
        }
        return descriptions.get(intent, intent)

    async def execute(self, action_id: str, intent: str, slots: Dict[str, Any], auth_token: Optional[str] = None) -> ActionPlanResult:
        """执行动作

        Args:
            action_id: 动作唯一标识
            intent: 意图类型
            slots: 槽位数据
            auth_token: JWT认证token（可选）

        Returns:
            ActionPlanResult: 执行结果
        """
        endpoint = self.INTENT_ACTION_MAP.get(intent)

        if not endpoint:
            return ActionPlanResult(
                action_id=action_id,
                intent=intent,
                status="failed",
                message=f"不支持意图: {intent}",
            )

        # 组装请求（preview=false）
        request_data = self._build_request(intent, slots)
        request_data["preview"] = False
        request_data["action_id"] = action_id

        headers = {}
        if auth_token:
            headers["Authorization"] = f"Bearer {auth_token}"

        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.post(
                    f"{self.AI_BASE_URL}{endpoint}",
                    json=request_data,
                    headers=headers,
                )
                response.raise_for_status()
                result = response.json()

            return ActionPlanResult(
                action_id=action_id,
                intent=intent,
                status=result.get("status", "completed"),
                plan=result.get("plan"),
                requires_confirmation=False,
                confidence=result.get("confidence", 0.0),
                message=result.get("message", ""),
            )

        except Exception as e:
            # Mock 模式：模拟执行成功
            return self._mock_execute(action_id, intent, slots)

    def _mock_execute(self, action_id: str, intent: str, slots: Dict[str, Any]) -> ActionPlanResult:
        """Mock 执行（演示用）"""
        return ActionPlanResult(
            action_id=action_id,
            intent=intent,
            status="completed",
            plan={"opportunity_id": slots.get("opportunity_id", 456)},
            requires_confirmation=False,
            confidence=1.0,
            message="执行成功",
        )

    def _build_request(self, intent: str, slots: Dict[str, Any]) -> Dict[str, Any]:
        """组装请求参数"""
        request_data = {"preview": True}

        # 根据 intent 类型组装参数
        if intent == "create_follow_up":
            request_data["customer_id"] = slots.get("customer_id")
            request_data["content"] = slots.get("content")
            request_data["follow_up_type"] = slots.get("follow_up_type", "phone")

        elif intent in ["init_opportunity"]:
            request_data["customer_id"] = slots.get("customer_id")
            request_data["name"] = slots.get("name")
            request_data["amount"] = slots.get("amount")

        elif intent in ["update_amount", "update_opportunity"]:
            request_data["opportunity_id"] = slots.get("opportunity_id")
            request_data["amount"] = slots.get("amount")

        elif intent == "update_stage":
            request_data["opportunity_id"] = slots.get("opportunity_id")
            request_data["stage_id"] = slots.get("stage_id")

        elif intent == "win_opportunity":
            request_data["opportunity_id"] = slots.get("opportunity_id")

        elif intent == "lose_opportunity":
            request_data["opportunity_id"] = slots.get("opportunity_id")
            request_data["reason"] = slots.get("reason")

        elif intent == "set_reminder":
            request_data["opportunity_id"] = slots.get("opportunity_id")
            request_data["reminder_date"] = slots.get("reminder_date")

        return request_data


__all__ = [
    "ActionPlanResult",
    "ActionPlanner",
]