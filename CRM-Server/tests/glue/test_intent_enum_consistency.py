"""测试 intent prompt 字面量与 IntentType 枚举一致性

Task 4.1: 确保 LLM 输出的 intent 值在 IntentType 枚举范围内。
"""

import re
from app.constants.ai_rules import IntentType


def test_intent_prompt_literals_match_enum():
    """INTENT_PARSE_PROMPT 中的 intent 字面量必须在 IntentType 枚举内"""
    from app.glue.core.intent import INTENT_PARSE_PROMPT

    # 提取 prompt 中列出的 intent 名（格式 "- xxx:" 或 '"intent": "xxx"'）
    # 从"支持的意图类型："段提取
    intent_lines = re.findall(r"- ([a-z_]+):", INTENT_PARSE_PROMPT)

    # 获取枚举有效值
    valid = {e.value for e in IntentType}

    # 交互控制意图（特殊，不在业务枚举内）
    control_intents = {"cancel", "confirm", "correction"}

    # 检查每个 prompt 字面量
    mismatches = []
    for intent in intent_lines:
        if intent in control_intents:
            continue  # 交互控制意图豁免
        if intent not in valid:
            mismatches.append(intent)

    assert not mismatches, f"Prompt 字面量不在枚举内: {mismatches}\n枚举有效值: {valid}"


def test_multi_intent_prompt_literals_match_enum():
    """MULTI_INTENT_PARSE_PROMPT 中的 intent 字面量必须在 IntentType 枚举内"""
    from app.glue.core.intent import MULTI_INTENT_PARSE_PROMPT

    intent_lines = re.findall(r"- ([a-z_]+):", MULTI_INTENT_PARSE_PROMPT)

    valid = {e.value for e in IntentType}
    control_intents = {"cancel", "confirm", "correction"}

    mismatches = []
    for intent in intent_lines:
        if intent in control_intents:
            continue
        if intent not in valid:
            mismatches.append(intent)

    assert not mismatches, f"Prompt 字面量不在枚举内: {mismatches}\n枚举有效值: {valid}"