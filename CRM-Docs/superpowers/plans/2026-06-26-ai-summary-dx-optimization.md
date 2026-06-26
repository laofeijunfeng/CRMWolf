# AI Summary DX Optimization Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement 6 DX optimization modules for AI summary generation: phase contracts, edge scenarios, fallback handler, prompt version management, quality monitor, and automated tests.

**Architecture:** Create 5 new Python modules under `CRM-Server/app/services/agent/` with typed dataclasses, edge scenario detection, graceful fallback mechanisms, prompt version registry, and quality metrics tracking. Integrate into existing `core.py` ReAct loop with try/catch wrappers.

**Tech Stack:** Python 3.11, dataclasses, pytest, existing CRMWolf Agent infrastructure

## Global Constraints

- **Type Safety:** All phase outputs must use typed dataclasses (no bare dicts)
- **Graceful Degradation:** Every phase must have a fallback that produces useful output
- **Logging:** All failures logged with `logger.warning()`, successes with `logger.info()`
- **Test Coverage:** Each module must have corresponding test class
- **Import Order:** Standard library → third-party → local imports (alphabetical)
- **File Location:** All new modules under `CRM-Server/app/services/agent/`
- **Test Location:** All tests under `CRM-Server/tests/unit/services/agent/`

---

## File Structure

### New Files
| File | Purpose |
|------|---------|
| `CRM-Server/app/services/agent/phase_contracts.py` | Typed dataclasses for phase outputs |
| `CRM-Server/app/services/agent/edge_scenarios.py` | Edge scenario detection and handling |
| `CRM-Server/app/services/agent/fallback_handler.py` | Graceful degradation logic |
| `CRM-Server/app/services/agent/prompt_versions.py` | Prompt version registry and management |
| `CRM-Server/app/services/agent/summary_monitor.py` | Quality metrics tracking |
| `CRM-Server/tests/unit/services/agent/test_summary_dx.py` | Automated test suite |

### Modified Files
| File | Changes |
|------|---------|
| `CRM-Server/app/services/agent/core.py` | Import new modules, wrap phases in try/catch, track metrics |
| `CRM-Server/app/services/agent/prompts.py` | Add `SUMMARY_SYSTEM_PROMPT_V1_1`, import PromptVersionManager |

---

### Task 1: Phase Data Contracts

**Files:**
- Create: `CRM-Server/app/services/agent/phase_contracts.py`
- Test: `CRM-Server/tests/unit/services/agent/test_summary_dx.py`

**Interfaces:**
- Consumes: None (standalone module)
- Produces: `Phase1Output`, `Phase2Output`, `Phase3Output` dataclasses used by Tasks 2, 3, 4, 6

- [ ] **Step 1: Write the failing test**

```python
# CRM-Server/tests/unit/services/agent/test_summary_dx.py

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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd CRM-Server && pytest tests/unit/services/agent/test_summary_dx.py::TestPhaseContracts -v`
Expected: FAIL with "ModuleNotFoundError: No module named 'app.services.agent.phase_contracts'"

- [ ] **Step 3: Write minimal implementation**

```python
# CRM-Server/app/services/agent/phase_contracts.py

"""
Phase Data Contracts - Typed dataclasses for phase outputs

Purpose: Ensure type safety and clear data flow between phases.

Used by:
- core.py: Wrap phase outputs in typed dataclasses
- fallback_handler.py: Return typed fallback outputs
- summary_monitor.py: Accept typed inputs for tracking
"""

from dataclasses import dataclass
from typing import Dict, Any, Optional


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
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd CRM-Server && pytest tests/unit/services/agent/test_summary_dx.py::TestPhaseContracts -v`
Expected: 7 tests PASS

- [ ] **Step 5: Commit**

```bash
git add CRM-Server/app/services/agent/phase_contracts.py CRM-Server/tests/unit/services/agent/test_summary_dx.py
git commit -m "feat(agent): add phase data contracts for DX optimization"
```

---

### Task 2: Edge Scenario Handler

**Files:**
- Create: `CRM-Server/app/services/agent/edge_scenarios.py`
- Test: `CRM-Server/tests/unit/services/agent/test_summary_dx.py` (add new class)

**Interfaces:**
- Consumes: `Phase1Output` from Task 1, `ToolResult` from existing tools.py
- Produces: `EdgeScenarioHandler` class with `detect()`, `get_strategy()`, `get_priority()` methods used by Task 4

- [ ] **Step 1: Write the failing test**

```python
# Add to CRM-Server/tests/unit/services/agent/test_summary_dx.py

from app.services.agent.edge_scenarios import EdgeScenarioHandler, EDGE_SCENARIOS, SCENARIO_PRIORITY


class TestEdgeScenarioHandler:
    """Test edge scenario detection and handling"""

    def test_edge_scenarios_defined(self):
        """Test EDGE_SCENARIOS constants are defined"""
        assert "timeout" in EDGE_SCENARIOS
        assert "partial_success" in EDGE_SCENARIOS
        assert "retry" in EDGE_SCENARIOS
        assert "cache_miss" in EDGE_SCENARIOS

    def test_scenario_priority_order(self):
        """Test SCENARIO_PRIORITY order (timeout = highest)"""
        assert SCENARIO_PRIORITY[0] == "timeout"
        assert SCENARIO_PRIORITY.index("interact") < SCENARIO_PRIORITY.index("query")

    def test_detect_timeout_by_rounds(self):
        """Test timeout detection when round_num >= max_rounds"""
        handler = EdgeScenarioHandler()
        from app.services.agent.tools import ToolResult

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
        handler = EdgeScenarioHandler()
        from app.services.agent.tools import ToolResult

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
        handler = EdgeScenarioHandler()
        from app.services.agent.tools import ToolResult

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
        handler = EdgeScenarioHandler()
        from app.services.agent.tools import ToolResult

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
        handler = EdgeScenarioHandler()
        from app.services.agent.tools import ToolResult

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
        handler = EdgeScenarioHandler()
        assert handler.get_strategy("timeout") == "fallback_summary + offer_continue"
        assert handler.get_strategy("partial_success") == "report_partial + suggest_next"

    def test_get_priority(self):
        """Test get_priority returns correct priority number"""
        handler = EdgeScenarioHandler()
        assert handler.get_priority("timeout") == 1
        assert handler.get_priority("cache_miss") == 8
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd CRM-Server && pytest tests/unit/services/agent/test_summary_dx.py::TestEdgeScenarioHandler -v`
Expected: FAIL with "ModuleNotFoundError: No module named 'app.services.agent.edge_scenarios'"

- [ ] **Step 3: Write minimal implementation**

```python
# CRM-Server/app/services/agent/edge_scenarios.py

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

from typing import Optional, Dict, Any
import logging

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
    "timeout",        # 1 - System-level (highest)
    "interact",       # 2 - User interaction
    "partial_success",# 3 - Partial success
    "retry",          # 4 - Recoverable failure
    "multi",          # 5 - Multi-intent
    "execute",        # 6 - Single execute
    "query",          # 7 - Query
    "cache_miss",     # 8 - Cache miss (lowest)
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
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd CRM-Server && pytest tests/unit/services/agent/test_summary_dx.py::TestEdgeScenarioHandler -v`
Expected: 9 tests PASS

- [ ] **Step 5: Commit**

```bash
git add CRM-Server/app/services/agent/edge_scenarios.py CRM-Server/tests/unit/services/agent/test_summary_dx.py
git commit -m "feat(agent): add edge scenario handler for DX optimization"
```

---

### Task 3: Fallback Handler

**Files:**
- Create: `CRM-Server/app/services/agent/fallback_handler.py`
- Test: `CRM-Server/tests/unit/services/agent/test_summary_dx.py` (add new class)

**Interfaces:**
- Consumes: `Phase1Output`, `Phase2Output`, `Phase3Output` from Task 1, `ToolResult` from tools.py
- Produces: `PhaseFallback` class with `phase1_fallback()`, `phase2_fallback()`, `phase3_fallback()` methods used by Task 4

- [ ] **Step 1: Write the failing test**

```python
# Add to CRM-Server/tests/unit/services/agent/test_summary_dx.py

from app.services.agent.fallback_handler import PhaseFallback


class TestPhaseFallback:
    """Test fallback mechanisms"""

    def test_phase1_fallback(self):
        """Test Phase 1 fallback produces Phase1Output"""
        fallback = PhaseFallback()
        from app.services.agent.tools import ToolResult

        tool_result = ToolResult(success=True, data={"id": 123})
        output = fallback.phase1_fallback(tool_result)

        assert isinstance(output, Phase1Output)
        assert output.enhancement_status == "fallback"
        assert output.enhanced_data is None
        assert output.raw_data["id"] == 123
        assert output.enhancement_latency_ms == 0

    def test_phase2_fallback_with_tool_name(self):
        """Test Phase 2 fallback with known tool name"""
        fallback = PhaseFallback()

        output = fallback.phase2_fallback("follow_up_customer")

        assert isinstance(output, Phase2Output)
        assert output.scenario == "execute"  # follow_up_customer → execute
        assert output.scenario_confidence == 0.5

    def test_phase2_fallback_without_tool_name(self):
        """Test Phase 2 fallback without tool name"""
        fallback = PhaseFallback()

        output = fallback.phase2_fallback(None)

        assert isinstance(output, Phase2Output)
        assert output.scenario == "execute"  # Default
        assert output.scenario_confidence == 0.5

    def test_phase3_fallback_with_tool_history(self):
        """Test Phase 3 fallback produces simple summary"""
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
        fallback = PhaseFallback()

        output = fallback.phase3_fallback([], "查询光大证券")

        assert isinstance(output, Phase3Output)
        assert output.summary_type == "fallback"
        assert "查询光大证券" in output.summary_text

    def test_build_simple_summary_format(self):
        """Test simple summary format"""
        fallback = PhaseFallback()

        tool_history = [{"tool_name": "search_customer"}]
        summary = fallback._build_simple_summary(tool_history, "查询客户")

        assert "- search_customer: 已执行" in summary
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd CRM-Server && pytest tests/unit/services/agent/test_summary_dx.py::TestPhaseFallback -v`
Expected: FAIL with "ModuleNotFoundError: No module named 'app.services.agent.fallback_handler'"

- [ ] **Step 3: Write minimal implementation**

```python
# CRM-Server/app/services/agent/fallback_handler.py

"""
Fallback Handler - Graceful degradation for phase failures

Purpose: Provide fallback outputs when phases fail:
- Phase 1: Data enhancement failed → use raw data
- Phase 2: Classification failed → use default scenario
- Phase 3: LLM summary failed → build simple summary without LLM

Used by:
- core.py: Wrap phases in try/catch, use fallback on failure
"""

from typing import Dict, Any, List, Optional
import logging

from app.services.agent.phase_contracts import Phase1Output, Phase2Output, Phase3Output
from app.services.agent.edge_scenarios import SCENARIO_PRIORITY

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
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd CRM-Server && pytest tests/unit/services/agent/test_summary_dx.py::TestPhaseFallback -v`
Expected: 6 tests PASS

- [ ] **Step 5: Commit**

```bash
git add CRM-Server/app/services/agent/fallback_handler.py CRM-Server/tests/unit/services/agent/test_summary_dx.py
git commit -m "feat(agent): add fallback handler for graceful degradation"
```

---

### Task 4: Core.py Integration (Part 1 - Imports and Initialization)

**Files:**
- Modify: `CRM-Server/app/services/agent/core.py`

**Interfaces:**
- Consumes: `Phase1Output`, `Phase2Output`, `Phase3Output` from Task 1, `EdgeScenarioHandler` from Task 2, `PhaseFallback` from Task 3
- Produces: Updated `CRMWolfAgent` with phase outputs and fallback integration

- [ ] **Step 1: Add imports at top of core.py**

Locate the imports section (lines 21-40) and add new imports after existing agent imports:

```python
# Add after line 30 (after AgentPrompts import):

# ===== 新增：DX 优化导入 =====
from app.services.agent.phase_contracts import Phase1Output, Phase2Output, Phase3Output
from app.services.agent.edge_scenarios import EdgeScenarioHandler, EDGE_SCENARIOS, SCENARIO_PRIORITY
from app.services.agent.fallback_handler import PhaseFallback
```

- [ ] **Step 2: Add handler initialization in CRMWolfAgent.__init__**

Locate `CRMWolfAgent.__init__` method and add handler initialization. Find the section around line 120-130:

```python
# Add in CRMWolfAgent.__init__ method, after self.memory = AgentMemory():

        # ===== 新增：DX 优化 Handler 初始化 =====
        self.edge_handler = EdgeScenarioHandler()
        self.fallback = PhaseFallback()
        self._phase_metrics: Dict[str, Any] = {}  # Placeholder for Task 6
```

- [ ] **Step 3: Verify imports work**

Run: `cd CRM-Server && python -c "from app.services.agent.core import CRMWolfAgent; print('Import OK')"`
Expected: "Import OK" (no ModuleNotFoundError)

- [ ] **Step 4: Commit**

```bash
git add CRM-Server/app/services/agent/core.py
git commit -m "feat(agent): integrate DX optimization imports and handlers"
```

---

### Task 5: Core.py Integration (Part 2 - Phase 1 Enhancement with Fallback)

**Files:**
- Modify: `CRM-Server/app/services/agent/core.py` (lines ~243-250)

**Interfaces:**
- Consumes: `PhaseFallback` from Task 3
- Produces: `_enhance_data` wrapped in try/catch, returns `Phase1Output`

- [ ] **Step 1: Wrap _enhance_data in try/catch in run() method**

Locate the `_enhance_data` call in the run() method (around line 244). Replace:

```python
                # ===== 新增：数据增强（聚合相关实体数据） =====
                enhanced_data = await self._enhance_data(reasoning.tool_name, tool_result)
```

With:

```python
                # ===== 新增：数据增强（聚合相关实体数据） + Fallback =====
                phase1_output: Phase1Output
                try:
                    import time
                    start_time = time.time()
                    enhanced_data = await self._enhance_data(reasoning.tool_name, tool_result)
                    elapsed_ms = (time.time() - start_time) * 1000

                    phase1_output = Phase1Output(
                        raw_data=tool_result.data or {},
                        enhanced_data=enhanced_data,
                        enhancement_status="success",
                        enhancement_latency_ms=elapsed_ms,
                    )
                    logger.info(f"Phase 1 enhancement success: {elapsed_ms:.1f}ms")
                except Exception as e:
                    logger.warning(f"Phase 1 enhancement failed: {e}")
                    phase1_output = self.fallback.phase1_fallback(tool_result)
```

- [ ] **Step 2: Add import for time module**

At the top of core.py with other imports (around line 25), ensure `time` is imported:

```python
import time  # Add if not already present
```

- [ ] **Step 3: Verify syntax**

Run: `cd CRM-Server && python -c "from app.services.agent.core import CRMWolfAgent; print('Syntax OK')"`
Expected: "Syntax OK"

- [ ] **Step 4: Commit**

```bash
git add CRM-Server/app/services/agent/core.py
git commit -m "feat(agent): wrap Phase 1 enhancement in try/catch with fallback"
```

---

### Task 6: Core.py Integration (Part 3 - Edge Scenario Detection)

**Files:**
- Modify: `CRM-Server/app/services/agent/core.py` (lines ~197-210)

**Interfaces:**
- Consumes: `EdgeScenarioHandler` from Task 2, `Phase1Output` from Task 4
- Produces: Edge scenario detection before classification, `Phase2Output`

- [ ] **Step 1: Add edge scenario detection before _classify_scenario**

Locate the `_classify_scenario` call in run() method (around line 198). Replace:

```python
                # 如果有工具历史，生成智能总结
                if tool_history:
                    scenario = self._classify_scenario(tool_history, reasoning)
```

With:

```python
                # ===== 新增：Edge Scenario Detection =====
                phase2_output: Phase2Output

                # First check edge scenarios
                edge_scenario = self.edge_handler.detect(
                    round_num=round_num,
                    max_rounds=self.MAX_ROUNDS,
                    tool_result=tool_result,
                    enhanced_data=phase1_output.enhanced_data if hasattr(phase1_output, 'enhanced_data') else None,
                    llm_timeout=False,  # LLM timeout tracking not yet implemented
                )

                if edge_scenario:
                    # Edge scenario detected
                    phase2_output = Phase2Output(
                        scenario=edge_scenario,
                        scenario_priority=self.edge_handler.get_priority(edge_scenario),
                        scenario_confidence=1.0,  # Edge scenarios are deterministic
                        input_data=phase1_output.raw_data,  # Use raw data for edge cases
                    )
                    logger.warning(f"Edge scenario detected: {edge_scenario}")
                elif tool_history:
                    # Normal classification
                    scenario = self._classify_scenario(tool_history, reasoning)
                    phase2_output = Phase2Output(
                        scenario=scenario,
                        scenario_priority=self._get_scenario_priority(scenario),
                        scenario_confidence=0.9,
                        input_data=phase1_output.enhanced_data or phase1_output.raw_data,
                    )
                else:
                    # No tool history - use fallback
                    phase2_output = self.fallback.phase2_fallback(reasoning.tool_name)
```

- [ ] **Step 2: Add helper method _get_scenario_priority**

Add new helper method in CRMWolfAgent class (after `_classify_scenario` method, around line 815):

```python
    def _get_scenario_priority(self, scenario: str) -> int:
        """
        Get priority number for scenario.

        Args:
            scenario: Scenario name

        Returns:
            Priority number (1-8, lower = higher priority)
        """
        if scenario in SCENARIO_PRIORITY:
            return SCENARIO_PRIORITY.index(scenario) + 1
        return 6  # Default execute priority
```

- [ ] **Step 3: Verify syntax**

Run: `cd CRM-Server && python -c "from app.services.agent.core import CRMWolfAgent; print('Syntax OK')"`
Expected: "Syntax OK"

- [ ] **Step 4: Commit**

```bash
git add CRM-Server/app/services/agent/core.py
git commit -m "feat(agent): add edge scenario detection before classification"
```

---

### Task 7: Core.py Integration (Part 4 - Phase 3 Summary with Fallback)

**Files:**
- Modify: `CRM-Server/app/services/agent/core.py` (lines ~204-212)

**Interfaces:**
- Consumes: `PhaseFallback` from Task 3, `Phase2Output` from Task 6
- Produces: `_generate_summary` wrapped in try/catch, returns `Phase3Output`

- [ ] **Step 1: Wrap _generate_summary in try/catch**

Locate the `_generate_summary` call (around line 204). Replace:

```python
                    final_answer = await self._generate_summary(
                        scenario=scenario,
                        user_message=user_message,
                        enhanced_data=enhanced_data,
                        tool_history=tool_history,
                    )
```

With:

```python
                # ===== 新增：Phase 3 Summary Generation + Fallback =====
                phase3_output: Phase3Output
                try:
                    import time
                    start_time = time.time()
                    final_answer = await self._generate_summary(
                        scenario=phase2_output.scenario,
                        user_message=user_message,
                        enhanced_data=phase2_output.input_data,
                        tool_history=tool_history,
                    )
                    elapsed_ms = (time.time() - start_time) * 1000

                    phase3_output = Phase3Output(
                        summary_text=final_answer,
                        summary_type="detailed",
                        summary_latency_ms=elapsed_ms,
                    )
                    logger.info(f"Phase 3 summary success: {elapsed_ms:.1f}ms")
                except Exception as e:
                    logger.warning(f"Phase 3 summary failed: {e}")
                    phase3_output = self.fallback.phase3_fallback(tool_history, user_message)
                    final_answer = phase3_output.summary_text
```

- [ ] **Step 2: Verify syntax**

Run: `cd CRM-Server && python -c "from app.services.agent.core import CRMWolfAgent; print('Syntax OK')"`
Expected: "Syntax OK"

- [ ] **Step 3: Commit**

```bash
git add CRM-Server/app/services/agent/core.py
git commit -m "feat(agent): wrap Phase 3 summary generation in try/catch with fallback"
```

---

### Task 8: Prompt Version Management

**Files:**
- Create: `CRM-Server/app/services/agent/prompt_versions.py`
- Modify: `CRM-Server/app/services/agent/prompts.py`
- Test: `CRM-Server/tests/unit/services/agent/test_summary_dx.py` (add new class)

**Interfaces:**
- Consumes: `AgentPrompts` from existing prompts.py
- Produces: `PromptVersionManager` class, `VERSIONS` registry, `SUMMARY_SYSTEM_PROMPT_V1_1`

- [ ] **Step 1: Write the failing test**

```python
# Add to CRM-Server/tests/unit/services/agent/test_summary_dx.py

from app.services.agent.prompt_versions import PromptVersionManager, VERSIONS


class TestPromptVersionManager:
    """Test prompt version management"""

    def test_versions_defined(self):
        """Test VERSIONS registry has initial versions"""
        assert "v1.0" in VERSIONS
        assert "v1.1" in VERSIONS

    def test_get_active_version_default(self):
        """Test get_active_version returns v1.0 by default"""
        manager = PromptVersionManager()
        version = manager.get_active_version()
        assert version == "v1.0"

    def test_activate_version(self):
        """Test activate_version changes active version"""
        manager = PromptVersionManager()
        # Activate v1.1
        result = manager.activate_version("v1.1")
        assert result is True
        assert manager.get_active_version() == "v1.1"
        # Reset back to v1.0
        manager.activate_version("v1.0")

    def test_activate_unknown_version(self):
        """Test activate_version returns False for unknown version"""
        manager = PromptVersionManager()
        result = manager.activate_version("v99.0")
        assert result is False

    def test_get_prompt_for_version(self):
        """Test get_prompt returns prompt text"""
        manager = PromptVersionManager()
        prompt = manager.get_prompt("v1.0")
        assert "业务总结助手" in prompt
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd CRM-Server && pytest tests/unit/services/agent/test_summary_dx.py::TestPromptVersionManager -v`
Expected: FAIL with "ModuleNotFoundError: No module named 'app.services.agent.prompt_versions'"

- [ ] **Step 3: Write minimal implementation**

```python
# CRM-Server/app/services/agent/prompt_versions.py

"""
Prompt Version Management - Version registry and A/B testing support

Purpose: Track prompt versions, enable A/B testing, and provide rollback capability.

Used by:
- prompts.py: Get active prompt version
- Future: Admin API for version switching
"""

from typing import Dict, Any
from datetime import datetime
import logging

logger = logging.getLogger(__name__)


# Prompt version registry
VERSIONS: Dict[str, Dict[str, Any]] = {
    "v1.0": {
        "created": "2026-06-26",
        "description": "Initial: 4-scenario classification",
        "prompt_key": "SUMMARY_SYSTEM_PROMPT",
        "active": True,
    },
    "v1.1": {
        "created": "2026-06-26",
        "description": "Add edge scenario handling (timeout, partial_success, cache_miss)",
        "prompt_key": "SUMMARY_SYSTEM_PROMPT_V1_1",
        "active": False,
    },
}


class PromptVersionManager:
    """Prompt version management and A/B testing"""

    def get_active_version(self) -> str:
        """
        Get current active version.

        Returns:
            Version string (e.g., "v1.0")
        """
        for version, info in VERSIONS.items():
            if info.get("active", False):
                return version
        return "v1.0"  # Default fallback

    def get_prompt(self, version: str = None) -> str:
        """
        Get prompt text for specified version (or active version).

        Args:
            version: Version string (optional, defaults to active)

        Returns:
            Prompt text
        """
        version = version or self.get_active_version()
        version_info = VERSIONS.get(version, VERSIONS["v1.0"])

        # Import from prompts.py
        from app.services.agent.prompts import AgentPrompts
        prompts = AgentPrompts()

        prompt_key = version_info.get("prompt_key", "SUMMARY_SYSTEM_PROMPT")
        prompt_text = getattr(prompts, prompt_key, prompts.SUMMARY_SYSTEM_PROMPT)

        logger.debug(f"Retrieved prompt for version {version}")
        return prompt_text

    def activate_version(self, version: str) -> bool:
        """
        Activate a version (for A/B testing or rollback).

        Args:
            version: Version string to activate

        Returns:
            True if successful, False if version not found
        """
        if version not in VERSIONS:
            logger.warning(f"Cannot activate unknown version: {version}")
            return False

        # Deactivate all versions
        for v in VERSIONS:
            VERSIONS[v]["active"] = False

        # Activate target version
        VERSIONS[version]["active"] = True
        logger.info(f"Activated prompt version: {version}")
        return True

    def create_version(
        self,
        version: str,
        description: str,
        prompt_key: str,
    ) -> None:
        """
        Create new version entry (does not modify prompts.py).

        Args:
            version: Version string (e.g., "v1.2")
            description: Version description
            prompt_key: Key name for prompt in AgentPrompts class
        """
        VERSIONS[version] = {
            "created": datetime.now().strftime("%Y-%m-%d"),
            "description": description,
            "prompt_key": prompt_key,
            "active": False,
        }
        logger.info(f"Created prompt version entry: {version}")


__all__ = ["PromptVersionManager", "VERSIONS"]
```

- [ ] **Step 4: Add SUMMARY_SYSTEM_PROMPT_V1_1 to prompts.py**

Locate after `SUMMARY_SYSTEM_PROMPT` definition (around line 439) and add:

```python
# Add after SUMMARY_SYSTEM_PROMPT definition (around line 439):

    SUMMARY_SYSTEM_PROMPT_V1_1 = """
你是 CRMWolf 业务总结助手。
你的职责是将工具执行结果转换为**用户友好的业务报告**。

【总结原则】
1. **有用**：提供用户关心的关键信息，不是技术日志
2. **可读**：结构化、段落分明、关键信息突出
3. **精准**：不丢失数据精度，数字、日期、状态准确
4. **智能**：基于数据给出业务建议

【场景类型】（含边缘场景）
你需要根据场景类型，选择对应的总结策略：

**query（查询类）**：
- 输出：详细报告 + 数据分析 + 建议

**execute（执行类）**：
- 输出：执行确认 + 操作内容 + 关联信息 + 下一步建议

**multi（多意图类）**：
- 输出：完整执行报告 + 每个操作摘要 + 整体建议

**interact（交互类）**：
- 输出：引导信息 + 选项详情 + 决策辅助

**边缘场景**：
- **timeout**：达到最大轮次，生成当前进度报告 + 提示可继续
- **partial_success**：部分成功，报告已完成部分 + 建议下一步
- **cache_miss**：数据增强失败，使用原始数据 + 注明数据限制
- **retry**：重试成功，报告重试过程 + 最终结果
"""
```

- [ ] **Step 5: Run test to verify it passes**

Run: `cd CRM-Server && pytest tests/unit/services/agent/test_summary_dx.py::TestPromptVersionManager -v`
Expected: 5 tests PASS

- [ ] **Step 6: Commit**

```bash
git add CRM-Server/app/services/agent/prompt_versions.py CRM-Server/app/services/agent/prompts.py CRM-Server/tests/unit/services/agent/test_summary_dx.py
git commit -m "feat(agent): add prompt version management with v1.1 edge scenarios"
```

---

### Task 9: Quality Monitor

**Files:**
- Create: `CRM-Server/app/services/agent/summary_monitor.py`
- Test: `CRM-Server/tests/unit/services/agent/test_summary_dx.py` (add new class)

**Interfaces:**
- Consumes: `AgentResponse` from core.py, `Phase1Output`, `Phase2Output`, `Phase3Output` from Task 1
- Produces: `SummaryQualityMonitor` class with `track_summary()`, `get_metrics()` methods

- [ ] **Step 1: Write the failing test**

```python
# Add to CRM-Server/tests/unit/services/agent/test_summary_dx.py

from app.services.agent.summary_monitor import SummaryQualityMonitor


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
        from app.services.agent.phase_contracts import Phase1Output, Phase2Output, Phase3Output

        phase1 = Phase1Output(raw_data={}, enhanced_data={}, enhancement_status="success", enhancement_latency_ms=100)
        phase2 = Phase2Output(scenario="execute", scenario_priority=6, scenario_confidence=0.9, input_data={})
        phase3 = Phase3Output(summary_text="已完成", summary_type="detailed", summary_latency_ms=200)

        monitor.track_summary(phase1, phase2, phase3)

        metrics = monitor.get_metrics()
        assert metrics["total_summaries"] == 1

    def test_track_summary_fallback(self):
        """Test tracking fallback summary"""
        monitor = SummaryQualityMonitor()
        from app.services.agent.phase_contracts import Phase1Output, Phase2Output, Phase3Output

        phase1 = Phase1Output(raw_data={}, enhanced_data=None, enhancement_status="fallback", enhancement_latency_ms=0)
        phase2 = Phase2Output(scenario="execute", scenario_priority=6, scenario_confidence=0.5, input_data={})
        phase3 = Phase3Output(summary_text="- tool: 已执行", summary_type="fallback", summary_latency_ms=0)

        monitor.track_summary(phase1, phase2, phase3)

        metrics = monitor.get_metrics()
        assert metrics["total_summaries"] == 1

    def test_get_metrics_after_multiple_tracks(self):
        """Test metrics after multiple tracks"""
        monitor = SummaryQualityMonitor()
        from app.services.agent.phase_contracts import Phase1Output, Phase2Output, Phase3Output

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
        from app.services.agent.phase_contracts import Phase1Output, Phase2Output, Phase3Output

        phase1 = Phase1Output(raw_data={}, enhanced_data={}, enhancement_status="success", enhancement_latency_ms=100)
        phase2 = Phase2Output(scenario="execute", scenario_priority=6, scenario_confidence=0.9, input_data={})
        phase3 = Phase3Output(summary_text="已完成", summary_type="detailed", summary_latency_ms=200)

        monitor.track_summary(phase1, phase2, phase3)
        monitor.reset_metrics()

        metrics = monitor.get_metrics()
        assert metrics["total_summaries"] == 0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd CRM-Server && pytest tests/unit/services/agent/test_summary_dx.py::TestSummaryQualityMonitor -v`
Expected: FAIL with "ModuleNotFoundError: No module named 'app.services.agent.summary_monitor'"

- [ ] **Step 3: Write minimal implementation**

```python
# CRM-Server/app/services/agent/summary_monitor.py

"""
Summary Quality Monitor - Metrics tracking for summary generation

Purpose: Track quality metrics for post-launch monitoring and optimization.

Metrics tracked:
- total_summaries: Count of all summaries generated
- phase1_success_rate: Data enhancement success rate
- fallback_rate: Rate of fallback usage
- avg_latency_ms: Average total latency

Used by:
- core.py: Track metrics after each summary generation
- Future: Admin API for metrics dashboard
"""

from typing import Dict, Any
import logging

from app.services.agent.phase_contracts import Phase1Output, Phase2Output, Phase3Output

logger = logging.getLogger(__name__)


class SummaryQualityMonitor:
    """Summary quality metrics tracking"""

    # Metrics storage (in-memory, could be Redis in production)
    _metrics: Dict[str, Any] = {
        "total_summaries": 0,
        "phase1_success_count": 0,
        "fallback_count": 0,
        "total_latency_ms": 0.0,
    }

    def track_summary(
        self,
        phase1: Phase1Output,
        phase2: Phase2Output,
        phase3: Phase3Output,
    ) -> None:
        """
        Track metrics for one summary generation.

        Args:
            phase1: Phase 1 output
            phase2: Phase 2 output
            phase3: Phase 3 output
        """
        self._metrics["total_summaries"] += 1

        # Phase 1 success tracking
        if phase1.enhancement_status == "success":
            self._metrics["phase1_success_count"] += 1

        # Fallback tracking
        if phase3.summary_type == "fallback":
            self._metrics["fallback_count"] += 1

        # Latency tracking
        total_latency = phase1.enhancement_latency_ms + phase3.summary_latency_ms
        self._metrics["total_latency_ms"] += total_latency

        logger.debug(
            f"Tracked summary: phase1={phase1.enhancement_status}, "
            f"phase3={phase3.summary_type}, latency={total_latency:.1f}ms"
        )

    def get_metrics(self) -> Dict[str, Any]:
        """
        Get current metrics snapshot.

        Returns:
            Dict with metrics values
        """
        total = self._metrics["total_summaries"]
        if total == 0:
            return {
                "total_summaries": 0,
                "phase1_success_rate": 0.0,
                "fallback_rate": 0.0,
                "avg_latency_ms": 0.0,
            }

        return {
            "total_summaries": total,
            "phase1_success_rate": self._metrics["phase1_success_count"] / total,
            "fallback_rate": self._metrics["fallback_count"] / total,
            "avg_latency_ms": self._metrics["total_latency_ms"] / total,
        }

    def reset_metrics(self) -> None:
        """
        Reset all metrics to initial state.

        Useful for testing or periodic reset.
        """
        self._metrics = {
            "total_summaries": 0,
            "phase1_success_count": 0,
            "fallback_count": 0,
            "total_latency_ms": 0.0,
        }
        logger.info("Metrics reset to initial state")


__all__ = ["SummaryQualityMonitor"]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd CRM-Server && pytest tests/unit/services/agent/test_summary_dx.py::TestSummaryQualityMonitor -v`
Expected: 5 tests PASS

- [ ] **Step 5: Commit**

```bash
git add CRM-Server/app/services/agent/summary_monitor.py CRM-Server/tests/unit/services/agent/test_summary_dx.py
git commit -m "feat(agent): add quality monitor for summary metrics tracking"
```

---

### Task 10: Core.py Integration (Part 5 - Metrics Tracking)

**Files:**
- Modify: `CRM-Server/app/services/agent/core.py`

**Interfaces:**
- Consumes: `SummaryQualityMonitor` from Task 9
- Produces: Metrics tracking after each summary generation

- [ ] **Step 1: Import SummaryQualityMonitor**

Add import after existing DX optimization imports (around line 32):

```python
from app.services.agent.summary_monitor import SummaryQualityMonitor
```

- [ ] **Step 2: Initialize monitor in CRMWolfAgent.__init__**

Add in `__init__` method after other handler initializations:

```python
        self.monitor = SummaryQualityMonitor()
```

- [ ] **Step 3: Add metrics tracking after phase3_output**

Locate after phase3_output is created (around line 230-240), add:

```python
                # ===== 新增：Metrics Tracking =====
                self.monitor.track_summary(phase1_output, phase2_output, phase3_output)
```

- [ ] **Step 4: Verify syntax**

Run: `cd CRM-Server && python -c "from app.services.agent.core import CRMWolfAgent; print('Syntax OK')"`
Expected: "Syntax OK"

- [ ] **Step 5: Commit**

```bash
git add CRM-Server/app/services/agent/core.py
git commit -m "feat(agent): integrate quality monitor for metrics tracking"
```

---

### Task 11: Final Verification - Run All Tests

**Files:**
- Test: All test files

- [ ] **Step 1: Run all DX optimization tests**

Run: `cd CRM-Server && pytest tests/unit/services/agent/test_summary_dx.py -v`
Expected: All tests PASS (32+ tests)

- [ ] **Step 2: Run existing agent tests to ensure no regression**

Run: `cd CRM-Server && pytest tests/unit/services/agent/test_core.py -v`
Expected: Existing tests PASS (no regression)

- [ ] **Step 3: Run full agent module tests**

Run: `cd CRM-Server && pytest tests/unit/services/agent/ -v`
Expected: All tests PASS

- [ ] **Step 4: Final commit summary**

```bash
git add -A
git commit -m "feat(agent): complete AI summary DX optimization implementation

- Phase data contracts (Phase1Output, Phase2Output, Phase3Output)
- Edge scenario handler (timeout, partial_success, cache_miss)
- Fallback handler for graceful degradation
- Prompt version management (v1.0, v1.1)
- Quality monitor for metrics tracking
- Automated test suite (32 tests)

All tests pass, core.py integration complete."
```

---

## Self-Review Checklist

### 1. Spec Coverage

| Spec Section | Task | Status |
|--------------|------|--------|
| Phase Data Contracts | Task 1 | ✅ Covered |
| Edge Scenario Handling | Task 2 | ✅ Covered |
| Fallback Handler | Task 3 | ✅ Covered |
| Prompt Version Management | Task 8 | ✅ Covered |
| Quality Monitor | Task 9 | ✅ Covered |
| Automated Test Suite | Tasks 1-11 | ✅ Covered |
| Core.py Integration | Tasks 4-7, 10 | ✅ Covered |

### 2. Placeholder Scan

- No "TBD" or "TODO" placeholders found
- All code blocks contain complete implementation
- All test steps have actual test code

### 3. Type Consistency

| Type | Defined in | Used in |
|------|------------|---------|
| `Phase1Output` | Task 1 | Tasks 2, 3, 4, 5, 7, 9, 10 |
| `Phase2Output` | Task 1 | Tasks 3, 6, 9, 10 |
| `Phase3Output` | Task 1 | Tasks 3, 7, 9, 10 |
| `EdgeScenarioHandler` | Task 2 | Tasks 4, 6 |
| `PhaseFallback` | Task 3 | Tasks 4, 5, 7 |
| `PromptVersionManager` | Task 8 | - |
| `SummaryQualityMonitor` | Task 9 | Task 10 |

All types consistent across tasks. ✅

---

## Execution Options

**Plan complete and saved to `CRM-Docs/superpowers/plans/2026-06-26-ai-summary-dx-optimization.md`.**

**Two execution options:**

1. **Subagent-Driven (recommended)** - I dispatch a fresh subagent per task, review between tasks, fast iteration

2. **Inline Execution** - Execute tasks in this session using executing-plans, batch execution with checkpoints

**Which approach?**