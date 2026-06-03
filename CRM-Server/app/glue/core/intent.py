"""IntentDetector

解析用户文本，强依赖 LLM 语义理解。

参见: CRM-Docs/requirements/AI-GLUE-REQUIREMENTS.md 九、核心组件设计 9.1
参见: CRM-Docs/plans/AI-GLUE-IMPLEMENTATION-PLAN.md Phase 2.2
"""

from typing import Dict, Any, Optional, List
from dataclasses import dataclass
import json
import logging
import re

from sqlalchemy.orm import Session

from app.glue.core.session import GlueSession
from app.services.ai_service import ai_service
from app.constants.ai_rules import IntentType, INTENT_DESCRIPTIONS


logger = logging.getLogger(__name__)


@dataclass
class IntentResult:
    """意图解析结果"""

    intent: str  # 意图类型（create_follow_up, update_opportunity, ...）
    confidence: float  # 置信度 0.0-1.0
    reasoning: str  # 判断依据
    slots: Dict[str, Any]  # 提取的槽位
    missing_fields: List[str]  # 缺失字段
    missing_slots: List[str]  # 缺失槽位（别名，兼容 DialogueEngine）
    ambiguity: Optional[Dict[str, Any]] = None  # 歧义信息
    error: Optional[str] = None  # 错误信息（如 AI 服务不可用）

    # Skill 相关（DialogueEngine 使用）
    skill_id: Optional[str] = None  # Skill ID
    skill_name: Optional[str] = None  # Skill 名称

    # 实体消解相关（DialogueEngine 使用）
    needs_entity_resolution: bool = False  # 是否需要实体消解
    entity_type_hint: Optional[str] = None  # 实体类型提示（Customer/Opportunity）
    entity_keyword: Optional[str] = None  # 实体名称关键词

    def __post_init__(self):
        # 确保 missing_slots 与 missing_fields 同步
        if not self.missing_slots and self.missing_fields:
            self.missing_slots = self.missing_fields


@dataclass
class MultiIntentResult:
    """多意图解析结果"""

    is_multi: bool  # 是否为多意图
    intents: List[IntentResult]  # 意图列表
    reasoning: str  # 判断依据
    error: Optional[str] = None  # 错误信息（如 AI 服务不可用）


# LLM 意图解析系统提示词
INTENT_PARSE_PROMPT = """你是一个意图识别助手。
从用户输入中识别意图并提取关键信息。

支持的意图类型：
- create_follow_up: 创建跟进记录
- init_opportunity: 创建新商机
- update_opportunity: 更新商机信息
- update_amount: 更新商机金额
- update_stage: 更新/推进商机阶段
- win_opportunity: 赢单/成交
- lose_opportunity: 输单/失败
- convert_lead: 转化线索
- set_reminder: 设置提醒/跟进时间
- query_info: 查询信息
- cancel: 取消操作
- confirm: 确认操作
- correction: 修正/修改参数

输出 JSON 格式：
{
    "intent": "意图类型",
    "confidence": 0.0-1.0,
    "reasoning": "判断依据",
    "slots": {
        "amount": 提取的金额数值（如有）,
        "amount_unit": 金额单位（万/千等）,
        "date": 日期描述（如有）,
        "content": 跟进内容（如有）,
        "stage": 阶段描述（如有）,
        "entity_reference": 实体引用方式（#ID/代词/名称）,
        "entity_keyword": 实体名称关键词（如有）
    }
}

示例：
输入："给#456加个跟进：客户说下周反馈"
输出：{"intent": "create_follow_up", "confidence": 0.9, "reasoning": "包含跟进关键词和商机ID引用", "slots": {"content": "客户说下周反馈", "entity_reference": "#ID", "entity_keyword": "456"}}

输入："这个商机的金额改成35万"
输出：{"intent": "update_amount", "confidence": 0.9, "reasoning": "包含金额更新关键词", "slots": {"amount": 35, "amount_unit": "万", "entity_reference": "代词"}}

输入："跟进一下张三客户"
输出：{"intent": "create_follow_up", "confidence": 0.85, "reasoning": "跟进意图+客户名称引用", "slots": {"entity_reference": "名称", "entity_keyword": "张三"}}

输入："推进到谈判阶段"
输出：{"intent": "update_stage", "confidence": 0.85, "reasoning": "阶段推进关键词", "slots": {"stage": "谈判"}}

注意：
1. 如果输入包含 #数字，entity_reference 应为 "#ID"，entity_keyword 为数字本身
2. 如果输入包含"这个/那个"，entity_reference 应为 "代词"
3. 如果输入包含名称关键词（如"张三"），entity_reference 应为 "名称"
4. 金额单位可能是"万"、"w"、"千"、"k"、"元"、"块"等
5. 如果无法确定意图，返回 {"intent": "unknown", "confidence": 0.0}
"""

# LLM 多意图解析系统提示词
MULTI_INTENT_PARSE_PROMPT = """你是一个多意图识别助手。
从用户输入中识别是否包含多个意图，并分解为独立的意图列表。

支持的意图类型：
- create_follow_up: 创建跟进记录
- init_opportunity: 创建新商机
- update_opportunity: 更新商机信息
- update_amount: 更新商机金额
- update_stage: 更新/推进商机阶段
- win_opportunity: 赢单/成交
- lose_opportunity: 输单/失败
- convert_lead: 转化线索
- set_reminder: 设置提醒/跟进时间
- query_info: 查询信息

输出 JSON 格式：
{
    "is_multi_intent": true/false,
    "intents": [
        {
            "intent": "意图类型",
            "slots": {
                "amount": 提取的金额数值（如有）,
                "amount_unit": 金额单位（万/千等）,
                "date": 日期描述（如有）,
                "content": 跟进内容（如有）,
                "stage": 阶段描述（如有）,
                "entity_reference": 实体引用方式（#ID/代词/名称）,
                "entity_keyword": 实体名称关键词（如有）
            }
        }
    ],
    "reasoning": "判断依据"
}

示例：
输入："跟进张三客户，并设置下周提醒"
输出：{"is_multi_intent": true, "intents": [{"intent": "create_follow_up", "slots": {"entity_reference": "名称", "entity_keyword": "张三"}}, {"intent": "set_reminder", "slots": {"date": "下周"}}], "reasoning": "包含跟进和设置提醒两个意图"}

输入："修改金额到35万并推进到谈判阶段"
输出：{"is_multi_intent": true, "intents": [{"intent": "update_amount", "slots": {"amount": 35, "amount_unit": "万"}}, {"intent": "update_stage", "slots": {"stage": "谈判"}}], "reasoning": "包含修改金额和推进阶段两个意图"}

输入："给#456加个跟进：客户说下周反馈"
输出：{"is_multi_intent": false, "intents": [{"intent": "create_follow_up", "slots": {"content": "客户说下周反馈", "entity_reference": "#ID", "entity_keyword": "456"}}], "reasoning": "单一跟进意图"}

输入："跟进一下张三客户"
输出：{"is_multi_intent": false, "intents": [{"intent": "create_follow_up", "slots": {"entity_reference": "名称", "entity_keyword": "张三"}}], "reasoning": "单一跟进意图"}

注意：
1. 多意图通常用"并"、"同时"、"然后"、"再"等连接词
2. 每个意图应独立提取 slots，后续意图可继承前意图的实体引用
3. 如果只有一个意图，is_multi_intent 为 false
4. 如果无法确定意图，返回 {"is_multi_intent": false, "intents": [{"intent": "unknown"}]}
"""


class IntentDetector:
    """意图检测器

    强依赖 LLM 语义理解，解析用户文本意图。
    """

    def __init__(self, db: Session, tenant_id: int):
        """初始化意图检测器

        Args:
            db: 数据库会话
            tenant_id: 租户 ID
        """
        self.db = db
        self.tenant_id = tenant_id

    async def detect(
        self,
        text: str,
        session: GlueSession,
        auth_token: Optional[str] = None,
    ) -> IntentResult:
        """解析用户文本

        Args:
            text: 用户输入文本
            session: 当前会话状态
            auth_token: JWT认证token（可选）

        Returns:
            IntentResult: 意图解析结果
        """
        # 1. LLM 解析意图
        intent_info = await self._parse_intent_with_llm(text)

        # AI 服务不可用
        if intent_info.error:
            return IntentResult(
                intent="unknown",
                confidence=0.0,
                reasoning="",
                slots={},
                missing_fields=[],
                error=intent_info.error,
            )

        # 2. 提取实体（金额、日期等）
        entities = self._extract_entities_from_slots(intent_info.slots)

        # 3. 结合 recent_entities 补全引用
        slots = self._merge_with_session(entities, session, intent_info.slots)

        # 4. 判断缺失字段
        missing_fields = self._check_missing_fields(intent_info.intent, slots)

        # 5. 返回结果
        # 检查是否需要实体消解
        needs_entity_resolution = slots.get("needs_entity_resolution", False)
        entity_keyword = slots.get("entity_keyword")

        # 确定实体类型提示
        entity_type_hint = None
        if needs_entity_resolution:
            # 根据 intent 判断实体类型
            if intent_info.intent in ["create_follow_up", "set_reminder"]:
                entity_type_hint = "Customer"
            elif intent_info.intent in [
                "update_opportunity", "update_amount", "update_stage",
                "win_opportunity", "lose_opportunity"
            ]:
                entity_type_hint = "Opportunity"
            else:
                entity_type_hint = "Customer"  # 默认

        return IntentResult(
            intent=intent_info.intent,
            confidence=intent_info.confidence,
            reasoning=intent_info.reasoning,
            slots=slots,
            missing_fields=missing_fields,
            missing_slots=missing_fields,  # 同步
            ambiguity=None,
            needs_entity_resolution=needs_entity_resolution,
            entity_type_hint=entity_type_hint,
            entity_keyword=entity_keyword,
        )

    async def detect_multi(
        self,
        text: str,
        session: GlueSession,
        auth_token: Optional[str] = None,
    ) -> MultiIntentResult:
        """解析多意图文本

        分解复合指令，如"跟进张三客户并设置下周提醒"。

        Args:
            text: 用户输入文本
            session: 当前会话状态
            auth_token: JWT认证token（可选）

        Returns:
            MultiIntentResult: 多意图解析结果
        """
        # 1. 获取 AI 配置
        config, api_key = ai_service.get_config_and_key(self.db)
        if not config or not api_key:
            logger.warning("AI 配置不可用")
            return MultiIntentResult(
                is_multi=False,
                intents=[],
                reasoning="",
                error="AI 服务未配置，请联系管理员配置 AI 服务后再使用",
            )

        # 2. 调用 LLM 多意图解析
        try:
            response = await ai_service._stream_chat_collect(
                api_host=config.api_host,
                api_key=api_key,
                model=config.model_name,
                messages=[
                    {"role": "system", "content": MULTI_INTENT_PARSE_PROMPT},
                    {"role": "user", "content": text}
                ],
                temperature=0.1,
                max_tokens=512,
                response_format={"type": "json_object"}
            )

            # 3. 解析响应
            clean_response = response.strip()
            if clean_response.startswith("```json"):
                clean_response = clean_response[7:]
            if clean_response.startswith("```"):
                clean_response = clean_response[3:]
            if clean_response.endswith("```"):
                clean_response = clean_response[:-3]
            clean_response = clean_response.strip()

            result = json.loads(clean_response)

            is_multi = result.get("is_multi_intent", False)
            raw_intents = result.get("intents", [])
            reasoning = result.get("reasoning", "")

            # 4. 转换为 IntentResult 列表
            intents: List[IntentResult] = []
            prev_entity_reference = None  # 继承前意图的实体引用

            for i, raw_intent in enumerate(raw_intents):
                intent_type = raw_intent.get("intent", "unknown")
                raw_slots = raw_intent.get("slots", {})

                # 提取实体
                entities = self._extract_entities_from_slots(raw_slots)

                # 后续意图继承前意图的实体引用（如果没有指定）
                if i > 0 and prev_entity_reference:
                    if not entities.get("entity_reference_type"):
                        entities["entity_reference_type"] = prev_entity_reference

                # 结合 session 补全
                slots = self._merge_with_session(entities, session, raw_slots)

                # 判断缺失字段
                missing_fields = self._check_missing_fields(intent_type, slots)

                # 判断实体消解
                needs_entity_resolution = slots.get("needs_entity_resolution", False)
                entity_keyword = slots.get("entity_keyword")
                entity_type_hint = None
                if needs_entity_resolution:
                    if intent_type in ["create_follow_up", "set_reminder"]:
                        entity_type_hint = "Customer"
                    elif intent_type in [
                        "update_opportunity", "update_amount", "update_stage",
                        "win_opportunity", "lose_opportunity"
                    ]:
                        entity_type_hint = "Opportunity"
                    else:
                        entity_type_hint = "Customer"

                intents.append(IntentResult(
                    intent=intent_type,
                    confidence=0.85,  # 多意图统一置信度
                    reasoning=reasoning,
                    slots=slots,
                    missing_fields=missing_fields,
                    missing_slots=missing_fields,
                    needs_entity_resolution=needs_entity_resolution,
                    entity_type_hint=entity_type_hint,
                    entity_keyword=entity_keyword,
                ))

                # 记录实体引用供后续继承
                if entities.get("entity_reference_type"):
                    prev_entity_reference = entities.get("entity_reference_type")

            return MultiIntentResult(
                is_multi=is_multi,
                intents=intents,
                reasoning=reasoning,
            )

        except Exception as e:
            logger.error(f"LLM 多意图解析失败: {e}")
            return MultiIntentResult(
                is_multi=False,
                intents=[],
                reasoning="",
                error="AI 服务暂时不可用，请稍后重试",
            )

    @dataclass
    class _LLMIntentResult:
        """LLM 解析结果"""
        intent: str
        confidence: float
        reasoning: str
        slots: Dict[str, Any]
        error: Optional[str] = None

    async def _parse_intent_with_llm(self, text: str) -> _LLMIntentResult:
        """使用 LLM 解析意图

        Args:
            text: 用户输入文本

        Returns:
            _LLMIntentResult: 解析结果，error 字段表示 AI 服务不可用
        """
        # 1. 获取 AI 配置
        config, api_key = ai_service.get_config_and_key(self.db)
        if not config or not api_key:
            logger.warning("AI 配置不可用")
            return self._LLMIntentResult(
                intent="unknown",
                confidence=0.0,
                reasoning="",
                slots={},
                error="AI 服务未配置，请联系管理员配置 AI 服务后再使用",
            )

        # 2. 调用 LLM
        try:
            response = await ai_service._stream_chat_collect(
                api_host=config.api_host,
                api_key=api_key,
                model=config.model_name,
                messages=[
                    {"role": "system", "content": INTENT_PARSE_PROMPT},
                    {"role": "user", "content": text}
                ],
                temperature=0.1,  # 低温度，精确提取
                max_tokens=512,
                response_format={"type": "json_object"}
            )

            # 3. 解析响应
            clean_response = response.strip()
            if clean_response.startswith("```json"):
                clean_response = clean_response[7:]
            if clean_response.startswith("```"):
                clean_response = clean_response[3:]
            if clean_response.endswith("```"):
                clean_response = clean_response[:-3]
            clean_response = clean_response.strip()

            result = json.loads(clean_response)

            return self._LLMIntentResult(
                intent=result.get("intent", "unknown"),
                confidence=result.get("confidence", 0.0),
                reasoning=result.get("reasoning", ""),
                slots=result.get("slots", {}),
            )

        except Exception as e:
            logger.error(f"LLM 意图解析失败: {e}")
            return self._LLMIntentResult(
                intent="unknown",
                confidence=0.0,
                reasoning="",
                slots={},
                error="AI 服务暂时不可用，请稍后重试",
            )

    def _extract_entities_from_slots(self, slots: Dict[str, Any]) -> Dict[str, Any]:
        """从 LLM slots 提取实体值（代码计算具体值）

        Args:
            slots: LLM 返回的 slots

        Returns:
            提取后的实体字典
        """
        entities = {}

        # 金额计算
        if "amount" in slots and slots["amount"]:
            amount = slots["amount"]
            unit = slots.get("amount_unit", "")

            # 转换为数值
            try:
                amount_value = float(amount)
                if unit in ["万", "w"]:
                    amount_value *= 10000
                elif unit in ["千", "k"]:
                    amount_value *= 1000

                entities["amount"] = amount_value
            except (ValueError, TypeError):
                pass

        # 日期保持描述形式，由后续处理
        if "date" in slots and slots["date"]:
            entities["date_description"] = slots["date"]

        # 跟进内容
        if "content" in slots and slots["content"]:
            entities["content"] = slots["content"]

        # 阶段描述
        if "stage" in slots and slots["stage"]:
            entities["stage_description"] = slots["stage"]

        # 实体引用
        if "entity_reference" in slots:
            entities["entity_reference_type"] = slots["entity_reference"]
            if "entity_keyword" in slots:
                entities["entity_keyword"] = slots["entity_keyword"]

        return entities

    def _merge_with_session(
        self,
        entities: Dict[str, Any],
        session: GlueSession,
        llm_slots: Dict[str, Any],
    ) -> Dict[str, Any]:
        """结合 session.recent_entities 补全引用

        Args:
            entities: 提取的实体
            session: 当前会话状态
            llm_slots: LLM 返回的原始 slots

        Returns:
            补全后的 slots
        """
        slots = entities.copy()

        # 根据 entity_reference_type 补全
        ref_type = entities.get("entity_reference_type", "")

        if ref_type == "#ID":
            # ID 引用：直接使用
            keyword = entities.get("entity_keyword", "")
            if keyword:
                # 根据文本上下文判断是客户还是商机
                if "商机" in llm_slots.get("entity_type_hint", "") or "商机" in str(session):
                    slots["opportunity_id"] = int(keyword)
                else:
                    slots["customer_id"] = int(keyword)

        elif ref_type == "代词":
            # 代词引用：使用 recent_entities
            if session.recent_entities:
                if session.recent_entities.opportunity_id:
                    slots["opportunity_id"] = session.recent_entities.opportunity_id
                if session.recent_entities.customer_id:
                    slots["customer_id"] = session.recent_entities.customer_id

        elif ref_type == "名称":
            # 名称引用：需要后续 EntityResolver 处理
            # 这里只记录关键词，不直接补全 ID
            slots["needs_entity_resolution"] = True

        return slots

    def _check_missing_fields(self, intent: str, slots: Dict[str, Any]) -> List[str]:
        """判断缺失字段

        根据 intent 类型判断必填字段是否缺失。
        """
        # 必填字段定义
        required_fields = {
            "create_follow_up": ["customer_id", "content"],
            "init_opportunity": ["customer_id"],
            "update_opportunity": ["opportunity_id"],
            "update_amount": ["opportunity_id", "amount"],
            "update_stage": ["opportunity_id", "stage_description"],
            "win_opportunity": ["opportunity_id"],
            "lose_opportunity": ["opportunity_id"],
            "convert_lead": ["lead_id"],
            "set_reminder": ["customer_id", "date_description"],
        }

        intent_required = required_fields.get(intent, [])

        # 特殊处理：需要 EntityResolver 的场景
        if slots.get("needs_entity_resolution"):
            # 名称引用需要消解后才能确定 customer_id/opportunity_id
            if "customer_id" in intent_required and "customer_id" not in slots:
                # 这个缺失会在后续 EntityResolver 处理
                pass
            if "opportunity_id" in intent_required and "opportunity_id" not in slots:
                pass

        # 检查其他缺失字段
        missing = []
        for field in intent_required:
            if field not in slots and not slots.get("needs_entity_resolution"):
                missing.append(field)

        return missing


__all__ = [
    "IntentResult",
    "MultiIntentResult",
    "IntentDetector",
]