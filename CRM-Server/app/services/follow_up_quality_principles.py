"""Shared follow-up quality principles used by runtime and async evaluation."""
from __future__ import annotations


FOLLOW_UP_QUALITY_PRINCIPLES = """1. 事实优先原则（20分）：只写客观事实、客户原话、已发生动作；不要把“感觉、应该、挺好、有戏”等主观判断当作有效信息。
2. 动作闭环原则（20分）：必须说明下一步什么时间、谁、做什么；“保持跟进、再联系、有消息再说”不得高分。
3. 阶段推进原则（15分）：结合当前商机和前序跟进，判断本次是否推动阶段、明确新节点或消除关键不确定性；连续原地询问不得高分。
4. 决策穿透原则（15分）：是否识别决策人、影响人、采购/技术/财务等角色和诉求；只写“客户说”不得高分。
5. 异议具象原则（15分）：是否具体记录价格、竞品、预算、流程、技术、安全等异议及原因；没有异议时可说明“本次未出现明确异议”，但不能编造。
6. 信息可接力原则（15分）：团队其他人看完后是否知道客户、对接人、当前进展、风险和下一步，不需要再问记录者。"""


def get_follow_up_quality_principles() -> str:
    """Return the effective six principles for follow-up quality evaluation."""
    return FOLLOW_UP_QUALITY_PRINCIPLES
