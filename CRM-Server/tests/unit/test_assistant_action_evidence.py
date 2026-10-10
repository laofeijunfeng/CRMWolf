"""Execution evidence requires an unambiguous deadline and the current action."""
# ruff: noqa: RUF001

from copy import deepcopy
from datetime import datetime

import pytest

from app.services.assistant.action_evidence import SourceSegment, reconcile_action_evidence, validate_action_evidence
from app.services.assistant.contracts import DraftField, TaskDraft

ANCHOR = datetime(2026, 10, 8, 23, 59)


def _meeting(source, *, owner="我", due="下周三", action="发方案"):
    draft = TaskDraft(
        next_action=DraftField(status="CANDIDATE", value=f"{owner}{action}"),
        content_json={"action_items": [{"item_id": "act_send", "owner": owner, "action": action, "due_date": due}]},
        source_records=[SourceSegment(segment_id="seg_original", text=source, recorded_at=ANCHOR)],
        source_segments=[source],
    )
    reconcile_action_evidence(draft, "ONLINE_MEETING")
    return draft


@pytest.mark.parametrize(
    "expression",
    ["下周三左右", "下周三下午", "下周三下午大概三点", "下周三下午三点左右", "大约下周三", "下周三到下周五"],
)
def test_partial_or_uncertain_deadline_never_authorizes_a_task(expression):
    source = f"我{expression}发方案"
    draft = _meeting(source, due=expression)
    assert draft.content_json["action_evidence"][0]["resolution_status"] != "RESOLVED"
    assert validate_action_evidence(draft.content_json, "act_send", source_content=source) is None


@pytest.mark.parametrize("owner,source", [("", "下周三发方案"), ("我", "我确认预算，小王下周三发方案")])
def test_missing_or_unrelated_owner_never_authorizes_a_task(owner, source):
    draft = _meeting(source, owner=owner)
    assert validate_action_evidence(draft.content_json, "act_send", source_content=source) is None


@pytest.mark.parametrize("change", ["removed", "owner", "action", "date", "none", "duplicate_id"])
def test_stale_sidecar_cannot_authorize_changed_or_removed_canonical_action(change):
    source = "我下周三发方案"
    draft = _meeting(source)
    assert validate_action_evidence(draft.content_json, "act_send", source_content=source) is not None
    content = deepcopy(draft.content_json)
    if change == "removed":
        content["action_items"] = []
    elif change == "none":
        content["next_action_absence_reason"] = "客户内部盘点，批准前不安排下一步"
        content["action_items"] = []
    elif change == "duplicate_id":
        content["action_items"].append(deepcopy(content["action_items"][0]))
    else:
        field, value = {"owner": ("owner", "小王"), "action": ("action", "审预算"), "date": ("due_date", "下周五")}[
            change
        ]
        content["action_items"][0][field] = value
    assert validate_action_evidence(content, "act_send", source_content=source) is None


def test_removed_action_retires_active_evidence_without_erasing_original_quote():
    source = "我下周三发方案"
    draft = _meeting(source)
    draft.content_json["action_items"] = []
    reconcile_action_evidence(draft, "ONLINE_MEETING")
    evidence = draft.content_json["action_evidence"][0]
    assert evidence["state"] == "SUPERSEDED"
    assert evidence["evidence_quote"] == source
    assert validate_action_evidence(draft.content_json, "act_send", source_content=source) is None


def test_model_deadline_conflicting_with_source_does_not_authorize_a_task():
    source = "我下周三发方案"
    draft = _meeting(source, due="2026-10-16")
    assert validate_action_evidence(draft.content_json, "act_send", source_content=source) is None


def test_follow_up_summary_binds_only_its_explicit_subject_and_original_deadline():
    source = "我下周三下午三点发方案"
    draft = TaskDraft(
        next_action=DraftField(status="CANDIDATE", value="我发方案"),
        next_follow_time=DraftField(status="CANDIDATE", value="下周三下午三点"),
        content_json={"next_action": "我发方案", "next_follow_time_text": "下周三下午三点"},
        source_records=[SourceSegment(segment_id="seg_follow_up", text=source, recorded_at=ANCHOR)],
        source_segments=[source],
    )
    reconcile_action_evidence(draft, "FOLLOW_UP")
    evidence = draft.content_json["action_evidence"][0]
    validated = validate_action_evidence(draft.content_json, evidence["action_id"], source_content=source)
    assert validated is not None
    assert (validated.action, validated.owner, validated.due_at) == ("发方案", "我", datetime(2026, 10, 14, 15))
    draft.content_json["next_action"] = "客户自行审预算"
    assert validate_action_evidence(draft.content_json, evidence["action_id"], source_content=source) is None


@pytest.mark.parametrize("source", ["我发方案，小王下周三审预算", "我发方案，客户下周三答复"])
def test_other_subject_deadline_cannot_authorize_my_undated_action(source):
    draft = _meeting(source)
    assert validate_action_evidence(draft.content_json, "act_send", source_content=source) is None


@pytest.mark.parametrize(
    "withdrawal", ["取消：我下周三发方案", "我取消下周三发方案", "更正：我发方案不是下周三，改为下周五"]
)
def test_later_accepted_withdrawal_revokes_unchanged_canonical_action(withdrawal):
    source = "我下周三发方案"
    draft = _meeting(source)
    draft.source_records.append(
        SourceSegment(segment_id="seg_withdrawal", text=withdrawal, recorded_at=datetime(2026, 10, 10, 8))
    )
    draft.source_segments.append(withdrawal)
    stale = deepcopy(draft.content_json)
    stale["source_records"] = [record.model_dump(mode="json") for record in draft.source_records]
    full_source = "\n".join(draft.source_segments)
    assert validate_action_evidence(stale, "act_send", source_content=full_source) is None
    reconcile_action_evidence(draft, "ONLINE_MEETING")
    assert validate_action_evidence(draft.content_json, "act_send", source_content=full_source) is None
    assert draft.content_json["action_evidence"][0]["state"] == "SUPERSEDED"
    assert draft.content_json["action_evidence"][0]["evidence_quote"] == source


@pytest.mark.parametrize("source", ["我发方案。下周三", "我发方案，改为小王下周三审预算"])
def test_separate_sentence_or_replacement_subject_cannot_supply_action_deadline(source):
    draft = _meeting(source)
    assert validate_action_evidence(draft.content_json, "act_send", source_content=source) is None
