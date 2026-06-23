"""
ask_user 工具 Handler

用于暂停 Agent 循环，等待用户回复

这是 ReAct Agent + Human-in-the-Loop 架构的核心组件
"""
from typing import Dict, Any, Optional
from sqlalchemy.orm import Session


class AskUserHandler:
    """用户交互 Handler"""

    handler_type = "AskUserHandler"

    async def execute(
        self,
        db: Session,
        handler_config: Dict[str, Any],
        params: Dict[str, Any],
        user_id: int,
        user_feishu_open_id: Optional[str] = None,
        team_id: Optional[int] = None
    ) -> Dict[str, Any]:
        """
        执行用户询问

        Args:
            db: 数据库 Session
            handler_config: Handler 配置
            params: 包含 question, options, missing_fields, context_hint
            user_id: 用户 ID
            user_feishu_open_id: 飞书 Open ID（可选）
            team_id: 团队 ID

        Returns:
            返回等待状态，告知前端需要用户输入
            此返回会触发 Agent 循环暂停
        """
        question = params.get("question")
        options = params.get("options")
        missing_fields = params.get("missing_fields") or []  # 确保 non-None
        context_hint = params.get("context_hint")

        # 验证必要参数
        if not question:
            return {
                "success": False,
                "message": "缺少问题内容"
            }

        # 构建返回结果
        result = {
            "success": True,
            "action": "ask_user",
            "halts_loop": True,  # 关键：标记暂停循环
            "question": question,
            "options": options,
            "missing_fields": missing_fields,
            "context_hint": context_hint,
            "message": question  # 用于前端显示
        }

        # 如果有选项，构建选项列表（用于前端渲染选择组件）
        if options and len(options) > 0:
            result["options_display"] = [
                {"value": opt, "label": opt}
                for opt in options
            ]
            result["interaction_type"] = "select"  # 标记交互类型为选择

        # 如果有缺失字段，构建字段提示（用于前端渲染输入表单）
        if missing_fields and len(missing_fields) > 0:
            result["fields_hint"] = [
                {"field": field, "required": True}
                for field in missing_fields
            ]
            result["interaction_type"] = "input"  # 标记交互类型为输入

        # 如果既有选项又有缺失字段，标记为混合类型
        if options and missing_fields:
            result["interaction_type"] = "mixed"

        return result