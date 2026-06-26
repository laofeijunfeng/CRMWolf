# AI Summary DX Optimization Design

**Created**: 2026-06-26
**Author**: Claude Code
**Status**: Approved for Implementation

---

## Overview

This document describes the design for implementing 6 DX (Developer Experience) optimization items for the AI summary feature:

1. Phase Data Contracts (typed dataclasses)
2. Edge Scenario Handling (timeout, partial_success, cache_miss, retry)
3. Fallback Mechanisms (graceful degradation)
4. Prompt Version Management (A/B testing, rollback)
5. Quality Monitoring (metrics tracking)
6. Automated Test Suite

---

## Architecture

### File Structure

```
CRM-Server/app/services/agent/
├── core.py                    # existing - imports and uses new modules
├── prompts.py                 # existing - imports PromptVersionManager
├── phase_contracts.py         # NEW - dataclasses for phase outputs
├── edge_scenarios.py          # NEW - edge scenario detection and handling
├── fallback_handler.py        # NEW - graceful degradation logic
├── prompt_versions.py         # NEW - prompt version registry and management
├── summary_monitor.py         # NEW - quality metrics tracking
└── tests/
    └── test_summary_dx.py     # NEW - automated test suite
```

### Module Dependencies

```
core.py
  ├── phase_contracts.py (imports Phase1Output, Phase2Output, Phase3Output)
  ├── edge_scenarios.py (imports EdgeScenarioHandler)
  ├── fallback_handler.py (imports PhaseFallback)
  └── summary_monitor.py (imports SummaryQualityMonitor)

prompts.py
  └── prompt_versions.py (imports PromptVersionManager)
```

---

## Module 1: Phase Data Contracts

### Purpose

Define typed dataclasses for each phase's output, ensuring type safety and clear data flow.

### Implementation

```python
# phase_contracts.py

from dataclasses import dataclass
from typing import Dict, Any, Optional

@dataclass
class Phase1Output:
    """Phase 1 (Data Enhancement) output"""
    raw_data: Dict[str, Any]
    enhanced_data: Optional[Dict[str, Any]]
    enhancement_status: str  # "success" | "fallback" | "timeout"
    enhancement_latency_ms: float

@dataclass
class Phase2Output:
    """Phase 2 (Scenario Classification) output"""
    scenario: str  # query | execute | multi | interact | edge types
    scenario_priority: int  # 1-8
    scenario_confidence: float  # 0.0-1.0
    input_data: Dict[str, Any]

@dataclass
class Phase3Output:
    """Phase 3 (Summary Generation) output"""
    summary_text: str
    summary_type: str  # "detailed" | "simple" | "fallback"
    summary_latency_ms: float
```

---

## Module 2: Edge Scenario Handling

### Purpose

Detect and handle edge scenarios that core classification doesn't cover.

### Edge Scenarios

| Scenario | Trigger | Priority | Strategy |
|----------|---------|----------|----------|
| timeout | round_num >= MAX_ROUNDS or llm_timeout | 1 | fallback_summary + offer_continue |
| partial_success | tool_result.success but incomplete data | 2 | report_partial + suggest_next |
| retry | recoverable failure | 3 | retry_with_adjusted_params |
| cache_miss | enhanced_data None after retries | 4 | use_raw_data + note_limitation |

### Implementation

```python
# edge_scenarios.py

EDGE_SCENARIOS = {
    "timeout": {...},
    "partial_success": {...},
    "retry": {...},
    "cache_miss": {...},
}

SCENARIO_PRIORITY = [
    "timeout", "interact", "partial_success", "retry",
    "multi", "execute", "query", "cache_miss",
]

class EdgeScenarioHandler:
    def detect(self, round_num, max_rounds, tool_result, enhanced_data, llm_timeout=False) -> Optional[str]:
        """Detect edge scenario, return name or None"""

    def get_strategy(self, scenario: str) -> str:
        """Get handling strategy"""

    def get_priority(self, scenario: str) -> int:
        """Get priority number"""
```

---

## Module 3: Fallback Handler

### Purpose

Provide graceful degradation when phases fail.

### Implementation

```python
# fallback_handler.py

class PhaseFallback:
    def phase1_fallback(self, tool_result: ToolResult) -> Phase1Output:
        """Data enhancement failure fallback"""

    def phase2_fallback(self, tool_name: Optional[str]) -> Phase2Output:
        """Scenario classification failure fallback"""

    def phase3_fallback(self, tool_history: List[Dict], user_message: str) -> Phase3Output:
        """LLM summary generation failure fallback"""

    def _build_simple_summary(self, tool_history, user_message) -> str:
        """Build simple summary without LLM"""
```

---

## Module 4: Prompt Version Management

### Purpose

Track prompt versions, enable A/B testing, and provide rollback capability.

### Implementation

```python
# prompt_versions.py

VERSIONS = {
    "v1.0": {
        "created": "2026-06-26",
        "description": "Initial: 4-scenario classification",
        "prompt_key": "SUMMARY_SYSTEM_PROMPT",
        "active": True,
    },
    "v1.1": {
        "created": "2026-06-27",
        "description": "Add edge scenario handling",
        "prompt_key": "SUMMARY_SYSTEM_PROMPT_V1_1",
        "active": False,
    },
}

class PromptVersionManager:
    def get_active_version(self) -> str:
        """Get current active version"""

    def get_prompt(self, version: str = None) -> str:
        """Get prompt for specified version"""

    def activate_version(self, version: str) -> bool:
        """Activate a version"""

    def create_version(self, version: str, description: str, prompt_text: str) -> None:
        """Create new version"""
```

---

## Module 5: Quality Monitor

### Purpose

Track quality metrics for summary generation.

### Metrics

| Metric | Description |
|--------|-------------|
| total_summaries | Count of all summaries generated |
| phase1_success_rate | Data enhancement success rate |
| fallback_rate | Rate of fallback usage |
| avg_latency_ms | Average total latency |
| user_satisfaction_rate | User feedback rate (optional) |

### Implementation

```python
# summary_monitor.py

class SummaryQualityMonitor:
    METRICS: Dict[str, Any] = {...}

    def track_summary(self, response, phase1, phase2, phase3) -> None:
        """Track metrics for one summary generation"""

    def get_metrics(self) -> Dict[str, Any]:
        """Get current metrics snapshot"""

    def record_user_feedback(self, satisfied: bool) -> None:
        """Record user feedback"""
```

---

## Module 6: Automated Test Suite

### Test Structure

```python
# tests/unit/services/agent/test_summary_dx.py

class TestPhaseContracts:
    def test_phase1_output_creation(self)
    def test_phase1_output_fallback(self)

class TestEdgeScenarioHandler:
    def test_detect_timeout(self)
    def test_detect_partial_success(self)
    def test_get_strategy(self)

class TestPhaseFallback:
    def test_phase1_fallback(self)
    def test_phase3_fallback(self)

class TestPromptVersionManager:
    def test_get_active_version(self)
    def test_activate_version(self)

class TestSummaryQualityMonitor:
    def test_track_summary(self)
    def test_get_metrics(self)
```

---

## Core.py Integration

### Changes

1. Add imports for all new modules
2. Initialize handlers in `CRMWolfAgent.__init__`
3. Wrap `_enhance_data` in try/catch, return `Phase1Output`
4. Check edge scenarios before `_classify_scenario`
5. Wrap `_generate_summary` in try/catch, return `Phase3Output`
6. Track metrics after summary generation

### Flow

```
run() method:
  1. Phase 1: _enhance_data() → Phase1Output (with fallback)
  2. Edge check: EdgeScenarioHandler.detect()
  3. Phase 2: _classify_scenario() → Phase2Output
  4. Phase 3: _generate_summary() → Phase3Output (with fallback)
  5. Track: SummaryQualityMonitor.track_summary()
  6. Return: AgentResponse with final_answer
```

---

## Implementation Order

1. **phase_contracts.py** - Foundation dataclasses
2. **edge_scenarios.py** - Edge scenario detection
3. **fallback_handler.py** - Fallback mechanisms
4. **core.py integration** - Update main agent loop
5. **prompt_versions.py** - Prompt version management
6. **summary_monitor.py** - Quality monitoring
7. **test_summary_dx.py** - Automated tests

Estimated time: ~4 hours

---

## Success Criteria

1. All edge scenarios detected and handled correctly
2. Fallback produces useful output when phases fail
3. Prompt versions can be switched without code changes
4. Quality metrics tracked for monitoring
5. All tests pass with >80% coverage