"""Tests for AI Summary DX Optimization modules"""

import pytest
from app.services.agent.phase_contracts import Phase1Output, Phase2Output, Phase3Output
from app.services.agent.summary_monitor import SummaryQualityMonitor


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


class TestPhaseFallback:
    """Test fallback mechanisms"""

    def test_phase1_fallback(self):
        """Test Phase 1 fallback produces Phase1Output"""
        from app.services.agent.fallback_handler import PhaseFallback
        from app.services.agent.tools import ToolResult

        fallback = PhaseFallback()
        tool_result = ToolResult(success=True, data={"id": 123})
        output = fallback.phase1_fallback(tool_result)

        assert isinstance(output, Phase1Output)
        assert output.enhancement_status == "fallback"
        assert output.enhanced_data is None
        assert output.raw_data["id"] == 123
        assert output.enhancement_latency_ms == 0

    def test_phase2_fallback_with_tool_name(self):
        """Test Phase 2 fallback with known tool name"""
        from app.services.agent.fallback_handler import PhaseFallback

        fallback = PhaseFallback()

        output = fallback.phase2_fallback("follow_up_customer")

        assert isinstance(output, Phase2Output)
        assert output.scenario == "execute"  # follow_up_customer → execute
        assert output.scenario_confidence == 0.5

    def test_phase2_fallback_without_tool_name(self):
        """Test Phase 2 fallback without tool name"""
        from app.services.agent.fallback_handler import PhaseFallback

        fallback = PhaseFallback()

        output = fallback.phase2_fallback(None)

        assert isinstance(output, Phase2Output)
        assert output.scenario == "execute"  # Default
        assert output.scenario_confidence == 0.5

    def test_phase3_fallback_with_tool_history(self):
        """Test Phase 3 fallback produces simple summary"""
        from app.services.agent.fallback_handler import PhaseFallback

        fallback = PhaseFallback()

        tool_history = [
            {"tool_name": "follow_up_customer", "tool_params": {}, "tool_result": "success"},
            {"tool_name": "create_opportunity", "tool_params": {}, "tool_result": "success"},
        ]
        output = fallback.phase3_fallback(tool_history, "跟进光大证券")

        assert isinstance(output, Phase3Output)
        assert output.summary_type == "fallback"
        assert "已完成" in output.summary_text
        assert "follow_up_customer" in output.summary_text
        assert output.summary_latency_ms == 0

    def test_phase3_fallback_empty_history(self):
        """Test Phase 3 fallback with empty tool history"""
        from app.services.agent.fallback_handler import PhaseFallback

        fallback = PhaseFallback()

        output = fallback.phase3_fallback([], "查询光大证券")

        assert isinstance(output, Phase3Output)
        assert output.summary_type == "fallback"
        assert "查询光大证券" in output.summary_text

    def test_build_simple_summary_format(self):
        """Test simple summary format"""
        from app.services.agent.fallback_handler import PhaseFallback

        fallback = PhaseFallback()

        tool_history = [{"tool_name": "search_customer"}]
        summary = fallback._build_simple_summary(tool_history, "查询客户")

        assert "- search_customer: 已执行" in summary


class TestPromptVersionManager:
    """Test prompt version management"""

    def test_versions_defined(self):
        """Test VERSIONS registry has initial versions"""
        from app.services.agent.prompt_versions import PromptVersionManager, VERSIONS

        assert "v1.0" in VERSIONS
        assert "v1.1" in VERSIONS

    def test_get_active_version_default(self):
        """Test get_active_version returns v1.0 by default"""
        from app.services.agent.prompt_versions import PromptVersionManager

        manager = PromptVersionManager()
        version = manager.get_active_version()
        assert version == "v1.0"

    def test_activate_version(self):
        """Test activate_version changes active version"""
        from app.services.agent.prompt_versions import PromptVersionManager

        manager = PromptVersionManager()
        # Activate v1.1
        result = manager.activate_version("v1.1")
        assert result is True
        assert manager.get_active_version() == "v1.1"
        # Reset back to v1.0
        manager.activate_version("v1.0")

    def test_activate_unknown_version(self):
        """Test activate_version returns False for unknown version"""
        from app.services.agent.prompt_versions import PromptVersionManager

        manager = PromptVersionManager()
        result = manager.activate_version("v99.0")
        assert result is False

    def test_get_prompt_for_version(self):
        """Test get_prompt returns prompt text"""
        from app.services.agent.prompt_versions import PromptVersionManager

        manager = PromptVersionManager()
        prompt = manager.get_prompt("v1.0")
        assert "业务总结助手" in prompt


class TestSummaryQualityMonitor:
    """Test quality monitoring"""

    def test_metrics_initial_state(self):
        """Test initial metrics state"""
        monitor = SummaryQualityMonitor()
        metrics = monitor.get_metrics()
        assert metrics["total_summaries"] == 0

    def test_track_summary_success(self):
        """Test tracking successful summary"""
        monitor = SummaryQualityMonitor()

        phase1 = Phase1Output(raw_data={}, enhanced_data={}, enhancement_status="success", enhancement_latency_ms=100)
        phase2 = Phase2Output(scenario="execute", scenario_priority=6, scenario_confidence=0.9, input_data={})
        phase3 = Phase3Output(summary_text="已完成", summary_type="detailed", summary_latency_ms=200)

        monitor.track_summary(phase1, phase2, phase3)

        metrics = monitor.get_metrics()
        assert metrics["total_summaries"] == 1

    def test_track_summary_fallback(self):
        """Test tracking fallback summary"""
        monitor = SummaryQualityMonitor()

        phase1 = Phase1Output(raw_data={}, enhanced_data=None, enhancement_status="fallback", enhancement_latency_ms=0)
        phase2 = Phase2Output(scenario="execute", scenario_priority=6, scenario_confidence=0.5, input_data={})
        phase3 = Phase3Output(summary_text="- tool: 已执行", summary_type="fallback", summary_latency_ms=0)

        monitor.track_summary(phase1, phase2, phase3)

        metrics = monitor.get_metrics()
        assert metrics["total_summaries"] == 1

    def test_get_metrics_after_multiple_tracks(self):
        """Test metrics after multiple tracks"""
        monitor = SummaryQualityMonitor()

        # Track 3 summaries
        for i in range(3):
            phase1 = Phase1Output(raw_data={}, enhanced_data={}, enhancement_status="success", enhancement_latency_ms=100)
            phase2 = Phase2Output(scenario="execute", scenario_priority=6, scenario_confidence=0.9, input_data={})
            phase3 = Phase3Output(summary_text="已完成", summary_type="detailed", summary_latency_ms=200)
            monitor.track_summary(phase1, phase2, phase3)

        metrics = monitor.get_metrics()
        assert metrics["total_summaries"] == 3
        assert metrics["avg_latency_ms"] > 0

    def test_reset_metrics(self):
        """Test reset_metrics"""
        monitor = SummaryQualityMonitor()

        phase1 = Phase1Output(raw_data={}, enhanced_data={}, enhancement_status="success", enhancement_latency_ms=100)
        phase2 = Phase2Output(scenario="execute", scenario_priority=6, scenario_confidence=0.9, input_data={})
        phase3 = Phase3Output(summary_text="已完成", summary_type="detailed", summary_latency_ms=200)

        monitor.track_summary(phase1, phase2, phase3)
        monitor.reset_metrics()

        metrics = monitor.get_metrics()
        assert metrics["total_summaries"] == 0