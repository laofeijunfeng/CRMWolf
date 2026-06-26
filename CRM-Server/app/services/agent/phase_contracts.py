"""
Phase Data Contracts - Typed dataclasses for phase outputs

Purpose: Ensure type safety and clear data flow between phases.

Used by:
- core.py: Wrap phase outputs in typed dataclasses
- fallback_handler.py: Return typed fallback outputs
- summary_monitor.py: Accept typed inputs for tracking
"""

from dataclasses import dataclass
from typing import Any, Dict, Optional


@dataclass
class Phase1Output:
    """
    Phase 1 (Data Enhancement) output contract.

    Attributes:
        raw_data: Tool original output (before enhancement)
        enhanced_data: Enhanced data with related entities (may be None)
        enhancement_status: "success" | "fallback" | "timeout"
        enhancement_latency_ms: Data aggregation latency in milliseconds
    """
    raw_data: Dict[str, Any]
    enhanced_data: Optional[Dict[str, Any]]
    enhancement_status: str  # "success" | "fallback" | "timeout"
    enhancement_latency_ms: float


@dataclass
class Phase2Output:
    """
    Phase 2 (Scenario Classification) output contract.

    Attributes:
        scenario: "query" | "execute" | "multi" | "interact" | edge type
        scenario_priority: Priority number (1-8, lower = higher priority)
        scenario_confidence: Classification confidence (0.0-1.0)
        input_data: Data passed to Phase 3
    """
    scenario: str
    scenario_priority: int  # 1-8
    scenario_confidence: float  # 0.0-1.0
    input_data: Dict[str, Any]


@dataclass
class Phase3Output:
    """
    Phase 3 (Summary Generation) output contract.

    Attributes:
        summary_text: Business-friendly summary text
        summary_type: "detailed" | "simple" | "fallback"
        summary_latency_ms: LLM summary generation latency in milliseconds
    """
    summary_text: str
    summary_type: str  # "detailed" | "simple" | "fallback"
    summary_latency_ms: float


__all__ = ["Phase1Output", "Phase2Output", "Phase3Output"]