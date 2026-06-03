"""AI OpenAPI 意图解析服务

将用户自然语言转换为结构化意图 + 实体。
支持关键词匹配（快速）和 LLM 解析（高级）。
参见: CRM-Docs/standards/AI-API-STANDARD.md
"""

from typing import Dict, Any, List, Optional, Tuple
from dataclasses import dataclass
import re

from app.constants.ai_rules import IntentType, INTENT_DESCRIPTIONS, BUSINESS_RULES


@dataclass
class IntentResult:
    """意图解析结果"""

    intent: IntentType
    confidence: float
    reasoning: str
    entities: Dict[str, Any] = None
    missing_fields: List[str] = None  # 缺失的必填字段提示


@dataclass
class EntityResult:
    """实体提取结果"""

    entity_type: str
    entity_value: Any
    confidence: float
    source: str  # "text_extract", "context_inherit", "default"


# ==================== 关键词映射 ====================

INTENT_KEYWORDS: Dict[IntentType, List[str]] = {
    IntentType.CREATE_FOLLOW_UP: [
        "跟进", "记录一下", "写个跟进", "添加跟进", "备注一下",
        "更新跟进", "跟进记录", "记录跟进", "添加备注",
    ],
    IntentType.CREATE_OPPORTUNITY: [
        "创建商机", "新建商机", "开个商机", "添加商机", "建立商机",
        "登记商机", "录入商机",
    ],
    IntentType.UPDATE_OPPORTUNITY: [
        "更新商机", "修改商机", "改一下商机", "调整商机",
        "更新金额", "改金额", "调整金额", "修改金额",
        "金额改成", "金额改", "改成金额", "金额改为",
        "金额更新", "金额调整", "改一下金额", "调整一下金额",
    ],
    IntentType.ADVANCE_STAGE: [
        "推进阶段", "进入下一阶段", "阶段推进", "推进到",
        "进入", "下一阶段", "更新阶段",
    ],
    IntentType.WIN_OPPORTUNITY: [
        "赢单", "成交", "签单", "赢了", "成单", "拿下",
        "成功", "成交了", "签合同",
    ],
    IntentType.LOSE_OPPORTUNITY: [
        "输单", "失败", "丢了", "没成", "输掉", "放弃",
        "竞争失败", "没拿下",
    ],
    IntentType.CONVERT_LEAD: [
        "转化", "转化线索", "转为客户", "转化客户", "线索转化",
        "转为成交客户",
    ],
    IntentType.SET_REMINDER: [
        "提醒", "设置提醒", "提醒我", "备忘", "待办",
        "下次跟进", "预约跟进", "安排跟进", "稍后跟进",
    ],
    IntentType.QUERY_INFO: [
        "查询", "查看", "看看", "帮我看看", "查一下", "显示",
        "列表", "详情", "信息", "什么状态", "多少",
    ],
}

# 金额提取正则
# 优先匹配带单位的金额，如 "35万"、"10w"、"5000元"
AMOUNT_PATTERN_WITH_UNIT = re.compile(
    r"(\d+(?:\.\d+)?)\s*(万|w|元|块|千|k)",
    re.IGNORECASE
)

# 匹配金额关键词后的数字，如 "金额5000"、"改成100"
AMOUNT_PATTERN_AFTER_KEYWORD = re.compile(
    r"(金额|改成|改为|改|调整|更新)\s*(\d+(?:\.\d+)?)",
    re.IGNORECASE
)

# 日期提取正则（简单版）
DATE_PATTERN = re.compile(
    r"(今天|明天|后天|下周|下周一|下周二|下周三|下周四|下周五|下个月|\d{1,2}月\d{1,2}[日号]|\d{4}-\d{1,2}-\d{1,2})"
)

# 客户名提取正则（假设格式）
CUSTOMER_PATTERN = re.compile(
    r"(客户|#\d+|为[一-龥]+)",
)


class IntentParser:
    """意图解析器

    实现策略：
    1. 关键词匹配（快速，置信度中等）
    2. 规则库触发（精确，置信度高）
    3. LLM 解析（高级，置信度最高）
    """

    def parse(self, text: str, context: Optional[Dict[str, Any]] = None) -> IntentResult:
        """解析用户输入意图

        Args:
            text: 用户输入文本
            context: 上下文信息（如当前页面、选中实体等）

        Returns:
            IntentResult: 解析结果
        """
        # 1. 规则库触发（优先级最高）
        rule_result = self._match_rules(text)
        if rule_result:
            return rule_result

        # 2. 关键词匹配
        keyword_result = self._match_keywords(text)
        if keyword_result:
            return keyword_result

        # 3. 未知意图
        return IntentResult(
            intent=IntentType.UNKNOWN,
            confidence=0.0,
            reasoning="未匹配到任何已知意图关键词或规则",
        )

    def _match_rules(self, text: str) -> Optional[IntentResult]:
        """从业务规则库匹配"""
        for rule in BUSINESS_RULES:
            if rule.get("trigger") == "keyword":
                keyword = rule.get("keyword", "")
                if keyword in text.lower():
                    action = rule.get("action", "")
                    # 映射 action 到 IntentType
                    intent_map = {
                        "update_stage": IntentType.ADVANCE_STAGE,
                        "win_opportunity": IntentType.WIN_OPPORTUNITY,
                        "lose_opportunity": IntentType.LOSE_OPPORTUNITY,
                    }
                    intent = intent_map.get(action, IntentType.UNKNOWN)
                    return IntentResult(
                        intent=intent,
                        confidence=0.95,
                        reasoning=f"规则触发: 关键词 '{keyword}' → 动作 '{action}'",
                        entities={"target": rule.get("target")},
                    )
        return None

    def _match_keywords(self, text: str) -> Optional[IntentResult]:
        """关键词匹配"""
        text_lower = text.lower()
        best_match: Tuple[IntentType, float, str] = None

        for intent_type, keywords in INTENT_KEYWORDS.items():
            for keyword in keywords:
                if keyword in text_lower:
                    # 计算置信度：关键词越长，置信度越高
                    confidence = min(0.5 + len(keyword) * 0.05, 0.85)
                    if best_match is None or confidence > best_match[1]:
                        best_match = (intent_type, confidence, f"关键词匹配: '{keyword}'")

        if best_match:
            return IntentResult(
                intent=best_match[0],
                confidence=best_match[1],
                reasoning=best_match[2],
            )
        return None

    def parse_multi(self, text: str, context: Optional[Dict[str, Any]] = None) -> List[IntentResult]:
        """解析多个可能的意图（返回候选列表）

        用于复杂输入，如"跟进一下这个客户，然后设置提醒"
        """
        results = []

        # 检测分隔符
        separators = ["然后", "接着", "再", "并且", "同时", "，", "。"]
        segments = [text]
        for sep in separators:
            if sep in text:
                segments = text.split(sep)
                break

        # 解析每个片段
        for segment in segments:
            segment = segment.strip()
            if segment:
                result = self.parse(segment, context)
                if result.intent != IntentType.UNKNOWN:
                    results.append(result)

        return results


class EntityExtractor:
    """实体提取器

    从用户文本中提取：
    - 金额（如"10万"、"5000元"）
    - 日期（如"明天"、"下周三"）
    - 客户名（需结合数据库）
    - 商机名
    """

    def extract_amount(self, text: str) -> Optional[EntityResult]:
        """提取金额

        优先级：
        1. 带单位的金额（如 "35万"、"10w"）
        2. 金额关键词后的数字（如 "金额改成5000"）
        """
        # 优先匹配带单位的金额
        match = AMOUNT_PATTERN_WITH_UNIT.search(text)
        if match:
            amount_str = match.group(1)
            unit = match.group(2)

            try:
                amount = float(amount_str)
                # 单位转换
                if unit in ["万", "w"]:
                    amount *= 10000
                elif unit in ["千", "k"]:
                    amount *= 1000

                return EntityResult(
                    entity_type="amount",
                    entity_value=amount,
                    confidence=0.8,
                    source="text_extract",
                )
            except ValueError:
                pass

        # 匹配金额关键词后的数字
        match = AMOUNT_PATTERN_AFTER_KEYWORD.search(text)
        if match:
            amount_str = match.group(2)

            try:
                amount = float(amount_str)
                return EntityResult(
                    entity_type="amount",
                    entity_value=amount,
                    confidence=0.7,
                    source="text_extract",
                )
            except ValueError:
                pass

        return None

    def extract_date(self, text: str) -> Optional[EntityResult]:
        """提取日期（返回相对日期描述）"""
        match = DATE_PATTERN.search(text)
        if match:
            date_str = match.group(1)
            return EntityResult(
                entity_type="date",
                entity_value=date_str,
                confidence=0.7,
                source="text_extract",
            )
        return None

    def extract_customer_reference(self, text: str, context: Optional[Dict[str, Any]] = None) -> Optional[EntityResult]:
        """提取客户引用

        优先级：
        1. 上下文继承（如当前页面是客户详情）
        2. 文本中的明确引用（如"客户#123"）
        """
        # 上下文继承
        if context and context.get("current_entity_type") == "Customer":
            return EntityResult(
                entity_type="customer_id",
                entity_value=context.get("current_entity_id"),
                confidence=0.95,
                source="context_inherit",
            )

        # 文本中的明确引用
        # 优先匹配 "客户#XXX" 格式
        match = re.search(r"客户\s*#(\d+)", text)
        if match:
            return EntityResult(
                entity_type="customer_id",
                entity_value=int(match.group(1)),
                confidence=0.9,
                source="text_extract",
            )

        # 仅在没有商机引用时匹配通用 #XXX（避免误抢）
        if not re.search(r"商机\s*#", text):
            match = re.search(r"#(\d+)", text)
            if match:
                return EntityResult(
                    entity_type="customer_id",
                    entity_value=int(match.group(1)),
                    confidence=0.85,
                    source="text_extract",
                )

        # 代词引用（如"这个客户"、"那个客户"）
        if re.search(r"(这个|那个|当前)客户", text):
            if context and context.get("current_entity_type") == "Customer":
                return EntityResult(
                    entity_type="customer_id",
                    entity_value=context.get("current_entity_id"),
                    confidence=0.85,
                    source="context_inherit",
                )

        return None

    def extract_opportunity_reference(self, text: str, context: Optional[Dict[str, Any]] = None) -> Optional[EntityResult]:
        """提取商机引用"""
        # 上下文继承
        if context and context.get("current_entity_type") == "Opportunity":
            return EntityResult(
                entity_type="opportunity_id",
                entity_value=context.get("current_entity_id"),
                confidence=0.95,
                source="context_inherit",
            )

        # 文本中的明确引用
        match = re.search(r"商机\s*#(\d+)", text)
        if match:
            return EntityResult(
                entity_type="opportunity_id",
                entity_value=int(match.group(1)),
                confidence=0.9,
                source="text_extract",
            )

        return None

    def extract_all(self, text: str, context: Optional[Dict[str, Any]] = None) -> Dict[str, EntityResult]:
        """提取所有可能的实体"""
        entities = {}

        amount = self.extract_amount(text)
        if amount:
            entities["amount"] = amount

        date = self.extract_date(text)
        if date:
            entities["date"] = date

        customer = self.extract_customer_reference(text, context)
        if customer:
            entities["customer_id"] = customer

        opportunity = self.extract_opportunity_reference(text, context)
        if opportunity:
            entities["opportunity_id"] = opportunity

        return entities


class RuleMatcher:
    """规则匹配器

    根据用户输入匹配业务规则，返回推荐的 Action 序列。
    """

    def match(self, intent: IntentType, text: str) -> List[Dict[str, Any]]:
        """匹配规则，返回推荐的 Action

        Args:
            intent: 解析出的意图
            text: 用户输入

        Returns:
            推荐的 Action 序列
        """
        actions = []

        # 1. 直接意图 → Action 映射
        intent_action_map = {
            IntentType.CREATE_FOLLOW_UP: [{"action": "create_follow_up", "risk": "low"}],
            IntentType.CREATE_OPPORTUNITY: [{"action": "init_opportunity", "risk": "medium"}],
            IntentType.UPDATE_OPPORTUNITY: [{"action": "update_amount", "risk": "medium"}],
            IntentType.ADVANCE_STAGE: [{"action": "update_stage", "risk": "medium"}],
            IntentType.WIN_OPPORTUNITY: [{"action": "win_opportunity", "risk": "high"}],
            IntentType.LOSE_OPPORTUNITY: [{"action": "lose_opportunity", "risk": "high"}],
            IntentType.CONVERT_LEAD: [{"action": "convert_lead", "risk": "high"}],
            IntentType.SET_REMINDER: [{"action": "set_reminder", "risk": "low"}],
        }

        base_actions = intent_action_map.get(intent, [])
        actions.extend(base_actions)

        # 2. 规则库触发
        for rule in BUSINESS_RULES:
            if rule.get("trigger") == "keyword":
                keyword = rule.get("keyword", "")
                if keyword in text.lower():
                    actions.append({
                        "action": rule.get("action"),
                        "risk": "medium",
                        "rule_triggered": True,
                        "rule_description": rule.get("description"),
                    })

        return actions


# ==================== 导出 ====================

intent_parser = IntentParser()
entity_extractor = EntityExtractor()
rule_matcher = RuleMatcher()

__all__ = [
    "IntentParser",
    "IntentResult",
    "EntityExtractor",
    "EntityResult",
    "RuleMatcher",
    "intent_parser",
    "entity_extractor",
    "rule_matcher",
]