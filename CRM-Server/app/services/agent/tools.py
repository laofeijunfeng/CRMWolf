"""
Agent Tool Registry
工具定义 + Handler 注册

核心设计：
- 完整的 JSON Schema（参数定义）
- 复用现有的 skills handlers
- 提供工具定义文本（用于 System Prompt）

遵循规范：
- CRUD 统一入口
- team_id 必传
- Pydantic 强制校验
"""

from typing import Dict, Any, List, Optional
from dataclasses import dataclass
import logging

logger = logging.getLogger(__name__)


@dataclass
class ToolResult:
    """工具执行结果（支持 Preview）"""
    success: bool
    error: Optional[str] = None
    data: Optional[Any] = None
    message: Optional[str] = None
    # ===== 新增：Preview 支持 =====
    waiting_for_user: bool = False  # 是否等待用户确认
    preview_data: Optional[Dict[str, Any]] = None  # Preview 变更计划


class ToolRegistry:
    """工具注册表"""

    def __init__(self, db, team_id: int):
        """
        初始化工具注册表

        Args:
            db: 数据库会话
            team_id: 团队 ID
        """
        self.db = db
        self.team_id = team_id

        # 注册所有工具
        self.tools = self._register_tools()
        self.handlers = self._register_handlers()

    def get_tools_schema(self) -> List[Dict[str, Any]]:
        """
        获取工具 Schema（JSON 格式）

        Returns:
            List[Dict]: 工具定义列表
        """
        return self.tools

    def get_tools_definition(self) -> str:
        """
        获取工具定义（文本格式，用于 System Prompt）

        Returns:
            str: 工具定义文本
        """
        definition = "【可用工具】\n\n"

        for tool in self.tools:
            definition += f"### {tool['name']}\n"
            definition += f"{tool['description']}\n\n"

            # 参数说明
            definition += "**参数**：\n"
            properties = tool['input_schema'].get('properties', {})
            required = tool['input_schema'].get('required', [])

            for param_name, param_info in properties.items():
                is_required = param_name in required
                param_desc = param_info.get('description', '')
                param_type = param_info.get('type', 'unknown')

                definition += f"- `{param_name}`（{'必填' if is_required else '可选'}，{param_type}）：{param_desc}\n"

            definition += "\n"

        return definition

    def get_handler(self, tool_name: str) -> tuple[Any, Dict[str, Any]]:
        """
        获取工具 Handler + config

        Args:
            tool_name: 工具名称

        Returns:
            tuple[Any, Dict]: (Handler实例, handler_config)
        """
        entry = self.handlers.get(tool_name)

        if not entry:
            logger.warning(f"Tool handler not found: {tool_name}")
            return None, {}

        return entry.get("handler"), entry.get("config", {})

    def _register_tools(self) -> List[Dict[str, Any]]:
        """
        注册所有工具

        Returns:
            List[Dict]: 工具列表
        """
        return [
            # ===== 实体搜索工具 =====

            {
                "name": "search_customer",
                "description": """搜索客户记录。

用途：在创建跟进/商机之前，必须先找到客户
参数：keyword（客户名称关键词）
返回：客户列表（ID、名称、最近跟进时间）

示例：
- keyword="光大证券" → [{"id": 123, "name": "光大证券股份有限公司"}]
- keyword="证券" → [光大证券, 中信证券, 国泰君安]（多个候选）

依赖：后续工具需要 customer_id
""",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "keyword": {
                            "type": "string",
                            "description": "客户名称关键词（口语化，如'光大证券')"
                        },
                        "limit": {
                            "type": "integer",
                            "description": "返回数量限制（默认5，最多10）"
                        },
                    },
                    "required": ["keyword"],
                },
            },

            {
                "name": "search_opportunity",
                "description": """搜索商机记录。

用途：在更新阶段/赢单之前，必须先找到商机
参数：keyword（商机名称关键词）或 customer_id
返回：商机列表（ID、名称、阶段、金额）

示例：
- keyword="光大证券立项" → [{"id": 456, "name": "光大证券立项项目"}]
- customer_id=123 → [客户的所有商机]

依赖：后续工具需要 opportunity_id
""",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "keyword": {
                            "type": "string",
                            "description": "商机名称关键词"
                        },
                        "customer_id": {
                            "type": "integer",
                            "description": "客户 ID（查找该客户的所有商机）"
                        },
                    },
                    "required": [],  # keyword 或 customer_id 至少一个
                },
            },

            # ===== 跟进工具 =====

            {
                "name": "follow_up_customer",
                "description": """创建客户跟进记录。

用途：记录与客户的沟通情况
依赖：必须先调用 search_customer 获取 customer_id
参数：
- customer_id（必填）：从 search_customer 获取
- content（必填）：跟进内容（总结用户的描述）
- method（可选）：跟进方式（电话/微信/邮件/拜访/其他）
- next_follow_time（可选）：下次跟进时间

示例：
用户："跟进光大证券，最近在走立项流程"
→ search_customer → customer_id=123
→ follow_up_customer(customer_id=123, content="最近在走立项流程")
""",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "customer_id": {
                            "type": "integer",
                            "description": "客户ID（必须先通过 search_customer 获取）"
                        },
                        "content": {
                            "type": "string",
                            "description": "跟进内容（总结用户的描述）"
                        },
                        "method": {
                            "type": "string",
                            "enum": ["电话", "微信", "邮件", "拜访", "其他"],
                            "description": "跟进方式（根据描述判断，默认'其他')"
                        },
                        "next_follow_time": {
                            "type": "string",
                            "description": "下次跟进时间（YYYY-MM-DD格式）"
                        },
                    },
                    "required": ["customer_id", "content"],
                },
            },

            {
                "name": "follow_up_lead",
                "description": """创建线索跟进记录。

用途：记录与线索的沟通情况
依赖：必须先调用 search_lead 获取 lead_id
参数：
- lead_id（必填）：从 search_lead 获取
- content（必填）：跟进内容
""",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "lead_id": {
                            "type": "integer",
                            "description": "线索ID（必须先通过 search_lead 获取）"
                        },
                        "content": {
                            "type": "string",
                            "description": "跟进内容"
                        },
                    },
                    "required": ["lead_id", "content"],
                },
            },

            # ===== 商机工具 =====

            {
                "name": "create_opportunity",
                "description": """创建商机记录。

用途：为客户创建商机
依赖：必须先调用 search_customer 获取 customer_id
参数：
- customer_id（必填）：从 search_customer 获取
- opportunity_name（可选）：商机名称（默认：客户名+项目）
- amount（必填）：商机金额（单位：万元）

示例：
用户："为光大证券创建商机，金额50万"
→ search_customer → customer_id=123
→ create_opportunity(customer_id=123, amount=50)
""",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "customer_id": {
                            "type": "integer",
                            "description": "客户ID（必须先通过 search_customer 获取）"
                        },
                        "opportunity_name": {
                            "type": "string",
                            "description": "商机名称（可选，默认自动生成）"
                        },
                        "amount": {
                            "type": "number",
                            "description": "商机金额（单位：万元）"
                        },
                    },
                    "required": ["customer_id", "amount"],
                },
            },

            {
                "name": "update_stage",
                "description": """更新商机阶段。

用途：推进商机阶段
依赖：必须先调用 search_opportunity 获取 opportunity_id
参数：
- opportunity_id（必填）：从 search_opportunity 获取
- stage（必填）：目标阶段（需求确认/方案沟通/报价谈判/合同签订）

示例：
用户："光大证券立项项目推进到报价谈判阶段"
→ search_opportunity → opportunity_id=456
→ update_stage(opportunity_id=456, stage="报价谈判")
""",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "opportunity_id": {
                            "type": "integer",
                            "description": "商机ID（必须先通过 search_opportunity 获取）"
                        },
                        "stage": {
                            "type": "string",
                            "enum": ["需求确认", "方案沟通", "报价谈判", "合同签订"],
                            "description": "目标阶段"
                        },
                    },
                    "required": ["opportunity_id", "stage"],
                },
            },

            {
                "name": "win_opportunity",
                "description": """标记商机为赢单。

用途：商机成交
依赖：必须先调用 search_opportunity 获取 opportunity_id
参数：opportunity_id（必填）

示例：
用户："光大证券立项项目赢单了"
→ search_opportunity → opportunity_id=456
→ win_opportunity(opportunity_id=456)
""",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "opportunity_id": {
                            "type": "integer",
                            "description": "商机ID（必须先通过 search_opportunity 获取）"
                        },
                    },
                    "required": ["opportunity_id"],
                },
            },

            {
                "name": "lose_opportunity",
                "description": """标记商机为输单。

用途：商机失败
依赖：必须先调用 search_opportunity 获取 opportunity_id
参数：
- opportunity_id（必填）
- reason（可选）：输单原因
""",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "opportunity_id": {
                            "type": "integer",
                            "description": "商机ID"
                        },
                        "reason": {
                            "type": "string",
                            "description": "输单原因（可选）"
                        },
                    },
                    "required": ["opportunity_id"],
                },
            },

            # ===== 提醒工具 =====

            {
                "name": "set_reminder",
                "description": """设置提醒。

用途：提醒用户跟进客户
依赖：可选 customer_id（如果涉及客户）
参数：
- reminder_time（必填）：提醒时间（YYYY-MM-DD）
- content（必填）：提醒内容
- customer_id（可选）：关联客户
""",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "reminder_time": {
                            "type": "string",
                            "description": "提醒时间（YYYY-MM-DD格式，如'下周'则计算日期）"
                        },
                        "content": {
                            "type": "string",
                            "description": "提醒内容"
                        },
                        "customer_id": {
                            "type": "integer",
                            "description": "关联客户ID（可选）"
                        },
                    },
                    "required": ["reminder_time", "content"],
                },
            },

            # ===== 其他工具（未来扩展）=====
            # create_contract, create_invoice, approve_contract 等
        ]

    def _register_handlers(self) -> Dict[str, Dict[str, Any]]:
        """
        注册工具 Handler（包含 handler 实例 + config）

        Returns:
            Dict[str, Dict]: {"handler": Handler实例, "config": handler_config}
        """
        # 复用现有的 skills handlers
        from app.services.skills.handlers.follow_up_handler import FollowUpHandler
        from app.services.skills.handlers.create_handler import CreateHandler
        from app.services.skills.handlers.status_change_handler import StatusChangeHandler
        from app.services.skills.handlers.stage_advance_handler import StageAdvanceHandler

        # 搜索工具暂时使用简化版本（后续优化）
        from app.services.agent.handlers import (
            SearchCustomerHandler,
            SearchOpportunityHandler,
            SetReminderHandler,
        )

        # 从 app/constants/tools.py 导入 handler config 映射
        from app.constants.tools import TOOL_HANDLER_MAP

        def _build_handler_entry(tool_name: str, handler_instance: Any) -> Dict[str, Any]:
            """构建 handler entry（包含 handler + config）"""
            config = TOOL_HANDLER_MAP.get(tool_name, {}).get("config", {})
            return {
                "handler": handler_instance,
                "config": config,
            }

        return {
            "search_customer": _build_handler_entry("search_customer", SearchCustomerHandler()),
            "search_opportunity": _build_handler_entry("search_opportunity", SearchOpportunityHandler()),
            "follow_up_customer": _build_handler_entry("follow_up_customer", FollowUpHandler()),
            "follow_up_lead": _build_handler_entry("follow_up_lead", FollowUpHandler()),
            "create_opportunity": _build_handler_entry("create_opportunity", CreateHandler()),
            "update_stage": _build_handler_entry("update_stage", StageAdvanceHandler()),
            "win_opportunity": _build_handler_entry("win_opportunity", StatusChangeHandler()),
            "lose_opportunity": _build_handler_entry("lose_opportunity", StatusChangeHandler()),
            "set_reminder": _build_handler_entry("set_reminder", SetReminderHandler()),
        }


__all__ = ["ToolRegistry", "ToolResult"]