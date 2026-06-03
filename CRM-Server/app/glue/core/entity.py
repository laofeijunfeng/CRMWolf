"""EntityResolver

消解"这个/那个/#ID"等模糊引用，支持 LLM 自然语言解析。

参见: CRM-Docs/requirements/AI-GLUE-REQUIREMENTS.md 九、核心组件设计 9.2
参见: CRM-Docs/plans/AI-GLUE-IMPLEMENTATION-PLAN.md Phase 2.3
"""

from typing import Dict, Any, Optional, List
from dataclasses import dataclass
import re
import json
import logging

from sqlalchemy.orm import Session

from app.glue.core.session import GlueSession
from app.glue.core.types import EntityCandidate, EntityResolveResult
from app.services.ai_service import ai_service
from app.services.ai.entity_search import EntitySearchService
from app.utils.name_normalizer import normalize_corp_name  # R-ST-02


logger = logging.getLogger(__name__)


@dataclass
class EntityExtractionResult:
    """LLM 实体提取结果"""

    entity_type: str  # "Customer" | "Opportunity"
    name_keyword: str  # 提取的名称关键词
    context: Optional[str] = None  # 上下文描述
    confidence: float = 0.0
    error: Optional[str] = None  # 错误信息


# LLM 实体提取系统提示词
ENTITY_EXTRACTION_PROMPT = """你是一个实体提取助手。
从用户输入中提取实体类型和名称关键词。

输出 JSON 格式：
{
    "entity_type": "Customer" | "Opportunity",
    "name_keyword": "提取的名称关键词",
    "context": "可选的上下文描述"
}

示例：
输入："跟进张三客户" → {"entity_type": "Customer", "name_keyword": "张三"}
输入："张三的商机" → {"entity_type": "Opportunity", "name_keyword": "张三", "context": "关联客户"}
输入："给#456加跟进" → {"entity_type": "Opportunity", "name_keyword": "", "context": "ID引用"}
输入："跟进一下这个客户" → {"entity_type": "Customer", "name_keyword": "", "context": "代词引用"}

注意：
1. 如果输入包含 #数字 格式，这是 ID 引用，name_keyword 应为空
2. 如果输入包含"这个/那个/该"等代词，name_keyword 应为空，context 标记为"代词引用"
3. 只提取明确的名称关键词，不要提取其他无关词汇
"""


class EntityResolver:
    """实体消解器

    处理模糊引用：
    - #ID 精确匹配 → entity_id（置信度 0.90）
    - "这个客户" → session.recent_entities.customer_id（置信度 0.85）
    - "张三" → LLM 解析 + CRUD 搜索 → 唯一？返回 ID；多个？返回 candidates
    """

    def __init__(self, db: Session, tenant_id: int):
        """初始化实体消解器

        Args:
            db: 数据库会话
            tenant_id: 租户 ID（用于 CRUD 搜索隔离）
        """
        self.db = db
        self.tenant_id = tenant_id

    async def resolve(
        self,
        text: str,
        entity_type: str,
        session: GlueSession,
    ) -> EntityResolveResult:
        """消解实体引用（R-ST-01：所有路径汇入搜索工具）

        优先级顺序（R-ST-01）：
        ① explicit #ID 命中 → load_by_id
        ② recent shortcut → load_by_id（仅当归一化名匹配）
        ③ fallback fuzzy → search_customers/opportunities

        Args:
            text: 用户输入文本
            entity_type: 实体类型（Customer/Opportunity）
            session: 当前会话状态

        Returns:
            EntityResolveResult: 消解结果
        """
        # 初始化搜索工具（R-ST-01）
        search_service = EntitySearchService(self.db, self.tenant_id)

        # ① explicit #ID 命中 → load_by_id（R-ST-05）
        id_match = self._match_explicit_id(text, entity_type)
        if id_match:
            candidate = search_service.load_customer_by_id(id_match) if entity_type == "Customer" \
                        else search_service.load_opportunity_by_id(id_match)
            if candidate:
                return EntityResolveResult(
                    entity_id=candidate.id,
                    entity_type=entity_type,
                    confidence=0.90,
                )
            # ID 不存在或无权限 → 返回错误（R-ST-04: 0 结果是流程）
            return EntityResolveResult(
                entity_id=None,
                entity_type=entity_type,
                confidence=0.0,
                error=f"#{id_match} 不存在或无权限",
            )

        # ② recent shortcut → load_by_id（R-ST-05）
        pronoun_match = self._match_pronoun(text, entity_type, session)
        if pronoun_match:
            candidate = search_service.load_customer_by_id(pronoun_match) if entity_type == "Customer" \
                        else search_service.load_opportunity_by_id(pronoun_match)
            if candidate:
                # 验证归一化名匹配（ST-2：需要验证而非直接 shortcut）
                kw_norm = normalize_corp_name(self._extract_keyword(text))
                cand_norm = normalize_corp_name(candidate.name)
                if cand_norm == kw_norm:
                    return EntityResolveResult(
                        entity_id=candidate.id,
                        entity_type=entity_type,
                        confidence=0.85,
                    )
                # 不匹配 → 降级到③（继续搜索）

        # ③ fallback fuzzy → search_entities（R-ST-01）
        candidates = await self._search_by_name(text, entity_type)

        # AI 服务不可用
        if candidates is None:
            return EntityResolveResult(
                entity_id=None,
                entity_type=entity_type,
                confidence=0.0,
                error="AI 服务未配置或暂时不可用，请联系管理员配置 AI 服务",
            )

        if len(candidates) == 1:
            # 唯一匹配 → lock（ST-4）
            return EntityResolveResult(
                entity_id=candidates[0].id,
                entity_type=entity_type,
                confidence=0.75,
            )

        if len(candidates) > 1:
            # 多候选 → 返回歧义列表（ST-4）
            return EntityResolveResult(
                entity_id=None,
                entity_type=entity_type,
                confidence=0.50,
                candidates=candidates,
            )

        # 0 结果 → 返回错误（R-ST-04）
        return EntityResolveResult(
            entity_id=None,
            entity_type=entity_type,
            confidence=0.0,
            error=f"未找到匹配的{entity_type}",
        )

    def _extract_keyword(self, text: str) -> str:
        """从代词引用中提取关键词（用于归一化验证）

        例如："这个光大证券客户" → "光大证券"
        """
        import re
        # 去除代词和实体类型词
        text_lower = text.lower()
        for pronoun in ["这个", "那个", "该", "一下"]:
            text_lower = text_lower.replace(pronoun, "")
        for entity_word in ["客户", "商机"]:
            text_lower = text_lower.replace(entity_word, "")
        return text_lower.strip()

    def _match_explicit_id(self, text: str, entity_type: str) -> Optional[int]:
        """#ID 精确匹配"""
        pattern = r"#(\d+)"
        match = re.search(pattern, text)

        if match:
            return int(match.group(1))

        # 商机特定格式："商机#456"
        if entity_type == "Opportunity":
            pattern = r"商机\s*#(\d+)"
            match = re.search(pattern, text)
            if match:
                return int(match.group(1))

        return None

    def _match_pronoun(self, text: str, entity_type: str, session: GlueSession) -> Optional[int]:
        """代词引用"""
        if not session.recent_entities:
            return None

        text_lower = text.lower()

        if entity_type == "Customer":
            if "这个客户" in text_lower or "那个客户" in text_lower or "该客户" in text_lower:
                return session.recent_entities.customer_id

        elif entity_type == "Opportunity":
            if "这个商机" in text_lower or "那个商机" in text_lower or "该商机" in text_lower:
                return session.recent_entities.opportunity_id

        return None

    async def _search_by_name(self, text: str, entity_type: str) -> List[EntityCandidate]:
        """搜索实体名称（LLM + CRUD）

        Args:
            text: 用户输入文本
            entity_type: 实体类型

        Returns:
            候选列表，或 None 表示 AI 服务不可用
        """
        # Step 1: LLM 提取实体信息
        extraction = await self._extract_entity_info_with_llm(text, entity_type)

        # AI 服务不可用，返回 None 表示错误
        if extraction.error:
            return None

        # 如果是 ID 引用或代词引用，无需搜索
        if extraction.context in ["ID引用", "代词引用"] or not extraction.name_keyword:
            return []

        # Step 2: CRUD 搜索候选
        candidates = await self._search_candidates(extraction.entity_type, extraction.name_keyword)
        return candidates

    async def _extract_entity_info_with_llm(
        self,
        text: str,
        entity_type_hint: str,
    ) -> EntityExtractionResult:
        """使用 LLM 提取实体类型和名称关键词

        Args:
            text: 用户输入文本
            entity_type_hint: 实体类型提示

        Returns:
            EntityExtractionResult: 提取结果，error 字段表示 AI 服务不可用
        """
        # 1. 获取 AI 配置
        config, api_key = ai_service.get_config_and_key(self.db)
        if not config or not api_key:
            logger.warning("AI 配置不可用")
            return EntityExtractionResult(
                entity_type=entity_type_hint,
                name_keyword="",
                error="AI 服务未配置，请联系管理员配置 AI 服务后再使用",
            )

        # 2. 调用 LLM
        try:
            response = await ai_service._stream_chat_collect(
                api_host=config.api_host,
                api_key=api_key,
                model=config.model_name,
                messages=[
                    {"role": "system", "content": ENTITY_EXTRACTION_PROMPT},
                    {"role": "user", "content": text}
                ],
                temperature=0.1,  # 低温度，精确提取
                max_tokens=256,
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

            return EntityExtractionResult(
                entity_type=result.get("entity_type", entity_type_hint),
                name_keyword=result.get("name_keyword", ""),
                context=result.get("context"),
                confidence=0.80,
            )

        except Exception as e:
            logger.error(f"LLM 提取失败: {e}")
            return EntityExtractionResult(
                entity_type=entity_type_hint,
                name_keyword="",
                error=f"AI 服务暂时不可用，请稍后重试",
            )

    
    async def _search_candidates(
        self,
        entity_type: str,
        name_keyword: str,
    ) -> List[EntityCandidate]:
        """使用只读服务层搜索候选

        Args:
            entity_type: 实体类型
            name_keyword: 名称关键词

        Returns:
            候选列表（直接返回 EntitySearchService 结果）
        """
        if not name_keyword:
            return []

        # 使用 EntitySearchService（只读服务层）  # READONLY_BRIDGE: EntityResolver 只读路径
        search_service = EntitySearchService(self.db, self.tenant_id)
        return search_service.search_entities(entity_type, name_keyword, limit=5)  # R-ST-03: limit=5~8


__all__ = [
    "EntityCandidate",
    "EntityResolveResult",
    "EntityExtractionResult",
    "EntityResolver",
]