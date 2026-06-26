"""Tests for AI Summary DX Optimization modules"""

import pytest
from app.services.agent.phase_contracts import Phase1Output, Phase2Output, Phase3Output


class TestPhaseContracts:
    """Test phase data contracts"""

    def test_phase1_output_creation(self):
        """Test Phase1Output dataclass creation"""
        output = Phase1Output(
            raw_data={"id": 123, "name": "test"},
            enhanced_data={"customer": {"id": 123, "opportunities": []}},
            enhancement_status="success",
            enhancement_latency_ms=150.5,
        )
        assert output.raw_data["id"] == 123
        assert output.enhancement_status == "success"
        assert output.enhancement_latency_ms == 150.5

    def test_phase1_output_fallback_status(self):
        """Test Phase1Output with fallback status"""
        output = Phase1Output(
            raw_data={"id": 123},
            enhanced_data=None,
            enhancement_status="fallback",
            enhancement_latency_ms=0,
        )
        assert output.enhanced_data is None
        assert output.enhancement_status == "fallback"

    def test_phase1_output_timeout_status(self):
        """Test Phase1Output with timeout status"""
        output = Phase1Output(
            raw_data={},
            enhanced_data=None,
            enhancement_status="timeout",
            enhancement_latency_ms=500,
        )
        assert output.enhancement_status == "timeout"

    def test_phase2_output_creation(self):
        """Test Phase2Output dataclass creation"""
        output = Phase2Output(
            scenario="query",
            scenario_priority=7,
            scenario_confidence=0.95,
            input_data={"customer": {"id": 123}},
        )
        assert output.scenario == "query"
        assert output.scenario_priority == 7
        assert output.scenario_confidence == 0.95

    def test_phase2_output_edge_scenario(self):
        """Test Phase2Output with edge scenario"""
        output = Phase2Output(
            scenario="timeout",
            scenario_priority=1,
            scenario_confidence=1.0,
            input_data={},
        )
        assert output.scenario == "timeout"
        assert output.scenario_priority == 1

    def test_phase3_output_creation(self):
        """Test Phase3Output dataclass creation"""
        output = Phase3Output(
            summary_text="已完成跟进光大证券",
            summary_type="detailed",
            summary_latency_ms=300.5,
        )
        assert output.summary_text == "已完成跟进光大证券"
        assert output.summary_type == "detailed"

    def test_phase3_output_fallback_type(self):
        """Test Phase3Output with fallback type"""
        output = Phase3Output(
            summary_text="- follow_up_customer: 已执行",
            summary_type="fallback",
            summary_latency_ms=0,
        )
        assert output.summary_type == "fallback"


class TestEdgeScenarioHandler:
    """Test edge scenario detection and handling"""

    def test_edge_scenarios_defined(self):
        """Test EDGE_SCENARIOS constants are defined"""
        from app.services.agent.edge_scenarios import EDGE_SCENARIOS, SCENARIO_PRIORITY

        assert "timeout" in EDGE_SCENARIOS
        assert "partial_success" in EDGE_SCENARIOS
        assert "retry" in EDGE_SCENARIOS
        assert "cache_miss" in EDGE_SCENARIOS

    def test_scenario_priority_order(self):
        """Test SCENARIO_PRIORITY order (timeout = highest)"""
        from app.services.agent.edge_scenarios import SCENARIO_PRIORITY

        assert SCENARIO_PRIORITY[0] == "timeout"
        assert SCENARIO_PRIORITY.index("interact") < SCENARIO_PRIORITY.index("query")

    def test_detect_timeout_by_rounds(self):
        """Test timeout detection when round_num >= max_rounds"""
        from app.services.agent.edge_scenarios import EdgeScenarioHandler
        from app.services.agent.tools import ToolResult

        handler = EdgeScenarioHandler()
        tool_result = ToolResult(success=True, data={"id": 123})
        scenario = handler.detect(
            round_num=10,
            max_rounds=10,
            tool_result=tool_result,
            enhanced_data={"customer": {}},
            llm_timeout=False,
        )
        assert scenario == "timeout"

    def test_detect_timeout_by_llm_timeout(self):
        """Test timeout detection when llm_timeout=True"""
        from app.services.agent.edge_scenarios import EdgeScenarioHandler
        from app.services.agent.tools import ToolResult

        handler = EdgeScenarioHandler()
        tool_result = ToolResult(success=True, data={"id": 123})
        scenario = handler.detect(
            round_num=1,
            max_rounds=10,
            tool_result=tool_result,
            enhanced_data={"customer": {}},
            llm_timeout=True,
        )
        assert scenario == "timeout"

    def test_detect_partial_success(self):
        """Test partial_success detection"""
        from app.services.agent.edge_scenarios import EdgeScenarioHandler
        from app.services.agent.tools import ToolResult

        handler = EdgeScenarioHandler()
        # Simulate incomplete data (missing critical fields)
        tool_result = ToolResult(success=True, data={"id": None})
        scenario = handler.detect(
            round_num=1,
            max_rounds=10,
            tool_result=tool_result,
            enhanced_data={"customer": {}},
            llm_timeout=False,
        )
        assert scenario == "partial_success"

    def test_detect_cache_miss(self):
        """Test cache_miss detection when enhanced_data is None"""
        from app.services.agent.edge_scenarios import EdgeScenarioHandler
        from app.services.agent.tools import ToolResult

        handler = EdgeScenarioHandler()
        tool_result = ToolResult(success=True, data={"id": 123})
        scenario = handler.detect(
            round_num=1,
            max_rounds=10,
            tool_result=tool_result,
            enhanced_data=None,
            llm_timeout=False,
        )
        assert scenario == "cache_miss"

    def test_detect_none_for_normal_case(self):
        """Test None return for normal case (no edge scenario)"""
        from app.services.agent.edge_scenarios import EdgeScenarioHandler
        from app.services.agent.tools import ToolResult

        handler = EdgeScenarioHandler()
        tool_result = ToolResult(success=True, data={"id": 123, "name": "光大证券"})
        scenario = handler.detect(
            round_num=1,
            max_rounds=10,
            tool_result=tool_result,
            enhanced_data={"customer": {"id": 123}},
            llm_timeout=False,
        )
        assert scenario is None

    def test_get_strategy(self):
        """Test get_strategy returns correct strategy"""
        from app.services.agent.edge_scenarios import EdgeScenarioHandler

        handler = EdgeScenarioHandler()
        assert handler.get_strategy("timeout") == "fallback_summary + offer_continue"
        assert handler.get_strategy("partial_success") == "report_partial + suggest_next"

    def test_get_priority(self):
        """Test get_priority returns correct priority number"""
        from app.services.agent.edge_scenarios import EdgeScenarioHandler

        handler = EdgeScenarioHandler()
        assert handler.get_priority("timeout") == 1
        assert handler.get_priority("cache_miss") == 8