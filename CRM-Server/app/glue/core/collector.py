"""槽位收集逻辑

强依赖 LLM 语义理解，根据 missing_fields 生成追问并理解用户回复。

参见: CRM-Docs/requirements/AI-GLUE-REQUIREMENTS.md 九、核心组件设计 9.9
参见: CRM-Docs/plans/AI-GLUE-IMPLEMENTATION-PLAN.md Phase 2.4
"""

from typing import Dict, Any, List, Optional
from dataclasses import dataclass
import json
import logging
import re
from datetime import datetime, timedelta

from sqlalchemy.orm import Session

from app.glue.core.intent import IntentResult
from app.services.ai_service import ai_service


logger = logging.getLogger(__name__)


@dataclass
class CollectResult:
    """槽位收集结果"""

    success: bool
    message: str  # 追问文本或成功消息
    missing_fields: List[str]  # 剩余缺失字段
    collected_slots: Dict[str, Any]  # 本次收集的槽位
    error: Optional[str] = None  # 错误信息（如 AI 服务不可用）

    # DialogueEngine 期望的字段（兼容）
    collected: bool = False  # 是否成功收集（别名）
    updated_slots: Dict[str, Any] = None  # 更新后的槽位
    remaining_missing: List[str] = None  # 剩余缺失
    needs_entity_resolution: bool = False  # 是否需要实体消解
    entity_type_hint: Optional[str] = None  # 实体类型提示
    entity_keyword: Optional[str] = None  # 实体名称关键词

    def __post_init__(self):
        # 确保兼容字段同步
        self.collected = self.success
        if self.updated_slots is None:
            self.updated_slots = self.collected_slots
        if self.remaining_missing is None:
            self.remaining_missing = self.missing_fields


@dataclass
class SlotFillResult:
    """槽位填充结果"""

    value: Optional[Any] = None
    confidence: float = 0.0
    needs_entity_resolution: bool = False  # 是否需要 EntityResolver 处理
    entity_keyword: Optional[str] = None  # 实体名称关键词（供 EntityResolver 使用）
    error: Optional[str] = None


# LLM 槽位理解系统提示词
SLOT_PARSE_PROMPT = """你是一个槽位提取助手。
根据缺失字段类型，从用户回复中提取对应信息。

输出 JSON 格式：
{
    "extracted": 提取的值（语义形式）,
    "unit": 单位（如有，如"万"/"千"）,
    "date_type": 日期类型（如有，如"relative"/"absolute"）,
    "is_entity_reference": 是否是实体引用（true/false）,
    "entity_keyword": 实体名称关键词（如有）
}

示例：
缺失字段: amount
用户回复: "大概35万左右"
输出: {"extracted": 35, "unit": "万"}

缺失字段: customer_id
用户回复: "张三那个客户"
输出: {"extracted": "张三", "is_entity_reference": true, "entity_keyword": "张三"}

缺失字段: content
用户回复: "就是他想了解一下价格"
输出: {"extracted": "他想了解一下价格"}

缺失字段: date_description
用户回复: "下周三再跟进"
输出: {"extracted": "下周三", "date_type": "relative"}

注意：
1. 金额单位可能是"万"、"w"、"千"、"k"、"元"、"块"等
2. 日期可能是相对表达（"明天"/"下周三"/"三天后"）或绝对表达（"5月20号"）
3. 实体引用可能是名称关键词或 #ID 格式
4. 文本类型直接提取完整语义
"""


class SlotCollector:
    """槽位收集器

    强依赖 LLM 语义理解，根据 missing_fields 生成追问并理解用户回复。
    """

    # 字段追问模板
    FIELD_PROMPTS = {
        "customer_id": "请告诉我要跟进哪个客户？可以回复客户名或 #客户ID。",
        "opportunity_id": "请告诉我要操作哪个商机？可以回复商机名或 #商机ID。",
        "content": "请告诉我跟进内容。",
        "name": "请告诉我商机名称。",
        "amount": "请告诉我金额是多少？",
        "stage_id": "请告诉我要推进到哪个阶段？",
        "stage_description": "请告诉我要推进到哪个阶段？",
        "reason": "请告诉我输单原因。",
        "date_description": "请告诉我什么时候跟进？",
    }

    def __init__(self, db: Session, tenant_id: int):
        """初始化槽位收集器

        Args:
            db: 数据库会话
            tenant_id: 租户 ID
        """
        self.db = db
        self.tenant_id = tenant_id

    async def collect(
        self,
        text: str,
        missing_slots: List[str],
        current_slots: Dict[str, Any],
    ) -> CollectResult:
        """收集槽位（理解用户回复）

        Args:
            text: 用户输入文本
            missing_slots: 缺失的槽位列表
            current_slots: 当前已收集的槽位

        Returns:
            CollectResult: 收集结果
        """
        if not missing_slots:
            # 所有字段已填充
            return CollectResult(
                success=True,
                message="所有信息已收集完成。",
                missing_fields=[],
                collected_slots=current_slots,
            )

        # 处理第一个缺失槽位
        first_missing = missing_slots[0]

        # 调用 fill_slot 处理单个槽位
        result = await self.fill_slot(text, first_missing, current_slots)

        # 更新剩余缺失
        if result.success:
            result.remaining_missing = missing_slots[1:] if len(missing_slots) > 1 else []
            result.missing_fields = result.remaining_missing

        return result

    async def fill_slot(
        self,
        text: str,
        missing_field: str,
        current_slots: Dict[str, Any],
    ) -> CollectResult:
        """填充单个槽位（强依赖 LLM 理解用户回复）

        Args:
            text: 用户输入文本
            missing_field: 缺失字段名
            current_slots: 当前已收集的槽位

        Returns:
            CollectResult: 收集结果，error 字段表示 AI 服务不可用
        """
        # 1. 检查是否是取消意图
        if self._is_cancel_intent(text):
            return CollectResult(
                success=False,
                message="已取消操作。",
                missing_fields=[],
                collected_slots={},
            )

        # 2. #ID 精确匹配（代码逻辑，无需 AI）
        id_match = self._match_explicit_id(text, missing_field)
        if id_match:
            new_slots = current_slots.copy()
            field_name = self._get_id_field_name(missing_field)
            new_slots[field_name] = id_match
            return CollectResult(
                success=True,
                message=f"已识别 ID: #{id_match}",
                missing_fields=[],
                collected_slots={field_name: id_match},
            )

        # 3. LLM 理解用户回复
        fill_result = await self._parse_slot_with_llm(text, missing_field)

        # AI 服务不可用
        if fill_result.error:
            return CollectResult(
                success=False,
                message="",
                missing_fields=[missing_field],
                collected_slots={},
                error=fill_result.error,
            )

        # 4. 代码计算具体值
        computed_value = self._compute_value(fill_result, missing_field)

        # 5. 更新槽位
        new_slots = current_slots.copy()
        entity_type_hint = None
        entity_keyword = None
        needs_entity_resolution = False

        if fill_result.needs_entity_resolution:
            # 需要后续 EntityResolver 处理
            new_slots["needs_entity_resolution"] = True
            new_slots["entity_keyword"] = fill_result.entity_keyword
            entity_type_hint = self._get_entity_type(missing_field)
            entity_keyword = fill_result.entity_keyword
            needs_entity_resolution = True
        elif computed_value is not None:
            field_name = self._get_value_field_name(missing_field)
            new_slots[field_name] = computed_value

        return CollectResult(
            success=True,
            message=f"已收集 {missing_field} 信息。",
            missing_fields=[],  # 后续由状态机判断是否还有缺失
            collected_slots=new_slots,
            updated_slots=new_slots,
            needs_entity_resolution=needs_entity_resolution,
            entity_type_hint=entity_type_hint,
            entity_keyword=entity_keyword,
        )

    async def _parse_slot_with_llm(
        self,
        text: str,
        missing_field: str,
    ) -> SlotFillResult:
        """使用 LLM 解析用户回复

        Args:
            text: 用户输入文本
            missing_field: 缺失字段名

        Returns:
            SlotFillResult: 解析结果，error 字段表示 AI 服务不可用
        """
        # 获取 AI 配置
        config, api_key = ai_service.get_config_and_key(self.db)
        if not config or not api_key:
            logger.warning("AI 配置不可用")
            return SlotFillResult(
                error="AI 服务未配置，请联系管理员配置 AI 服务后再使用",
            )

        # 调用 LLM
        try:
            user_prompt = f"缺失字段: {missing_field}\n用户回复: {text}"
            response = await ai_service._stream_chat_collect(
                api_host=config.api_host,
                api_key=api_key,
                model=config.model_name,
                messages=[
                    {"role": "system", "content": SLOT_PARSE_PROMPT},
                    {"role": "user", "content": user_prompt}
                ],
                temperature=0.1,
                max_tokens=256,
                response_format={"type": "json_object"}
            )

            # 解析响应
            clean_response = response.strip()
            if clean_response.startswith("```json"):
                clean_response = clean_response[7:]
            if clean_response.startswith("```"):
                clean_response = clean_response[3:]
            if clean_response.endswith("```"):
                clean_response = clean_response[:-3]
            clean_response = clean_response.strip()

            result = json.loads(clean_response)

            return SlotFillResult(
                value=result.get("extracted"),
                confidence=0.8,
                needs_entity_resolution=result.get("is_entity_reference", False),
                entity_keyword=result.get("entity_keyword") or result.get("extracted"),
            )

        except Exception as e:
            logger.error(f"LLM 槽位解析失败: {e}")
            return SlotFillResult(
                error="AI 服务暂时不可用，请稍后重试",
            )

    def _compute_value(
        self,
        fill_result: SlotFillResult,
        missing_field: str,
    ) -> Optional[Any]:
        """代码计算具体值（金额、日期等）

        Args:
            fill_result: LLM 解析结果
            missing_field: 缺失字段名

        Returns:
            计算后的具体值
        """
        if fill_result.needs_entity_resolution:
            # 实体引用需要 EntityResolver，不在此计算
            return None

        extracted = fill_result.value

        if missing_field == "amount":
            # 金额计算
            if extracted is not None:
                try:
                    # LLM 可能已经提取数值，这里处理单位转换
                    # 如果 fill_result.value 已经是数值，直接返回
                    return float(extracted)
                except (ValueError, TypeError):
                    pass

        elif missing_field in ["date_description", "follow_up_time"]:
            # 日期保持描述形式，后续由专门的日期计算处理
            return extracted

        elif missing_field in ["content", "reason", "name", "stage_description"]:
            # 文本类型直接使用
            return extracted

        return extracted

    def _match_explicit_id(self, text: str, missing_field: str) -> Optional[int]:
        """#ID 精确匹配（代码逻辑）"""
        pattern = r"#(\d+)"
        match = re.search(pattern, text)
        if match:
            return int(match.group(1))
        return None

    def _get_id_field_name(self, missing_field: str) -> str:
        """获取 ID 字段名"""
        if "customer" in missing_field.lower():
            return "customer_id"
        elif "opportunity" in missing_field.lower():
            return "opportunity_id"
        elif "lead" in missing_field.lower():
            return "lead_id"
        return missing_field

    def _get_value_field_name(self, missing_field: str) -> str:
        """获取值字段名"""
        return missing_field

    def _get_entity_type(self, missing_field: str) -> str:
        """获取实体类型提示"""
        if "customer" in missing_field.lower():
            return "Customer"
        elif "opportunity" in missing_field.lower():
            return "Opportunity"
        elif "lead" in missing_field.lower():
            return "Lead"
        return "Customer"

    def _is_cancel_intent(self, text: str) -> bool:
        """检测取消意图（简单关键词，后续可用 LLM 增强）"""
        cancel_keywords = ["取消", "算了", "不用了", "不", "算了"]
        text_lower = text.lower()
        return any(kw in text_lower for kw in cancel_keywords)


__all__ = [
    "CollectResult",
    "SlotFillResult",
    "SlotCollector",
]