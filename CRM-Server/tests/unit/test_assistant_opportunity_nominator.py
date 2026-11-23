"""Opportunity nomination is model-suggested and server-bound."""

from __future__ import annotations

import asyncio
import json
from datetime import date
from types import SimpleNamespace

import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session


class FakeTransport:
    def __init__(self, payload: dict) -> None:
        self.payload = payload
        self.calls: list[dict] = []

    async def ainvoke_structured(self, *, system_prompt, user_prompt, response_model, **kwargs):
        self.calls.append({"system": system_prompt[:30], "user": user_prompt})
        return response_model.model_validate_json(json.dumps(self.payload))


def _task():
    return SimpleNamespace(public_id="ast_n1", team_id=7, user_id=3)


def _activity():
    return SimpleNamespace(
        team_id=7,
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

    def order_by(self, *a):
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
    from app.services.assistant import opportunity_nominator as mod

    monkeypatch.setattr(mod, "team_model_credentials", lambda db, team_id: ("host", "key", "m1"))
    monkeypatch.setattr(mod, "team_output_mode", lambda db, team_id: "json_object")


def test_create_signal_uses_segment_quote(monkeypatch):
    from app.services.assistant.opportunity_nominator import OpportunityNominator

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
    nominator = OpportunityNominator(runtime=transport)

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


def test_stage_signal_with_unknown_reference_is_dropped(monkeypatch, stage_context):
    from app.services.assistant.opportunity_nominator import OpportunityNominator

    db, task, activity = stage_context
    transport = FakeTransport(
        {"candidates": [{"opportunity_ref": "A2", "advance": True, "quote": activity.source_content}]}
    )
    _patch(monkeypatch)

    result = asyncio.run(OpportunityNominator(runtime=transport).nominate(db, task, activity))

    assert result == []


def test_no_signal_returns_empty(monkeypatch):
    from app.services.assistant.opportunity_nominator import OpportunityNominator

    transport = FakeTransport({"candidates": []})
    _patch(monkeypatch)

    result = asyncio.run(OpportunityNominator(runtime=transport).nominate(FakeDB(), _task(), _activity()))

    assert result == []


@pytest.fixture
def stage_context():
    from app.core.database import Base
    from app.models.customer import Customer
    from app.models.customer_activity import CustomerActivity
    from app.models.opportunity import Opportunity
    from app.models.procurement import OpportunityStageSnapshot, ProcurementMethod, ProcurementStageTemplate

    task = _task()
    task.committed_json = [{"kind": "customer_activity", "public_id": "1"}]
    task.authority_json = {"customer_public_id": "cus_stage"}
    quote = "客户确认推进到方案"
    activity = CustomerActivity(
        id=1, team_id=7, customer_id=11, activity_kind="FOLLOW_UP", source_content=quote,
        content_json="{}", creator_id="3", owner_id="3",
    )
    customer = Customer(id=11, team_id=7, public_id="cus_stage", account_name="北方科技", city="北京", creator_id="3")
    opportunity = Opportunity(
        id=21,
        team_id=7,
        customer_id=11,
        public_id="opp_stage",
        opportunity_name="报销项目",
        opportunity_number="ST-1",
        procurement_method_id=31,
        current_stage_snapshot_id=41,
        total_amount=1000,
        user_count=1,
        unit_price=1000,
        license_type="PERPETUAL",
        purchase_type="NEW",
        expected_closing_date=date(2026, 12, 31),
        owner_id="3",
        creator_id="3",
        approval_phase="approved",
        version=4,
    )
    snapshot = OpportunityStageSnapshot(
        id=41, team_id=7, opportunity_id=21, procurement_stage_template_id=51, stage_name="接触",
        win_probability=10, template_sort_order=10, template_code="contact", snapshot_version=1,
    )
    stages = [
        ProcurementStageTemplate(
            id=stage_id, team_id=team_id, procurement_method_id=31, template_code=f"s{stage_id}",
            stage_name=name, sort_order=order, win_probability=10, created_by="3",
        )
        for stage_id, team_id, name, order in (
            (51, 7, "接触", 10), (52, 7, "方案", 30), (53, 7, "签约", 40), (54, 8, "其他团队阶段", 20),
        )
    ]
    engine = create_engine("sqlite:///:memory:")

    @event.listens_for(engine, "before_cursor_execute", retval=True)
    def skip_sqlite_indexes(conn, cursor, statement, parameters, context, executemany):
        # MySQL permits reused index names across tables; SQLite does not.
        if statement.startswith("CREATE INDEX"):
            return "SELECT 1", ()
        return statement, parameters

    try:
        Base.metadata.create_all(
            engine,
            tables=[
                Customer.__table__, CustomerActivity.__table__, Opportunity.__table__, ProcurementMethod.__table__,
                ProcurementStageTemplate.__table__, OpportunityStageSnapshot.__table__,
            ],
        )
        with Session(engine) as db:
            method = ProcurementMethod(id=31, team_id=7, code="standard", name="标准", sort_order=1, created_by="3")
            db.add_all([activity, customer, opportunity, snapshot, method, *stages])
            db.commit()
            yield db, task, activity
    finally:
        engine.dispose()


def test_injected_model_ids_do_not_change_the_stage_command(monkeypatch, stage_context):
    from app.api import opportunities
    from app.services.assistant import proposals
    from app.services.assistant import crm_proposal_commands
    from app.services.assistant.opportunity_nominator import OpportunityNominator

    db, task, activity = stage_context
    _patch(monkeypatch)
    monkeypatch.setattr(crm_proposal_commands, "_permissions", lambda db, task: {"opportunity:edit:own"})
    transport = FakeTransport(
        {
            "candidates": [
                {
                    "opportunity_ref": "A1",
                    "advance": True,
                    "quote": activity.source_content,
                    "stage_template_id": 53,
                    "target_public_id": "opp_unrelated",
                }
            ]
        }
    )

    (candidate,) = asyncio.run(OpportunityNominator(runtime=transport).nominate(db, task, activity))
    assert json.loads(transport.calls[0]["user"])["active_opportunities"] == [
        {"opportunity_ref": "A1", "name": "报销项目", "current_stage_name": "接触", "next_stage_name": "方案"}
    ]
    assert candidate["payload"] == {}
    bound = crm_proposal_commands.validate_candidate(db, task, candidate)
    assert bound is not None
    assert bound["target_public_id"] == "opp_stage"
    assert bound["payload"] == {
        "stage_template_id": 52,
        "stage_name": "方案",
        "current_stage_name": "接触",
        "opportunity_name": "报销项目",
    }
    assert (bound["prior_stage_snapshot_id"], bound["prior_version"]) == (41, 4)

    class ReachedCRMWrite(Exception):
        pass

    async def inspect_move(*, opportunity_id, stage_move, **kwargs):
        assert opportunity_id == "opp_stage"
        assert stage_move.stage_template_id == 52
        raise ReachedCRMWrite

    monkeypatch.setattr(opportunities, "move_opportunity_stage", inspect_move)
    monkeypatch.setattr(crm_proposal_commands, "_user", lambda db, task: SimpleNamespace(id=3))
    frozen = {**bound, "key": proposals._candidate_key(bound)}
    with pytest.raises(ReachedCRMWrite):
        asyncio.run(crm_proposal_commands.RealCRMProposalExecutor().execute(db, task, frozen))

    frozen["payload"] = {**frozen["payload"], "stage_template_id": 53}
    assert crm_proposal_commands.validate_candidate(db, task, frozen) is None
    with pytest.raises(ValueError):
        asyncio.run(crm_proposal_commands.RealCRMProposalExecutor().execute(db, task, frozen))
