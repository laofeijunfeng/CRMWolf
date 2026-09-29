"""Production assistant model calls fail closed and use activity-specific rubrics."""

import httpx
import pytest

from app.services.assistant import model_transport
from app.services.assistant.llm import AssistantLLM
from app.services.assistant.llm_contracts import KindDecision
from app.services.assistant.model_transport import AssistantLLMError, AssistantModelTransport
from app.services.assistant.quality_gate import QualityGate


class Config:
    api_host = "https://ai.example/v1"
    model_name = "model"


def _team_config(monkeypatch):
    monkeypatch.setattr(model_transport.ai_config_crud, "get_config", lambda db, team_id: Config())
    monkeypatch.setattr(model_transport.ai_config_crud, "get_decrypted_api_key", lambda db, team_id: "sk-test")


@pytest.mark.parametrize("content", ["", "not json", "{}", '{"kind":"INVALID"}', '{"kind":"FOLLOW_UP","unknown":1}'])
async def test_classification_rejects_empty_or_invalid_model_output(monkeypatch, content):
    _team_config(monkeypatch)
    original_client = httpx.AsyncClient

    def respond(request):
        assert request.url == "https://ai.example/v1/chat/completions"
        assert request.headers["authorization"] == "Bearer sk-test"
        return httpx.Response(200, json={"choices": [{"message": {"content": content}}]})

    monkeypatch.setattr(
        model_transport.httpx,
        "AsyncClient",
        lambda **kwargs: original_client(transport=httpx.MockTransport(respond), **kwargs),
    )
    with pytest.raises(AssistantLLMError):
        await AssistantLLM().classify_kind(object(), team_id=3, user_text="客户电话沟通")


async def test_quality_technical_failure_is_not_a_content_gap(monkeypatch):
    _team_config(monkeypatch)

    class Unavailable:
        async def ainvoke_structured(self, **kwargs):
            raise TimeoutError("timeout")

    with pytest.raises(AssistantLLMError):
        await QualityGate(evaluator=Unavailable()).evaluate(
            object(), team_id=1, user_text="客户反馈预算未定", content="客户反馈预算未定", next_action="约周三复盘"
        )


async def test_meeting_quality_uses_meeting_rubric_and_preserves_score_detail(monkeypatch):
    _team_config(monkeypatch)

    class ScoreMeeting:
        async def ainvoke_structured(self, **kwargs):
            assert "会议主题与背景原则" in kwargs["system_prompt"]
            assert "客户反馈原则" not in kwargs["system_prompt"]
            assert '"activity_kind": "ONLINE_MEETING"' in kwargs["user_prompt"]
            assert '"meeting_subject": "Q4评审"' in kwargs["user_prompt"]
            return {
                "score": 52,
                "reason": "参会角色不清楚",
                "principle_scores": {"会议主题与背景": {"score": 11, "max_score": 15, "comment": "主题明确"}},
                "supplement_question": "请问客户方是谁参会？",
            }

    result = await QualityGate(evaluator=ScoreMeeting()).evaluate(
        object(), team_id=1, user_text="开了Q4评审会", content="讨论预算", next_action="周三补方案",
        kind="ONLINE_MEETING", content_json={"meeting_subject": "Q4评审", "key_minutes": ["讨论预算"]},
    )
    assert not result.passed
    assert result.score == 52
    assert result.question == "请问客户方是谁参会？"
    assert result.detail["principle_scores"]["会议主题与背景"]["max_score"] == 15


async def test_http_timeout_is_typed_model_failure(monkeypatch):
    original_client = httpx.AsyncClient

    def fail(request):
        raise httpx.ReadTimeout("timed out", request=request)

    monkeypatch.setattr(
        model_transport.httpx,
        "AsyncClient",
        lambda **kwargs: original_client(transport=httpx.MockTransport(fail), **kwargs),
    )
    with pytest.raises(AssistantLLMError):
        await AssistantModelTransport().ainvoke_structured(
            api_host="https://ai.example/v1", api_key="sk-test", model="model", temperature=0,
            system_prompt="classify", user_prompt="text", response_model=KindDecision,
            error_prefix="分类",
        )



async def test_classification_uses_thirty_second_budget(monkeypatch):
    seen = {}

    def fake_client(**kwargs):
        seen.update(kwargs)
        raise httpx.ReadTimeout("timed out")

    monkeypatch.setattr(model_transport.httpx, "AsyncClient", fake_client)
    with pytest.raises(AssistantLLMError):
        await AssistantModelTransport().ainvoke_structured(
            api_host="https://ai.example/v1", api_key="sk-test", model="fast-classifier", temperature=0,
            system_prompt="classify", user_prompt="text", response_model=KindDecision,
            error_prefix="活动类型判断", timeout_seconds=30,
        )
    assert seen["timeout"] == 30

async def test_meeting_structuring_preserves_all_canonical_action_items(monkeypatch):
    _team_config(monkeypatch)

    class Meeting:
        async def ainvoke_structured(self, **kwargs):
            assert "action_items" in kwargs["system_prompt"]
            return {
                "meeting_subject": "Q4评审", "content": "讨论预算与POC", "participants": "客户王总、我方李经理",
                "next_action": "周三发方案", "content_json": {
                    "meeting_subject": "Q4评审", "meeting_background": "年度预算", "communication_context": "现场会议",
                    "participants": {"internal": ["李经理"], "customer": ["王总"]},
                    "key_minutes": ["讨论预算与POC"], "qa_items": [{"question": "POC何时", "answer": "下周"}],
                    "requirements": ["POC"], "concerns_or_objections": ["预算"], "risks": ["延期"],
                    "decisions_or_commitments": ["准备方案"],
                    "action_items": [
                        {"owner": "李经理", "action": "发方案", "due_date": "周三"},
                        {"owner": "王总", "action": "审预算", "due_date": "周五"},
                    ], "next_step_summary": "双方继续推进", "next_action_absence_reason": "",
                },
            }

    result = await AssistantLLM(runtime=Meeting()).structure_draft(
        object(), team_id=1, kind="OFFLINE_MEETING", user_text="评审预算、POC及后续两件事"
    )
    assert [item["action"] for item in result.content_json["action_items"]] == ["发方案", "审预算"]


async def test_meeting_rejects_incomplete_canonical_content(monkeypatch):
    _team_config(monkeypatch)

    class Incomplete:
        async def ainvoke_structured(self, **kwargs):
            return {"content": "有两项行动", "content_json": {"meeting_subject": "Q4评审"}}

    with pytest.raises(AssistantLLMError):
        await AssistantLLM(runtime=Incomplete()).structure_draft(
            object(), team_id=1, kind="ONLINE_MEETING", user_text="评审两件事"
        )


async def test_quality_rejects_model_score_omission(monkeypatch):
    _team_config(monkeypatch)

    class MissingScore:
        async def ainvoke_structured(self, **kwargs):
            return {"reason": "信息不足", "principle_scores": {"事实": {"score": 3, "max_score": 20}}}

    with pytest.raises(AssistantLLMError):
        await QualityGate(evaluator=MissingScore()).evaluate(
            object(), team_id=1, user_text="客户反馈", content="客户反馈", next_action="约下周沟通"
        )


async def test_meeting_rejects_absent_canonical_content(monkeypatch):
    _team_config(monkeypatch)

    class FlatOnly:
        async def ainvoke_structured(self, **kwargs):
            return {"content": "讨论项目", "meeting_subject": "项目评审"}

    with pytest.raises(AssistantLLMError):
        await AssistantLLM(runtime=FlatOnly()).structure_draft(
            object(), team_id=1, kind="ONLINE_MEETING", user_text="项目评审"
        )


async def test_http_transport_validates_structured_classification(monkeypatch):
    _team_config(monkeypatch)
    original_client = httpx.AsyncClient

    def respond(request):
        data = request.read().decode()
        assert '"response_format": {"type": "json_object"}' in data
        return httpx.Response(200, json={"choices": [{"message": {"content": '{"kind":"FOLLOW_UP","reason":"电话沟通"}'}}]})

    monkeypatch.setattr(
        model_transport.httpx,
        "AsyncClient",
        lambda **kwargs: original_client(transport=httpx.MockTransport(respond), **kwargs),
    )
    decision = await AssistantLLM().classify_kind(object(), team_id=3, user_text="客户电话沟通")
    assert decision.kind == "FOLLOW_UP"
    assert decision.reason == "电话沟通"


async def test_follow_up_structuring_preserves_feedback_progress_and_risks(monkeypatch):
    _team_config(monkeypatch)

    class FollowUp:
        async def ainvoke_structured(self, **kwargs):
            assert "customer_feedback" in kwargs["system_prompt"]
            return {
                "customer_name": "睿狐科技", "content": "客户预算待批，POC顺利，实施有延期风险。",
                "next_action": "周三联系王总", "next_follow_time_text": "周三",
                "content_json": {
                    "content": "客户预算待批，POC顺利，实施有延期风险。",
                    "customer_feedback": "预算待批", "current_progress": "POC顺利", "risks": ["实施延期"],
                    "next_action": "周三联系王总", "next_follow_time_text": "周三",
                    "next_action_absence_reason": "",
                },
            }

    result = await AssistantLLM(runtime=FollowUp()).structure_draft(
        object(), team_id=1, kind="FOLLOW_UP", user_text="睿狐预算未批，POC顺利但延期"
    )
    assert result.content_json["customer_feedback"] == "预算待批"
    assert result.content_json["risks"] == ["实施延期"]


async def test_follow_up_uses_canonical_facts_when_flat_fields_diverge(monkeypatch):
    _team_config(monkeypatch)

    class Conflicting:
        async def ainvoke_structured(self, **kwargs):
            return {
                "content": "客户已批准预算", "next_action": "周三签约",
                "content_json": {
                    "content": "客户尚未批准预算", "customer_feedback": "预算待批", "current_progress": "立项",
                    "risks": ["预算"], "next_action": "周三复核预算", "next_follow_time_text": "周三",
                    "next_action_absence_reason": "",
                },
            }

    result = await AssistantLLM(runtime=Conflicting()).structure_draft(
        object(), team_id=1, kind="FOLLOW_UP", user_text="客户预算待批"
    )
    assert result.content == "客户尚未批准预算"
    assert result.next_action == "周三复核预算"
