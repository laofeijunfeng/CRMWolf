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

    def __init__(self):
        """Initialize metrics storage."""
        self._metrics: Dict[str, Any] = {
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