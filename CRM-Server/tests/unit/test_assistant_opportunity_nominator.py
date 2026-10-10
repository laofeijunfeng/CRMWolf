"""Opportunity nomination is model-suggested and server-bound."""

from __future__ import annotations

from types import SimpleNamespace


class FakeTransport:
    def __init__(self, payload: dict) -> None:
        self.payload = payload
        self.calls: list[dict] = []

    async def ainvoke_structured(self, *, system_prompt, user_prompt, response_model, **kwargs):
        self.calls.append({"system": system_prompt[:30], "user": user_prompt})
        return self.payload


def _task():
    return SimpleNamespace(public_id="ast_n1", team_id=7, user_id=3)


def _activity():
    return SimpleNamespace(
        activity_revision=2,
        customer_id=11,
        source_content="陈总明确表示下季度采购星河报销系统",
        content_json='{"source_records":[{"segment_id":"seg_a1","text":"陈总明确表示下季度采购星河报销系统"}]}',
    )


class FakeQuery:
    def __init__(self, rows):
        self.rows = rows

    def filter(self, *a, **k):
        return self

    def all(self):
        return self.rows

    def one_or_none(self):
        return None


class FakeDB:
    def __init__(self, active_opportunities=None):
        self.active = active_opportunities or []

    def query(self, model):
        name = getattr(model, "__name__", str(model))
        if name == "Opportunity":
            return FakeQuery(self.active)
        return FakeQuery([])


def _patch(monkeypatch):
    import app.services.assistant.task_state as task_state
    from app.services.assistant import opportunity_nominator as mod

    monkeypatch.setattr(mod, "team_model_credentials", lambda db, team_id: ("host", "key", "m1"))
    monkeypatch.setattr(task_state, "load_draft", lambda task: SimpleNamespace(source_segments=["x"]))


def test_create_signal_uses_segment_quote_and_forwards_opportunities(monkeypatch):
    import asyncio

    transport = FakeTransport(
        {
            "candidates": [
                {
                    "kind": "opportunity_create",
                    "evidence_quote": "采购星河报销系统",
                    "segment_id": "seg_a1",
                }
            ]
        }
    )
    _patch(monkeypatch)
    nominator = __import__(
        "app.services.assistant.opportunity_nominator", fromlist=["OpportunityNominator"]
    ).OpportunityNominator(runtime=transport)

    result = asyncio.run(nominator.nominate(FakeDB(), _task(), _activity()))

    assert result == [
        {
            "kind": "opportunity_create",
            "evidence_quote": "采购星河报销系统",
            "segment_id": "seg_a1",
            "payload": {},
        }
    ]
    user_payload = transport.calls[0]["user"]
    assert "seg_a1" in user_payload
    assert "陈总明确表示下季度采购星河报销系统" in user_payload


def test_stage_signal_without_target_is_dropped(monkeypatch):
    import asyncio

    from app.services.assistant.opportunity_nominator import OpportunityNominator

    transport = FakeTransport(
        {
            "candidates": [
                {
                    "kind": "opportunity_stage",
                    "evidence_quote": "推进到方案",
                    "segment_id": "seg_a1",
                    "target_public_id": None,
                    "stage_template_id": 5,
                }
            ]
        }
    )
    _patch(monkeypatch)

    result = asyncio.run(OpportunityNominator(runtime=transport).nominate(FakeDB(), _task(), _activity()))

    assert result == []


def test_no_signal_returns_empty(monkeypatch):
    import asyncio

    from app.services.assistant.opportunity_nominator import OpportunityNominator

    transport = FakeTransport({"candidates": []})
    _patch(monkeypatch)

    result = asyncio.run(OpportunityNominator(runtime=transport).nominate(FakeDB(), _task(), _activity()))

    assert result == []
