"""Contract tests for the public Agent UI v1 business evaluator."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))

from run_agent_business_eval import (
    EvalCase,
    evaluate_case,
    extract_final_answer,
    interaction_values,
    next_resume_input,
    protocol_validation_errors,
)


def _final_message(*blocks: dict[str, object], route: str = "QUERY") -> dict[str, object]:
    return {
        "event": "agent_ui",
        "phase": "final",
        "message_id": 10,
        "turn_id": "turn_10",
        "sequence": 1,
        "message": {
            "schema_version": "crm.agent.ui.v1",
            "message_id": 10,
            "turn_id": "turn_10",
            "role": "assistant",
            "state": "final",
            "blocks": list(blocks),
            "suggested_actions": [],
            "metadata": {"display": "MESSAGE", "route": route},
        },
    }


def test_evaluator_reads_route_text_and_entity_refs_from_authoritative_final_event() -> None:
    events = [
        {"event": "session", "session_id": 10, "session_key": "session_10"},
        _final_message(
            {"id": "text", "type": "text", "format": "markdown", "text": "共找到 1 家公司。"},
            {
                "id": "entities",
                "type": "entity_list",
                "entity_type": "customer",
                "items": [
                    {
                        "entity_ref": {
                            "ref_id": "eref_1",
                            "resource": "customer",
                            "public_id": "cus_1",
                            "display_name": "上海示例科技有限公司",
                            "result_set_id": "rs_1",
                        }
                    }
                ],
                "total": 1,
                "result_set_id": "rs_1",
            },
        ),
        {"event": "done", "session_id": 10},
    ]

    result = evaluate_case(
        EvalCase(
            case_id="query_1",
            category="read_customer_summary",
            content="上海有哪些客户",
            expected_route="QUERY",
            expected_customer_name="上海示例科技有限公司",
            required_terms=["上海示例科技"],
        ),
        events,
        [],
        0.1,
    )

    assert result.passed is True
    assert result.routes_seen == ["QUERY"]
    assert result.block_types_seen == ["text", "entity_list"]
    assert result.final_answer == "共找到 1 家公司。"


def test_evaluator_does_not_depend_on_removed_legacy_intent_or_tool_events() -> None:
    events = [
        _final_message(
            {"id": "text", "type": "text", "format": "plain", "text": "已完成。"},
            route="WORKFLOW",
        ),
        {"event": "done", "session_id": 10},
    ]

    result = evaluate_case(
        EvalCase(
            case_id="write_1",
            category="write_activity",
            content="记录跟进",
            expected_route="WORKFLOW",
        ),
        events,
        [],
        0.1,
    )

    assert result.passed is True
    assert result.routes_seen == ["WORKFLOW"]
    assert result.action_statuses_seen == []


def test_next_resume_input_submits_server_signed_interaction_action() -> None:
    events = [
        _final_message(
            {
                "id": "interaction",
                "type": "interaction",
                "interaction_id": "int_1",
                "interaction_type": "confirmation",
                "state": "ACTIVE",
                "prompt": "确认创建?",
                "fields": [],
                "options": [
                    {"value": "confirm", "label": "确认创建"},
                    {"value": "cancel", "label": "取消"},
                ],
                "selection_mode": "single",
                "min_selections": None,
                "max_selections": None,
                "allow_blank": None,
                "submit_on_select": False,
                "submit_label": "确认",
                "submit_action_id": "act_submit_1",
            },
            route="WORKFLOW",
        )
    ]

    assert next_resume_input(events, fallback_confirmation="确认执行") == {
        "type": "interaction_submission",
        "action_id": "act_submit_1",
        "values": {"choice": "confirm"},
    }


def test_action_result_success_is_visible_to_public_evaluator() -> None:
    events = [
        _final_message(
            {
                "id": "result",
                "type": "action_result",
                "action_id": "act_1",
                "status": "SUCCESS",
                "title": "创建成功",
                "message": "已创建跟进记录。",
            },
            route="WORKFLOW",
        ),
        {"event": "done", "session_id": 10},
    ]

    result = evaluate_case(
        EvalCase(
            case_id="write_2",
            category="write_activity",
            content="记录跟进",
            expected_route="WORKFLOW",
            expected_action_status="SUCCESS",
        ),
        events,
        [],
        0.1,
    )

    assert result.passed is True
    assert result.action_statuses_seen == ["SUCCESS"]
    assert extract_final_answer(events) == ""


def test_confirmation_resume_requires_explicit_confirm_option() -> None:
    block = {
        "interaction_type": "confirmation",
        "options": [
            {"value": "cancel", "label": "取消"},
            {"value": "dismiss", "label": "暂不处理"},
        ],
    }

    assert interaction_values(block, fallback_confirmation="确认执行") is None


def test_evaluator_rejects_invalid_agent_ui_final_envelope() -> None:
    events = [
        {
            **_final_message(
                {"id": "text", "type": "text", "format": "plain", "text": "已完成。"}
            ),
            "message": {
                **_final_message(
                    {"id": "text", "type": "text", "format": "plain", "text": "已完成。"}
                )["message"],
                "schema_version": "crm.agent.ui.v0",
            },
        },
        {"event": "done", "session_id": 10},
    ]

    result = evaluate_case(
        EvalCase(case_id="invalid_ui", category="contract", content="测试", expected_route="QUERY"),
        events,
        [],
        0.1,
    )

    assert result.passed is False
    assert any("Agent UI v1 协议校验失败" in reason for reason in result.reasons)


def test_evaluator_requires_done_event() -> None:
    events = [_final_message({"id": "text", "type": "text", "format": "plain", "text": "已完成。"})]

    result = evaluate_case(
        EvalCase(case_id="missing_done", category="contract", content="测试", expected_route="QUERY"),
        events,
        [],
        0.1,
    )

    assert result.passed is False
    assert "未收到 done 事件" in result.reasons


def test_transport_error_is_reported_as_a_failed_business_case() -> None:
    events = [
        {
            "event": "transport_error",
            "code": "UPSTREAM_TIMEOUT",
            "message": "模型服务超时",
            "retryable": True,
            "session_id": 10,
            "status_code": 504,
        }
    ]

    result = evaluate_case(
        EvalCase(case_id="transport_error", category="contract", content="测试", expected_route="QUERY"),
        events,
        [],
        0.1,
    )

    assert result.passed is False
    assert "未收到 done 事件" in result.reasons
    assert any("UPSTREAM_TIMEOUT" in reason for reason in result.reasons)
    assert protocol_validation_errors(events) == []


def test_failed_action_result_does_not_satisfy_success_expectation() -> None:
    events = [
        _final_message(
            {
                "id": "result",
                "type": "action_result",
                "action_id": "act_1",
                "status": "FAILED",
                "title": "创建失败",
                "message": "业务校验失败。",
            },
            route="WORKFLOW",
        ),
        {"event": "done", "session_id": 10},
    ]

    result = evaluate_case(
        EvalCase(
            case_id="failed_action",
            category="write_activity",
            content="记录跟进",
            expected_route="WORKFLOW",
            expected_action_status="SUCCESS",
        ),
        events,
        [],
        0.1,
    )

    assert result.passed is False
    assert result.action_statuses_seen == ["FAILED"]
    assert "未看到期望操作结果 SUCCESS" in result.reasons


def test_invalid_entity_reference_is_not_accepted_as_a_query_result() -> None:
    events = [
        _final_message(
            {
                "id": "entities",
                "type": "entity_list",
                "entity_type": "customer",
                "items": [{"title": "错误的旧格式"}],
                "total": 1,
                "result_set_id": "rs_1",
            }
        ),
        {"event": "done", "session_id": 10},
    ]

    result = evaluate_case(
        EvalCase(case_id="invalid_entity", category="read_customer_summary", content="上海有哪些客户"),
        events,
        [],
        0.1,
    )

    assert result.passed is False
    assert any("Agent UI v1 协议校验失败" in reason for reason in result.reasons)
    assert result.block_types_seen == []
