"""Production assistant model calls fail closed and use activity-specific rubrics."""

import json
from datetime import datetime
from types import SimpleNamespace

import httpx
import pytest

from app.services.assistant import model_transport
from app.services.assistant.action_evidence import SourceSegment
from app.services.assistant.contracts import TaskDraft
from app.services.assistant.intake_flow import apply_structured_draft
from app.services.assistant.llm import AssistantLLM
from app.services.assistant.llm_contracts import KindDecision, ModelDraftAction, ModelTemporalMention
from app.services.assistant.model_transport import AssistantLLMError, AssistantModelTransport
from app.services.assistant.quality_gate import QualityGate
from app.services.assistant.temporal_evidence import ActionContractError, TemporalContractError, find_time_spans


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



def _follow_content(text: str, next_action: str = "", when: str = "") -> dict:
    return {
        "content": text,
        "customer_feedback": "",
        "current_progress": "",
        "risks": [],
        "next_action": next_action,
        "next_follow_time_text": when,
        "next_action_absence_reason": "",
    }


def _meeting_content(text: str, next_action: str = "") -> dict:
    return {
        "meeting_subject": "准备会",
        "meeting_background": "",
        "communication_context": "",
        "participants": {"internal": [], "customer": []},
        "key_minutes": [text],
        "qa_items": [],
        "requirements": [],
        "concerns_or_objections": [],
        "risks": [],
        "decisions_or_commitments": [],
        "action_items": [],
        "next_step_summary": next_action,
        "next_action_absence_reason": "",
    }


def _evidence(text: str, *, with_time: bool, with_action: bool) -> tuple[list[dict], list[dict]]:
    mentions = []
    actions = []
    if with_time:
        for index, span in enumerate(find_time_spans(text)):
            mentions.append({
                "raw_text": span.raw_text,
                "quote_start": span.start,
                "quote_end": span.end,
                "kind": span.kind,
                "role": "SALES_FOLLOW_UP",
                "owner": "我",
                "action_ref": f"a{index}",
                "confidence": 0.8,
            })
            actions.append({
                "action_ref": f"a{index}",
                "owner_role": "SALES",
                "owner_text": "我",
                "action_text": "联系叶老师",
                "action_status": "PLANNED",
                "evidence_quote": span.raw_text,
                "quote_start": span.start,
                "quote_end": span.end,
            })
    elif with_action:
        quote = "会完成准备"
        start = text.find(quote)
        actions.append({
            "action_ref": "a1",
            "owner_role": "CUSTOMER",
            "owner_text": "叶老师",
            "action_text": "完成准备",
            "action_status": "COMMITTED",
            "evidence_quote": quote,
            "quote_start": start,
            "quote_end": start + len(quote),
        })
    return mentions, actions


def _mock_completion(monkeypatch, payload: dict) -> None:
    _team_config(monkeypatch)
    original = httpx.AsyncClient

    def respond(request):
        assert request.url == "https://ai.example/v1/chat/completions"
        body = json.dumps(payload, ensure_ascii=False)
        return httpx.Response(200, json={"choices": [{"message": {"content": body}}]})

    monkeypatch.setattr(
        model_transport.httpx,
        "AsyncClient",
        lambda **kwargs: original(transport=httpx.MockTransport(respond), **kwargs),
    )


@pytest.mark.parametrize("kind", ["FOLLOW_UP", "ONLINE_MEETING", "OFFLINE_MEETING"])
@pytest.mark.parametrize("shape", ["time", "action", "none"])
async def test_http_200_structured_output_reaches_draft(monkeypatch, kind, shape):
    if shape == "time":
        text = "我下周三联系叶老师"
    elif shape == "action":
        text = "叶老师会完成准备"
    else:
        text = "客户预算待批"
    mentions, actions = _evidence(text, with_time=shape == "time", with_action=shape == "action")
    meeting = kind != "FOLLOW_UP"
    payload = {
        "content": text,
        "customer_name": "通力",
        "next_action": "联系叶老师" if shape == "time" else "",
        "next_follow_time_text": "下周三" if shape == "time" else "",
        "temporal_mentions": mentions,
        "actions": actions,
        "content_json": _meeting_content(text, "联系叶老师" if shape == "time" else "") if meeting else _follow_content(
            text, "联系叶老师" if shape == "time" else "", "下周三" if shape == "time" else ""
        ),
    }
    if meeting:
        payload["meeting_subject"] = "准备会"
        payload["participants"] = "双方参会"
    _mock_completion(monkeypatch, payload)
    result = await AssistantLLM().structure_draft(object(), team_id=1, kind=kind, user_text=text)
    if shape == "time":
        assert isinstance(result.temporal_mentions[0], ModelTemporalMention)
        assert isinstance(result.actions[0], ModelDraftAction)
    draft = TaskDraft(
        source_segments=[text],
        source_records=[SourceSegment(segment_id="seg_test", recorded_at=datetime(2026, 10, 27, 15), text=text)],
    )
    task = SimpleNamespace(draft_json=draft.model_dump(mode="json"), activity_kind=kind)
    merged = apply_structured_draft(task, result, correction_text=text)
    if shape == "none":
        assert "temporal_evidence" not in merged.content_json
    else:
        bundle = merged.content_json["temporal_evidence"]
        assert bundle["version"] == "temporal-evidence-v1"
        if shape == "time":
            assert bundle["mentions"][0]["raw_text"] == "下周三"
        else:
            assert bundle["actions"][0]["action_text"] == "完成准备"


async def test_http_200_missing_time_stays_a_temporal_contract_error(monkeypatch):
    text = "我下周三联系叶老师"
    payload = {
        "content": text,
        "customer_name": "通力",
        "next_action": "联系叶老师",
        "next_follow_time_text": "下周三",
        "temporal_mentions": [],
        "actions": [],
        "content_json": _follow_content(text, "联系叶老师", "下周三"),
    }
    _mock_completion(monkeypatch, payload)
    with pytest.raises(TemporalContractError, match="temporal mentions do not cover the source") as caught:
        await AssistantLLM().structure_draft(object(), team_id=1, kind="FOLLOW_UP", user_text=text)
    assert not isinstance(caught.value, AssistantLLMError)
    assert "model_type" not in str(caught.value)


async def test_illegal_action_model_is_not_a_temporal_mention_error():
    text = "叶老师会完成准备"
    draft = TaskDraft(
        source_segments=[text],
        source_records=[SourceSegment(segment_id="seg_test", recorded_at=datetime(2026, 10, 27, 15), text=text)],
        content_json=_follow_content(text),
    )
    task = SimpleNamespace(draft_json=draft.model_dump(mode="json"), activity_kind="FOLLOW_UP")
    from app.services.assistant.llm_contracts import StructureDraftResult

    structured = StructureDraftResult(
        kind_confirmed="FOLLOW_UP",
        content=text,
        content_json=_follow_content(text),
        actions=[ModelDraftAction(
            action_ref="a1",
            owner_role="CUSTOMER",
            owner_text="叶老师",
            action_text="完成准备",
            action_status="COMMITTED",
            evidence_quote="不在原文",
            quote_start=0,
            quote_end=4,
        )],
    )
    with pytest.raises(ActionContractError, match="action quote is not in the source"):
        apply_structured_draft(task, structured, correction_text=text)
