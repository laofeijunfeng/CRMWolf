"""AI OpenAPI 意图层路由

负责自然语言 → 结构化意图 + 实体的转换。
参见: CRM-Docs/standards/AI-API-STANDARD.md
"""

from typing import Dict, Any, List, Optional
from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.api.ai.deps import get_ai_user
from app.core.database import get_db
from app.models.user import User
from app.constants.ai_rules import IntentType, INTENT_DESCRIPTIONS, BUSINESS_RULES
from app.services.ai.intent_parser import (
    intent_parser,
    entity_extractor,
    rule_matcher,
    IntentResult,
    EntityResult,
)


router = APIRouter()


# ==================== 请求/响应 Schema ====================

class IntentParseRequest(BaseModel):
    """意图解析请求"""

    text: str = Field(..., description="用户输入文本")
    context: Optional[Dict[str, Any]] = Field(default=None, description="上下文信息")


class IntentParseResponse(BaseModel):
    """意图解析响应"""

    intent: str = Field(..., description="意图类型")
    intent_description: str = Field(..., description="意图描述")
    confidence: float = Field(..., ge=0.0, le=1.0, description="置信度")
    reasoning: str = Field(..., description="判断依据")
    entities: Optional[Dict[str, Any]] = Field(default=None, description="提取的实体")


class IntentParseMultiResponse(BaseModel):
    """多意图解析响应"""

    intents: List[IntentParseResponse] = Field(..., description="意图列表")


class EntityExtractRequest(BaseModel):
    """实体提取请求"""

    text: str = Field(..., description="用户输入文本")
    context: Optional[Dict[str, Any]] = Field(default=None, description="上下文信息")
    target_entities: Optional[List[str]] = Field(
        default=None,
        description="目标实体类型（如 ['amount', 'customer_id']）",
    )


class EntityExtractResponse(BaseModel):
    """实体提取响应"""

    entities: Dict[str, Dict[str, Any]] = Field(..., description="提取的实体")
    text: str = Field(..., description="原始文本")


class RuleMatchRequest(BaseModel):
    """规则匹配请求"""

    intent: str = Field(..., description="意图类型")
    text: str = Field(..., description="用户输入文本")


class RuleMatchResponse(BaseModel):
    """规则匹配响应"""

    recommended_actions: List[Dict[str, Any]] = Field(..., description="推荐的 Action 序列")
    rule_triggered: bool = Field(default=False, description="是否触发规则库")


# ==================== 意图解析 ====================

@router.post("/parse", response_model=IntentParseResponse, summary="解析用户意图")
async def parse_intent(
    request: IntentParseRequest,
    user: User = Depends(get_ai_user),
) -> IntentParseResponse:
    """解析用户输入意图

    返回最可能的意图类型、置信度和判断依据。
    """
    result: IntentResult = intent_parser.parse(request.text, request.context)

    # 转换 IntentType 枚举为字符串
    intent_str = result.intent.value
    intent_desc = INTENT_DESCRIPTIONS.get(result.intent, "未知意图")

    return IntentParseResponse(
        intent=intent_str,
        intent_description=intent_desc,
        confidence=result.confidence,
        reasoning=result.reasoning,
        entities=result.entities,
    )


@router.post("/parse-multi", response_model=IntentParseMultiResponse, summary="解析多个意图")
async def parse_intent_multi(
    request: IntentParseRequest,
    user: User = Depends(get_ai_user),
) -> IntentParseMultiResponse:
    """解析多个可能的意图

    用于复杂输入，如"跟进一下这个客户，然后设置提醒"
    """
    results = intent_parser.parse_multi(request.text, request.context)

    intents = []
    for result in results:
        intent_str = result.intent.value
        intent_desc = INTENT_DESCRIPTIONS.get(result.intent, "未知意图")
        intents.append(IntentParseResponse(
            intent=intent_str,
            intent_description=intent_desc,
            confidence=result.confidence,
            reasoning=result.reasoning,
            entities=result.entities,
        ))

    return IntentParseMultiResponse(intents=intents)


# ==================== 实体提取 ====================

@router.post("/extract", response_model=EntityExtractResponse, summary="提取实体")
async def extract_entities(
    request: EntityExtractRequest,
    user: User = Depends(get_ai_user),
    db: Session = Depends(get_db),
) -> EntityExtractResponse:
    """从用户文本提取实体

    可提取：
    - 金额（如"10万"、"5000元"）
    - 日期（如"明天"、"下周三"）
    - 客户引用（如"#123"、"这个客户"）
    - 商机引用（如"商机#456"）
    """
    entities = entity_extractor.extract_all(request.text, request.context)

    # 转换 EntityResult 为字典
    entities_dict = {}
    for entity_type, result in entities.items():
        entities_dict[entity_type] = {
            "value": result.entity_value,
            "confidence": result.confidence,
            "source": result.source,
        }

    return EntityExtractResponse(
        entities=entities_dict,
        text=request.text,
    )


# ==================== 规则匹配 ====================

@router.post("/rules/match", response_model=RuleMatchResponse, summary="匹配业务规则")
async def match_rules(
    request: RuleMatchRequest,
    user: User = Depends(get_ai_user),
) -> RuleMatchResponse:
    """根据意图匹配业务规则

    返回推荐的 Action 序列。
    """
    # 转换字符串为 IntentType 枚举
    try:
        intent = IntentType(request.intent)
    except ValueError:
        intent = IntentType.UNKNOWN

    actions = rule_matcher.match(intent, request.text)

    # 检查是否触发规则库
    rule_triggered = any(a.get("rule_triggered") for a in actions)

    return RuleMatchResponse(
        recommended_actions=actions,
        rule_triggered=rule_triggered,
    )


@router.get("/rules/list", summary="获取意图类型列表")
async def list_intent_types(
    user: User = Depends(get_ai_user),
) -> Dict[str, Any]:
    """获取所有支持的意图类型"""
    return {
        "intent_types": [
            {
                "code": intent.value,
                "description": INTENT_DESCRIPTIONS.get(intent, ""),
            }
            for intent in IntentType
        ],
        "total": len(IntentType),
    }


__all__ = ["router"]