"""Comparison and merge rules for customer profile source watermarks."""

from __future__ import annotations

from collections.abc import Mapping  # noqa: TC003
from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class WatermarkComparison:
    """Result of comparing a candidate snapshot with a known watermark."""

    is_behind: bool
    advanced_keys: tuple[str, ...] = ()
    regressed_keys: tuple[str, ...] = ()
    missing_keys: tuple[str, ...] = ()


class CustomerProfileWatermarkService:
    """Compare complete eligible-source snapshots by their monotonic revision.

    Live IDs and timestamps can decrease after deletion; they describe the
    current view, not its ordering. Sparse refresh events are scheduling
    metadata, never a replacement for a complete source snapshot.
    """

    def compare(self, candidate: Mapping[str, object], known: Mapping[str, object]) -> WatermarkComparison:
        candidate_full = self._is_complete_source(candidate)
        known_full = self._is_complete_source(known)
        if candidate_full and known_full:
            if candidate["source_policy_version"] != known["source_policy_version"]:
                return WatermarkComparison(is_behind=True, regressed_keys=("source_policy_version",))
            keys = ("eligible_revision", "deletion_revision")
            advanced = tuple(key for key in keys if candidate[key] > known[key])
            regressed = tuple(key for key in keys if candidate[key] < known[key])
            return WatermarkComparison(bool(regressed), advanced, regressed)
        if candidate_full:
            return WatermarkComparison(False, advanced_keys=("eligible_revision",))
        if known_full:
            return WatermarkComparison(True, missing_keys=("eligible_revision", "source_snapshot_hash"))
        advanced: list[str] = []
        regressed: list[str] = []
        missing: list[str] = []
        for key in sorted(set(candidate) | set(known)):
            if key not in candidate and key in known and known[key] not in (None, ""):
                missing.append(key)
                continue
            if key not in known:
                if candidate.get(key) not in (None, ""):
                    advanced.append(key)
                continue
            relation = self._compare_value(candidate.get(key), known.get(key))
            if relation is None:
                continue
            if relation > 0:
                advanced.append(key)
            elif relation < 0:
                regressed.append(key)
        return WatermarkComparison(
            is_behind=bool(regressed),
            advanced_keys=tuple(advanced),
            regressed_keys=tuple(regressed),
            missing_keys=tuple(missing),
        )

    def merge(self, known: Mapping[str, object], candidate: Mapping[str, object]) -> dict[str, object]:
        if self._is_complete_source(candidate):
            if self._is_complete_source(known) and self.compare(candidate, known).is_behind:
                return dict(known)
            return dict(candidate)
        if self._is_complete_source(known):
            return {**known, **{key: value for key, value in candidate.items()
                              if key in {"event_key", "trigger_type", "occurred_at"}}}
        result = dict(known)
        for key, value in candidate.items():
            relation = self._compare_value(value, result.get(key)) if key in result else 1
            if key not in result or relation is None or relation >= 0:
                result[key] = value
        return result

    def is_behind(self, candidate: Mapping[str, object], known: Mapping[str, object]) -> bool:
        return self.compare(candidate, known).is_behind

    @staticmethod
    def _is_complete_source(watermark: Mapping[str, object]) -> bool:
        return (
            isinstance(watermark.get("eligible_revision"), int)
            and isinstance(watermark.get("deletion_revision"), int)
            and isinstance(watermark.get("source_policy_version"), str)
            and isinstance(watermark.get("source_snapshot_hash"), str)
        )

    @classmethod
    def _compare_value(cls, left: object, right: object) -> int | None:
        if left == right:
            return 0
        if left in (None, ""):
            return -1 if right not in (None, "") else 0
        if right in (None, ""):
            return 1
        if isinstance(left, bool) or isinstance(right, bool):
            return None
        left_int = cls._to_int(left)
        right_int = cls._to_int(right)
        if left_int is not None and right_int is not None:
            return (left_int > right_int) - (left_int < right_int)
        left_datetime = cls._to_datetime(left)
        right_datetime = cls._to_datetime(right)
        if left_datetime is not None and right_datetime is not None:
            return (left_datetime > right_datetime) - (left_datetime < right_datetime)
        # Arbitrary strings (event keys, trigger types, labels) are metadata,
        # not ordered watermarks. They must never make a valid snapshot stale.
        return None

    @staticmethod
    def _to_int(value: object) -> int | None:
        if isinstance(value, int):
            return value
        if isinstance(value, str) and value.strip().isdigit():
            return int(value.strip())
        return None

    @staticmethod
    def _to_datetime(value: object) -> datetime | None:
        if not isinstance(value, str) or not value.strip():
            return None
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None


customer_profile_watermark_service = CustomerProfileWatermarkService()
