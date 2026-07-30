"""Canonical structuring and evaluation rules for customer activities."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ActivityEvaluationRubric:
    score_rule: str
    title: str
    principles: str
    emphasis: str


FOLLOW_UP_RUBRIC = ActivityEvaluationRubric(
    score_rule="follow_up",
    title="客户跟进有效性评分规则",
    principles="""1. 事实清晰原则（20分）：记录客观事实、客户原话、已发生动作；主观感觉不得高分。
2. 客户反馈原则（20分）：清楚记录客户需求、态度、疑问、异议或确认信息；只写“已沟通”不得高分。
3. 推进动作原则（20分）：体现销售阶段、关键节点、决策链或采购流程的新进展；连续原地询问不得高分。
4. 风险异议原则（15分）：具体记录价格、竞品、预算、流程、技术、安全等异议及原因；没有异议可说明未出现。
5. 下一步闭环原则（15分）：说明下一步什么时间、谁、做什么；“保持跟进、有消息再说”不得高分。
6. 信息可接力原则（10分）：团队其他人看完后知道客户、对接人、当前进展、风险和下一步。""",
    emphasis="普通客户跟进重点看客户反馈、推进动作、风险异议和下一步闭环是否清楚。",
)


MEETING_RUBRIC = ActivityEvaluationRubric(
    score_rule="meeting",
    title="客户会议纪要有效性评分规则",
    principles="""1. 会议主题与背景原则（15分）：说明会议主题、业务背景、会议目的或触发原因；只有流水账不得高分。
2. 参会角色原则（15分）：清楚区分我方和客户方成员、角色、职责或影响力；只写“双方参会”不得高分。
3. 核心纪要原则（20分）：完整记录关键讨论、客户诉求、方案回应、决策信息和承诺事项。
4. 关注点问答原则（15分）：沉淀客户关注点、问题、答复和未决事项；只写结论不得高分。
5. 风险分歧原则（15分）：明确风险、异议、分歧、阻塞点及可能影响；没有风险可说明未出现。
6. 行动计划原则（20分）：明确后续行动、责任人、时间节点和交付物；没有 owner/time/action 不得高分。""",
    emphasis="会议记录重点看参会角色、会议背景、关键问答、风险分歧、承诺事项和行动计划是否完整。",
)


def get_activity_evaluation_rubric(score_rule: str | None) -> ActivityEvaluationRubric:
    if score_rule == "meeting":
        return MEETING_RUBRIC
    return FOLLOW_UP_RUBRIC


def get_follow_up_quality_principles() -> str:
    """Compatibility entry for existing Agent quality code."""
    return FOLLOW_UP_RUBRIC.principles

