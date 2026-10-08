"""规模区间解析的 prompt 规则回归测试。

锁定两条规则（避免回归为日期误判或思考死循环）：
1. 纯数字区间（~、-、到 连接）是人数规模，不是日期
2. 跨枚举段的区间按上限归段
"""
import pytest

from app.services.ai_parser.customer_parser import CustomerAIParser
from app.services.ai_parser.lead_parser import LeadAIParser


@pytest.mark.parametrize("parser_cls", [LeadAIParser, CustomerAIParser], ids=["lead", "customer"])
class TestScaleIntervalPromptRules:
    def _prompt(self, parser_cls) -> str:
        return parser_cls().get_system_prompt(None, None)

    def test_prompt_states_numeric_intervals_are_scale(self, parser_cls):
        prompt = self._prompt(parser_cls)
        assert "纯数字区间是人数规模" in prompt
        assert "不是日期" in prompt

    def test_prompt_covers_tilde_dash_and_dao_connectors(self, parser_cls):
        prompt = self._prompt(parser_cls)
        assert "10~29" in prompt
        assert "100-199" in prompt
        assert "15到40" in prompt

    def test_prompt_gives_cross_segment_rule_by_upper_bound(self, parser_cls):
        prompt = self._prompt(parser_cls)
        assert "按区间的**上限**归段" in prompt
        assert "800~1200" in prompt
        assert "不要反复权衡" in prompt

    def test_prompt_examples_map_to_expected_segments(self, parser_cls):
        prompt = self._prompt(parser_cls)
        # 示例映射必须与枚举段一致
        assert '"10~29" →\n"1-50人"' in prompt or '"10~29" → "1-50人"' in prompt.replace('"\n+"', '" "')
