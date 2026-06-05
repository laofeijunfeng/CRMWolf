"""CancelDetector

强依赖 LLM 语义理解，检测取消/暂停意图。

参见: CRM-Docs/requirements/AI-GLUE-REQUIREMENTS.md 九、核心组件设计 9.11
参见: CRM-Docs/plans/AI-GLUE-IMPLEMENTATION-PLAN.md Phase 4.3
"""

from typing import Tuple, Optional
from dataclasses import dataclass
import json
import logging

from sqlalchemy.orm import Session

from app.services.ai_service import ai_service


logger = logging.getLogger(__name__)


@dataclass
class CancelResult:
    """取消检测结果"""

    is_cancel: bool
    confidence: float
    reasoning: str = ""
    error: Optional[str] = None  # 错误信息（如 AI 服务不可用）


# LLM 取消意图系统提示词
CANCEL_DETECT_PROMPT = """你是一个意图识别助手。
判断用户输入是否表示取消或暂停意图。

输出 JSON 格式：
{
    "is_cancel": true/false,
    "confidence": 0.0-1.0,
    "reasoning": "判断依据",
    "cancel_type": "cancel"/"pause"/"abort"
}

示例：
输入："算了" → {"is_cancel": true, "confidence": 0.95, "reasoning": "明确取消关键词", "cancel_type": "cancel"}
输入："取消" → {"is_cancel": true, "confidence": 0.95, "reasoning": "直接取消指令", "cancel_type": "cancel"}
输入："不用了，谢谢" → {"is_cancel": true, "confidence": 0.90, "reasoning": "婉拒表达", "cancel_type": "cancel"}
输入："等等，我再想想" → {"is_cancel": true, "confidence": 0.85, "reasoning": "暂停请求", "cancel_type": "pause"}
输入："不，先别执行" → {"is_cancel": true, "confidence": 0.90, "reasoning": "阻止执行", "cancel_type": "abort"}
输入："好的，确认执行" → {"is_cancel": false, "confidence": 0.95, "reasoning": "确认意图"}
输入："金额改成35万" → {"is_cancel": false, "confidence": 0.90, "reasoning": "修正意图，不是取消"}

注意：
1. 区分取消（完全放弃）、暂停（暂时停下）、阻止（阻止当前操作）
2. 用户表达"等等"、"让我想想"通常是暂停而非完全取消
3. 修正意图（"改成XXX"）不是取消
4. 确认意图（"好的"、"可以"、"没问题"）不是取消
"""


class CancelDetector:
    """取消检测器

    强依赖 LLM 语义理解，支持自然表达取消意图。
    """

    def __init__(self, db: Session, tenant_id: int):
        """初始化取消检测器

        Args:
            db: 数据库会话
            tenant_id: 租户 ID
        """
        self.db = db
        self.tenant_id = tenant_id

    async def detect(self, text: str) -> CancelResult:
        """检测取消意图

        Args:
            text: 用户输入文本

        Returns:
            CancelResult: 检测结果，error 字段表示 AI 服务不可用
        """
        # 1. 强关键词优先（代码逻辑，无需 AI）
        strong_cancel = self._check_strong_cancel(text)
        if strong_cancel:
            return CancelResult(
                is_cancel=True,
                confidence=0.95,
                reasoning=f"强取消关键词: '{strong_cancel}'",
            )

        # 2. LLM 语义理解
        llm_result = await self._detect_with_llm(text)

        # AI 服务不可用
        if llm_result.error:
            return llm_result

        return llm_result

    def _check_strong_cancel(self, text: str) -> Optional[str]:
        """检查强取消关键词（代码逻辑，优先级最高）

        Args:
            text: 用户输入文本

        Returns:
            匹配的强关键词，或 None
        """
        text_lower = text.lower().strip()

        # 精确匹配强关键词
        strong_keywords = ["取消", "算了", "不用了", "放弃"]
        for kw in strong_keywords:
            if text_lower == kw or text_lower.startswith(kw + " ") or text_lower.endswith(" " + kw):
                return kw

        return None

    async def _detect_with_llm(self, text: str) -> CancelResult:
        """使用 LLM 检测取消意图

        Args:
            text: 用户输入文本

        Returns:
            CancelResult: 检测结果，error 字段表示 AI 服务不可用
        """
        # 获取 AI 配置
        config, api_key = ai_service.get_config_and_key(self.db, self.tenant_id)
        if not config or not api_key:
            logger.warning("AI 配置不可用")
            return CancelResult(
                is_cancel=False,
                confidence=0.0,
                error="AI 服务未配置，请联系管理员配置 AI 服务后再使用",
            )

        # 调用 LLM
        try:
            response = await ai_service._stream_chat_collect(
                api_host=config.api_host,
                api_key=api_key,
                model=config.model_name,
                messages=[
                    {"role": "system", "content": CANCEL_DETECT_PROMPT},
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

            return CancelResult(
                is_cancel=result.get("is_cancel", False),
                confidence=result.get("confidence", 0.0),
                reasoning=result.get("reasoning", ""),
            )

        except Exception as e:
            logger.error(f"LLM 取消检测失败: {e}")
            return CancelResult(
                is_cancel=False,
                confidence=0.0,
                error="AI 服务暂时不可用，请稍后重试",
            )

    def is_strong_cancel(self, text: str) -> bool:
        """是否为强取消意图（同步方法，用于快速判断）

        Args:
            text: 用户输入文本

        Returns:
            是否强取消
        """
        return self._check_strong_cancel(text) is not None


__all__ = [
    "CancelResult",
    "CancelDetector",
]