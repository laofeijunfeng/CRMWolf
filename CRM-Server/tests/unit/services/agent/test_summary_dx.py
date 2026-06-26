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