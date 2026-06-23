"""
业务流程定义（硬编码）

所有业务流程定义在此文件中硬编码，AI 无法干预。
每个流程包含：触发关键词、步骤序列、前置条件、回滚点等。
"""
from typing import Dict, Any, Optional, List, Callable
import re


def _get_opportunities_from_context(session: Dict[str, Any]) -> List[Dict[str, Any]]:
    """从 session.entity_context.related_entities 中提取商机列表

    _build_entity_summary 返回的 context_summary 使用 related_entities 字段存储关联实体，
    其中 type="opportunity" 的为商机。

    Args:
        session: Workflow session 状态

    Returns:
        商机列表 [{id, name, status, amount, stage}, ...]
    """
    entity_context = session.get("entity_context", {})
    related_entities = entity_context.get("related_entities", [])
    # 过滤只取商机类型
    opportunities = [e for e in related_entities if e.get("type") == "opportunity"]
    return opportunities


class WorkflowDefinitions:
    """业务流程定义"""

    # 流程注册表
    WORKFLOW_REGISTRY: Dict[str, Dict[str, Any]] = {

        # ==================== 客户赢单流程 ====================
        "customer_win_flow": {
            "name": "客户确认采购（赢单场景）",
            "description": "当用户提到'确认采购'、'已签约'等关键词时触发",
            "trigger_keywords": ["确认采购", "已签约", "准备签合同", "赢单", "成交", "签合同"],
            "trigger_intent_types": ["create_follow_up"],  # 触发的意图类型

            # 流程步骤（硬编码，AI 无法改变顺序）
            "steps": [
                {
                    "id": "create_follow_up",
                    "type": "tool",
                    "tool_name": "follow_up_customer",
                    "required": True,
                    "description": "创建跟进记录",
                    "precondition": None,
                    "params_mapping": {
                        "customer_id": lambda session: session.get("entity_context", {}).get("entity_id"),
                        "customer_name": lambda session: session.get("entity_context", {}).get("basic_info", {}).get("account_name"),
                        "content": lambda session: session.get("user_input", "")  # 新增：从 session 获取用户输入
                    }
                },
                {
                    "id": "get_entity_context",
                    "type": "tool",
                    "tool_name": "get_entity_context",
                    "required": True,
                    "description": "获取客户商机列表",
                    "precondition": "create_follow_up_success",
                    "on_success": "check_opportunity_count",
                    "params_mapping": {
                        "entity_type": lambda session: session.get("entity_context", {}).get("entity_type", "customer"),
                        "entity_id": lambda session: session.get("entity_context", {}).get("entity_id"),
                        "entity_name": lambda session: session.get("entity_context", {}).get("basic_info", {}).get("account_name")
                    }
                },
                {
                    "id": "check_opportunity",
                    "type": "decision",
                    "required": True,
                    "description": "检查商机数量",
                    "branches": {
                        "no_opportunity": {
                            "condition": lambda session: len(_get_opportunities_from_context(session)) == 0,
                            "next_step": "ask_create_opportunity"
                        },
                        "single_opportunity": {
                            "condition": lambda session: len(_get_opportunities_from_context(session)) == 1,
                            "next_step": "ask_confirm_win_single"
                        },
                        "multiple_opportunities": {
                            "condition": lambda session: len(_get_opportunities_from_context(session)) > 1,
                            "next_step": "ask_select_opportunity"
                        }
                    }
                },
                {
                    "id": "ask_create_opportunity",
                    "type": "ask_user",
                    "required": True,
                    "description": "询问是否创建商机（无商机时）",
                    "question": "客户确认采购，但没有商机记录。是否创建商机？",
                    "options": ["是，创建商机", "否，暂不创建"],
                    "precondition": "check_opportunity == no_opportunity",
                    "on_user_choice": {
                        "是，创建商机": "create_opportunity_first",
                        "否，暂不创建": "workflow_complete"
                    }
                },
                {
                    "id": "create_opportunity_first",
                    "type": "ask_user",
                    "required": True,
                    "description": "收集创建商机所需信息",
                    "question": "请补充商机的预计总金额、预期成交日期、采购类型和采购方式",
                    "missing_fields": ["total_amount", "expected_closing_date", "purchase_type", "procurement_method_name"],
                    "field_options": {
                        "purchase_type": {
                            "type": "select",
                            "options": ["新购", "续购", "增购"],
                            "default": "新购"
                        },
                        "procurement_method_name": {
                            "type": "select",
                            "options_from_db": "procurement_methods",  # 从数据库查询
                            "default_from": "customer_procurement_method"  # 从客户获取默认值
                        }
                    },
                    "precondition": "user_choose_create_opportunity",
                    "on_user_response": "create_opportunity_for_win"
                },
                {
                    "id": "create_opportunity_for_win",
                    "type": "tool",
                    "tool_name": "create_opportunity",
                    "required": True,
                    "description": "创建商机（为后续赢单准备）",
                    "precondition": "user_provided_opportunity_info",
                    "on_success": "set_created_opportunity_id",
                    "rollback_point": True
                },
                {
                    "id": "ask_confirm_win_single",
                    "type": "ask_user",
                    "required": True,
                    "description": "确认赢单（单个商机）",
                    "question_template": lambda session: (
                        f"客户确认采购，是否标记商机「{_get_opportunities_from_context(session)[0]['name']}」为赢单？"
                        if _get_opportunities_from_context(session) else
                        "客户确认采购，是否标记为赢单？"
                    ),
                    "options": ["是，标记赢单", "否，暂不标记"],
                    "precondition": "check_opportunity == single_opportunity",
                    "on_user_choice": {
                        "是，标记赢单": "win_opportunity",
                        "否，暂不标记": "workflow_complete"
                    }
                },
                {
                    "id": "ask_select_opportunity",
                    "type": "ask_user",
                    "required": True,
                    "description": "选择商机（多个商机时）",
                    "question": "客户有多个跟进中商机，请选择确认采购的是哪个？",
                    "options_template": lambda session: [
                        f"{opp['name']} (金额: {opp.get('amount', '未知')}万, 阶段: {opp.get('stage', '未知')})"
                        for opp in _get_opportunities_from_context(session)
                    ],
                    "metadata_template": lambda session: {
                        "candidates": [
                            {"id": opp.get("id"), "name": opp.get("name"), "amount": opp.get("amount")}
                            for opp in _get_opportunities_from_context(session)
                        ]
                    },
                    "precondition": "check_opportunity == multiple_opportunities",
                    "on_user_choice": "set_selected_opportunity"
                },
                {
                    "id": "win_opportunity",
                    "type": "tool",
                    "tool_name": "win_opportunity",
                    "required": True,
                    "description": "标记商机为赢单",
                    "precondition": "opportunity_selected_or_single",
                    "params_mapping": {
                        "opportunity_id": lambda session: session.get("selected_opportunity_id") or
                            (_get_opportunities_from_context(session)[0].get("id") if len(_get_opportunities_from_context(session)) == 1 else None)
                    },
                    "rollback_point": True,
                    "on_success": "ask_create_contract"
                },
                {
                    "id": "ask_create_contract",
                    "type": "ask_user",
                    "required": False,
                    "description": "询问是否创建合同",
                    "question": "商机已标记为赢单。是否现在创建合同？",
                    "options": ["是，创建合同", "否，稍后创建"],
                    "precondition": "win_opportunity_success",
                    "on_user_choice": {
                        "是，创建合同": "create_contract",
                        "否，稍后创建": "workflow_complete"
                    }
                },
                {
                    "id": "create_contract",
                    "type": "tool",
                    "tool_name": "create_contract",
                    "required": False,
                    "description": "创建合同草稿",
                    "precondition": "user_confirmed_create_contract",
                    "params_mapping": {
                        "customer_id": lambda session: session.get("entity_context", {}).get("entity_id"),
                        "opportunity_id": lambda session: session.get("selected_opportunity_id") or session.get("created_opportunity_id"),
                        "customer_name": lambda session: session.get("entity_context", {}).get("entity_name")
                    },
                    "rollback_point": True
                }
            ],

            # 流程配置
            "timeout": 120,  # 总超时（秒）
            "max_retries": 3,  # 单步最大重试次数
            "session_timeout": 1800,  # Session 过期时间（30分钟）

            # 完成消息模板
            "complete_message_template": lambda session: (
                f"✅ 流程完成！\n\n"
                f"已执行操作：\n"
                f"- 创建跟进记录\n"
                f"- 标记商机「{session.get('selected_opportunity_name', '商机')}」为赢单\n"
                f"- {'创建合同草稿' if session.get('contract_created') else '（未创建合同）'}\n\n"
                f"💡 提示：您可以在合同模块继续完善合同信息。"
            )
        },

        # ==================== 线索转化流程 ====================
        "lead_convert_flow": {
            "name": "线索转客户",
            "description": "当用户提到'转化'、'转客户'等关键词时触发",
            "trigger_keywords": ["转客户", "转化", "线索转化", "线索转成客户"],
            "trigger_intent_types": ["follow_up_lead"],

            "steps": [
                {
                    "id": "create_follow_up",
                    "type": "tool",
                    "tool_name": "follow_up_lead",
                    "required": True,
                    "description": "创建线索跟进记录"
                },
                {
                    "id": "check_lead_status",
                    "type": "decision",
                    "required": True,
                    "branches": {
                        "can_convert": {
                            "condition": lambda session: session.get("entity_context", {}).get("status") in ["NEW", "FOLLOWING"],
                            "next_step": "ask_convert_confirmation"
                        },
                        "already_converted": {
                            "condition": lambda session: session.get("entity_context", {}).get("status") == "CONVERTED",
                            "next_step": "workflow_complete_with_message"
                        },
                        "invalid": {
                            "condition": lambda session: session.get("entity_context", {}).get("status") == "INVALID",
                            "next_step": "workflow_complete_with_error"
                        }
                    }
                },
                {
                    "id": "ask_convert_confirmation",
                    "type": "ask_user",
                    "required": True,
                    "question": "线索状态符合转化条件，是否转化为客户？",
                    "options": ["是，转化", "否，暂不转化"]
                },
                {
                    "id": "convert_lead",
                    "type": "tool",
                    "tool_name": "convert_lead",
                    "required": True,
                    "rollback_point": True
                },
                {
                    "id": "create_opportunity_for_new_customer",
                    "type": "ask_user",
                    "required": False,
                    "question": "客户已创建，是否同时创建商机？",
                    "options": ["是，创建商机", "否，稍后创建"]
                }
            ],

            "timeout": 60,
            "max_retries": 2
        }
    }

    def get(self, workflow_id: str) -> Optional[Dict[str, Any]]:
        """获取流程定义

        Args:
            workflow_id: 流程 ID

        Returns:
            流程定义字典，如果不存在返回 None
        """
        return self.WORKFLOW_REGISTRY.get(workflow_id)

    def match_workflow(
        self,
        user_input: str,
        intent_types: List[str],
        entity_type: str
    ) -> Optional[str]:
        """根据用户输入和意图匹配流程

        Args:
            user_input: 用户输入文本
            intent_types: AI 识别的意图类型列表
            entity_type: 当前实体类型

        Returns:
            匹配的流程 ID，如果无匹配返回 None
        """
        for workflow_id, workflow_def in self.WORKFLOW_REGISTRY.items():
            # 检查触发关键词
            trigger_keywords = workflow_def.get("trigger_keywords", [])
            keyword_matched = any(keyword in user_input for keyword in trigger_keywords)

            if not keyword_matched:
                continue

            # 检查触发意图类型（如果定义了）
            trigger_intents = workflow_def.get("trigger_intent_types", [])

            # 如果没有定义 trigger_intent_types，关键词匹配即可触发
            if not trigger_intents:
                return workflow_id

            # 如果定义了 trigger_intent_types，需要意图也匹配
            # 但是 intent_types 可能是空的，所以我们放宽条件：
            # 只要关键词匹配，即使 intent_types 为空也触发
            if trigger_intents:
                # 如果 intent_types 非空，检查是否有匹配
                if intent_types and any(intent in trigger_intents for intent in intent_types):
                    return workflow_id
                # 如果 intent_types 为空，但关键词匹配，也触发（降级策略）
                elif not intent_types:
                    return workflow_id

        return None

    def get_step(self, workflow_id: str, step_id: str) -> Optional[Dict[str, Any]]:
        """获取流程中的特定步骤

        Args:
            workflow_id: 流程 ID
            step_id: 步骤 ID

        Returns:
            步骤定义字典
        """
        workflow = self.get(workflow_id)
        if not workflow:
            return None

        for step in workflow.get("steps", []):
            if step.get("id") == step_id:
                return step

        return None

    def get_next_step(
        self,
        workflow_id: str,
        current_step_id: str,
        session: Dict[str, Any]
    ) -> Optional[Dict[str, Any]]:
        """获取下一个步骤

        Args:
            workflow_id: 流程 ID
            current_step_id: 当前步骤 ID
            session: Session 状态

        Returns:
            下一个步骤定义
        """
        workflow = self.get(workflow_id)
        if not workflow:
            return None

        steps = workflow.get("steps", [])

        # 找到当前步骤
        current_step = self.get_step(workflow_id, current_step_id)
        if not current_step:
            return None

        # 检查是否有分支
        branches = current_step.get("branches")
        if branches:
            # 根据条件匹配分支
            for branch_name, branch_config in branches.items():
                condition = branch_config.get("condition")
                if condition and condition(session):
                    next_step_id = branch_config.get("next_step")
                    return self.get_step(workflow_id, next_step_id)

        # 检查是否有用户选择后的处理
        on_user_choice = current_step.get("on_user_choice")
        if on_user_choice and session.get("user_choice"):
            choice = session.get("user_choice")
            if isinstance(on_user_choice, dict):
                next_step_id = on_user_choice.get(choice)
                if next_step_id:
                    return self.get_step(workflow_id, next_step_id)
            elif isinstance(on_user_choice, str):
                return self.get_step(workflow_id, on_user_choice)

        # 检查是否有成功后的处理
        on_success = current_step.get("on_success")
        if on_success and session.get("last_result", {}).get("success"):
            return self.get_step(workflow_id, on_success)

        # 默认：按顺序找下一个步骤
        for i, step in enumerate(steps):
            if step.get("id") == current_step_id and i < len(steps) - 1:
                return steps[i + 1]

        return None

    def list_all_workflows(self) -> List[Dict[str, Any]]:
        """列出所有流程

        Returns:
            流程列表（包含 ID、名称、描述）
        """
        return [
            {
                "id": workflow_id,
                "name": workflow_def.get("name"),
                "description": workflow_def.get("description"),
                "trigger_keywords": workflow_def.get("trigger_keywords", [])
            }
            for workflow_id, workflow_def in self.WORKFLOW_REGISTRY.items()
        ]