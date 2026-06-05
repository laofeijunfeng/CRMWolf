"""CorrectionResolver

强依赖 LLM 语义理解，处理修正句（"不对/改/应该是"）。

参见: CRM-Docs/requirements/AI-GLUE-REQUIREMENTS.md 九、核心组件设计 9.6
参见: CRM-Docs/plans/AI-GLUE-IMPLEMENTATION-PLAN.md Phase 4.1
"""

from typing import Dict, Any, Optional
from dataclasses import dataclass
import json
import logging
import re

from sqlalchemy.orm import Session

from app.glue.core.session import PendingAction
from app.services.ai_service import ai_service


logger = logging.getLogger(__name__)


@dataclass
class CorrectionResult:
    """修正结果"""

    success: bool
    updated_slots: Dict[str, Any]  # 更新后的槽位
    message: str  # 提示消息
    corrected_field: Optional[str] = None  # 修正的字段
    error: Optional[str] = None  # 错误信息（如 AI 服务不可用）


# LLM 修正解析系统提示词
CORRECTION_PARSE_PROMPT = """你是一个修正意图识别助手。
判断用户输入是否是修正意图，并提取修正的字段和修正值。

输出 JSON 格式：
{
    "is_correction": true/false,
    "field": "修正的字段名（amount/stage/content/customer/date）",
    "value": "修正的值（语义形式）",
    "unit": "单位（如有，如万/千）",
    "confidence": 0.0-1.0
}

示例：
输入："不对，金额应该是35万"
输出：{"is_correction": true, "field": "amount", "value": 35, "unit": "万", "confidence": 0.9}

输入："改成下周三跟进"
输出：{"is_correction": true, "field": "date", "value": "下周三", "confidence": 0.85}

输入："不是这个客户，是张三那个"
输出：{"is_correction": true, "field": "customer", "value": "张三", "confidence": 0.85}

输入："阶段改成谈判中"
输出：{"is_correction": true, "field": "stage", "value": "谈判中", "confidence": 0.85}

输入："跟进内容改成他说要考虑一下"
输出：{"is_correction": true, "field": "content", "value": "他说要考虑一下", "confidence": 0.8}

输入："好的，确认执行"（不是修正）
输出：{"is_correction": false, "confidence": 0.9}

注意：
1. 修正关键词包括"不对"、"错了"、"改"、"应该是"、"改成"、"修改"等
2. 如果用户只是确认或取消，is_correction 应为 false
3. field 可能是 amount（金额）、stage（阶段）、content（内容）、customer（客户）、date（日期）
4. 金额的单位可能是"万"、"w"、"千"、"k"、"元"、"块"等
"""


class CorrectionResolver:
    """修正处理器

    强依赖 LLM 语义理解，检测修正意图并提取新值，merge 回 pending.slots。
    """

    def __init__(self, db: Session, tenant_id: int):
        """初始化修正处理器

        Args:
            db: 数据库会话
            tenant_id: 租户 ID
        """
        self.db = db
        self.tenant_id = tenant_id

    async def resolve(self, text: str, pending: PendingAction) -> CorrectionResult:
        """处理修正句

        Args:
            text: 用户输入文本
            pending: 当前 pending action

        Returns:
            CorrectionResult: 修正结果，error 字段表示 AI 服务不可用
        """
        # 1. LLM 判断修正意图 + 提取修正信息
        correction_info = await self._parse_correction_with_llm(text)

        # AI 服务不可用
        if correction_info.error:
            return CorrectionResult(
                success=False,
                updated_slots=pending.slots,
                message="",
                error=correction_info.error,
            )

        # 2. 不是修正意图
        if not correction_info.is_correction:
            return CorrectionResult(
                success=False,
                updated_slots=pending.slots,
                message="未检测到修正意图。",
            )

        # 3. 代码计算具体值
        computed_value = self._compute_value(correction_info)

        # 4. merge 到 pending.slots
        updated_slots = pending.slots.copy()

        # 根据 field 确定存储位置
        slot_field = self._get_slot_field(correction_info.field)
        if correction_info.field == "customer":
            # 客户修正需要后续 EntityResolver 处理
            updated_slots["needs_entity_resolution"] = True
            updated_slots["entity_keyword"] = correction_info.value
            updated_slots["entity_type_hint"] = "Customer"
        else:
            updated_slots[slot_field] = computed_value

        # 5. 返回结果
        return CorrectionResult(
            success=True,
            updated_slots=updated_slots,
            message=f"已更新 {self._get_field_display(correction_info.field)}。",
            corrected_field=correction_info.field,
        )

    @dataclass
    class _CorrectionInfo:
        """LLM 修正解析结果"""
        is_correction: bool
        field: Optional[str] = None
        value: Optional[Any] = None
        unit: Optional[str] = None
        confidence: float = 0.0
        error: Optional[str] = None

    async def _parse_correction_with_llm(self, text: str) -> _CorrectionInfo:
        """使用 LLM 解析修正意图

        Args:
            text: 用户输入文本

        Returns:
            _CorrectionInfo: 解析结果，error 字段表示 AI 服务不可用
        """
        # 获取 AI 配置
        config, api_key = ai_service.get_config_and_key(self.db, self.tenant_id)
        if not config or not api_key:
            logger.warning("AI 配置不可用")
            return self._CorrectionInfo(
                is_correction=False,
                error="AI 服务未配置，请联系管理员配置 AI 服务后再使用",
            )

        # 调用 LLM
        try:
            response = await ai_service._stream_chat_collect(
                api_host=config.api_host,
                api_key=api_key,
                model=config.model_name,
                messages=[
                    {"role": "system", "content": CORRECTION_PARSE_PROMPT},
                    {"role": "user", "content": text}
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

            return self._CorrectionInfo(
                is_correction=result.get("is_correction", False),
                field=result.get("field"),
                value=result.get("value"),
                unit=result.get("unit"),
                confidence=result.get("confidence", 0.0),
            )

        except Exception as e:
            logger.error(f"LLM 修正解析失败: {e}")
            return self._CorrectionInfo(
                is_correction=False,
                error="AI 服务暂时不可用，请稍后重试",
            )

    def _compute_value(self, correction_info: _CorrectionInfo) -> Any:
        """代码计算具体值（金额、日期等）

        Args:
            correction_info: LLM 解析结果

        Returns:
            计算后的具体值
        """
        field = correction_info.field
        value = correction_info.value
        unit = correction_info.unit

        if field == "amount":
            # 金额计算
            if value is not None:
                try:
                    amount = float(value)
                    if unit in ["万", "w"]:
                        amount *= 10000
                    elif unit in ["千", "k"]:
                        amount *= 1000
                    return amount
                except (ValueError, TypeError):
                    pass

        elif field == "date":
            # 日期保持描述形式，后续由日期计算处理
            return value

        elif field == "stage":
            # 阶段保持描述形式，后续转换为 stage_id
            return value

        elif field == "content":
            # 内容直接使用
            return value

        return value

    def _get_slot_field(self, llm_field: str) -> str:
        """将 LLM field 映射到 slot field"""
        field_map = {
            "amount": "amount",
            "stage": "stage_description",
            "content": "content",
            "customer": "customer_id",  # 需要 EntityResolver 处理
            "date": "date_description",
        }
        return field_map.get(llm_field, llm_field)

    def _get_field_display(self, field: str) -> str:
        """获取字段显示名"""
        field_names = {
            "amount": "金额",
            "stage": "阶段",
            "content": "跟进内容",
            "customer": "客户",
            "date": "跟进时间",
        }
        return field_names.get(field, field)


__all__ = [
    "CorrectionResult",
    "CorrectionResolver",
]