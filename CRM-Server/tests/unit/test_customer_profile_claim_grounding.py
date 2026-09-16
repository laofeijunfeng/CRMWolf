import pytest
from sqlalchemy import BigInteger, create_engine
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import sessionmaker
from sqlalchemy.orm.attributes import flag_modified
from sqlalchemy.pool import StaticPool

from app.core.database import Base
from app.models.customer import Customer
from app.models.customer_profile_projection import (
    CustomerProfileCurrent,
    CustomerProfileProjectionVersion,
)
from app.schemas.customer_profile import CustomerProfileSections
from app.services.customer_profile_claim_grounding import (
    PROFILE_CLAIM_UNGROUNDED,
    assert_claims_grounded,
)
from app.services.customer_profile_projection_service import (
    CustomerProfileProjectionDraft,
    CustomerProfileProjectionError,
    CustomerProfileProjectionService,
)
from app.services.customer_profile_projection_validator import (
    CustomerProfileProjectionValidationError,
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

OLD = "客户正在重新评估 Apifox 私有化部署方案，需要私有环境安装包和试用方案。"
QUOTE = "今天看到了 Hifox，需要私有化部署。"
BOUND_STATEMENT = "客户正在评估 Apifox 私有化部署。"


def test_assert_claims_grounded_rejects_apifox_template():
    sections = CustomerProfileSections(
        current_situation={
            "summary": OLD,
            "demand_background": {
                "summary": OLD,
                "items": [{
                    "statement": OLD,
                    "evidence_refs": ["activity:1"],
                    "product_names": [],
                }],
            },
        },
        current_journeys=[],
        important_changes=[],
        long_term_context={},
        follow_up_process=[],
        recorded_follow_ups=[],
    )
    with pytest.raises(CustomerProfileProjectionValidationError) as exc:
        assert_claims_grounded(
            sections,
            evidence_refs=[{"evidence_key": "activity:1", "snippet": QUOTE}],
            product_catalog_names=["Hifox", "Apifox"],
        )
    assert exc.value.code == PROFILE_CLAIM_UNGROUNDED


def test_validate_draft_rejects_ungrounded_demand_statement():
    service = CustomerProfileProjectionService()
    draft = CustomerProfileProjectionDraft(
        sections=CustomerProfileSections(
            current_situation={
                "demand_background": {
                    "summary": OLD,
                    "items": [{"statement": OLD, "evidence_refs": ["activity:1"]}],
                }
            },
            current_journeys=[],
            important_changes=[],
            long_term_context={},
            follow_up_process=[],
            recorded_follow_ups=[],
        ),
        evidence_refs=[{"evidence_key": "activity:1", "source_type": "customer_activity", "snippet": QUOTE}],
        source_watermark={"product_catalog_names": ["Hifox", "Apifox"]},
    )
    with pytest.raises(CustomerProfileProjectionError) as exc:
        service.validate_draft(draft)
    assert exc.value.code == PROFILE_CLAIM_UNGROUNDED


def test_xiexin_draft_passes_grounding():
    service = CustomerProfileProjectionService()
    text = (
        "联系人研发 + 产品团队大概是 15 人左右，因为团队刚刚也是在推动 AI Coding 的事项，"
        "在找相关的平台，今天是刚刚好看到了 Hifox，感觉比较感兴趣，另外公司层面如果使用，"
        "会需要私有化部署，所以过来了解相关的部署情况；先给客户同步产品介绍材料，"
        "客户这周会花时间深度体验，先配合客户沟通产品体验方面的问题，后续争取做产品交流。"
    )
    draft = service.draft_from_context(
        context={
            "product_catalog": [
                {"public_id": "prd_hifox", "name": "Hifox", "is_active": True},
                {"public_id": "prd_apifox", "name": "Apifox", "is_active": True},
            ],
            "strong_context": {
                "customer": {"account_name": "成都协鑫数智科技有限责任公司", "products": []},
                "customer_facts": [],
                "contacts": [],
                "opportunities": [],
                "contracts": [],
                "payment_plans": [],
                "payment_records": [],
                "recent_activities": [{
                    "id": 1,
                    "content": text,
                    "source_content": text,
                    "occurred_at": "2026-09-16T10:00:00",
                    "title": "电话跟进",
                }],
                "deal_journeys": [],
                "deal_journey_events": [],
                "recorded_follow_ups": [],
                "sales_commitments": [],
                "follow_up_task_events": [],
            },
        },
        source_event_key="repro",
    )
    service.validate_draft(draft)
    item = draft.sections.current_situation["demand_background"]["items"][0]
    assert "Hifox" in item["statement"]
    assert "Apifox" not in item["statement"]
    assert draft.evidence_refs[0]["snippet"]


def _apifox_claim_sections(*, product_names, product_public_ids=None):
    item = {
        "statement": BOUND_STATEMENT,
        "evidence_refs": ["activity:1"],
        "product_names": product_names,
    }
    if product_public_ids is not None:
        item["product_public_ids"] = product_public_ids
    return CustomerProfileSections(
        current_situation={
            "summary": BOUND_STATEMENT,
            "demand_background": {
                "summary": BOUND_STATEMENT,
                "items": [item],
            },
        },
        current_journeys=[],
        important_changes=[],
        long_term_context={},
        follow_up_process=[],
        recorded_follow_ups=[],
    )


def test_assert_claims_grounded_rejects_unbound_product_names():
    sections = _apifox_claim_sections(product_names=["Apifox"])
    with pytest.raises(CustomerProfileProjectionValidationError) as exc:
        assert_claims_grounded(
            sections,
            evidence_refs=[{"evidence_key": "activity:1", "snippet": QUOTE}],
            product_catalog_names=["Hifox", "Apifox"],
        )
    assert exc.value.code == PROFILE_CLAIM_UNGROUNDED


def test_assert_claims_grounded_allows_bound_product_names():
    sections = _apifox_claim_sections(
        product_names=["Apifox"],
        product_public_ids=["prd_apifox"],
    )
    assert_claims_grounded(
        sections,
        evidence_refs=[{"evidence_key": "activity:1", "snippet": QUOTE}],
        product_catalog_names=["Hifox", "Apifox"],
    )


def test_semantic_evidence_activity_key_collision_keeps_activity_snippet():
    service = CustomerProfileProjectionService()
    text = (
        "联系人研发 + 产品团队大概是 15 人左右，因为团队刚刚也是在推动 AI Coding 的事项，"
        "在找相关的平台，今天是刚刚好看到了 Hifox，感觉比较感兴趣，另外公司层面如果使用，"
        "会需要私有化部署，所以过来了解相关的部署情况；先给客户同步产品介绍材料，"
        "客户这周会花时间深度体验，先配合客户沟通产品体验方面的问题，后续争取做产品交流。"
    )
    draft = service.draft_from_context(
        context={
            "product_catalog": [
                {"public_id": "prd_hifox", "name": "Hifox", "is_active": True},
                {"public_id": "prd_apifox", "name": "Apifox", "is_active": True},
            ],
            "semantic_evidence": [
                {
                    "evidence_key": "activity:1",
                    "source_type": "semantic_evidence",
                    "source_id": "1",
                    "title": "语义召回",
                }
            ],
            "strong_context": {
                "customer": {"account_name": "成都协鑫数智科技有限责任公司", "products": []},
                "customer_facts": [],
                "contacts": [],
                "opportunities": [],
                "contracts": [],
                "payment_plans": [],
                "payment_records": [],
                "recent_activities": [{
                    "id": 1,
                    "content": text,
                    "source_content": text,
                    "occurred_at": "2026-09-16T10:00:00",
                    "title": "电话跟进",
                }],
                "deal_journeys": [],
                "deal_journey_events": [],
                "recorded_follow_ups": [],
                "sales_commitments": [],
                "follow_up_task_events": [],
            },
        },
        source_event_key="collision",
    )
    activity_rows = [row for row in draft.evidence_refs if row.get("evidence_key") == "activity:1"]
    assert len(activity_rows) == 1
    row = activity_rows[0]
    snippet = row.get("snippet") or ""
    assert snippet
    assert "Hifox" in snippet
    assert "私有化部署" in snippet
    assert row["source_type"] == "customer_activity"
    assert row["title"] == "电话跟进"
    service.validate_draft(draft)
    item = draft.sections.current_situation["demand_background"]["items"][0]
    assert "Hifox" in item["statement"]
    assert_claims_grounded(
        draft.sections,
        evidence_refs=draft.evidence_refs,
        product_catalog_names=["Hifox", "Apifox"],
    )


_CATALOG = [
    {"public_id": "prd_hifox", "name": "Hifox", "is_active": True},
    {"public_id": "prd_apifox", "name": "Apifox", "is_active": True},
]


def _empty_strong_context(*, account_name="测试客户", activities):
    return {
        "customer": {"account_name": account_name, "products": []},
        "customer_facts": [],
        "contacts": [],
        "opportunities": [],
        "contracts": [],
        "payment_plans": [],
        "payment_records": [],
        "recent_activities": activities,
        "deal_journeys": [],
        "deal_journey_events": [],
        "recorded_follow_ups": [],
        "sales_commitments": [],
        "follow_up_task_events": [],
    }


def test_summary_from_hifox_note_without_demand_topic_passes_validate():
    service = CustomerProfileProjectionService()
    text = "今天看到了 Hifox。"
    draft = service.draft_from_context(
        context={
            "product_catalog": _CATALOG,
            "strong_context": _empty_strong_context(activities=[{
                "id": 1,
                "content": text,
                "source_content": text,
                "occurred_at": "2026-09-16T10:00:00",
                "title": "电话跟进",
            }]),
        },
        source_event_key="hifox-no-demand",
    )
    demand_items = (draft.sections.current_situation.get("demand_background") or {}).get("items") or []
    assert demand_items == []
    summary = draft.sections.current_situation.get("summary") or ""
    assert "Hifox" in summary
    service.validate_draft(draft)


def test_summary_echoing_later_travel_note_passes_validate():
    service = CustomerProfileProjectionService()
    private_text = "今天看到了 Hifox，需要私有化部署。"
    later_text = "人员出差，项目暂缓。"
    draft = service.draft_from_context(
        context={
            "product_catalog": _CATALOG,
            "strong_context": _empty_strong_context(activities=[
                {
                    "id": 2,
                    "content": later_text,
                    "source_content": later_text,
                    "occurred_at": "2026-09-16T12:00:00",
                    "title": "电话跟进",
                },
                {
                    "id": 1,
                    "content": private_text,
                    "source_content": private_text,
                    "occurred_at": "2026-09-16T10:00:00",
                    "title": "电话跟进",
                },
            ]),
        },
        source_event_key="travel-after-private",
    )
    summary = draft.sections.current_situation.get("summary") or ""
    assert "人员出差" in summary
    items = (draft.sections.current_situation.get("demand_background") or {}).get("items") or []
    assert items
    assert items[0]["evidence_refs"] == ["activity:1"]
    service.validate_draft(draft)


def test_invented_apifox_summary_still_rejected_with_summary_refs():
    sections = CustomerProfileSections(
        current_situation={
            "summary": OLD,
            "evidence_refs": ["activity:1"],
            "demand_background": {"summary": "", "items": []},
        },
        current_journeys=[],
        important_changes=[],
        long_term_context={},
        follow_up_process=[],
        recorded_follow_ups=[],
    )
    with pytest.raises(CustomerProfileProjectionValidationError) as exc:
        assert_claims_grounded(
            sections,
            evidence_refs=[{"evidence_key": "activity:1", "snippet": QUOTE}],
            product_catalog_names=["Hifox", "Apifox"],
        )
    assert exc.value.code == PROFILE_CLAIM_UNGROUNDED


def test_validate_draft_skips_byte_identical_inherited_current_situation():
    service = CustomerProfileProjectionService()
    canned_situation = {
        "summary": OLD,
        "demand_background": {
            "summary": OLD,
            "items": [{"statement": OLD, "evidence_refs": ["activity:1"]}],
        },
    }
    inherited = {
        "current_situation": canned_situation,
        "follow_up_process": [{"business_change": OLD, "evidence_refs": ["activity:1"]}],
    }
    draft = CustomerProfileProjectionDraft(
        sections=CustomerProfileSections(
            current_situation=canned_situation,
            current_journeys=[],
            important_changes=[{"summary": "联系人已更新"}],
            long_term_context={"overview": "新的长期背景"},
            follow_up_process=inherited["follow_up_process"],
            recorded_follow_ups=[],
        ),
        evidence_refs=[{"evidence_key": "activity:1", "source_type": "customer_activity", "snippet": QUOTE}],
        source_watermark={"product_catalog_names": ["Hifox", "Apifox"]},
        target_sections=("long_term_context", "important_changes"),
    )
    service.validate_draft(draft, inherited_sections=inherited)
    assert draft.sections.current_situation["summary"] == OLD


def test_validate_draft_still_rejects_canned_sentence_without_inherited_payload():
    service = CustomerProfileProjectionService()
    draft = CustomerProfileProjectionDraft(
        sections=CustomerProfileSections(
            current_situation={
                "summary": OLD,
                "demand_background": {
                    "summary": OLD,
                    "items": [{"statement": OLD, "evidence_refs": ["activity:1"]}],
                },
            },
            current_journeys=[],
            important_changes=[],
            long_term_context={},
            follow_up_process=[],
            recorded_follow_ups=[],
        ),
        evidence_refs=[{"evidence_key": "activity:1", "source_type": "customer_activity", "snippet": QUOTE}],
        source_watermark={"product_catalog_names": ["Hifox", "Apifox"]},
        target_sections=("long_term_context", "important_changes"),
    )
    with pytest.raises(CustomerProfileProjectionError) as exc:
        service.validate_draft(draft)
    assert exc.value.code == PROFILE_CLAIM_UNGROUNDED


def test_validate_draft_does_not_skip_new_demand_claims_when_current_situation_changed():
    service = CustomerProfileProjectionService()
    inherited = {
        "current_situation": {"summary": "客户处于早期沟通阶段。"},
        "follow_up_process": [],
    }
    draft = CustomerProfileProjectionDraft(
        sections=CustomerProfileSections(
            current_situation={
                "summary": "客户处于早期沟通阶段。",
                "demand_background": {
                    "summary": OLD,
                    "items": [{"statement": OLD, "evidence_refs": ["activity:1"]}],
                },
            },
            current_journeys=[],
            important_changes=[],
            long_term_context={},
            follow_up_process=[],
            recorded_follow_ups=[],
        ),
        evidence_refs=[{"evidence_key": "activity:1", "source_type": "customer_activity", "snippet": QUOTE}],
        source_watermark={"product_catalog_names": ["Hifox", "Apifox"]},
        target_sections=("current_situation",),
    )
    with pytest.raises(CustomerProfileProjectionError) as exc:
        service.validate_draft(draft, inherited_sections=inherited)
    assert exc.value.code == PROFILE_CLAIM_UNGROUNDED


def test_partial_publish_keeps_legacy_canned_current_situation(profile_db):
    service = CustomerProfileProjectionService()
    first = CustomerProfileProjectionDraft(
        sections=CustomerProfileSections(
            current_situation={"summary": "早期沟通。"},
            current_journeys=[],
            important_changes=[],
            long_term_context={"overview": "旧长期背景"},
            follow_up_process=[],
            recorded_follow_ups=[],
        ),
        evidence_refs=[{"evidence_key": "activity:1", "source_type": "customer_activity", "snippet": QUOTE}],
        source_watermark={"activity_id": 1},
    )
    publication = service.publish(profile_db, team_id=1, customer_id=1, draft=first)
    profile_db.commit()
    publication.version.current_situation_json = {
        "summary": OLD,
        "demand_background": {
            "summary": OLD,
            "items": [{"statement": OLD, "evidence_refs": ["activity:1"]}],
        },
    }
    flag_modified(publication.version, "current_situation_json")
    profile_db.commit()

    partial = CustomerProfileProjectionDraft(
        sections=CustomerProfileSections(
            current_situation={"summary": "不应覆盖当前情况"},
            current_journeys=[],
            important_changes=[{"summary": "联系人已更新"}],
            long_term_context={"overview": "新的长期背景"},
            follow_up_process=[{"business_change": "不应覆盖"}],
            recorded_follow_ups=[],
        ),
        evidence_refs=[{"evidence_key": "activity:2", "source_type": "customer_activity", "snippet": "更新了联系人"}],
        source_watermark={"activity_id": 2, "product_catalog_names": ["Hifox", "Apifox"]},
        target_sections=("long_term_context", "important_changes"),
    )
    published = service.publish(profile_db, team_id=1, customer_id=1, draft=partial)
    profile_db.commit()
    assert published.version.current_situation_json["summary"] == OLD
    assert published.version.long_term_context_json == {"overview": "新的长期背景"}


def test_full_draft_that_writes_canned_apifox_still_fails():
    service = CustomerProfileProjectionService()
    draft = CustomerProfileProjectionDraft(
        sections=CustomerProfileSections(
            current_situation={
                "summary": OLD,
                "demand_background": {
                    "summary": OLD,
                    "items": [{"statement": OLD, "evidence_refs": ["activity:1"]}],
                },
            },
            current_journeys=[],
            important_changes=[],
            long_term_context={},
            follow_up_process=[],
            recorded_follow_ups=[],
        ),
        evidence_refs=[{"evidence_key": "activity:1", "source_type": "customer_activity", "snippet": QUOTE}],
        source_watermark={"product_catalog_names": ["Hifox", "Apifox"]},
        target_sections=(
            "current_situation",
            "current_journeys",
            "important_changes",
            "long_term_context",
            "follow_up_process",
            "recorded_follow_ups",
        ),
    )
    with pytest.raises(CustomerProfileProjectionError) as exc:
        service.validate_draft(draft, inherited_sections={
            "current_situation": {"summary": "早期沟通。"},
            "follow_up_process": [],
        })
    assert exc.value.code == PROFILE_CLAIM_UNGROUNDED
