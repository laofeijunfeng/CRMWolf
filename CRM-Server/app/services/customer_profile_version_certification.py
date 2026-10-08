"""Per-version, publisher-signed source attestation for the legacy profile read model.

A customer-level progress row or snapshot hash cannot certify an existing version:
only a publisher-generated certificate binding that exact version's content, refs,
and source watermark is readable. Historical versions have no certificate.
"""

from __future__ import annotations

import hmac
import json
from hashlib import sha256
from typing import TYPE_CHECKING

from app.core.config import get_settings
from app.services.legacy_profile_source import LEGACY_PROFILE_SOURCE_POLICY

if TYPE_CHECKING:
    from app.models.customer_profile_projection import CustomerProfileProjectionVersion

CERTIFICATION_VERSION = "LEGACY_PROFILE_PUBLICATION_V1"
SOURCE_DISCRIMINATOR = "CERTIFIED_V1"


def _canonical(value: object) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, default=str, separators=(",", ":")).encode("utf-8")


def _version_payload(version: CustomerProfileProjectionVersion) -> dict[str, object]:
    return {
        "team_id": version.team_id,
        "customer_id": version.customer_id,
        "id": version.id,
        "public_id": version.public_id,
        "profile_version": version.profile_version,
        "schema_version": version.schema_version,
        "graph_version": version.graph_version,
        "source_event_key": version.source_event_key,
        "sections": {
            "current_situation": version.current_situation_json,
            "current_journeys": version.current_journeys_json,
            "important_changes": version.important_changes_json,
            "long_term_context": version.long_term_context_json,
            "follow_up_process": version.follow_up_process_json,
            "recorded_follow_ups": version.recorded_follow_ups_json,
        },
        "evidence_refs": version.evidence_refs_json,
        "source_watermark": version.source_watermark_json,
        "source_watermark_hash": version.source_watermark_hash,
        "content_hash": version.content_hash,
        "fact_watermark": version.fact_watermark,
        "journey_watermark": version.journey_watermark,
        "task_watermark": version.task_watermark,
        "commitment_watermark": version.commitment_watermark,
    }


def _signature(payload: dict[str, object]) -> str:
    key = get_settings().get_secret_key().encode("utf-8")
    return hmac.new(key, _canonical(payload), sha256).hexdigest()


def certify_profile_version(version: CustomerProfileProjectionVersion) -> None:
    """Call only after the fenced, deterministic publisher inserts a fresh row."""
    watermark = version.source_watermark_json
    if not isinstance(watermark, dict) or watermark.get("source_policy_version") != LEGACY_PROFILE_SOURCE_POLICY:
        raise ValueError("Cannot certify a version without the legacy source policy")
    if watermark.get("source_provenance_status") != "VERIFIED":
        raise ValueError("Cannot certify a version without verified source provenance")
    snapshot_hash = watermark.get("source_snapshot_hash")
    if not isinstance(snapshot_hash, str) or len(snapshot_hash) != 64:
        raise ValueError("Cannot certify a version without a full source snapshot")
    if version.id is None or not version.public_id:
        raise ValueError("Cannot certify an unpersisted version")
    payload = {"certificate_version": CERTIFICATION_VERSION, "source_policy": LEGACY_PROFILE_SOURCE_POLICY,
               "source_snapshot_hash": snapshot_hash, "version": _version_payload(version)}
    version.source_attestation_json = {"certificate_version": CERTIFICATION_VERSION,
                                       "signature": _signature(payload)}


def is_certified_profile_version(version: CustomerProfileProjectionVersion) -> bool:
    """Authenticate one persisted version; status may become SUPERSEDED later."""
    attestation = version.source_attestation_json
    if (not isinstance(attestation, dict) or version.source_discriminator != SOURCE_DISCRIMINATOR
            or attestation.get("certificate_version") != CERTIFICATION_VERSION):
        return False
    signature = attestation.get("signature")
    watermark = version.source_watermark_json
    if not isinstance(signature, str) or not isinstance(watermark, dict):
        return False
    if watermark.get("source_policy_version") != LEGACY_PROFILE_SOURCE_POLICY:
        return False
    if watermark.get("source_provenance_status") != "VERIFIED":
        return False
    snapshot_hash = watermark.get("source_snapshot_hash")
    if not isinstance(snapshot_hash, str) or len(snapshot_hash) != 64:
        return False
    if version.id is None or not version.public_id:
        return False
    payload = {"certificate_version": CERTIFICATION_VERSION, "source_policy": LEGACY_PROFILE_SOURCE_POLICY,
               "source_snapshot_hash": snapshot_hash, "version": _version_payload(version)}
    return hmac.compare_digest(signature, _signature(payload))
