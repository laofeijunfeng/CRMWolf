"""Contract tests for the single CRM Agent UI and typed input protocol."""

from __future__ import annotations

from uuid import UUID

import pytest
from pydantic import TypeAdapter, ValidationError

from app.services.agent.ui import (
    AgentChatInput,
    AgentChatRequest,
    AgentTransportErrorEvent,
    AgentUIBlock,
    AgentUIEnvelope,
    AgentUIStreamEvent,
    InteractionBlock,
)


def _customer_list_envelope_payload() -> dict[str, object]:
    return {
        "schema_version": "crm.agent.ui.v1",
        "message_id": 12345,
        "turn_id": "turn_01JEXAMPLE",
        "role": "assistant",
        "state": "final",
        "blocks": [
            {
                "id": "b_text_1",
                "type": "text",
                "format": "plain",
                "text": "你当前可访问的上海客户共有 18 家，先展示最近更新的 10 家。",
            },
            {
                "id": "b_customers_1",
                "type": "entity_list",
                "entity_type": "customer",
                "result_set_id": "rs_01JEXAMPLE",
                "items": [
                    {
                        "entity_ref": {
                            "ref_id": "eref_01J1",
                            "resource": "customer",
                            "public_id": "cus_01J1",
                            "display_name": "示例科技有限公司",
                            "result_set_id": "rs_01JEXAMPLE",
                        }
                    }
                ],
                "total": 18,
            },
            {
                "id": "b_page_1",
                "type": "pagination",
                "result_set_id": "rs_01JEXAMPLE",
                "range_start": 1,
                "range_end": 10,
                "total": 18,
                "next_action_id": "act_next_01J",
            },
        ],
        "suggested_actions": [
            {
                "action_id": "act_filter_mine",
                "type": "query_refinement",
                "label": "只看我负责的客户",
            }
        ],
        "metadata": {
            "route": "QUERY",
            "result_set_id": "rs_01JEXAMPLE",
            "accessibility_label": "上海客户列表，共18家",
        },
    }



def test_agent_ui_stream_event_freezes_delta_and_final_authority() -> None:
    adapter = TypeAdapter(AgentUIStreamEvent)

    delta = adapter.validate_python(
        {
            "event": "agent_ui",
            "phase": "delta",
            "message_id": 12345,
            "turn_id": "turn_01JEXAMPLE",
            "sequence": 7,
            "operations": [
                {"op": "append_text", "block_id": "b_text_1", "delta": "你当前可访问的"},
            ],
        }
    )
    final = adapter.validate_python(
        {
            "event": "agent_ui",
            "phase": "final",
            "message_id": 12345,
            "turn_id": "turn_01JEXAMPLE",
            "sequence": 8,
            "message": _customer_list_envelope_payload(),
        }
    )

    assert delta.phase == "delta"
    assert delta.operations[0].op == "append_text"
    assert final.phase == "final"
    assert final.message.state == "final"


def test_agent_ui_final_stream_event_must_match_the_authoritative_envelope_identity() -> None:
    payload = {
        "event": "agent_ui",
        "phase": "final",
        "message_id": 12345,
        "turn_id": "turn_mismatch",
        "sequence": 8,
        "message": _customer_list_envelope_payload(),
    }

    with pytest.raises(ValidationError, match="final stream identity must match message envelope"):
        TypeAdapter(AgentUIStreamEvent).validate_python(payload)


def test_agent_ui_delta_stream_event_rejects_non_text_operations() -> None:
    payload = {
        "event": "agent_ui",
        "phase": "delta",
        "message_id": 12345,
        "turn_id": "turn_01JEXAMPLE",
        "sequence": 1,
        "operations": [{"op": "replace_table", "block_id": "b_table_1", "delta": "invalid"}],
    }

    with pytest.raises(ValidationError):
        TypeAdapter(AgentUIStreamEvent).validate_python(payload)

def test_customer_list_agent_ui_envelope_matches_the_frozen_contract() -> None:
    envelope = AgentUIEnvelope.model_validate(_customer_list_envelope_payload())

    assert envelope.schema_version == "crm.agent.ui.v1"
    assert [block.type for block in envelope.blocks] == ["text", "entity_list", "pagination"]
    assert envelope.suggested_actions[0].type == "query_refinement"


def test_entity_list_items_reject_legacy_display_fields_and_mismatched_resources() -> None:
    payload = _customer_list_envelope_payload()
    entity_list = payload["blocks"][1]
    assert isinstance(entity_list, dict)
    items = entity_list["items"]
    assert isinstance(items, list)
    item = items[0]
    assert isinstance(item, dict)

    legacy_payload = _customer_list_envelope_payload()
    legacy_list = legacy_payload["blocks"][1]
    assert isinstance(legacy_list, dict)
    legacy_items = legacy_list["items"]
    assert isinstance(legacy_items, list)
    legacy_item = legacy_items[0]
    assert isinstance(legacy_item, dict)
    legacy_item["title"] = "旧标题"
    with pytest.raises(ValidationError):
        AgentUIEnvelope.model_validate(legacy_payload)

    mismatched_payload = _customer_list_envelope_payload()
    mismatched_list = mismatched_payload["blocks"][1]
    assert isinstance(mismatched_list, dict)
    mismatched_items = mismatched_list["items"]
    assert isinstance(mismatched_items, list)
    mismatched_item = mismatched_items[0]
    assert isinstance(mismatched_item, dict)
    entity_ref = mismatched_item["entity_ref"]
    assert isinstance(entity_ref, dict)
    entity_ref["resource"] = "contact"
    with pytest.raises(ValidationError, match="entity resource must match entity_type"):
        AgentUIEnvelope.model_validate(mismatched_payload)

    mismatched_result_set_payload = _customer_list_envelope_payload()
    mismatched_result_set_list = mismatched_result_set_payload["blocks"][1]
    assert isinstance(mismatched_result_set_list, dict)
    mismatched_result_set_items = mismatched_result_set_list["items"]
    assert isinstance(mismatched_result_set_items, list)
    mismatched_result_set_item = mismatched_result_set_items[0]
    assert isinstance(mismatched_result_set_item, dict)
    mismatched_result_set_ref = mismatched_result_set_item["entity_ref"]
    assert isinstance(mismatched_result_set_ref, dict)
    mismatched_result_set_ref["result_set_id"] = "rs_other"
    with pytest.raises(ValidationError, match="entity result_set_id must match list result_set_id"):
        AgentUIEnvelope.model_validate(mismatched_result_set_payload)


def test_all_p0_block_and_action_discriminators_are_closed_world() -> None:
    payloads: list[dict[str, object]] = [
        {"id": "text", "type": "text", "format": "markdown", "text": "**摘要**"},
        {"id": "list", "type": "entity_list", "entity_type": "customer", "items": [], "total": 0},
        {
            "id": "card",
            "type": "entity_card",
            "entity_type": "customer",
            "ref_id": "eref_1",
            "title": "示例客户",
            "sections": [],
            "actions": [],
        },
        {
            "id": "table",
            "type": "table",
            "columns": [{"key": "name", "label": "名称", "align": "left"}],
            "rows": [
                {
                    "id": "row_1",
                    "cells": [{"column_key": "name", "value": {"kind": "text", "value": "示例客户"}}],
                }
            ],
        },
        {
            "id": "timeline",
            "type": "timeline",
            "items": [{"id": "event_1", "occurred_at": "2026-08-21T10:00:00+08:00", "title": "完成拜访"}],
        },
        {
            "id": "metrics",
            "type": "metric_group",
            "metrics": [{"key": "count", "label": "客户数", "value": {"kind": "number", "value": 18}}],
        },
        {"id": "notice", "type": "notice", "tone": "info", "text": "结果按最近更新时间排序。"},
        {
            "id": "error",
            "type": "error",
            "code": "PERMISSION_DENIED",
            "title": "无权访问",
            "message": "你没有查看该客户的权限。",
            "retryable": False,
        },
        {
            "id": "interaction",
            "type": "interaction",
            "interaction_id": "int_1",
            "interaction_type": "confirmation",
            "state": "ACTIVE",
            "prompt": "确认创建跟进任务吗？",
            "fields": [],
            "options": [
                {"value": "confirm", "label": "确认"},
                {"value": "cancel", "label": "取消"},
            ],
            "selection_mode": "single",
            "submit_action_id": "act_submit_1",
        },
        {
            "id": "action",
            "type": "action_result",
            "action_id": "act_1",
            "status": "SUCCESS",
            "title": "创建成功",
            "message": "已创建跟进任务。",
        },
        {
            "id": "page",
            "type": "pagination",
            "result_set_id": "rs_1",
            "range_start": 1,
            "range_end": 10,
            "total": 18,
            "next_action_id": "act_next",
        },
    ]
    adapter = TypeAdapter(AgentUIBlock)

    assert [adapter.validate_python(payload).type for payload in payloads] == [
        "text",
        "entity_list",
        "entity_card",
        "table",
        "timeline",
        "metric_group",
        "notice",
        "error",
        "interaction",
        "action_result",
        "pagination",
    ]

    with pytest.raises(ValidationError):
        adapter.validate_python({"id": "legacy", "type": "legacy_markdown", "content": "old"})

    with pytest.raises(ValidationError):
        adapter.validate_python(
            {"id": "unsafe", "type": "text", "format": "markdown", "text": "摘要<script>alert(1)</script>"}
        )


def test_envelope_rejects_duplicate_block_ids() -> None:
    payload = _customer_list_envelope_payload()
    blocks = payload["blocks"]
    assert isinstance(blocks, list)
    duplicate = dict(blocks[0])
    blocks.append(duplicate)

    with pytest.raises(ValidationError):
        AgentUIEnvelope.model_validate(payload)


def test_interaction_contract_enforces_server_signed_confirmation_options() -> None:
    with pytest.raises(ValidationError):
        InteractionBlock.model_validate(
            {
                "id": "interaction",
                "type": "interaction",
                "interaction_id": "int_1",
                "interaction_type": "confirmation",
                "state": "ACTIVE",
                "prompt": "确认吗？",
                "fields": [],
                "options": [{"value": "yes", "label": "好的"}],
                "selection_mode": "single",
                "submit_action_id": "act_submit_1",
            }
        )


def test_typed_chat_request_accepts_each_input_and_rejects_legacy_content() -> None:
    input_adapter = TypeAdapter(AgentChatInput)
    assert input_adapter.validate_python({"type": "text", "text": "我在上海有哪些客户"}).type == "text"
    assert (
        input_adapter.validate_python(
            {"type": "interaction_submission", "action_id": "act_submit_1", "values": {"choice": "confirm"}}
        ).type
        == "interaction_submission"
    )
    assert input_adapter.validate_python({"type": "entity_action", "action_id": "act_open_1"}).type == "entity_action"

    request = AgentChatRequest.model_validate(
        {
            "session_id": 123,
            "client_request_id": "6fa2e0e8-86d4-4d6c-a1b0-6490b2bf12be",
            "input": {"type": "text", "text": "我在上海有哪些客户"},
        }
    )
    assert request.client_request_id == UUID("6fa2e0e8-86d4-4d6c-a1b0-6490b2bf12be")

    with pytest.raises(ValidationError):
        AgentChatRequest.model_validate(
            {
                "session_id": 123,
                "client_request_id": "6fa2e0e8-86d4-4d6c-a1b0-6490b2bf12be",
                "content": "旧协议",
            }
        )



def test_transport_error_event_is_strict_and_uses_closed_error_codes() -> None:
    event = AgentTransportErrorEvent.model_validate(
        {
            "event": "transport_error",
            "code": "ACTION_EXPIRED",
            "message": "该操作已过期，请刷新会话后重新发起。",
            "retryable": False,
            "session_id": 123,
        }
    )
    assert event.code == "ACTION_EXPIRED"

    with pytest.raises(ValidationError):
        AgentTransportErrorEvent.model_validate(
            {
                "event": "transport_error",
                "code": "LEGACY_ACTION_ERROR",
                "message": "旧错误码",
                "retryable": False,
                "session_id": 123,
            }
        )

    with pytest.raises(ValidationError):
        AgentTransportErrorEvent.model_validate(
            {
                "event": "transport_error",
                "code": "ACTION_INVALID",
                "message": "无效操作",
                "retryable": False,
                "session_id": 123,
                "content": "不允许旧内容字段",
            }
        )

def test_agent_ui_contracts_do_not_coerce_transport_scalars() -> None:
    payload = _customer_list_envelope_payload()
    payload["message_id"] = "12345"

    with pytest.raises(ValidationError):
        AgentUIEnvelope.model_validate(payload)


def test_choice_requires_explicit_bounded_selection_and_unique_options() -> None:
    base = {
        "id": "choice",
        "type": "interaction",
        "interaction_id": "int_choice",
        "interaction_type": "choice",
        "state": "ACTIVE",
        "prompt": "请选择客户",
        "fields": [],
        "options": [
            {"value": "customer_1", "label": "客户一"},
            {"value": "customer_2", "label": "客户二"},
        ],
        "selection_mode": "multiple",
        "submit_action_id": "act_submit_choice",
    }

    with pytest.raises(ValidationError):
        InteractionBlock.model_validate(base)

    with pytest.raises(ValidationError):
        InteractionBlock.model_validate(
            {
                **base,
                "min_selections": 1,
                "max_selections": 2,
                "options": [
                    {"value": "customer_1", "label": "客户一"},
                    {"value": "customer_1", "label": "重复客户"},
                ],
            }
        )


def test_confirmation_rejects_duplicate_server_option_values() -> None:
    with pytest.raises(ValidationError):
        InteractionBlock.model_validate(
            {
                "id": "confirmation",
                "type": "interaction",
                "interaction_id": "int_confirm",
                "interaction_type": "confirmation",
                "state": "ACTIVE",
                "prompt": "确认吗？",
                "fields": [],
                "options": [
                    {"value": "confirm", "label": "确认"},
                    {"value": "cancel", "label": "取消"},
                    {"value": "confirm", "label": "再次确认"},
                ],
                "selection_mode": "single",
                "submit_action_id": "act_submit_confirm",
            }
        )


def test_text_input_requires_explicit_length_bounds() -> None:
    with pytest.raises(ValidationError):
        InteractionBlock.model_validate(
            {
                "id": "text_input",
                "type": "interaction",
                "interaction_id": "int_text",
                "interaction_type": "text_input",
                "state": "ACTIVE",
                "prompt": "请输入说明",
                "fields": [
                    {
                        "key": "reason",
                        "label": "说明",
                        "field_type": "textarea",
                        "required": True,
                    }
                ],
                "options": [],
                "allow_blank": False,
                "submit_action_id": "act_submit_text",
            }
        )
