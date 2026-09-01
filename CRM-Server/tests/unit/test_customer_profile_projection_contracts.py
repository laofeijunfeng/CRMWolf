import pytest
from fastapi import HTTPException
from sqlalchemy import BigInteger, create_engine, func
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.api.customer_profiles import _decode_cursor, _encode_cursor
from app.core.database import Base
from app.crud.customer_profile_projection import customer_profile_projection_crud
from app.models.customer import Customer
from app.models.customer_profile_projection import (
    CustomerProfileCurrent,
    CustomerProfileProjectionVersion,
    CustomerProfileStatus,
)
from app.schemas.customer_profile import CustomerProfileSections
from app.services.agent.customer_profile_projection_graph import CustomerProfileNarrativeDraft
from app.services.customer_profile_projection_quality import (
    CustomerProfileProjectionQualityLinter,
)
from app.services.customer_profile_projection_service import (
    PROFILE_WORKFLOW_OWNER,
    CustomerProfileProjectionDraft,
    CustomerProfileProjectionError,
    CustomerProfileProjectionService,
    _current_situation_summary,
    _demand_items,
    _diff_values,
    _follow_up_process,
    _important_change_items,
    _recorded_follow_ups,
)


@compiles(BigInteger, "sqlite")
def _bigint_to_sqlite_int(element, compiler, **kw):
    return "INTEGER"


@pytest.fixture
def profile_db():
    engine = create_engine(
        "sqlite:///:memory:",
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )
    Base.metadata.create_all(
        engine,
        tables=[
            Customer.__table__,
            CustomerProfileProjectionVersion.__table__,
            CustomerProfileCurrent.__table__,
        ],
    )
    session = sessionmaker(bind=engine)()
    session.add(
        Customer(
            id=1,
            public_id="cus_profile_test",
            team_id=1,
            account_name="客户档案测试客户",
            city="上海",
            creator_id="user_1",
        )
    )
    session.commit()
    yield session
    session.close()
    engine.dispose()


def _draft(*, summary: str = "当前已有明确的项目背景。", activity_watermark: int = 1):
    return CustomerProfileProjectionDraft(
        sections=CustomerProfileSections(
            current_situation={"summary": summary},
            current_journeys=[],
            important_changes=[],
            long_term_context={},
            follow_up_process=[],
            recorded_follow_ups=[],
        ),
        evidence_refs=[{"evidence_key": "activity:1", "source_type": "customer_activity"}],
        source_watermark={"activity_id": activity_watermark},
        fact_watermark=2,
        journey_watermark=3,
        task_watermark=4,
        commitment_watermark=5,
        source_event_key="customer_activity:1",
    )


def test_profile_diff_reports_nested_leaf_changes_and_new_values():
    changes = _diff_values(
        {"status": "进行中", "owner": {"name": "甲"}},
        {"status": "已完成", "owner": {"name": "乙"}, "stage": "验收"},
    )

    assert {item["path"] for item in changes} == {"owner.name", "stage", "status"}
    assert next(item for item in changes if item["path"] == "status") == {
        "path": "status",
        "before": "进行中",
        "after": "已完成",
    }


def test_profile_diff_treats_list_as_one_readable_section_change():
    assert _diff_values([{"id": 1}], [{"id": 1}, {"id": 2}], path="journeys") == [
        {"path": "journeys", "before": [{"id": 1}], "after": [{"id": 1}, {"id": 2}]}
    ]


def test_profile_cursor_is_bound_to_resource_and_customer():
    cursor = _encode_cursor(resource="changes", customer_public_id="cus_1", sort_key="12")

    assert _decode_cursor(cursor, resource="changes", customer_public_id="cus_1") == 12

    with pytest.raises(HTTPException) as exc_info:
        _decode_cursor(cursor, resource="changes", customer_public_id="cus_2")

    assert exc_info.value.status_code == 400
    assert exc_info.value.detail["code"] == "PROFILE_CURSOR_INVALID"


def test_profile_cursor_rejects_legacy_unscoped_cursor():
    with pytest.raises(HTTPException) as exc_info:
        _decode_cursor("djE6MTI", resource="profile_versions", customer_public_id="cus_1")

    assert exc_info.value.detail["code"] == "PROFILE_CURSOR_INVALID"


def test_narrative_draft_partial_publish_keeps_typed_sections(profile_db):
    service = CustomerProfileProjectionService()
    service.publish(profile_db, team_id=1, customer_id=1, draft=_draft())
    profile_db.commit()

    narrative = CustomerProfileNarrativeDraft(
        sections=CustomerProfileSections(
            current_situation={"summary": "第二版当前情况"},
            current_journeys=[],
            important_changes=[],
            long_term_context={},
            follow_up_process=[],
            recorded_follow_ups=[],
        ),
        evidence_refs=[{"evidence_key": "activity:1", "source_type": "customer_activity"}],
        source_watermark={"activity_id": 2},
        target_sections=("current_situation",),
    )

    draft = narrative.to_projection_draft()
    assert isinstance(draft.sections, CustomerProfileSections)
    publication = service.publish(profile_db, team_id=1, customer_id=1, draft=draft)

    assert publication.version.current_situation_json == {"summary": "第二版当前情况"}



def test_projection_service_ensure_current_is_idempotent_and_updates_run_state(profile_db):
    service = CustomerProfileProjectionService()

    current = service.ensure_current(profile_db, team_id=1, customer_id=1)
    profile_db.commit()

    assert current.profile_status == CustomerProfileStatus.NOT_READY
    assert current.latest_source_watermark_json == {}
    assert profile_db.query(CustomerProfileCurrent).count() == 1

    same_current = service.ensure_current(profile_db, team_id=1, customer_id=1)
    assert same_current.id == current.id
    assert profile_db.query(CustomerProfileCurrent).count() == 1

    updating_current = service.ensure_current(
        profile_db,
        team_id=1,
        customer_id=1,
        status=CustomerProfileStatus.UPDATING,
        active_run_id=42,
    )
    profile_db.commit()

    assert updating_current.id == current.id
    assert updating_current.profile_status == CustomerProfileStatus.UPDATING
    assert updating_current.active_run_id == 42


def test_projection_service_recovers_from_first_insert_unique_race(profile_db, monkeypatch):
    service = CustomerProfileProjectionService()
    original_get_current = customer_profile_projection_crud.get_current
    calls = 0

    def get_current_with_race(db, *, team_id, customer_id, for_update=False):
        nonlocal calls
        calls += 1
        if calls == 1:
            # Simulate another transaction winning between the initial
            # snapshot read and this transaction's INSERT.
            db.add(
                CustomerProfileCurrent(
                    team_id=team_id,
                    customer_id=customer_id,
                    profile_status=CustomerProfileStatus.NOT_READY,
                    latest_source_watermark_json={},
                )
            )
            db.flush()
            return None
        return original_get_current(db, team_id=team_id, customer_id=customer_id, for_update=for_update)

    monkeypatch.setattr(customer_profile_projection_crud, "get_current", get_current_with_race)

    current = service.ensure_current(
        profile_db,
        team_id=1,
        customer_id=1,
        status=CustomerProfileStatus.UPDATING,
        active_run_id=99,
    )
    profile_db.commit()

    assert calls == 2
    assert profile_db.query(CustomerProfileCurrent).count() == 1
    assert current.profile_status == CustomerProfileStatus.UPDATING
    assert current.active_run_id == 99


def test_projection_service_publishes_reads_and_deduplicates_on_sqlite(profile_db):
    service = CustomerProfileProjectionService()
    draft = _draft()

    publication = service.publish(profile_db, team_id=1, customer_id=1, draft=draft)
    profile_db.commit()

    assert publication.deduplicated is False
    assert publication.changed_sections == ("current_situation",)
    assert publication.version.profile_version == 1
    assert publication.current.profile_status == CustomerProfileStatus.READY
    assert publication.current.latest_source_watermark_json == {"activity_id": 1}

    customer, current, version = service.get_current_by_public_id(
        profile_db, team_id=1, customer_public_id="cus_profile_test"
    )
    assert customer.id == 1
    assert current is not None
    assert version is not None
    assert version.id == publication.version.id
    assert version.current_situation_json == draft.sections.current_situation

    duplicate = service.publish(profile_db, team_id=1, customer_id=1, draft=draft)
    profile_db.commit()

    assert duplicate.deduplicated is True
    assert duplicate.changed_sections == ()
    assert duplicate.version.id == publication.version.id
    assert profile_db.query(CustomerProfileProjectionVersion).count() == 1
    assert profile_db.query(func.count(CustomerProfileCurrent.id)).scalar() == 1

    changed = service.publish(
        profile_db,
        team_id=1,
        customer_id=1,
        draft=_draft(summary="项目背景已补充新的事实。", activity_watermark=2),
    )
    profile_db.commit()

    assert changed.deduplicated is False
    assert changed.changed_sections == ("current_situation",)
    assert changed.version.profile_version == 2
    assert changed.current.current_profile_version_id == changed.version.id
    assert profile_db.query(CustomerProfileProjectionVersion).count() == 2


def test_projection_publish_rejects_stale_expected_version_and_watermark(profile_db):
    service = CustomerProfileProjectionService()
    first = service.publish(profile_db, team_id=1, customer_id=1, draft=_draft(activity_watermark=5))
    profile_db.commit()

    with pytest.raises(Exception) as cas_error:
        service.publish(
            profile_db,
            team_id=1,
            customer_id=1,
            draft=_draft(summary="并发写入", activity_watermark=6),
            expected_current_version=0,
        )
    assert getattr(cas_error.value, "code", None) == "PROFILE_PUBLISH_REJECTED_STALE"

    with pytest.raises(Exception) as watermark_error:
        service.publish(
            profile_db,
            team_id=1,
            customer_id=1,
            draft=_draft(summary="落后水位", activity_watermark=4),
        )
    assert getattr(watermark_error.value, "code", None) == "PROFILE_PUBLISH_REJECTED_STALE"
    assert first.version.profile_version == 1


def test_projection_publish_keeps_immutable_history_and_current_pointer_at_latest(profile_db):
    service = CustomerProfileProjectionService()
    first = service.publish(profile_db, team_id=1, customer_id=1, draft=_draft(summary="第一版", activity_watermark=1))
    profile_db.commit()
    first_summary = first.version.current_situation_json["summary"]

    second = service.publish(profile_db, team_id=1, customer_id=1, draft=_draft(summary="第二版", activity_watermark=2))
    profile_db.commit()

    stored_first = profile_db.query(CustomerProfileProjectionVersion).filter_by(id=first.version.id).one()
    current = profile_db.query(CustomerProfileCurrent).filter_by(team_id=1, customer_id=1).one()
    assert stored_first.current_situation_json["summary"] == first_summary
    assert stored_first.publication_status == "SUPERSEDED"
    assert second.version.profile_version == 2
    assert current.current_profile_version_id == second.version.id
    assert current.last_successful_version == 2

    # Replaying an older version cannot move the current pointer backwards.
    with pytest.raises(Exception) as stale_error:
        service.publish(
            profile_db,
            team_id=1,
            customer_id=1,
            draft=_draft(summary="第一版", activity_watermark=1),
        )
    assert getattr(stale_error.value, "code", None) == "PROFILE_PUBLISH_REJECTED_STALE"
    current = profile_db.query(CustomerProfileCurrent).filter_by(team_id=1, customer_id=1).one()
    assert current.current_profile_version_id == second.version.id
    assert current.last_successful_version == 2


def test_partial_projection_preserves_unaffected_sections(profile_db):
    service = CustomerProfileProjectionService()
    first = CustomerProfileProjectionDraft(
        sections=CustomerProfileSections(
            current_situation={"summary": "第一版当前情况"},
            current_journeys=[{"id": "journey-1", "status": "ACTIVE"}],
            important_changes=[{"summary": "第一版变化"}],
            long_term_context={"overview": "长期背景"},
            follow_up_process=[{"summary": "第一版跟进过程"}],
            recorded_follow_ups=[{"summary": "第一版后续事项"}],
        ),
        evidence_refs=[{"evidence_key": "activity:1", "source_type": "customer_activity"}],
        source_watermark={"activity_id": 1},
        target_sections=("current_situation",),
    )
    service.publish(profile_db, team_id=1, customer_id=1, draft=first)
    profile_db.commit()

    partial = CustomerProfileProjectionDraft(
        sections=CustomerProfileSections(
            current_situation={"summary": "第二版当前情况"},
            current_journeys=[{"id": "journey-2", "status": "ACTIVE"}],
            important_changes=[{"summary": "第二版变化"}],
            long_term_context={"overview": "不应覆盖"},
            follow_up_process=[{"summary": "不应覆盖"}],
            recorded_follow_ups=[{"summary": "不应覆盖"}],
        ),
        evidence_refs=[{"evidence_key": "activity:2", "source_type": "customer_activity"}],
        source_watermark={"activity_id": 2},
        target_sections=("current_situation",),
    )
    publication = service.publish(profile_db, team_id=1, customer_id=1, draft=partial)
    profile_db.commit()

    assert publication.version.current_situation_json == {"summary": "第二版当前情况"}
    assert publication.version.current_journeys_json == [{"id": "journey-1", "status": "ACTIVE"}]
    assert publication.version.long_term_context_json == {"overview": "长期背景"}
    assert publication.version.follow_up_process_json == [{"summary": "第一版跟进过程"}]
    assert {item["evidence_key"] for item in publication.version.evidence_refs_json} == {
        "activity:1",
        "activity:2",
    }


def test_projection_omits_system_boundary_disclaimer_from_customer_profile():
    service = CustomerProfileProjectionService()
    draft = service.draft_from_context(
        context={
            "strong_context": {
                "customer": {"account_name": "档案边界测试客户", "city": "上海"},
                "customer_facts": [],
                "contacts": [],
                "opportunities": [],
                "contracts": [],
                "payment_plans": [],
                "payment_records": [],
                "recent_activities": [],
                "deal_journeys": [],
                "deal_journey_events": [],
                "recorded_follow_ups": [],
                "sales_commitments": [],
                "follow_up_task_events": [],
            },
            "source_watermark": {},
        },
        source_event_key="profile-boundary-test",
        source_watermark={},
    )

    service.validate_draft(draft)

    assert "note" not in draft.sections.current_situation["business_status"]



def _activity(activity_id: int, content: str, *, occurred_at: str, next_action: str | None = None):
    return {
        "id": activity_id,
        "content": content,
        "source_content": content,
        "occurred_at": occurred_at,
        "next_action": next_action,
        "deal_journey_id": 11,
    }


def test_profile_current_situation_summary_does_not_duplicate_terminal_punctuation():
    summary = _current_situation_summary(
        customer={"account_name": "测试客户"},
        active_journeys=[],
        opportunities=[],
        contracts=[],
        latest_activity={"content": "项目正在走立项流程。。"},
        process=[],
    )

    assert summary == "测试客户:最近记录：项目正在走立项流程。"


def test_profile_current_situation_summary_uses_latest_phase_not_topic_order():
    summary = _current_situation_summary(
        customer={"account_name": "测试客户"},
        active_journeys=[],
        opportunities=[],
        contracts=[],
        latest_activity={"content": "项目正在走立项流程。"},
        process=[
            {"title": "立项与审批推进", "ended_at": "2026-08-27T10:00:00"},
            {"title": "POC 试用验证", "ended_at": "2026-08-26T10:00:00"},
        ],
    )

    assert "当前跟进集中在立项与审批推进" in summary


def test_profile_important_changes_are_newest_first():
    changes = _important_change_items([
        _activity(1, "项目暂无进展。", occurred_at="2026-07-24T10:00:00"),
        _activity(2, "项目正在走立项流程。", occurred_at="2026-08-27T10:00:00"),
    ])

    assert [item["title"] for item in changes] == ["立项与审批推进", "项目推进受阻"]


def test_profile_important_changes_ignore_non_material_activity_and_same_task_status():
    changes = _important_change_items(
        [
            _activity(1, "测试测试", occurred_at="2026-08-29T10:00:00"),
            _activity(2, "普通沟通记录", occurred_at="2026-08-28T10:00:00"),
        ],
        tasks=[{"id": 10, "task_id": 10, "title": "确认预算", "deal_journey_id": 11}],
        task_events=[
            {
                "id": 20,
                "task_id": 10,
                "event_type": "UPDATED",
                "previous_status": "OPEN",
                "new_status": "OPEN",
                "created_time": "2026-08-29T11:00:00",
            },
            {
                "id": 21,
                "task_id": 10,
                "event_type": "CREATED",
                "previous_status": None,
                "new_status": "OPEN",
                "created_time": "2026-08-29T09:00:00",
            },
        ],
    )

    assert changes == []


def test_profile_demand_items_integrate_structured_facts_without_fact_dump():
    items = _demand_items(
        [
            _activity(
                1,
                "团队已使用产品，账号已经用满，近期计划增购10个账号。",
                occurred_at="2026-08-29T10:00:00",
            )
        ],
        facts=[
            {
                "id": 101,
                "fact_type": "need",
                "subject": "数据报表导出",
                "content": "客户要求数据报表支持按部门导出。",
                "occurred_at": "2026-08-29T11:00:00",
            },
            {
                "id": 102,
                "fact_type": "budget",
                "subject": "大范围采购预算",
                "content": "客户侧曾提出约采购100人、总预算约30万元，并可能采用公开招标。",
                "occurred_at": "2026-08-29T12:00:00",
            },
            {
                "id": 103,
                "fact_type": "next_step",
                "subject": "内部试用与CTO汇报",
                "content": "客户需要内部选取1-2个项目试用，并向上级CTO汇报项目情况。",
                "occurred_at": "2026-08-29T13:00:00",
            },
        ],
    )

    topics = {item["topic"] for item in items}
    assert {"usage_expansion", "reporting", "procurement", "internal_validation"} <= topics
    reporting = next(item for item in items if item["topic"] == "reporting")
    assert "按部门导出" in reporting["statement"]
    assert reporting["evidence_refs"] == ["fact:101"]
    assert all("客户事实" not in item["statement"] for item in items)


def test_profile_current_situation_summary_prefers_business_state_over_process_label():
    summary = _current_situation_summary(
        customer={"account_name": "广州睿狐科技有限公司"},
        active_journeys=[
            {"name": "10人增购", "status": "ACTIVE", "current_stage": "需求确认"},
            {"name": "50人续费", "status": "ACTIVE", "current_stage": "需求确认"},
        ],
        opportunities=[
            {"status": 0, "stage": "需求确认"},
            {"status": 0, "stage": "需求确认"},
        ],
        contracts=[],
        latest_activity={"content": "普通沟通记录"},
        process=[{"title": "其他跟进过程", "ended_at": "2026-08-29T10:00:00"}],
        demand_items=[
            {
                "topic": "usage_expansion",
                "statement": "客户团队已在使用产品且账号已用满，正在推进授权增购。",
            },
            {
                "topic": "reporting",
                "statement": "客户要求数据报表支持按部门导出。",
            },
        ],
    )

    assert "实际使用后的扩容评估阶段" in summary
    assert "2条并行业务旅程" in summary
    assert "需求确认" in summary
    assert "当前推进重点是" in summary
    assert "其他跟进过程" not in summary
    assert "客户团队已在使用产品且账号已用满，正在推进授权增购" not in summary


def test_profile_demand_items_merge_near_duplicates_and_keep_all_evidence():
    activities = [
        _activity(
            1,
            "客户重新评估 Apifox 私有化部署方案，需要私有环境安装包和试用方案开展 POC 部署试用。",
            occurred_at="2026-08-25T10:00:00",
        ),
        _activity(
            2,
            "客户重新评估私有化部署 Apifox 方案，需提供私有环境安装包和试用方案开展 POC 部署试用。",
            occurred_at="2026-08-25T11:00:00",
        ),
        _activity(
            3,
            "POC 环境已部署完成，接下来将开展正式试用。",
            occurred_at="2026-08-25T12:00:00",
        ),
        _activity(
            4,
            "POC 正常进行，暂无问题。",
            occurred_at="2026-08-26T12:00:00",
        ),
    ]

    items = _demand_items(activities)

    assert [item["topic"] for item in items] == ["private_solution", "poc"]
    assert items[0]["activity_count"] == 2
    assert items[0]["evidence_refs"] == ["activity:1", "activity:2"]
    assert "私有化部署" in items[0]["statement"]
    assert "正式试用" in items[1]["statement"]
    assert items[1]["evidence_refs"] == ["activity:3", "activity:4"]


def test_profile_follow_up_process_is_phase_summary_not_one_row_per_activity():
    activities = [
        _activity(
            1,
            "项目暂无进展，领导出差，需等待返回。",
            occurred_at="2026-07-24T10:00:00",
            next_action="月底继续联系",
        ),
        _activity(
            2,
            "项目正在走立项流程。",
            occurred_at="2026-08-25T10:00:00",
            next_action="继续跟进立项流程",
        ),
        _activity(
            3,
            "已提交立项材料，正在内部审批。",
            occurred_at="2026-08-25T11:00:00",
            next_action="确认审批结果",
        ),
        _activity(
            4,
            "POC 环境已部署完成，进入正式试用。",
            occurred_at="2026-08-25T12:00:00",
            next_action="三天后跟进正式试用情况",
        ),
        _activity(5, "项目正在走立项流程。", occurred_at="2026-08-26T10:00:00", next_action="继续跟进立项流程"),
        _activity(6, "POC 正常进行，暂无问题。", occurred_at="2026-08-26T12:00:00", next_action="询问 POC 情况如何"),
    ]

    process = _follow_up_process(activities)

    assert [item["topic"] for item in process] == ["project_blocked", "approval", "poc"]
    approval = next(item for item in process if item["topic"] == "approval")
    assert approval["activity_count"] == 3
    assert approval["evidence_refs"] == ["activity:2", "activity:3", "activity:5"]
    assert "立项材料已提交" in approval["business_change"]
    assert "继续跟进立项流程" in approval["sales_follow_up"]
    assert len(process) < len(activities)


def test_profile_follow_ups_merge_semantically_same_open_tasks_without_meta_explanation():
    tasks = [
        {
            "kind": "task",
            "id": 10,
            "task_id": 10,
            "title": "继续跟进立项流程",
            "content": "跟进项目立项进度",
            "status": "OPEN",
            "due_at": "2026-08-29T10:00:00",
            "updated_time": "2026-08-27T10:00:00",
            "deal_journey_id": 11,
        },
        {
            "kind": "task",
            "id": 11,
            "task_id": 11,
            "title": "继续确认审批结果",
            "content": "确认立项材料审批结果",
            "status": "OPEN",
            "due_at": "2026-08-30T10:00:00",
            "updated_time": "2026-08-28T10:00:00",
            "deal_journey_id": 11,
        },
    ]

    follow_ups = _recorded_follow_ups(tasks, [], [])

    assert len(follow_ups) == 1
    assert follow_ups[0]["activity_count"] == 2
    assert follow_ups[0]["recorded_titles"] == ["继续跟进立项流程", "继续确认审批结果"]
    assert follow_ups[0]["status"] == "待完成"
    assert "result_boundary" not in follow_ups[0]


def test_profile_important_changes_hide_bookkeeping_next_action():
    changes = _important_change_items(
        [
            _activity(
                1,
                "客户确认放款已搞定，当前跟进记录可以关闭。",
                occurred_at="2026-08-19T10:00:00",
                next_action="关闭跟进任务",
            )
        ]
    )

    assert len(changes) == 1
    assert changes[0]["next_action_recorded"] is None


def test_profile_follow_ups_keep_open_replacement_when_duplicate_was_completed():
    tasks = [
        {
            "kind": "task",
            "id": 18,
            "task_id": 18,
            "commitment_id": 18,
            "title": "下周三找余老师再确认放款方面的情况，争取在8月份完成回款",
            "status": "COMPLETED",
            "due_at": "2026-08-26T09:00:00",
            "updated_time": "2026-08-19T00:24:14",
        },
        {
            "kind": "task",
            "id": 19,
            "task_id": 19,
            "commitment_id": 19,
            "title": "下周三找余老师再确认下放款方面的情况",
            "status": "OPEN",
            "due_at": "2026-08-26T09:00:00",
            "updated_time": "2026-08-18T18:45:57",
        },
    ]
    commitments = [
        {
            "kind": "commitment",
            "id": 20,
            "title": "等待余老师这周再给答复",
            "status": "OPEN",
            "updated_time": "2026-08-19T00:04:26",
        }
    ]

    follow_ups = _recorded_follow_ups(tasks, commitments, [])

    assert len(follow_ups) == 1
    assert follow_ups[0]["status"] == "待完成"
    assert follow_ups[0]["raw_status"] == "OPEN"
    assert follow_ups[0]["title"] == "下周三找余老师再确认下放款方面的情况"
    assert follow_ups[0]["recorded_titles"] == [
        "下周三找余老师再确认放款方面的情况，争取在8月份完成回款",
        "下周三找余老师再确认下放款方面的情况",
        "等待余老师这周再给答复",
    ]


def test_profile_important_changes_include_journey_and_task_state_events():
    service = CustomerProfileProjectionService()
    draft = service.draft_from_context(
        context={
            "strong_context": {
                "customer": {"account_name": "事件闭环客户"},
                "customer_facts": [],
                "contacts": [],
                "opportunities": [],
                "contracts": [],
                "payment_plans": [],
                "payment_records": [],
                "recent_activities": [],
                "deal_journeys": [{"id": 11, "name": "采购旅程", "status": "ACTIVE"}],
                "deal_journey_events": [
                    {
                        "id": 21,
                        "deal_journey_id": 11,
                        "event_type": "STAGE_CHANGED",
                        "event_time": "2026-08-30T10:00:00",
                        "summary": "业务旅程进入技术验证阶段",
                    }
                ],
                "recorded_follow_ups": [
                    {
                        "id": 31,
                        "task_id": 31,
                        "kind": "task",
                        "deal_journey_id": 11,
                        "title": "确认技术验证结果",
                        "status": "COMPLETED",
                    }
                ],
                "sales_commitments": [
                    {
                        "id": 51,
                        "title": "提供技术验证资料",
                        "status": "OPEN",
                        "deal_journey_id": 11,
                    }
                ],
                "follow_up_task_events": [
                    {
                        "id": 41,
                        "task_id": 31,
                        "event_type": "COMPLETED",
                        "previous_status": "OPEN",
                        "new_status": "COMPLETED",
                        "created_time": "2026-08-30T11:00:00",
                    }
                ],
            },
            "source_watermark": {},
        },
        source_event_key="task:31:completed",
        source_watermark={"journey_event_id": 21, "task_event_id": 41},
    )

    changes = draft.sections.important_changes

    assert changes[0]["title"] == "跟进待办状态变化"
    assert "已完成" in changes[0]["change"]
    assert changes[0]["evidence_refs"] == ["task:31"]
    assert any(
        item["title"] == "业务旅程阶段变化"
        and item["evidence_refs"] == ["journey_event:21"]
        for item in changes
    )
    assert not any(item["title"] == "销售承诺状态" for item in changes)

    journey = draft.sections.current_journeys[0]
    task_timeline_event = next(item for item in journey["timeline"] if item["type"] == "follow_up_task_status")
    assert task_timeline_event["task_id"] == 31
    assert task_timeline_event["evidence_refs"] == ["task:31"]
    assert "已完成" in task_timeline_event["summary"]


def test_profile_quality_linter_distinguishes_customer_expression_from_sales_guidance():
    linter = CustomerProfileProjectionQualityLinter()
    report = linter.lint(
        {
            "current_situation": {
                "demand_background": {
                    "items": [
                        {
                            "statement": "客户建议先完成内部试用，再决定是否扩大采购。",
                            "statement_role": "customer_expression",
                        },
                        {"statement": "建议销售本周联系客户确认预算。"},
                    ]
                }
            }
        }
    )

    assert len(report.issues) == 1
    assert report.issues[0].code == "PROFILE_NARRATIVE_SALES_GUIDANCE_SUSPECTED"
    assert report.issues[0].path.endswith("items[1].statement")


def test_profile_contract_rejects_explicit_sales_guidance_role():
    service = CustomerProfileProjectionService()
    draft = _draft()
    draft = CustomerProfileProjectionDraft(
        sections=CustomerProfileSections(
            current_situation={"summary": "客户情况", "statement_role": "sales_guidance"},
            current_journeys=[],
            important_changes=[],
            long_term_context={},
            follow_up_process=[],
            recorded_follow_ups=[],
        ),
        evidence_refs=draft.evidence_refs,
        source_watermark=draft.source_watermark,
    )

    with pytest.raises(CustomerProfileProjectionError, match="销售指导角色"):
        service.validate_draft(draft)


def test_profile_quality_warning_does_not_block_publication(profile_db):
    service = CustomerProfileProjectionService()
    draft = CustomerProfileProjectionDraft(
        sections=CustomerProfileSections(
            current_situation={"summary": "建议销售本周联系客户确认预算。"},
            current_journeys=[],
            important_changes=[],
            long_term_context={},
            follow_up_process=[],
            recorded_follow_ups=[],
        ),
        evidence_refs=[{"evidence_key": "activity:1", "source_type": "customer_activity"}],
        source_watermark={"activity_id": 1},
    )

    publication = service.publish(profile_db, team_id=1, customer_id=1, draft=draft)

    assert publication.version.publication_status == "PUBLISHED_WITH_WARNINGS"
    assert publication.version.quality_report_json["issues"][0]["code"] == (
        "PROFILE_NARRATIVE_SALES_GUIDANCE_SUSPECTED"
    )


def test_durable_profile_publish_requires_dedicated_workflow_owner(profile_db):
    service = CustomerProfileProjectionService()

    with pytest.raises(CustomerProfileProjectionError) as exc_info:
        service.publish(
            profile_db,
            team_id=1,
            customer_id=1,
            draft=_draft(),
            run_id=42,
        )

    assert exc_info.value.code == "PROFILE_PUBLISH_OWNER_FORBIDDEN"


def test_dedicated_workflow_owner_can_publish_durable_profile(profile_db):
    service = CustomerProfileProjectionService()

    publication = service.publish(
        profile_db,
        team_id=1,
        customer_id=1,
        draft=_draft(),
        run_id=42,
        publication_owner=PROFILE_WORKFLOW_OWNER,
    )

    assert publication.version.profile_version == 1
    assert publication.version.run_id == 42


def test_customer_expression_advice_wording_is_publishable(profile_db):
    service = CustomerProfileProjectionService()
    draft = CustomerProfileProjectionDraft(
        sections=CustomerProfileSections(
            current_situation={"summary": "客户建议先完成内部试用。"},
            current_journeys=[],
            important_changes=[],
            long_term_context={},
            follow_up_process=[],
            recorded_follow_ups=[],
        ),
        evidence_refs=[{"evidence_key": "activity:1", "source_type": "customer_activity"}],
        source_watermark={"activity_id": 2},
    )

    publication = service.publish(profile_db, team_id=1, customer_id=1, draft=draft)

    assert publication.version.publication_status == "PUBLISHED"
    assert publication.version.quality_report_json == {"issues": []}
