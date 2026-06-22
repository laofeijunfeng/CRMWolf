"""
Intent Detector Node for LangGraph AI Assistant

This module implements intent detection using project's AIConfig.
It parses user input to determine:
1. Action type (create_customer, follow_up, win_opportunity, etc.)
2. Entity references (entity_type, entity_hint)
3. Parameters extracted from user message

Uses project's AIService with OpenAI-compatible API (DeepSeek, etc.):
- Dynamic Skill/Action description injection
- Enum rules injection for parameter validation
- AIConfig from database for team isolation

Usage in graph:
    graph.add_node("intent_detector", intent_detector_node)
"""

import json
import re
from datetime import datetime
from typing import Any, Dict, Optional

import httpx
from langchain_core.runnables import RunnableConfig
from pydantic import BaseModel, Field

from app.crud.ai_config import ai_config_crud
from app.services.langgraph.state import AgentState
from app.constants.ai_rules import IntentType
from app.services.ai.intent_parser import INTENT_KEYWORDS


# ==================== Intent Result Schema ====================


class IntentResult(BaseModel):
    """
    Structured intent detection result.

    Used with LangChain JsonOutputParser for type-safe parsing.
    """

    action: str = Field(
        description="Action type: create_customer, follow_up, win_opportunity, etc."
    )
    action_id: Optional[str] = Field(
        default=None,
        description="Action ID if known (from tools definition)"
    )
    entity_type: Optional[str] = Field(
        default=None,
        description="Entity type: Customer, Opportunity, Lead"
    )
    entity_hint: Optional[str] = Field(
        default=None,
        description="Entity name/keyword hint for resolution"
    )
    entity_id: Optional[int] = Field(
        default=None,
        description="Entity ID if explicitly mentioned (e.g., #456)"
    )
    confidence: float = Field(
        default=0.8,
        ge=0.0,
        le=1.0,
        description="Confidence level (0.0-1.0)"
    )
    params: Dict[str, Any] = Field(
        default_factory=dict,
        description="Extracted parameters"
    )
    needs_entity_resolution: bool = Field(
        default=False,
        description="True if entity needs to be resolved"
    )
    needs_slot_collection: bool = Field(
        default=False,
        description="True if missing parameters need collection"
    )
    missing_params: list[str] = Field(
        default_factory=list,
        description="List of missing required parameters"
    )
    reply_text: Optional[str] = Field(
        default=None,
        description="Human-readable action description"
    )


# ==================== System Prompt Template ====================

SYSTEM_PROMPT_TEMPLATE = """你是 CRMWolf AI 助手，帮助用户管理客户关系。

【当前上下文】
当前日期: {current_date}
当前实体: {entity_context}

【可用操作】
{skill_descriptions}

【枚举规则】
{enum_rules}

【工作原则】
1. 充分思考再行动：每次操作前，先分析当前状态
2. 智能暂停：缺少信息时使用 ask_user 工具询问用户
3. 多候选处理：发现多个候选实体时，让用户选择
4. 关键确认：重要操作（创建合同、回款）前先确认
5. 完整业务链路：不要只执行一个操作就返回，要完成整个业务流程

【输出格式】
返回 JSON 格式的意图分析结果：
{{
  "action": "操作类型",
  "entity_type": "实体类型（如果涉及实体）",
  "entity_hint": "实体名称提示",
  "confidence": 0.8,
  "params": {{\"参数名\": "参数值"}},
  "needs_entity_resolution": true/false,
  "needs_slot_collection": true/false,
  "missing_params": ["缺少的参数列表"],
  "reply_text": "操作描述"
}}

【示例】
用户输入："跟进张三客户"
输出：
{{
  "action": "create_follow_up",
  "entity_type": "Customer",
  "entity_hint": "张三",
  "confidence": 0.85,
  "params": {{}},
  "needs_entity_resolution": true,
  "missing_params": ["content"]
}}

用户输入："创建客户光大证券，电话13800138000"
输出：
{{
  "action": "create_customer",
  "entity_type": "Customer",
  "confidence": 0.9,
  "params": {{
    "account_name": "光大证券",
    "contact_phone": "13800138000"
  }},
  "needs_entity_resolution": false
}}
"""


# ==================== Intent Detector Node ====================


def intent_detector_node(state: AgentState, config: RunnableConfig) -> Dict[str, Any]:
    """
    Detect user intent using project's AIConfig.

    Flow:
    0. Keyword preprocessing (high confidence 0.95)
    1. Build prompt with Skill/Action descriptions
    2. Get AI config from database (AIConfig table)
    3. Call OpenAI-compatible API (DeepSeek, etc.)
    4. Parse structured output as IntentResult
    5. Return state updates with intent_result

    Args:
        state: Current AgentState with messages
        config: RunnableConfig with db and user

    Returns:
        State updates with intent_result
    """
    # Get user message
    messages = state.get("messages", [])
    if not messages:
        return {"error": "No messages to analyze"}

    # LangGraph messages can be HumanMessage objects or dicts
    last_message = messages[-1]
    if hasattr(last_message, "content"):
        user_message = last_message.content
    else:
        user_message = last_message.get("content", "")

    # ===== Phase 0: Keyword Preprocessing (NEW) =====
    keyword_result = _keyword_preprocessing(user_message)
    if keyword_result:
        return {"intent_result": keyword_result}

    # ===== Phase 1: LLM Parsing (Existing logic) =====

    # Get database session and team_id from config
    db = config.get("configurable", {}).get("db")
    team_id = config.get("configurable", {}).get("team_id", 1)

    if not db:
        return {
            "error": "Database session not available",
            "intent_result": None,
        }

    # Get AI config from database
    ai_config = ai_config_crud.get_config(db, team_id)
    if not ai_config:
        return {
            "error": "AI configuration not found for team",
            "intent_result": None,
        }

    # Get decrypted API key
    api_key = ai_config_crud.get_decrypted_api_key(db, team_id)
    if not api_key:
        return {
            "error": "Failed to decrypt API key",
            "intent_result": None,
        }

    # Get dynamic prompt components
    entity_context = state.get("entity_context")

    skill_descriptions = _generate_skill_descriptions(db)
    enum_rules = _generate_enum_rules(db)
    entity_context_text = _format_entity_context(entity_context)

    # Build system prompt
    system_prompt = SYSTEM_PROMPT_TEMPLATE.format(
        current_date=datetime.now().strftime("%Y-%m-%d"),
        entity_context=entity_context_text,
        skill_descriptions=skill_descriptions,
        enum_rules=enum_rules,
    )

    # Build messages for API call
    api_messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_message},
    ]

    # Call AI API using httpx (OpenAI-compatible format)
    try:
        request_body = {
            "model": ai_config.model_name,
            "messages": api_messages,
            "temperature": ai_config.temperature,
            "max_tokens": ai_config.max_tokens,
            "stream": False,  # Non-streaming for intent detection
        }

        with httpx.Client(timeout=30.0) as client:
            response = client.post(
                f"{ai_config.api_host}/chat/completions",
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                },
                json=request_body,
            )
            response.raise_for_status()

            response_data = response.json()
            choices = response_data.get("choices", [])
            if not choices:
                return {
                    "error": "AI returned no choices",
                    "intent_result": None,
                }

            content = choices[0].get("message", {}).get("content", "")

            # Parse response as IntentResult
            intent_result = _parse_intent_response(content)

            return {"intent_result": intent_result}

    except httpx.HTTPStatusError as e:
        return {
            "error": f"AI API request failed: {e.response.status_code}",
            "intent_result": None,
        }
    except Exception as e:
        return {
            "error": f"Intent detection failed: {str(e)}",
            "intent_result": None,
        }


# ==================== Helper Functions ====================


def _keyword_preprocessing(user_message: str) -> Optional[Dict[str, Any]]:
    """
    Keyword preprocessing for intent detection (Phase 0).

    High confidence (0.95) keyword matching before LLM parsing.
    This preserves the three-layer strategy from old architecture:
    0. Keyword matching (confidence 0.95)
    1. LLM parsing (confidence 0.7-0.9)

    Args:
        user_message: User input text

    Returns:
        IntentResult dict if keyword matched, None otherwise
    """
    # Check keyword matching
    for intent_type, keywords in INTENT_KEYWORDS.items():
        for keyword in keywords:
            if keyword in user_message:
                # Keyword matched - build intent result
                result = _build_intent_from_keyword(
                    intent_type, user_message, keyword
                )
                return result

    return None


def _build_intent_from_keyword(
    intent_type: IntentType,
    user_message: str,
    matched_keyword: str,
) -> Dict[str, Any]:
    """
    Build IntentResult from keyword match.

    Args:
        intent_type: Detected IntentType
        user_message: Full user input
        matched_keyword: Keyword that triggered match

    Returns:
        IntentResult dict with high confidence
    """
    # Determine entity_type based on intent_type
    entity_type_mapping = {
        IntentType.CREATE_FOLLOW_UP: "Customer",  # Follow up customer/lead
        IntentType.CREATE_OPPORTUNITY: "Customer",
        IntentType.UPDATE_OPPORTUNITY: "Opportunity",
        IntentType.ADVANCE_STAGE: "Opportunity",
        IntentType.WIN_OPPORTUNITY: "Opportunity",
        IntentType.LOSE_OPPORTUNITY: "Opportunity",
        IntentType.CONVERT_LEAD: "Lead",
        IntentType.SET_REMINDER: "Customer",
        IntentType.QUERY_INFO: "Customer",
    }

    entity_type = entity_type_mapping.get(intent_type)

    # Extract entity_hint (entity name) from user message
    entity_hint = _extract_entity_hint(user_message, matched_keyword)

    # Build intent result
    result = {
        "action": intent_type.value,
        "confidence": 0.95,  # High confidence for keyword match
        "entity_type": entity_type,
        "entity_hint": entity_hint,
        "params": {},
        "needs_entity_resolution": bool(entity_hint),  # Need entity if hint exists
        "needs_slot_collection": False,
        "missing_params": [],
        "reply_text": f"检测到关键词 '{matched_keyword}'，准备执行 {intent_type.value}",
    }

    return result


def _extract_entity_hint(user_message: str, matched_keyword: str) -> Optional[str]:
    """
    Extract entity name hint from user message.

    Strategy:
    1. Remove matched keyword and common stop words
    2. Extract company names with specific suffixes (证券, 银行, etc.)
    3. Fallback to generic entity name (consecutive Chinese chars)

    Args:
        user_message: User input
        matched_keyword: Keyword that matched

    Returns:
        Entity name hint or None
    """
    import re

    # Step 1: Remove matched keyword
    text_after_keyword = user_message.replace(matched_keyword, "").strip()

    # Remove common stop words
    stop_words = ["一下", "这个", "那个", "的", "了", "，", "。", "最近", "还在", "走", "流程", "帮我", "为"]
    for stop_word in stop_words:
        text_after_keyword = text_after_keyword.replace(stop_word, "").strip()

    # Step 2: Extract company names with specific suffixes (priority)
    company_suffix_pattern = r"[一-龥]{2,4}(证券|银行|保险|基金|投资|科技|公司|集团)"
    match = re.search(company_suffix_pattern, text_after_keyword)
    if match:
        entity_name = match.group(0)
        return entity_name

    # Step 3: Fallback - extract consecutive Chinese chars (2-6 chars)
    # Stop at punctuation or business keywords
    generic_pattern = r"[一-龥]{2,6}"
    match = re.search(generic_pattern, text_after_keyword)
    if match:
        entity_name = match.group(0)
        # Filter out business keywords (not entity names)
        business_keywords = ["客户", "商机", "线索", "合同", "发票", "项目", "金额", "跟进", "状态"]
        if entity_name not in business_keywords:
            return entity_name

    # Step 4: No entity hint found (EntityResolver will handle)
    return None


def _generate_skill_descriptions(db: Optional[Any]) -> str:
    """
    Generate Skill/Action descriptions from database.

    Uses dynamic_prompt_service for database-driven descriptions.

    Args:
        db: Database session (from config)

    Returns:
        Formatted skill descriptions string
    """
    if not db:
        return _get_default_skill_descriptions()

    # Import dynamic prompt service
    try:
        from app.services.skills.dynamic_prompt_service import dynamic_prompt_service

        skills = dynamic_prompt_service.get_all_active_skills(db)

        descriptions = []
        for skill in skills:
            desc = f"- {skill.skill_name}: {skill.description}"
            if skill.skill_actions:
                actions = skill.skill_actions.split(",")
                desc += f" (动作: {', '.join(actions)})"
            descriptions.append(desc)

        return "\n".join(descriptions) if descriptions else _get_default_skill_description()

    except Exception:
        return _get_default_skill_descriptions()


def _get_default_skill_descriptions() -> str:
    """Return default skill descriptions if database unavailable."""
    return """
- 创建客户: 创建新客户记录 (create_customer)
- 跟进客户: 为客户创建跟进记录 (create_follow_up)
- 创建商机: 为客户创建商机 (init_opportunity)
- 更新金额: 更新商机金额 (update_amount)
- 更新阶段: 更新商机阶段 (update_stage)
- 赢单: 标记商机为赢单 (win_opportunity)
- 输单: 标记商机为输单 (lose_opportunity)
- 设置提醒: 为客户设置提醒 (set_reminder)
- 查询客户: 查询客户列表和详情 (query_customer)
- 查询商机: 查询商机列表和详情 (query_opportunity)
"""


def _generate_enum_rules(db: Optional[Any]) -> str:
    """
    Generate enum rules for parameter validation.

    Provides allowed values for enum fields.

    Args:
        db: Database session

    Returns:
        Formatted enum rules string
    """
    return """
【客户来源】
线上咨询, 电话咨询, 转介绍, 展会, 其他

【跟进方式】
电话, 邀约面谈, 微信沟通, 邮件, 其他

【商机阶段】
需求确认, 方案沟通, 报价谈判, 合同签订, 已成交

【采购类型】
新购, 续购, 增购

【商机状态】
FOLLOWING: 进行中
WON: 已赢单
LOST: 已输单
"""


def _format_entity_context(entity_context: Optional[Dict[str, Any]]) -> str:
    """
    Format entity context for prompt.

    Args:
        entity_context: Current entity context dict

    Returns:
        Human-readable context string
    """
    if not entity_context:
        return "无当前实体上下文"

    entity_type = entity_context.get("entity_type", "")
    entity_id = entity_context.get("entity_id", "")
    entity_name = entity_context.get("entity_name", "")

    if entity_type and entity_name:
        return f"当前{entity_type}: {entity_name} (#{entity_id})"

    return "无当前实体上下文"


def _parse_intent_response(content: str) -> Dict[str, Any]:
    """
    Parse LLM response as IntentResult.

    Handles both JSON and text responses.

    Args:
        content: LLM response content

    Returns:
        IntentResult dict
    """
    import json
    import re

    # Try to extract JSON from response
    # Look for JSON block in response
    json_match = re.search(r"\{[\s\S]*\}", content)

    if json_match:
        try:
            json_str = json_match.group(0)
            result = json.loads(json_str)

            # Validate required fields
            if "action" not in result:
                result["action"] = "unknown"

            # Set defaults
            result.setdefault("confidence", 0.8)
            result.setdefault("params", {})
            result.setdefault("needs_entity_resolution", False)
            result.setdefault("needs_slot_collection", False)
            result.setdefault("missing_params", [])

            return result

        except json.JSONDecodeError:
            pass

    # Fallback: extract action from text
    action_match = re.search(r"action[:\s]+(\w+)", content.lower())

    if action_match:
        action = action_match.group(1)
        return {
            "action": action,
            "confidence": 0.5,
            "params": {},
            "needs_entity_resolution": True,
            "needs_slot_collection": True,
            "missing_params": [],
        }

    # Unknown intent
    return {
        "action": "unknown",
        "confidence": 0.3,
        "params": {},
        "needs_entity_resolution": False,
        "needs_slot_collection": False,
        "missing_params": [],
        "reply_text": "无法识别操作意图，请描述您想做什么",
    }


# ==================== Route Decision Functions ====================


def route_after_intent(state: AgentState) -> str:
    """
    Conditional routing after intent detection.

    Routes based on intent_result:
    - entity_resolver: if needs_entity_resolution
    - slot_collector: if needs_slot_collection
    - preview: if ready to execute
    - end: if unknown action

    Args:
        state: Current AgentState

    Returns:
        Next node name
    """
    intent_result = state.get("intent_result")

    if not intent_result:
        return "end"

    action = intent_result.get("action", "unknown")

    # Unknown action - end conversation
    if action == "unknown":
        return "end"

    # Needs entity resolution first
    if intent_result.get("needs_entity_resolution"):
        return "entity_resolver"

    # Needs slot collection (missing params)
    if intent_result.get("needs_slot_collection") and intent_result.get("missing_params"):
        return "slot_collector"

    # Ready to preview
    return "preview"


# ==================== Export ====================


__all__ = [
    "intent_detector_node",
    "route_after_intent",
    "IntentResult",
]