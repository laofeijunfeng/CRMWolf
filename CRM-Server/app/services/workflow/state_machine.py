"""
CRM 状态机校验

硬编码的状态流转规则，防止 AI 跳过必要节点。
"""
from typing import Dict, Any, Optional, Tuple, List


class CRMStateMachine:
    """CRM 状态机（硬编码校验）"""

    # 状态流转规则（不可变）
    STATE_TRANSITIONS: Dict[str, Dict[str, List[str]]] = {
        "lead": {
            "NEW": ["FOLLOWING", "CONVERTED", "INVALID"],
            "FOLLOWING": ["CONVERTED", "INVALID"],
            "CONVERTED": [],  # 终态
            "INVALID": []     # 终态
        },
        "opportunity": {
            "FOLLOWING": ["WON", "LOST"],
            "WON": [],        # 终态
            "LOST": []        # 终态
        },
        "contract": {
            "DRAFT": ["PENDING_REVIEW", "TERMINATED"],
            "PENDING_REVIEW": ["SIGNED", "REJECTED", "TERMINATED"],
            "SIGNED": ["EFFECTIVE", "TERMINATED"],
            "EFFECTIVE": ["EXPIRED", "TERMINATED"],
            "EXPIRED": [],      # 终态
            "TERMINATED": [],   # 终态
            "REJECTED": ["DRAFT"]  # 拒绝后可以重新编辑
        },
        "customer": {
            "FOLLOWING": ["CONVERTED", "LOST", "INACTIVE"],
            "CONVERTED": [],    # 终态（已成交）
            "LOST": [],         # 终态（已流失）
            "INACTIVE": ["FOLLOWING"]  # 公海客户可以被重新领取
        }
    }

    # 状态映射（数字 → 字符串）
    STATUS_VALUE_MAP: Dict[str, Dict[int, str]] = {
        "opportunity": {
            0: "FOLLOWING",
            1: "WON",
            2: "LOST"
        },
        "customer": {
            0: "FOLLOWING",
            1: "CONVERTED",
            2: "LOST",
            3: "INACTIVE"
        },
        "lead": {
            0: "NEW",
            1: "FOLLOWING",
            2: "CONVERTED",
            3: "INVALID"
        }
    }

    def validate_transition(
        self,
        entity_type: str,
        from_status: Any,
        to_status: Any
    ) -> Tuple[bool, str]:
        """校验状态流转是否合法

        Args:
            entity_type: 实体类型
            from_status: 当前状态（可能是枚举值或整数）
            to_status: 目标状态

        Returns:
            (是否合法, 错误消息)
        """
        # 转换状态值为字符串
        from_status_str = self._status_to_string(entity_type, from_status)
        to_status_str = self._status_to_string(entity_type, to_status)

        # 获取允许的流转
        allowed_transitions = self.STATE_TRANSITIONS.get(entity_type, {}).get(from_status_str, [])

        if to_status_str in allowed_transitions:
            return True, ""

        return False, f"状态流转非法：{from_status_str} → {to_status_str}（允许的状态：{allowed_transitions})"

    def validate_precondition(
        self,
        step: Dict[str, Any],
        session: Dict[str, Any]
    ) -> Tuple[bool, str]:
        """校验步骤前置条件

        Args:
            step: 步骤定义
            session: Session 状态

        Returns:
            (是否满足, 错误消息)
        """
        precondition = step.get("precondition")

        if not precondition:
            return True, ""

        # 解析前置条件
        entity_context = session.get("entity_context", {})
        opportunities = entity_context.get("opportunities", [])

        # 商机相关前置条件
        if precondition == "opportunity_exists":
            if len(opportunities) == 0:
                return False, "客户无商机记录，无法执行此操作"

        if precondition == "opportunity_selected_or_single":
            selected_id = session.get("selected_opportunity_id")
            if not selected_id and len(opportunities) != 1:
                return False, "需要选择一个商机才能执行此操作"

        if precondition == "opportunity_is_won":
            selected_id = session.get("selected_opportunity_id")
            if not selected_id:
                return False, "未选择商机"
            # 检查商机状态
            selected_opp = next(
                (opp for opp in opportunities if opp.get("id") == selected_id),
                None
            )
            if not selected_opp:
                return False, "选择的商机不存在"
            if selected_opp.get("status") != 1:  # 1 = WON
                return False, "商机未赢单，无法执行此操作"

        # 步骤成功前置条件
        if precondition == "create_follow_up_success":
            last_result = session.get("last_result", {})
            if not last_result.get("success"):
                return False, "跟进记录创建失败，无法继续"

        if precondition == "win_opportunity_success":
            # 检查执行历史中是否有 win_opportunity 且成功
            execution_history = session.get("execution_history", [])
            win_executed = any(
                exec.get("step_id") == "win_opportunity" and exec.get("result", {}).get("success")
                for exec in execution_history
            )
            if not win_executed:
                return False, "商机未标记为赢单"

        # 用户确认前置条件
        if precondition == "user_confirmed_create_contract":
            user_choice = session.get("user_choice")
            if user_choice != "是，创建合同":
                return False, "用户未确认创建合同"

        return True, ""

    def get_required_fields(
        self,
        entity_type: str,
        action: str
    ) -> List[str]:
        """获取操作的必填字段

        Args:
            entity_type: 实体类型
            action: 操作类型

        Returns:
            必填字段列表
        """
        REQUIRED_FIELDS: Dict[str, Dict[str, List[str]]] = {
            "opportunity": {
                "create": ["opportunity_name", "total_amount", "user_count", "customer_id"],
                "win": ["opportunity_id"],
                "lose": ["opportunity_id"]
            },
            "contract": {
                "create": ["contract_name", "total_amount", "customer_id", "opportunity_id"],
                "sign": ["contract_id"]
            },
            "lead": {
                "convert": ["lead_id"]
            }
        }

        return REQUIRED_FIELDS.get(entity_type, {}).get(action, [])

    def is_terminal_state(self, entity_type: str, status: Any) -> bool:
        """检查是否是终态

        Args:
            entity_type: 实体类型
            status: 当前状态

        Returns:
            是否是终态
        """
        status_str = self._status_to_string(entity_type, status)
        allowed_transitions = self.STATE_TRANSITIONS.get(entity_type, {}).get(status_str, [])
        return len(allowed_transitions) == 0

    def _status_to_string(self, entity_type: str, status: Any) -> str:
        """将状态值转换为字符串

        Args:
            entity_type: 实体类型
            status: 状态值（可能是枚举、整数、字符串）

        Returns:
            状态字符串
        """
        if isinstance(status, str):
            return status.upper()

        if isinstance(status, int):
            return self.STATUS_VALUE_MAP.get(entity_type, {}).get(status, str(status))

        if hasattr(status, "value"):
            # 枚举类型
            if isinstance(status.value, int):
                return self.STATUS_VALUE_MAP.get(entity_type, {}).get(status.value, str(status.value))
            return str(status.value).upper()

        return str(status).upper()