"""Reusable Agent choice projection and resolution tests."""
from __future__ import annotations

import json

from app.services.agent import choice_resolution


def test_project_business_choice_keeps_ids_in_metadata_not_user_label():
    event = {
        "opportunities": [
            {
                "id": 301,
                "opportunity_name": "CRM 一期",
                "procurement_method_id": 2,
                "procurement_method_name": "公开招标",
                "target_stage_template_id": 9,
                "target_stage_name": "POC",
            }
        ]
    }

    choices = choice_resolution.project_business_choices(event)
    serialized = json.dumps(choices, ensure_ascii=False)

    assert choices[0]["label"] == "CRM 一期（目标阶段：POC，采购方式：公开招标）"
    assert choices[0]["value"] == "1"
    assert choices[0]["metadata"]["selected_opportunity_id"] == 301
    assert "procurement_method_id" not in serialized
    assert "target_stage_template_id" not in serialized


def test_resolve_choice_prefers_structured_metadata_over_visible_text():
    candidates = [
        {"id": 301, "opportunity_name": "CRM 一期"},
        {"id": 302, "opportunity_name": "CRM 二期"},
    ]

    result = choice_resolution.resolve_choice(
        "CRM 一期",
        metadata={"resource_type": "opportunity", "selected_opportunity_id": 302},
        spec=choice_resolution.OPPORTUNITY_SPEC,
        candidates=candidates,
    )

    assert result.selected == candidates[1]
    assert result.confidence == 1.0
    assert result.reason == "structured_metadata"


def test_resolve_choice_supports_protocol_ordinal_only():
    candidates = [
        {"id": 301, "opportunity_name": "CRM 一期", "procurement_method_name": "竞争性磋商"},
        {"id": 302, "opportunity_name": "CRM 二期", "procurement_method_name": "公开招标"},
    ]

    ordinal = choice_resolution.resolve_choice(
        "第二个",
        metadata={},
        spec=choice_resolution.OPPORTUNITY_SPEC,
        candidates=candidates,
    )

    assert ordinal.selected == candidates[1]
    assert ordinal.reason == "ordinal"


def test_resolve_choice_defers_business_semantics_to_resource_graph():
    candidates = [
        {"id": 301, "opportunity_name": "CRM 一期", "target_stage_name": "签约"},
        {"id": 302, "opportunity_name": "CRM 二期", "target_stage_name": "签约"},
    ]

    result = choice_resolution.resolve_choice(
        "签约",
        metadata={},
        spec=choice_resolution.OPPORTUNITY_SPEC,
        candidates=candidates,
    )

    assert result.selected is None
    assert result.reason == "semantic_required"
