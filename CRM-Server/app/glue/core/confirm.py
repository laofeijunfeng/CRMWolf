"""ConfirmationDetector

强依赖 LLM 语义理解，检测确认意图。

参见: CRM-Docs/requirements/AI-GLUE-REQUIREMENTS.md 九、核心组件设计 9.11
参见: CRM-Docs/plans/AI-GLUE-IMPLEMENTATION-PLAN.md Phase 4.4
"""

from typing import Optional
from dataclasses import dataclass
import json
import logging

from sqlalchemy.orm import Session

from app.services.ai_service import ai_service


logger = logging.getLogger(__name__)


@dataclass
class ConfirmationResult:
    """确认检测结果"""

    is_confirm: bool
    confidence: float
    reasoning: str = ""
    error: Optional[str] = None  # 错误信息（如 AI 服务不可用）


# LLM 确认意图系统提示词
CONFIRM_DETECT_PROMPT = """你是一个意图识别助手。
判断用户输入是否表示确认或同意意图。

输出 JSON 格式：
{
    "is_confirm": true/false,
    "confidence": 0.0-1.0,
    "reasoning": "判断依据",
    "confirm_type": "confirm"/"agree"/"proceed"
}

示例：
输入："确认" → {"is_confirm": true, "confidence": 0.95, "reasoning": "直接确认指令", "confirm_type": "confirm"}
输入："好的" → {"is_confirm": true, "confidence": 0.90, "reasoning": "同意表达", "confirm_type": "agree"}
输入："可以" → {"is_confirm": true, "confidence": 0.90, "reasoning": "许可表达", "confirm_type": "agree"}
输入："没问题" → {"is_confirm": true, "confidence": 0.85, "reasoning": "积极同意", "confirm_type": "agree"}
输入："那就这样吧" → {"is_confirm": true, "confidence": 0.80, "reasoning": "无奈同意", "confirm_type": "agree"}
输入："行，执行吧" → {"is_confirm": true, "confidence": 0.90, "reasoning": "执行请求", "confirm_type": "proceed"}
输入："对，就是这样" → {"is_confirm": true, "confidence": 0.85, "reasoning": "确认表达", "confirm_type": "confirm"}
输入："取消" → {"is_confirm": false, "confidence": 0.95, "reasoning": "取消意图"}
输入："算了" → {"is_confirm": false, "confidence": 0.95, "reasoning": "放弃意图"}
输入："金额改成35万" → {"is_confirm": false, "confidence": 0.90, "reasoning": "修正意图，需要重新预览"}

注意：
1. 区分确认（确认当前操作）、同意（同意执行）、执行请求（直接执行）
2. 用户表达"就这样吧"、"好的吧"通常是无奈同意，置信度稍低
3. 修正意图（"改成XXX"）不是确认，需要重新预览
4. 取消意图（"取消"、"算了"）不是确认
5. 短语如"嗯"、"行"、"OK"也是确认表达
"""


class ConfirmationDetector:
    """确认检测器

    强依赖 LLM 语义理解，支持自然表达确认意图。
    """

    def __init__(self, db: Session, tenant_id: int):
        """初始化确认检测器

        Args:
            db: 数据库会话
            tenant_id: 租户 ID
        """
        self.db = db
        self.tenant_id = tenant_id

    async def detect(self, text: str) -> ConfirmationResult:
        """检测确认意图

        Args:
            text: 用户输入文本

        Returns:
            ConfirmationResult: 检测结果，error 字段表示 AI 服务不可用
        """
        # 1. 强关键词优先（代码逻辑，无需 AI）
        strong_confirm = self._check_strong_confirm(text)
        if strong_confirm:
            return ConfirmationResult(
                is_confirm=True,
                confidence=0.95,
                reasoning=f"强确认关键词: '{strong_confirm}'",
            )

        # 2. LLM 语义理解
        llm_result = await self._detect_with_llm(text)

        # AI 服务不可用
        if llm_result.error:
            return llm_result

        return llm_result

    def _check_strong_confirm(self, text: str) -> Optional[str]:
        """检查强确认关键词（代码逻辑，优先级最高）

        Args:
            text: 用户输入文本

        Returns:
            匹配的强关键词，或 None
        """
        text_lower = text.lower().strip()

        # 精确匹配强关键词
        strong_keywords = ["确认", "执行", "是的", "对的"]
        for kw in strong_keywords:
            if text_lower == kw or text_lower.startswith(kw + " ") or text_lower.endswith(" " + kw):
                return kw

        return None

    async def _detect_with_llm(self, text: str) -> ConfirmationResult:
        """使用 LLM 检测确认意图

        Args:
            text: 用户输入文本

        Returns:
            ConfirmationResult: 检测结果，error 字段表示 AI 服务不可用
        """
        # 获取 AI 配置
        config, api_key = ai_service.get_config_and_key(self.db, self.tenant_id)
        if not config or not api_key:
            logger.warning("AI 配置不可用")
            return ConfirmationResult(
                is_confirm=False,
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
                    {"role": "system", "content": CONFIRM_DETECT_PROMPT},
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

            return ConfirmationResult(
                is_confirm=result.get("is_confirm", False),
                confidence=result.get("confidence", 0.0),
                reasoning=result.get("reasoning", ""),
            )

        except Exception as e:
            logger.error(f"LLM 确认检测失败: {e}")
            return ConfirmationResult(
                is_confirm=False,
                confidence=0.0,
                error="AI 服务暂时不可用，请稍后重试",
            )

    def is_strong_confirm(self, text: str) -> bool:
        """是否为强确认意图（同步方法，用于快速判断）

        Args:
            text: 用户输入文本

        Returns:
            是否强确认
        """
        return self._check_strong_confirm(text) is not None


__all__ = [
    "ConfirmationResult",
    "ConfirmationDetector",
]