"""Explicit pending confirmation Case matching behavior."""

from __future__ import annotations

from app.services.agent.orchestrator.contracts import PendingCaseContext
from app.services.agent.orchestrator.pending_case_matcher import match_pending_case


def _case(
    public_id: str = "fuc_" + "1" * 32,
    *,
    customer_name: str = "广州凡亚信息科技有限公司",
    aliases: list[str] | None = None,
    title: str = "跟进 POC 环境部署情况",
) -> PendingCaseContext:
    return PendingCaseContext(
        case_public_id=public_id,
        customer_name=customer_name,
        customer_aliases=aliases or ["凡亚信息"],
        task_title=title,
        task_description="确认客户 POC 环境部署进度",
        due_at_text="周四",
        question_text="是否完成该待办？",  # noqa: RUF001
    )


def test_normal_activity_does_not_enter_pending_case_flow() -> None:
    result = match_pending_case("今天联系了凡亚信息，客户反馈项目正在评估", [_case()])  # noqa: RUF001

    assert result.status == "NONE"
    assert result.case is None


def test_normal_query_does_not_enter_pending_case_flow() -> None:
    result = match_pending_case("上海有哪些客户", [_case()])

    assert result.status == "NONE"


def test_explicit_case_id_matches_only_server_context() -> None:
    case = _case()
    result = match_pending_case(f"完成 {case.case_public_id}", [case])

    assert result.status == "MATCHED"
    assert result.case == case


def test_customer_alias_matches_unique_pending_case() -> None:
    case = _case()
    result = match_pending_case("完成凡亚信息的待办", [case], semantic_reference_authorized=True)

    assert result.status == "MATCHED"
    assert result.case == case


def test_multiple_cases_for_same_customer_require_clarification() -> None:
    first = _case()
    second = _case("fuc_" + "2" * 32, title="跟进立项流程")
    result = match_pending_case("完成凡亚信息的待办", [first, second], semantic_reference_authorized=True)

    assert result.status == "AMBIGUOUS"
    assert result.case is None
    assert result.candidates == (first, second)


def test_unknown_explicit_case_is_not_guessed() -> None:
    result = match_pending_case("完成 fuc_" + "9" * 32, [_case()])

    assert result.status == "NOT_FOUND"
    assert result.case is None


def test_continue_previous_workflow_is_not_a_pending_case_reference() -> None:
    result = match_pending_case("继续刚才的任务", [_case()])

    assert result.status == "NONE"


def test_normal_follow_up_task_transition_is_not_pending_case_reference() -> None:
    result = match_pending_case("把这个跟进任务标记完成", [_case()])

    assert result.status == "NONE"




def test_generic_previous_task_reference_matches_only_when_unique() -> None:
    case = _case()
    result = match_pending_case("完成上面的待办", [case], semantic_reference_authorized=True)

    assert result.status == "MATCHED"
    assert result.case == case


def test_generic_previous_task_reference_is_ambiguous_with_multiple_cases() -> None:
    first = _case()
    second = _case("fuc_" + "2" * 32, title="跟进立项流程")
    result = match_pending_case("完成上面的任务", [first, second], semantic_reference_authorized=True)

    assert result.status == "AMBIGUOUS"
    assert result.candidates == (first, second)
