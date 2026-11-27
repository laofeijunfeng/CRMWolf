"""Unit tests for CRM-180 historical customer-activity Markdown backfill."""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timedelta
from types import SimpleNamespace
from typing import Any

import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker

from app.core.database import Base
from app.crud.customer_activity import (
    ACTIVITY_MARKDOWN_FORMAT_VERSION,
    customer_activity_crud,
    has_markdown_format_version,
)
from app.models.customer import Customer
from app.models.customer_activity import CustomerActivity
from app.models.customer_activity_post_commit_job import CustomerActivityPostCommitJob
from app.models.lead import LeadFollowUp
from app.services.customer_activity_contracts import (
    CustomerActivityProcessingStatus,
    CustomerActivitySubmissionSource,
)
from app.services.customer_activity_markdown_backfill_service import (
    CustomerActivityMarkdownBackfillService,
)

def _make_session_factory(tmp_path):
    db_path = tmp_path / "crm180_backfill.sqlite3"
    engine = create_engine(f"sqlite:///{db_path}", connect_args={"check_same_thread": False})

    @event.listens_for(engine, "before_cursor_execute", retval=True)
    def _skip_sqlite_indexes(conn, cursor, statement, parameters, context, executemany):
        if statement.startswith("CREATE INDEX"):
            return "SELECT 1", ()
        return statement, parameters

    Base.metadata.create_all(
        bind=engine,
        tables=[
            Customer.__table__,
            CustomerActivity.__table__,
            CustomerActivityPostCommitJob.__table__,
            LeadFollowUp.__table__,
        ],
    )
    return sessionmaker(autocommit=False, autoflush=False, expire_on_commit=False, bind=engine)


def _seed_customer(db, *, team_id: int = 1, account_name: str = "测试客户") -> Customer:
    customer = Customer(
        team_id=team_id,
        account_name=account_name,
        city="上海",
        owner_id="user_owner",
        creator_id="user_creator",
    )
    db.add(customer)
    db.commit()
    db.refresh(customer)
    return customer


def _seed_activity(
    db,
    *,
    customer_id: int,
    team_id: int = 1,
    submission_source: str = CustomerActivitySubmissionSource.FORM.value,
    processing_status: str = CustomerActivityProcessingStatus.COMPLETED.value,
    activity_kind: str = "PHONE_FOLLOW_UP",
    source_content: str = "与王总沟通了项目进度，客户希望下周看演示。",
    summary: str = "与王总沟通了项目进度，客户希望下周看演示。",
    content_json: dict[str, Any] | None = None,
    occurred_at: datetime | None = None,
    next_action: str | None = "下周三安排产品演示",
    next_action_source: str | None = "USER",
    next_follow_time: datetime | None = None,
    next_follow_time_source: str | None = "USER",
    original_lead_id: int | None = None,
    effectiveness_score: int | None = 86,
) -> CustomerActivity:
    is_assistant2 = submission_source == CustomerActivitySubmissionSource.ASSISTANT_2.value
    payload = content_json if content_json is not None else {"content": source_content}
    row = CustomerActivity(
        customer_id=customer_id,
        team_id=team_id,
        creator_id="user_creator",
        owner_id="user_owner",
        activity_kind=activity_kind,
        title="电话跟进",
        source_content=source_content,
        content_json=json.dumps(payload, ensure_ascii=False),
        summary=summary,
        submission_source=submission_source,
        submission_id=f"sub_{uuid.uuid4().hex[:12]}" if is_assistant2 else None,
        submission_fingerprint=(uuid.uuid4().hex * 2) if is_assistant2 else None,
        occurred_at=occurred_at or datetime(2026, 10, 15, 10, 30, 0),
        next_action=next_action,
        next_action_source=next_action_source,
        next_follow_time=next_follow_time or datetime(2026, 10, 22, 14, 0, 0),
        next_follow_time_source=next_follow_time_source,
        original_lead_id=original_lead_id,
        processing_status=processing_status,
        effectiveness_status="COMPLETED" if effectiveness_score is not None else "PENDING",
        effectiveness_score=effectiveness_score,
        activity_revision=3,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


class _StubStructuringAgent:
    def __init__(self, *, fail_on_substring: str | None = None) -> None:
        self.fail_on_substring = fail_on_substring
        self.calls: list[dict[str, Any]] = []

    async def structure(self, db, *, team_id: int, context: dict[str, Any]) -> dict[str, Any]:
        self.calls.append({"team_id": team_id, "context": context})
        source = context["current_activity"]["source_content"]
        if self.fail_on_substring and self.fail_on_substring in source:
            raise RuntimeError("simulated llm timeout")
        markdown = f"### 沟通要点\n- {source}\n- **下一步**：持续跟进"
        return {
            "title": "AI生成新标题",
            "summary": markdown,
            "next_action": "AI编造的下一步不应覆盖历史值",
            "content_json": {
                "content": markdown,
                "customer_feedback": "希望下周看演示",
                "current_progress": "评估中",
                "risks": [],
                "next_action": "AI编造的下一步不应覆盖历史值",
                "next_follow_time_text": "下周五",
            },
        }


@pytest.fixture
def fake_ai_config(monkeypatch):
    from app.services import customer_activity_markdown_backfill_service as mod

    monkeypatch.setattr(mod.ai_config_crud, "get_config", lambda db, team_id: SimpleNamespace(team_id=team_id))
    monkeypatch.setattr(mod.ai_config_crud, "get_decrypted_api_key", lambda db, team_id: "sk-test-key")


@pytest.mark.asyncio
async def test_backfill_dry_run_selects_all_legacy_sources_and_writes_nothing(tmp_path, fake_ai_config):
    session_factory = _make_session_factory(tmp_path)
    db = session_factory()
    try:
        customer = _seed_customer(db)
        a_form = _seed_activity(db, customer_id=customer.id, submission_source="FORM")
        a_agent = _seed_activity(db, customer_id=customer.id, submission_source="AGENT")
        a_assistant = _seed_activity(
            db,
            customer_id=customer.id,
            submission_source="ASSISTANT_2",
            content_json={"content": "旧助手纯文本", "temporal_evidence": {"version": "temporal-evidence-v1"}},
        )
        a_cutover = _seed_activity(db, customer_id=customer.id, submission_source="CUTOVER_MIGRATION")
        # Already upgraded -> skipped
        _seed_activity(
            db,
            customer_id=customer.id,
            submission_source="FORM",
            content_json={"content": "### 已升级", "markdown_format_version": ACTIVITY_MARKDOWN_FORMAT_VERSION},
        )
        # In-flight PENDING -> skipped
        _seed_activity(
            db,
            customer_id=customer.id,
            submission_source="FORM",
            processing_status=CustomerActivityProcessingStatus.PENDING.value,
        )
        # Empty source_content -> skipped
        _seed_activity(db, customer_id=customer.id, source_content="   ")
    finally:
        db.close()

    agent = _StubStructuringAgent()
    service = CustomerActivityMarkdownBackfillService(structuring_agent=agent)
    result = await service.backfill_activities(session_factory=session_factory, dry_run=True)

    assert result.dry_run is True
    assert result.candidates == 3
    assert result.upgraded == 0
    assert result.skipped_already_upgraded == 1
    assert result.skipped_assistant_2 == 1
    assert result.skipped_empty == 1
    assert result.activity_ids == [a_form.id, a_agent.id, a_cutover.id]
    assert agent.calls == []

    opt_in = await service.backfill_activities(
        session_factory=session_factory,
        include_assistant_2=True,
        dry_run=True,
    )
    assert opt_in.candidates == 4
    assert opt_in.skipped_assistant_2 == 0
    assert opt_in.activity_ids == [a_form.id, a_agent.id, a_assistant.id, a_cutover.id]

@pytest.mark.asyncio
async def test_backfill_confirm_locks_historical_fields_is_idempotent_and_skips_post_commit(
    tmp_path,
    fake_ai_config,
    monkeypatch,
):
    from app.crud import customer_activity as crud_mod

    monkeypatch.setattr(crud_mod, "_upsert_customer_activity_evidence", lambda *args, **kwargs: None)

    session_factory = _make_session_factory(tmp_path)
    db = session_factory()
    try:
        customer = _seed_customer(db)
        lead_id = 99001
        lead_follow_up = LeadFollowUp(
            lead_id=lead_id,
            team_id=1,
            method="电话",
            content="线索纯文本跟进，禁止被客户活动升级脚本修改",
            creator_id="user_creator",
        )
        db.add(lead_follow_up)
        db.flush()

        original_occurred = datetime(2026, 9, 1, 9, 15, 0)
        original_follow_time = datetime(2026, 9, 10, 15, 0, 0)
        activity = _seed_activity(
            db,
            customer_id=customer.id,
            submission_source=CustomerActivitySubmissionSource.FORM.value,
            activity_kind="PHONE_FOLLOW_UP",
            source_content="客户认可方案，等待内部审批，下周三确认。",
            summary="旧纯文本摘要",
            content_json={
                "content": "旧纯文本摘要",
                "next_action": "原历史下一步行动",
                "next_follow_time_text": "2026-09-10",
                "temporal_evidence": {"version": "temporal-evidence-v1", "mentions": []},
                "action_evidence": [{"action_id": "a1", "state": "ACTIVE"}],
            },
            occurred_at=original_occurred,
            next_action="原历史下一步行动",
            next_action_source="USER",
            next_follow_time=original_follow_time,
            next_follow_time_source="USER",
            original_lead_id=lead_id,
            effectiveness_score=91,
        )
        activity_id = activity.id
        lead_follow_up_id = lead_follow_up.id
    finally:
        db.close()

    agent = _StubStructuringAgent()
    service = CustomerActivityMarkdownBackfillService(structuring_agent=agent)

    first = await service.backfill_activities(session_factory=session_factory, dry_run=False)
    assert first.upgraded == 1
    assert first.failed == 0
    assert first.activity_ids == [activity_id]
    assert len(agent.calls) == 1

    # Verify DB state: Markdown upgraded, historical facts & metadata preserved, zero post-commit jobs, lead untouched.
    db = session_factory()
    try:
        upgraded = db.query(CustomerActivity).filter(CustomerActivity.id == activity_id).one()
        parsed_json = json.loads(upgraded.content_json)
        assert has_markdown_format_version(parsed_json) is True
        assert parsed_json["markdown_format_version"] == ACTIVITY_MARKDOWN_FORMAT_VERSION
        assert "### 沟通要点" in upgraded.summary
        assert "### 沟通要点" in parsed_json["content"]

        # Immutable historical fields locked
        assert upgraded.occurred_at == original_occurred
        assert upgraded.creator_id == "user_creator"
        assert upgraded.owner_id == "user_owner"
        assert upgraded.activity_kind == "PHONE_FOLLOW_UP"
        assert upgraded.title == "电话跟进"
        assert upgraded.source_content == "客户认可方案，等待内部审批，下周三确认。"
        assert upgraded.next_action == "原历史下一步行动"
        assert upgraded.next_action_source == "USER"
        assert upgraded.next_follow_time == original_follow_time
        assert upgraded.next_follow_time_source == "USER"
        assert upgraded.original_lead_id == lead_id
        assert upgraded.effectiveness_score == 91
        assert upgraded.activity_revision == 3
        assert parsed_json["next_action"] == "原历史下一步行动"
        assert parsed_json["temporal_evidence"] == {"version": "temporal-evidence-v1", "mentions": []}
        assert parsed_json["action_evidence"] == [{"action_id": "a1", "state": "ACTIVE"}]

        # No post-commit jobs enqueued
        assert db.query(CustomerActivityPostCommitJob).count() == 0

        # LeadFollowUp completely untouched
        lfu = db.query(LeadFollowUp).filter(LeadFollowUp.id == lead_follow_up_id).one()
        assert lfu.content == "线索纯文本跟进，禁止被客户活动升级脚本修改"
    finally:
        db.close()

    # Second run must be a strict no-op (idempotent)
    second = await service.backfill_activities(session_factory=session_factory, dry_run=False)
    assert second.candidates == 0
    assert second.upgraded == 0
    assert second.skipped_already_upgraded == 1
    assert len(agent.calls) == 1


@pytest.mark.asyncio
async def test_backfill_preserves_source_content_and_summary_on_llm_failure(tmp_path, fake_ai_config, monkeypatch):
    from app.crud import customer_activity as crud_mod

    monkeypatch.setattr(crud_mod, "_upsert_customer_activity_evidence", lambda *args, **kwargs: None)

    session_factory = _make_session_factory(tmp_path)
    db = session_factory()
    try:
        customer = _seed_customer(db)
        ok_row = _seed_activity(db, customer_id=customer.id, source_content="正常记录内容", summary="正常摘要")
        fail_row = _seed_activity(
            db,
            customer_id=customer.id,
            source_content="TRIGGER_FAIL 原始历史文本",
            summary="原始历史摘要",
        )
        ok_id, fail_id = ok_row.id, fail_row.id
    finally:
        db.close()

    agent = _StubStructuringAgent(fail_on_substring="TRIGGER_FAIL")
    service = CustomerActivityMarkdownBackfillService(structuring_agent=agent)
    result = await service.backfill_activities(session_factory=session_factory, dry_run=False, concurrency=2)

    assert result.upgraded == 1
    assert result.failed == 1
    assert result.activity_ids == [ok_id]
    assert result.errors[0]["activity_id"] == fail_id

    db = session_factory()
    try:
        failed_row = db.query(CustomerActivity).filter(CustomerActivity.id == fail_id).one()
        assert failed_row.source_content == "TRIGGER_FAIL 原始历史文本"
        assert failed_row.summary == "原始历史摘要"
        assert has_markdown_format_version(failed_row.content_json) is False
    finally:
        db.close()


@pytest.mark.asyncio
async def test_backfill_respects_team_id_days_limit_and_missing_ai_config(tmp_path, monkeypatch):
    from app.services import customer_activity_markdown_backfill_service as mod

    monkeypatch.setattr(mod.ai_config_crud, "get_config", lambda db, team_id: None)
    monkeypatch.setattr(mod.ai_config_crud, "get_decrypted_api_key", lambda db, team_id: None)

    session_factory = _make_session_factory(tmp_path)
    db = session_factory()
    try:
        c1 = _seed_customer(db, team_id=1)
        c2 = _seed_customer(db, team_id=2)
        recent = _seed_activity(db, customer_id=c1.id, team_id=1, occurred_at=datetime.now() - timedelta(days=2))
        _seed_activity(db, customer_id=c1.id, team_id=1, occurred_at=datetime.now() - timedelta(days=120))
        _seed_activity(db, customer_id=c2.id, team_id=2, occurred_at=datetime.now() - timedelta(days=1))
        recent_id = recent.id
    finally:
        db.close()

    agent = _StubStructuringAgent()
    service = CustomerActivityMarkdownBackfillService(structuring_agent=agent)
    result = await service.backfill_activities(
        session_factory=session_factory,
        team_id=1,
        days=30,
        limit=10,
        dry_run=False,
    )

    assert result.candidates == 1
    assert result.upgraded == 0
    assert result.skipped_no_ai_config == 1
    assert result.failed == 0
    assert agent.calls == []
    assert recent_id > 0


@pytest.mark.asyncio
async def test_backfill_never_overwrites_non_empty_fields_with_empty_values(tmp_path, fake_ai_config, monkeypatch):
    from app.crud import customer_activity as crud_mod

    monkeypatch.setattr(crud_mod, "_upsert_customer_activity_evidence", lambda *args, **kwargs: None)

    class _PartialEmptyAgent:
        async def structure(self, db, *, team_id: int, context: dict[str, Any]) -> dict[str, Any]:
            return {
                "title": "微信跟进",
                "summary": "### 沟通进展\n- 客户确认预算 50 万\n- 下周安排安全评审",
                "next_action": "",
                "content_json": {
                    "content": "### 沟通进展\n- 客户确认预算 50 万\n- 下周安排安全评审",
                    "customer_feedback": "",
                    "current_progress": "",
                    "risks": [],
                    "next_action": "",
                    "next_follow_time_text": "",
                },
            }

    session_factory = _make_session_factory(tmp_path)
    db = session_factory()
    try:
        customer = _seed_customer(db)
        activity = _seed_activity(
            db,
            customer_id=customer.id,
            submission_source="FORM",
            source_content="客户确认预算 50 万，安全团队关注合规，下周安排安全评审",
            summary="旧摘要",
            content_json={
                "content": "旧正文",
                "customer_feedback": "客户确认预算 50 万",
                "current_progress": "安全评审准备中",
                "risks": ["安全团队关注公网回调合规"],
                "next_action": "下周安排安全评审",
            },
        )
        activity_id = activity.id
    finally:
        db.close()

    service = CustomerActivityMarkdownBackfillService(structuring_agent=_PartialEmptyAgent())
    result = await service.backfill_activities(session_factory=session_factory, dry_run=False)
    assert result.upgraded == 1
    assert result.failed == 0

    db = session_factory()
    try:
        upgraded = db.query(CustomerActivity).filter(CustomerActivity.id == activity_id).one()
        parsed = json.loads(upgraded.content_json)
        assert "### 沟通进展" in upgraded.summary
        assert "### 沟通进展" in parsed["content"]
        assert parsed["customer_feedback"] == "客户确认预算 50 万"
        assert parsed["current_progress"] == "安全评审准备中"
        assert parsed["risks"] == ["安全团队关注公网回调合规"]
        assert parsed["next_action"] == "下周安排安全评审"
        assert parsed["markdown_format_version"] == ACTIVITY_MARKDOWN_FORMAT_VERSION
    finally:
        db.close()


@pytest.mark.asyncio
async def test_backfill_rejects_empty_summary_or_empty_content_without_stamping(tmp_path, fake_ai_config, monkeypatch):
    from app.crud import customer_activity as crud_mod

    monkeypatch.setattr(crud_mod, "_upsert_customer_activity_evidence", lambda *args, **kwargs: None)

    class _DegradedAgent:
        async def structure(self, db, *, team_id: int, context: dict[str, Any]) -> dict[str, Any]:
            return {
                "title": None,
                "summary": "",
                "next_action": None,
                "content_json": {
                    "content": "",
                    "customer_feedback": "",
                    "current_progress": "",
                    "risks": [],
                },
            }

    session_factory = _make_session_factory(tmp_path)
    db = session_factory()
    try:
        customer = _seed_customer(db)
        activity = _seed_activity(
            db,
            customer_id=customer.id,
            submission_source="FORM",
            source_content="原完整历史记录，不能被清空",
            summary="原历史摘要",
            content_json={
                "content": "原完整历史正文",
                "customer_feedback": "原客户反馈",
                "current_progress": "原项目进展",
                "risks": ["原风险点"],
            },
        )
        activity_id = activity.id
    finally:
        db.close()

    service = CustomerActivityMarkdownBackfillService(structuring_agent=_DegradedAgent())
    result = await service.backfill_activities(session_factory=session_factory, dry_run=False)
    assert result.upgraded == 0
    assert result.failed == 1
    assert result.errors[0]["activity_id"] == activity_id

    db = session_factory()
    try:
        row = db.query(CustomerActivity).filter(CustomerActivity.id == activity_id).one()
        parsed = json.loads(row.content_json)
        assert row.summary == "原历史摘要"
        assert parsed["content"] == "原完整历史正文"
        assert parsed["customer_feedback"] == "原客户反馈"
        assert parsed["current_progress"] == "原项目进展"
        assert parsed["risks"] == ["原风险点"]
        assert has_markdown_format_version(parsed) is False
    finally:
        db.close()


@pytest.mark.asyncio
async def test_backfill_supports_targeted_activity_ids_and_force_rerun(tmp_path, fake_ai_config, monkeypatch):
    from app.crud import customer_activity as crud_mod

    monkeypatch.setattr(crud_mod, "_upsert_customer_activity_evidence", lambda *args, **kwargs: None)

    session_factory = _make_session_factory(tmp_path)
    db = session_factory()
    try:
        customer = _seed_customer(db)
        stamped_target = _seed_activity(
            db,
            customer_id=customer.id,
            submission_source="FORM",
            source_content="需要定向重跑的已打标记录",
            summary="误打标的截断摘要",
            content_json={
                "content": "",
                "markdown_format_version": ACTIVITY_MARKDOWN_FORMAT_VERSION,
            },
        )
        other_row = _seed_activity(
            db,
            customer_id=customer.id,
            submission_source="FORM",
            source_content="不在目标 ID 列表中的记录",
            summary="其他记录摘要",
        )
        target_id, other_id = stamped_target.id, other_row.id
    finally:
        db.close()

    agent = _StubStructuringAgent()
    service = CustomerActivityMarkdownBackfillService(structuring_agent=agent)

    # Without force, stamped target is skipped
    no_force = await service.backfill_activities(
        session_factory=session_factory,
        activity_ids=[target_id],
        force=False,
        dry_run=False,
    )
    assert no_force.candidates == 0
    assert no_force.skipped_already_upgraded == 1
    assert no_force.upgraded == 0

    # With force=True and activity_ids, only target_id is re-upgraded
    forced = await service.backfill_activities(
        session_factory=session_factory,
        activity_ids=[target_id],
        force=True,
        dry_run=False,
    )
    assert forced.candidates == 1
    assert forced.upgraded == 1
    assert forced.activity_ids == [target_id]

    db = session_factory()
    try:
        repaired = db.query(CustomerActivity).filter(CustomerActivity.id == target_id).one()
        untouched = db.query(CustomerActivity).filter(CustomerActivity.id == other_id).one()
        assert "### 沟通要点" in repaired.summary
        assert untouched.summary == "其他记录摘要"
        assert has_markdown_format_version(untouched.content_json) is False
    finally:
        db.close()
