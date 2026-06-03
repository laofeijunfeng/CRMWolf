"""PreviewRenderer

ActionPlan → 人类可读 diff 文本。

参见: CRM-Docs/requirements/AI-GLUE-REQUIREMENTS.md 九、核心组件设计 9.5
参见: CRM-Docs/plans/AI-GLUE-IMPLEMENTATION-PLAN.md Phase 3.2
"""

from typing import Dict, Any, Optional, List


class PreviewRenderer:
    """预览渲染器

    将 ActionPlan 转换为人类可读的 diff 文本。
    """

    # 动作类型描述模板
    ACTION_DESCRIPTIONS = {
        "create_follow_up": "创建跟进记录",
        "init_opportunity": "初始化商机",
        "update_amount": "更新商机金额",
        "update_stage": "更新商机阶段",
        "win_opportunity": "标记赢单",
        "lose_opportunity": "标记输单",
        "set_reminder": "设置提醒",
    }

    def render(self, plan: Dict[str, Any], entity_info: Optional[Dict[str, Any]] = None) -> str:
        """渲染预览文本

        Args:
            plan: ActionPlan 数据
            entity_info: 实体信息（name, type, id）

        Returns:
            str: 预览文本
        """
        action_type = plan.get("action_type", "")
        description = plan.get("description", "")
        changes = plan.get("changes", [])

        # 动作描述
        action_desc = self.ACTION_DESCRIPTIONS.get(action_type, action_type)

        # 构建预览文本
        lines = [f"⏱ 预览：{action_desc}"]

        # 实体信息
        if entity_info:
            entity_name = entity_info.get("name", "")
            entity_id = entity_info.get("id", "")
            entity_type = entity_info.get("type", "")

            if entity_type == "Opportunity":
                lines.append(f"  商机：{entity_name}（#{entity_id}）")
            elif entity_type == "Customer":
                lines.append(f"  客户：{entity_name}（#{entity_id}）")

        # 变更详情
        for change in changes:
            field = change.get("field", "")
            to_value = change.get("to_value")
            from_value = change.get("from_value")

            # 字段显示名
            field_display = self._get_field_display(field)

            # 格式化值
            to_display = self._format_value(field, to_value)
            from_display = self._format_value(field, from_value) if from_value else "（无）"

            # 变更行
            if from_value:
                lines.append(f"  {field_display}：{from_display} → {to_display}")
            else:
                lines.append(f"  {field_display}：{to_display}")

        # 提示语
        lines.append("")
        lines.append("回「确认」执行；要改就说如「金额 38 万」；取消回「取消」。")

        return "\n".join(lines)

    def render_receipt(self, action_type: str, result: Dict[str, Any]) -> str:
        """渲染执行回执

        Args:
            action_type: 动作类型
            result: 执行结果

        Returns:
            str: 回执文本
        """
        action_desc = self.ACTION_DESCRIPTIONS.get(action_type, action_type)

        # 构建回执
        lines = [f"✅ {action_desc}已完成"]

        # 补充信息
        if result.get("opportunity_id"):
            lines.append(f"  商机 #${result['opportunity_id']}")

        if result.get("amount"):
            lines.append(f"  金额：{self._format_amount(result['amount'])}")

        if result.get("follow_up_id"):
            lines.append(f"  跟进记录已创建")

        return "\n".join(lines)

    def render_error(self, error_type: str, message: str) -> str:
        """渲染错误提示

        Args:
            error_type: 错误类型
            message: 错误消息

        Returns:
            str: 错误文本
        """
        # 错误类型描述
        error_descs = {
            "AI_PERMISSION_DENIED": "操作失败：您没有权限执行该操作。",
            "AI_ENTITY_NOT_FOUND": "操作失败：找不到指定的数据。",
            "AI_MISSING_FIELD": "信息不完整：请补充必要信息。",
            "AI_RISK_REJECTED": "操作失败：该操作风险过高，已被拒绝。",
            "AI_DUPLICATE_ACTION": "操作失败：该操作已执行过。",
            "AI_EXECUTION_FAILED": "操作失败：执行过程中发生错误。",
        }

        desc = error_descs.get(error_type, f"操作失败：{message}")

        return f"❌ {desc}"

    def _get_field_display(self, field: str) -> str:
        """获取字段显示名"""
        field_names = {
            "amount": "金额",
            "stage_id": "阶段",
            "name": "名称",
            "content": "跟进内容",
            "follow_up_type": "跟进方式",
            "reminder_date": "提醒时间",
            "reason": "输单原因",
        }
        return field_names.get(field, field)

    def _format_value(self, field: str, value: Any) -> str:
        """格式化值"""
        if value is None:
            return "（无）"

        if field == "amount":
            return self._format_amount(value)

        if field == "stage_id":
            # TODO: 从 stage_id 获取阶段名称
            return f"阶段#{value}"

        if isinstance(value, (int, float)):
            return str(value)

        return str(value)

    def _format_amount(self, amount: float) -> str:
        """格式化金额"""
        if amount >= 10000:
            wan = amount / 10000
            # 整数万时不显示小数
            if wan == int(wan):
                return f"{int(wan)}万"
            return f"{wan:.1f}万"
        return f"{amount:,.0f}"


__all__ = ["PreviewRenderer"]