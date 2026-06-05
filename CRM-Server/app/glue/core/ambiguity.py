"""AmbiguityResolver

候选列表 → 用户选择，支持 LLM 描述性选择理解。

参见: CRM-Docs/requirements/AI-GLUE-REQUIREMENTS.md 九、核心组件设计 9.10
参见: CRM-Docs/plans/AI-GLUE-IMPLEMENTATION-PLAN.md Phase 4.2
"""

from typing import List, Optional
from dataclasses import dataclass
import json
import logging
import re

from sqlalchemy.orm import Session

from app.glue.core.types import EntityCandidate
from app.services.ai_service import ai_service


logger = logging.getLogger(__name__)


@dataclass
class AmbiguityResult:
    """歧义消解结果"""

    resolved: bool  # 是否已消解
    selected_id: Optional[int] = None  # 选中的 entity_id
    message: str = ""  # 提示消息
    remaining_candidates: List[EntityCandidate] = None  # 剩余候选
    error: Optional[str] = None  # 错误信息（如 AI 服务不可用）

    def __post_init__(self):
        if self.remaining_candidates is None:
            self.remaining_candidates = []


# LLM 描述性选择系统提示词
DESCRIBE_SELECT_PROMPT = """你是一个选择理解助手。
根据用户描述，从候选列表中选择最匹配的一个。

候选列表格式：
序号 | 名称 | 描述
① 张三科技 - 最近跟进 5/20
② 张三贸易 - 阶段：谈判中
③ 张三网络 - 最近跟进 4/15

输出 JSON 格式：
{
    "selected_index": 0-4（选中的序号，从0开始）,
    "confidence": 0.0-1.0,
    "reasoning": "选择依据"
}

示例：
候选列表见上方
用户输入："选谈判中的那个"
输出：{"selected_index": 1, "confidence": 0.85, "reasoning": "匹配候选②的'谈判中'描述"}

用户输入："最近跟进的那个"
输出：{"selected_index": 0, "confidence": 0.80, "reasoning": "匹配候选①'最近跟进 5/20'，日期最近"}

用户输入："第一个"
输出：{"selected_index": 0, "confidence": 0.90, "reasoning": "序号选择"}

用户输入："张三科技"
输出：{"selected_index": 0, "confidence": 0.95, "reasoning": "名称精确匹配"}

用户输入："取消"
输出：{"selected_index": -1, "confidence": 0.95, "reasoning": "取消选择"}

注意：
1. 如果用户取消，selected_index 应为 -1
2. 描述匹配时，根据候选的 hint 判断
3. 名称精确匹配置信度最高
4. 如果无法匹配，selected_index 应为 -2（表示无法识别）
"""


class AmbiguityResolver:
    """歧义消解器

    处理多个候选时的用户选择，支持 LLM 描述性选择理解。
    """

    # 选择序号模式
    NUMBER_PATTERNS = [
        r"①|②|③|④|⑤",  # 中文序号
        r"[1-5]",  # 数字序号
        r"第[一二三四五]",  # 第X
    ]

    # 取消关键词
    CANCEL_KEYWORDS = ["取消", "都不是", "算了", "不用了"]

    def __init__(self, db: Session, tenant_id: int):
        """初始化歧义消解器

        Args:
            db: 数据库会话
            tenant_id: 租户 ID
        """
        self.db = db
        self.tenant_id = tenant_id

    async def resolve(
        self,
        text: str,
        candidates: List[EntityCandidate],
    ) -> AmbiguityResult:
        """消解歧义

        Args:
            text: 用户输入文本
            candidates: 候选列表

        Returns:
            AmbiguityResult: 消解结果，error 字段表示 AI 服务不可用
        """
        if not candidates:
            return AmbiguityResult(
                resolved=False,
                message="无候选可消解。",
            )

        text_lower = text.lower()

        # 1. 检测取消（代码逻辑，优先级最高）
        if self._is_cancel(text_lower):
            return AmbiguityResult(
                resolved=True,
                selected_id=None,
                message="已取消选择。",
            )

        # 2. 检测序号选择（代码逻辑，优先级高）
        index = self._detect_index(text_lower)
        if index is not None and 0 <= index < len(candidates):
            selected = candidates[index]
            return AmbiguityResult(
                resolved=True,
                selected_id=selected.id,
                message=f"已选择：{selected.name}",
            )

        # 3. 检测名称精确匹配（代码逻辑，优先级高）
        selected_id = self._detect_name(text_lower, candidates)
        if selected_id:
            return AmbiguityResult(
                resolved=True,
                selected_id=selected_id,
                message="已通过名称匹配选择。",
            )

        # 4. LLM 描述性选择理解
        llm_result = await self._resolve_with_llm(text, candidates)

        # AI 服务不可用：仅支持序号/名称，返回提示
        if llm_result.error:
            return AmbiguityResult(
                resolved=False,
                message=f"无法识别选择。请回复序号（①②③）或名称；都不是回「取消」。\n\n{llm_result.error}",
                remaining_candidates=candidates,
                error=llm_result.error,
            )

        # 5. 处理 LLM 结果
        if llm_result.selected_index == -1:
            # 取消
            return AmbiguityResult(
                resolved=True,
                selected_id=None,
                message="已取消选择。",
            )

        if llm_result.selected_index == -2:
            # 无法识别
            return AmbiguityResult(
                resolved=False,
                message='无法识别选择。请回复序号（①②③）、名称或描述性选择（如"选最近跟进的那个"）。',
                remaining_candidates=candidates,
            )

        if 0 <= llm_result.selected_index < len(candidates):
            selected = candidates[llm_result.selected_index]
            return AmbiguityResult(
                resolved=True,
                selected_id=selected.id,
                message=f"已选择：{selected.name}",
            )

        # 未消解
        return AmbiguityResult(
            resolved=False,
            message="无法识别选择。请回复序号（①②③）或名称；都不是回「取消」。",
            remaining_candidates=candidates,
        )

    def _is_cancel(self, text: str) -> bool:
        """检测取消（代码逻辑）"""
        return any(kw in text for kw in self.CANCEL_KEYWORDS)

    def _detect_index(self, text: str) -> Optional[int]:
        """检测序号选择（代码逻辑）"""
        # 中文序号
        chinese_nums = {"①": 0, "②": 1, "③": 2, "④": 3, "⑤": 4}
        for symbol, index in chinese_nums.items():
            if symbol in text:
                return index

        # 数字序号
        digit_match = re.search(r"[1-5]", text)
        if digit_match:
            return int(digit_match.group()) - 1

        # 第X
        ordinal_match = re.search(r"第[一二三四五]", text)
        if ordinal_match:
            ordinal_map = {"一": 0, "二": 1, "三": 2, "四": 3, "五": 4}
            ordinal = ordinal_match.group().replace("第", "")
            return ordinal_map.get(ordinal)

        return None

    def _detect_name(self, text: str, candidates: List[EntityCandidate]) -> Optional[int]:
        """检测名称选择（代码逻辑）"""
        # 去除关键词
        keywords_to_remove = ["选择", "选", "是", "对"]
        clean_text = text
        for kw in keywords_to_remove:
            clean_text = clean_text.replace(kw, "")

        clean_text = clean_text.strip()

        # 匹配候选名称
        for candidate in candidates:
            if candidate.name.lower() == clean_text.lower():
                return candidate.id

            # 部分匹配
            if clean_text.lower() in candidate.name.lower():
                return candidate.id

        return None

    @dataclass
    class _LLMSelectResult:
        """LLM 选择结果"""
        selected_index: int
        confidence: float
        reasoning: str
        error: Optional[str] = None

    async def _resolve_with_llm(
        self,
        text: str,
        candidates: List[EntityCandidate],
    ) -> _LLMSelectResult:
        """使用 LLM 理解描述性选择

        Args:
            text: 用户输入文本
            candidates: 候选列表

        Returns:
            _LLMSelectResult: 选择结果，error 字段表示 AI 服务不可用
        """
        # 获取 AI 配置
        config, api_key = ai_service.get_config_and_key(self.db, self.tenant_id)
        if not config or not api_key:
            logger.warning("AI 配置不可用")
            return self._LLMSelectResult(
                selected_index=-2,
                confidence=0.0,
                reasoning="",
                error="AI 服务未配置，请使用序号或名称选择",
            )

        # 构建候选列表描述
        candidate_desc = self._build_candidate_description(candidates)

        # 调用 LLM
        try:
            user_prompt = f"候选列表：\n{candidate_desc}\n\n用户输入：{text}"
            response = await ai_service._stream_chat_collect(
                api_host=config.api_host,
                api_key=api_key,
                model=config.model_name,
                messages=[
                    {"role": "system", "content": DESCRIBE_SELECT_PROMPT},
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

            return self._LLMSelectResult(
                selected_index=result.get("selected_index", -2),
                confidence=result.get("confidence", 0.0),
                reasoning=result.get("reasoning", ""),
            )

        except Exception as e:
            logger.error(f"LLM 描述性选择失败: {e}")
            return self._LLMSelectResult(
                selected_index=-2,
                confidence=0.0,
                reasoning="",
                error="AI 服务暂时不可用，请使用序号或名称选择",
            )

    def _build_candidate_description(self, candidates: List[EntityCandidate]) -> str:
        """构建候选列表描述"""
        lines = []
        for i, candidate in enumerate(candidates[:5]):  # 最多 5 个
            symbol = ["①", "②", "③", "④", "⑤"][i]
            extra = f"- {candidate.hint}" if candidate.hint else ""
            lines.append(f"{symbol} {candidate.name} {extra}")
        return "\n".join(lines)

    def render_candidates(self, candidates: List[EntityCandidate]) -> str:
        """渲染候选列表"""
        if not candidates:
            return "无候选。"

        lines = ["没锁定到唯一结果，您指的是？"]

        for i, candidate in enumerate(candidates[:5]):  # 最多显示 5 个
            symbol = ["①", "②", "③", "④", "⑤"][i]
            extra = f"（{candidate.hint}）" if candidate.hint else ""
            lines.append(f" {symbol} {candidate.name}{extra}")

        lines.append("")
        lines.append('回序号或名称；也可以描述性选择（如"选最近跟进的那个"）；都不是回「取消」。')

        return "\n".join(lines)


__all__ = [
    "AmbiguityResult",
    "AmbiguityResolver",
]