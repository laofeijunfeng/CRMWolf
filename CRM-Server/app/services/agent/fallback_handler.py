"""
Fallback Handler - Graceful degradation for phase failures

Purpose: Provide fallback outputs when phases fail:
- Phase 1: Data enhancement failed → use raw data
- Phase 2: Classification failed → use default scenario
- Phase 3: LLM summary failed → build simple summary without LLM

Used by:
- core.py: Wrap phases in try/catch, use fallback on failure
"""

import logging
from typing import Any, Dict, List, Optional

from app.services.agent.edge_scenarios import SCENARIO_PRIORITY
from app.services.agent.phase_contracts import Phase1Output, Phase2Output, Phase3Output

logger = logging.getLogger(__name__)


# Default scenario map (copied from core.py for fallback)
FALLBACK_SCENARIO_MAP: Dict[str, str] = {
    "search_customer": "query",
    "search_opportunity": "query",
    "get_entity_context": "query",
    "follow_up_customer": "execute",
    "follow_up_lead": "execute",
    "create_opportunity": "execute",
    "update_stage": "execute",
    "win_opportunity": "execute",
    "lose_opportunity": "execute",
    "set_reminder": "execute",
}


class PhaseFallback:
    """Phase failure fallback strategies"""

    def phase1_fallback(self, tool_result: Any) -> Phase1Output:
        """
        Phase 1 (Data Enhancement) failure fallback.

        Use raw tool data instead of enhanced data.

        Args:
            tool_result: Tool execution result

        Returns:
            Phase1Output with fallback status
        """
        logger.warning("Phase 1 enhancement failed, using raw data fallback")

        return Phase1Output(
            raw_data=tool_result.data or {},
            enhanced_data=None,
            enhancement_status="fallback",
            enhancement_latency_ms=0,
        )

    def phase2_fallback(self, tool_name: Optional[str]) -> Phase2Output:
        """
        Phase 2 (Scenario Classification) failure fallback.

        Use default scenario based on tool name or generic "execute".

        Args:
            tool_name: Tool name (may be None)

        Returns:
            Phase2Output with low confidence
        """
        logger.warning(f"Phase 2 classification failed, using fallback for tool: {tool_name}")

        default_scenario = FALLBACK_SCENARIO_MAP.get(tool_name or "", "execute")

        # Get priority from SCENARIO_PRIORITY
        priority = 6  # Default execute priority
        if default_scenario in SCENARIO_PRIORITY:
            priority = SCENARIO_PRIORITY.index(default_scenario) + 1

        return Phase2Output(
            scenario=default_scenario,
            scenario_priority=priority,
            scenario_confidence=0.5,  # Low confidence for fallback
            input_data={},
        )

    def phase3_fallback(
        self,
        tool_history: List[Dict[str, Any]],
        user_message: str,
    ) -> Phase3Output:
        """
        Phase 3 (Summary Generation) failure fallback.

        Build simple summary without LLM.

        Args:
            tool_history: List of tool calls with results
            user_message: Original user input

        Returns:
            Phase3Output with fallback summary
        """
        logger.warning("Phase 3 summary generation failed, using simple summary fallback")

        simple_summary = self._build_simple_summary(tool_history, user_message)

        return Phase3Output(
            summary_text=simple_summary,
            summary_type="fallback",
            summary_latency_ms=0,
        )

    def _build_simple_summary(
        self,
        tool_history: List[Dict[str, Any]],
        user_message: str,
    ) -> str:
        """
        Build simple summary without LLM.

        Format:
        - Task completed: [user message]
        - Or: Completed operations:
          - [tool_name]: executed

        Args:
            tool_history: List of tool calls
            user_message: Original user input

        Returns:
            Simple summary text
        """
        if not tool_history:
            return f"任务已处理：{user_message}"

        parts = ["已完成以下操作："]
        for call in tool_history:
            tool_name = call.get("tool_name", "unknown")
            parts.append(f"- {tool_name}: 已执行")

        return "\n".join(parts)


__all__ = ["PhaseFallback"]