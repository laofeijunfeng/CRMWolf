"""AI OpenAPI 服务层

Phase 2 实现后将包含 ActionExecutor 等服务。
参见: CRM-Docs/standards/AI-API-STANDARD.md
"""

from app.services.ai.action_executor import ActionExecutor
from app.services.ai.intent_parser import (
    IntentParser,
    IntentResult,
    EntityExtractor,
    EntityResult,
    RuleMatcher,
    intent_parser,
    entity_extractor,
    rule_matcher,
)
from app.services.ai.idempotency import (
    IdempotencyManager,
    idempotency_manager,
)

__all__ = [
    "ActionExecutor",
    "IntentParser",
    "IntentResult",
    "EntityExtractor",
    "EntityResult",
    "RuleMatcher",
    "intent_parser",
    "entity_extractor",
    "rule_matcher",
    "IdempotencyManager",
    "idempotency_manager",
]