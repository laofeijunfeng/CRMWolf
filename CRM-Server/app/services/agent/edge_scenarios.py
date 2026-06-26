"""
Edge Scenario Handler - Detect and handle edge scenarios

Purpose: Handle edge scenarios that core classification doesn't cover:
- timeout: ReAct loop reaches max rounds or LLM timeout
- partial_success: Tool succeeds but returns incomplete data
- retry: Recoverable failure that can be retried
- cache_miss: Data enhancement failed after retries

Used by:
- core.py: Check edge scenarios before normal classification
"""

import logging
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)


# Edge scenario definitions with strategies
EDGE_SCENARIOS: Dict[str, Dict[str, Any]] = {
    "timeout": {
        "trigger": "round_num >= MAX_ROUNDS or llm_timeout",
        "priority": 1,  # Highest priority
        "strategy": "fallback_summary + offer_continue",
    },
    "partial_success": {
        "trigger": "tool_result.success == True but has incomplete data",
        "priority": 2,
        "strategy": "report_partial + suggest_next",
    },
    "retry": {
        "trigger": "tool_result.success == False and error is recoverable",
        "priority": 3,
        "strategy": "retry_with_adjusted_params",
    },
    "cache_miss": {
        "trigger": "enhanced_data is None after retries",
        "priority": 4,
        "strategy": "use_raw_data + note_limitation",
    },
}

# Scenario priority order (lower index = higher priority)
SCENARIO_PRIORITY: list[str] = [
    "timeout",         # 1 - System-level (highest)
    "interact",        # 2 - User interaction
    "partial_success", # 3 - Partial success
    "retry",           # 4 - Recoverable failure
    "multi",           # 5 - Multi-intent
    "execute",         # 6 - Single execute
    "query",           # 7 - Query
    "cache_miss",      # 8 - Cache miss (lowest)
]


class EdgeScenarioHandler:
    """Detect and classify edge scenarios"""

    def detect(
        self,
        round_num: int,
        max_rounds: int,
        tool_result: Any,  # ToolResult type
        enhanced_data: Optional[Dict[str, Any]],
        llm_timeout: bool = False,
    ) -> Optional[str]:
        """
        Detect edge scenario, return scenario name or None.

        Priority order:
        1. timeout (highest)
        2. partial_success
        3. cache_miss
        4. retry (not currently detected, placeholder)

        Args:
            round_num: Current ReAct round number
            max_rounds: Maximum rounds allowed
            tool_result: Tool execution result
            enhanced_data: Enhanced data (may be None if enhancement failed)
            llm_timeout: Whether LLM timed out

        Returns:
            Edge scenario name or None if normal case
        """
        # 1. Check timeout (highest priority)
        if round_num >= max_rounds or llm_timeout:
            logger.warning(f"Edge scenario detected: timeout (round {round_num}/{max_rounds})")
            return "timeout"

        # 2. Check partial_success
        if tool_result.success:
            data = tool_result.data
            # Incomplete data: missing critical fields
            if self._has_incomplete_data(data):
                logger.warning("Edge scenario detected: partial_success (incomplete data)")
                return "partial_success"

        # 3. Check cache_miss (enhanced_data None)
        if enhanced_data is None:
            logger.warning("Edge scenario detected: cache_miss (enhancement failed)")
            return "cache_miss"

        # 4. Normal case - no edge scenario
        return None

    def _has_incomplete_data(self, data: Any) -> bool:
        """
        Check if data is incomplete (missing critical fields).

        Args:
            data: Tool result data

        Returns:
            True if data is incomplete
        """
        if data is None:
            return True

        if isinstance(data, dict):
            # Missing id means incomplete
            if data.get("id") is None:
                return True

        if isinstance(data, list):
            # Empty list or missing id in first item
            if len(data) == 0:
                return True
            if isinstance(data[0], dict) and data[0].get("id") is None:
                return True

        return False

    def get_strategy(self, scenario: str) -> str:
        """
        Get handling strategy for scenario.

        Args:
            scenario: Edge scenario name

        Returns:
            Strategy string
        """
        if scenario not in EDGE_SCENARIOS:
            return "unknown_strategy"
        return EDGE_SCENARIOS[scenario]["strategy"]

    def get_priority(self, scenario: str) -> int:
        """
        Get priority number for scenario.

        Args:
            scenario: Scenario name (edge or normal)

        Returns:
            Priority number (1-8, lower = higher priority)
        """
        if scenario in SCENARIO_PRIORITY:
            return SCENARIO_PRIORITY.index(scenario) + 1
        # Default to lowest priority for unknown scenarios
        return 8


__all__ = ["EdgeScenarioHandler", "EDGE_SCENARIOS", "SCENARIO_PRIORITY"]